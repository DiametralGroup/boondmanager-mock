"""The 22 collections: dialect, referential integrity, business coherence.

This is the suite that prepares the comparison with the real API: paths,
lowercase JSON:API `type`, full `meta` envelope, resolved `included`, `/{id}`
detail where the vendor has one — and NOWHERE else.
"""

from __future__ import annotations

import re

import pytest

from tests.conftest import JWT

# (path, JSON:API type, detail?, included?)
COLLECTIONS = [
    ("absences", "absence", False, False),
    ("actions", "action", True, True),
    ("agencies", "agency", True, False),
    ("banking-transactions", "bankingtransaction", True, True),
    ("business-units", "businessunit", True, True),
    ("candidates", "candidate", True, True),
    ("companies", "company", True, True),
    ("contacts", "contact", True, True),
    ("contracts", "contract", True, True),
    ("deliveries", "delivery", True, True),
    ("expenses", "expense", False, False),
    ("invoices", "invoice", True, True),
    ("opportunities", "opportunity", True, True),
    ("orders", "order", True, True),
    ("payments", "payment", True, True),
    ("poles", "pole", True, False),
    ("projects", "project", True, True),
    ("purchases", "purchase", True, True),
    ("resources", "resource", True, True),
    ("roles", "role", True, False),
    ("times", "time", False, True),
    ("times-reports", "timesreport", True, True),
]

OFFICIAL_ID = re.compile(r"^[1-9][0-9]*$")
#: /times ids are composite for real: `regular_1`, `exceptional_3`…
TIME_ID = re.compile(r"^(regular|exceptional)_[1-9][0-9]*$")
#: Searches absent for real (405) — the data goes through details.
NO_LIST = {"contracts", "deliveries"}
#: Mandatory parameters per collection (timesheet window).
REQUIRED_PARAMS = {"times-reports": {"startMonth": "2026-05", "endMonth": "2026-07"}}


def _dataset_key(path: str) -> str:
    return path.replace("-", "_")


def _list(client, path: str, **params):
    return client.get(
        f"/api/{path}",
        headers=JWT,
        params={**REQUIRED_PARAMS.get(path, {}), **params},
    )


@pytest.mark.parametrize(("path", "type_", "detail", "included"), COLLECTIONS)
def test_list_dialect(client, path, type_, detail, included):  # noqa: ARG001
    """200, official envelope, lowercase types, real-format ids."""
    if path in NO_LIST:
        pytest.skip("search absent for real (405) — covered by test_dialect")
    response = _list(client, path)
    assert response.status_code == 200
    body = response.json()

    meta = body["meta"]
    assert meta["totals"]["rows"] >= 1, f"/{path} is empty — the dataset must be complete"
    assert meta["isLogged"] is True
    assert meta["language"] == "fr"
    assert isinstance(meta["version"], str)

    pattern = TIME_ID if path == "times" else OFFICIAL_ID
    assert body["data"], f"/{path} returns no data"
    for item in body["data"]:
        assert item["type"] == type_
        assert pattern.match(item["id"]), f"non-conforming id: {item['id']!r}"
        assert isinstance(item["attributes"], dict)

    if included:
        assert body.get("included"), f"/{path} should carry an included array"
    else:
        assert "included" not in body, f"/{path} must not carry included (official schema)"


@pytest.mark.parametrize(("path", "type_"), [(c, t) for c, t, detail, _ in COLLECTIONS if detail])
def test_detail_and_404(client, boond_state, path, type_):
    first = boond_state.dataset[_dataset_key(path)][0]
    response = client.get(f"/api/{path}/{first['id']}", headers=JWT)
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == first["id"]
    assert body["data"]["type"] == type_
    # The detail carries meta WITHOUT totals — the real profile shape.
    assert "totals" not in body["meta"]
    assert body["meta"]["isLogged"] is True

    absent = client.get(f"/api/{path}/999999", headers=JWT)
    assert absent.status_code == 404
    error = absent.json()["errors"][0]
    assert error["code"] == "404"
    assert error["detail"] == f"HTTP 404 (GET /api/{path}/999999)"


@pytest.mark.parametrize("path", [c for c, _, detail, _ in COLLECTIONS if not detail])
def test_no_detail_on_search_only_collections(client, boond_state, path):
    """/absences, /expenses and /times have no /{id} at the vendor."""
    first = boond_state.dataset[_dataset_key(path)][0]
    response = client.get(f"/api/{path}/{first['id']}", headers=JWT)
    assert response.status_code == 404
    assert response.json()["errors"][0]["title"] == "404"  # the envelope, not FastAPI's 404


@pytest.mark.parametrize(
    "path", [c for c, _, _, included in COLLECTIONS if included and c not in NO_LIST]
)
def test_included_resolves_the_pages_relations(client, path):
    """Every relationship carried by the page has its entity in `included`.

    This is the property real clients rely on (displaying labels without an
    extra request) — a gap in `included` would go unnoticed until the
    consumer's first render.
    """
    body = _list(client, path, maxResults=100).json()
    included = {(e["type"], e["id"]) for e in body.get("included", [])}
    # schedule/batch: always null here; opportunityparsingjob: outside the
    # module's whitelist (like for real).
    IGNORED = {"schedule", "batch", "opportunityparsingjob"}
    for item in body["data"]:
        for name, relation in (item.get("relationships") or {}).items():
            data = relation.get("data")
            refs = data if isinstance(data, list) else ([data] if data else [])
            for ref in refs:
                if ref["type"] in IGNORED:
                    continue
                assert (ref["type"], ref["id"]) in included, (
                    f"/{path} item {item['id']}: relation {name} → "
                    f"{ref['type']}/{ref['id']} missing from included"
                )


def test_dataset_referential_integrity(boond_state):
    """Every {id, type} reference in the dataset resolves, with no exception."""
    dataset = boond_state.dataset
    collections = {k: v for k, v in dataset.items() if isinstance(v, list) and k != "remuneration"}
    index = {(item["type"], item["id"]) for items in collections.values() for item in items}
    for key, items in collections.items():
        for item in items:
            for name, relation in (item.get("relationships") or {}).items():
                data = relation.get("data")
                refs = data if isinstance(data, list) else ([data] if data else [])
                for ref in refs:
                    assert (ref["type"], ref["id"]) in index, (
                        f"{key}/{item['id']}: {name} → {ref['type']}/{ref['id']} broken"
                    )


def test_billing_coherence(boond_state):
    """Invoices ↔ orders ↔ projects: the cumulatives reconcile."""
    d = boond_state.dataset
    invoices_by_order: dict[str, float] = {}
    for f in d["invoices"]:
        if f["attributes"]["state"] > 0:
            cid = f["relationships"]["order"]["data"]["id"]
            invoices_by_order[cid] = round(
                invoices_by_order.get(cid, 0.0) + f["attributes"]["turnoverInvoicedExcludingTax"],
                2,
            )
    for order in d["orders"]:
        attrs = order["attributes"]
        assert attrs["turnoverInvoicedExcludingTax"] == invoices_by_order.get(order["id"], 0.0)
        assert attrs["deltaInvoicedExcludingTax"] == round(
            attrs["turnoverOrderedExcludingTax"] - attrs["turnoverInvoicedExcludingTax"], 2
        )
        # Including tax = excluding tax x 1.20 on every invoice.
    for f in d["invoices"]:
        attrs = f["attributes"]
        assert attrs["turnoverInvoicedIncludingTax"] == round(
            attrs["turnoverInvoicedExcludingTax"] * 1.20, 2
        )


def test_activity_coherence(boond_state):
    """Time ↔ timesheet ↔ deliveries: rows fall in the right month and timesheet."""
    d = boond_state.dataset
    timesreports = {t["id"]: t for t in d["times_reports"]}
    deliveries = {m["id"]: m for m in d["deliveries"]}
    for time_row in d["times"]:
        attrs = time_row["attributes"]
        timesreport = timesreports[time_row["relationships"]["timesReport"]["data"]["id"]]
        assert attrs["startDate"][:7] == timesreport["attributes"]["term"], (
            f"time row {time_row['id']} outside its timesheet's term"
        )
        delivery_ref = time_row["relationships"]["delivery"]["data"]
        if delivery_ref is not None:
            delivery = deliveries[delivery_ref["id"]]
            assert (
                delivery["relationships"]["dependsOn"]["data"]["id"]
                == (timesreport["relationships"]["resource"]["data"]["id"])
            ), f"time row {time_row['id']}: timesheet does not belong to the delivery's consultant"
        assert attrs["workUnitType"]["activityType"] in (
            "production",
            "internal",
            "exceptionalTime",
        )


def test_absences_and_expenses_coherence(boond_state):
    d = boond_state.dataset
    for absence in d["absences"]:
        attrs = absence["attributes"]
        assert attrs["workUnitType"]["activityType"] == "absence"
        assert attrs["startDate"] <= attrs["endDate"]
        assert attrs["absencesReport"]["resource"]["id"]
        assert attrs["duration"] >= 1
    for expense in d["expenses"]:
        attrs = expense["attributes"]
        assert attrs["expensesReport"]["term"] == attrs["startDate"][:7]
        if attrs["isKilometricExpense"]:
            rate = attrs["expensesReport"]["ratePerKilometerType"]["amount"]
            assert attrs["amountIncludingTax"] == round(attrs["numberOfKilometers"] * rate, 2)


def test_hr_coherence(boond_state):
    """Contracts ↔ resources: every employee has a contract, fixed-term chains linked."""
    d = boond_state.dataset
    resources = {r["id"]: r for r in d["resources"]}
    holders = set()
    for contract in d["contracts"]:
        ref = contract["relationships"]["dependsOn"]["data"]
        assert ref["type"] == "resource"
        holders.add(ref["id"])
        res = resources[ref["id"]]
        assert res["attributes"]["typeOf"] == 0, "a subcontractor has no employment contract"
        assert contract["attributes"]["monthlySalary"] > 1500
        parent = contract["relationships"]["parentContract"]
        if parent["data"] is not None:
            ids = {c["id"] for c in d["contracts"]}
            assert parent["data"]["id"] in ids
    employees = {r["id"] for r in d["resources"] if r["attributes"]["typeOf"] == 0}
    assert employees <= holders, "every employee must carry at least one contract"


def test_purchase_payments(boond_state):
    d = boond_state.dataset
    for purchase in d["purchases"]:
        engaged = round(
            sum(
                p["attributes"]["amountExcludingTax"]
                for p in d["payments"]
                if p["relationships"]["purchase"]["data"]["id"] == purchase["id"]
            ),
            2,
        )
        assert purchase["attributes"]["engagedPaymentsAmountExcludingTax"] == engaged
