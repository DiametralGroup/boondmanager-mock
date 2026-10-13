"""Where the mock used to tell a different story than the vendor.

┌─ WHAT THESE TESTS DEFEND ──────────────────────────────────────────────────┐
│ This repository exists so a consumer can develop without touching the      │
│ real API. That promise only holds if what it emits is what the vendor      │
│ emits — a mock more generous than the real API does no favor: it moves     │
│ the discovery of the defect into production, where it costs the most.      │
│                                                                             │
│ Two probes, both READ-ONLY against a production tenant:                    │
│                                                                             │
│   2026-08-12 — the eighteen collections, one page each. Four gaps.          │
│                Each had already broken the insights360 chain in            │
│                production while CI stayed green — at the worst time, and    │
│                for the worst reason: because the mock was trusted.          │
│                                                                             │
│   2026-09-10 — the SALARY PACKAGE: contract profiles and benefits. Three    │
│                fields the mock filled and the vendor leaves empty, a shape  │
│                never observed (`advantageTypes`), and a whole route that    │
│                was missing (`/resources/{id}/advantages`, where variable    │
│                pay lives).                                                 │
│                                                                             │
│ These tests therefore do not check a design choice, but a MEASUREMENT.     │
│ They must only move if a new probe shows something else.                   │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from tests.conftest import ADMIN, JWT

# The eighteen collections probed, by their API path.
COLLECTIONS = [
    "resources",
    "agencies",
    "companies",
    "contacts",
    "projects",
    "times",
    "actions",
    "opportunities",
    "poles",
    "candidates",
    "orders",
    "purchases",
    "business-units",
    "absences",
    "invoices",
    "expenses",
    "payments",
]


def _first(client, collection: str, **params) -> list[dict]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/{collection}" + (f"?{query}" if query else "")
    response = client.get(url, headers=JWT)
    assert response.status_code == 200, f"{collection}: {response.status_code}"
    return response.json()["data"]


# ── 1. `isDeleted` is not a vendor field ──────────────────────────────────────


def test_no_collection_serves_isdeleted_by_default(client):
    """Absent from all EIGHTEEN real collections — it must be here too.

    This is the gap that cost the most: seventeen staging models built on
    `where not is_deleted`, all green against this mock, all broken on the
    first production run.
    """
    offenders = []
    for collection in COLLECTIONS:
        rows = _first(client, collection, maxResults=5)
        if any("isDeleted" in (row.get("attributes") or {}) for row in rows):
            offenders.append(collection)

    assert not offenders, (
        "isDeleted served by default on: "
        + ", ".join(offenders)
        + " — the vendor exposes it on NO collection."
    )


def test_the_flag_stays_available_after_an_explicit_deletion(client):
    """The affordance is not removed: it stops being a DEFAULT.

    `/__admin/delete` must keep setting the flag, otherwise the only way to
    exercise deletion handling at the consumer is lost. What changes is that
    it must be REQUESTED — and a default payload then resembles the vendor's.
    """
    client.post("/__admin/delete", headers=ADMIN, json={"collection": "resources", "id": "8"})
    rows = _first(client, "resources", maxResults=500)
    marked = next(row for row in rows if row["id"] == "8")
    assert marked["attributes"]["isDeleted"] is True

    others = [row for row in rows if row["id"] != "8"]
    assert all("isDeleted" not in row["attributes"] for row in others), (
        "only the explicitly deleted record carries the flag"
    )


# ── 2. `/orders` carries no update timestamp ─────────────────────────────────


def test_orders_have_neither_updatedate_nor_creationdate(client):
    """`/orders` carries NEITHER of the two timestamps.

    `updateDate` first: it drives extraction strategy, and serving it makes
    the collection get declared incremental — the cursor then breaks for
    real.

    `creationDate` next, and it is a mistake worth keeping under test: 0.6.0
    had kept it on the grounds that "it drives no strategy, so serving it
    costs nothing". That was false: a model that READS a column needs it to
    EXIST, and `stg_commande` hit "column o.creation_date does not exist" on
    the next run.

    Hence this test's shape: the rule admits no "harmless" exception.
    """
    for row in _first(client, "orders", maxResults=10):
        attributes = row["attributes"]
        for field in ("updateDate", "creationDate"):
            assert field not in attributes, f"the vendor does not render `{field}` on orders"
        assert "date" in attributes, (
            "`date` (the order date) is indeed rendered for real — do not remove it"
        )


def test_other_collections_keep_their_updatedate(client):
    """The inverse guard: do not "fix" beyond what has been measured."""
    for collection in ("resources", "companies", "projects", "invoices"):
        rows = _first(client, collection, maxResults=5)
        assert all("updateDate" in row["attributes"] for row in rows), (
            f"{collection} must keep its updateDate — it is indeed rendered for real"
        )


# ── 3. `/actions` caps `maxResults` at 100 ───────────────────────────────────


def test_actions_cap_maxresults_at_100(client):
    """`/actions` honors `maxResults` up to 100, and falls back to 30 beyond it.

    2026-08-12 survey: `maxResults=500` renders 30 rows, then read as "the
    parameter is ignored". 2026-09-29 probe: 2 → 2, 30 → 30, 100 → 100,
    101 → 30, 500 → 30. This is not a refusal but a cap of 100, beyond which
    the vendor falls back to its default size.
    """
    total = client.get("/api/actions", headers=JWT).json()["meta"]["totals"]["rows"]
    assert total > 30, "the dataset must exceed one default page to exercise the cap"
    for requested, expected in ((2, 2), (100, min(100, total)), (101, 30), (500, 30)):
        response = client.get(f"/api/actions?maxResults={requested}", headers=JWT)
        assert response.status_code == 200, "the parameter is accepted, never rejected"
        assert len(response.json()["data"]) == expected, f"maxResults={requested}"


def test_other_collections_honor_maxresults(client):
    """Without this guard, everyone would have been "fixed" instead of just
    /actions: elsewhere, the cap is 500."""
    for collection in ("contacts", "candidates", "times"):
        rows = _first(client, collection, maxResults=100)
        total = client.get(f"/api/{collection}", headers=JWT).json()["meta"]["totals"]["rows"]
        expected = min(100, total)
        assert len(rows) == expected, (
            f"{collection} must honor maxResults ({len(rows)} instead of {expected})"
        )


# ── 4. A NEED's `startDate` can be "immediate" ───────────────────────────────


def test_a_needs_start_can_be_the_literal_immediate(client):
    """1,523 of the 1,850 production needs carry "immediate", i.e. 82%.

    So this is not an edge case but the DOMINANT case. The mock only ever
    served dates, so `stg_opportunite` cast with no safety net and hit
    "invalid input syntax for type date: \"immediate\"".

    Proportion matters as much as presence: a dataset where the majority case
    is a minority lets models that do not handle it pass.
    """
    rows = _first(client, "opportunities", maxResults=500)
    starts = [row["attributes"].get("startDate") for row in rows]
    filled = [d for d in starts if d]

    assert "immediate" in filled, "the literal must be present"
    immediate_count = sum(1 for d in filled if d == "immediate")
    assert immediate_count > len(filled) / 2, (
        f'"immediate" must be the MAJORITY ({immediate_count}/{len(filled)}) — '
        "that is what production renders"
    )
    assert any(d != "immediate" for d in filled), "real dates must remain: both shapes coexist"


# ── 5. A CANDIDATE's `availability` is a code, not a date ────────────────────


def test_a_candidates_availability_is_an_integer_code(client):
    """Observed on 26,814 real candidates: integers, `-1` on 24,289.

    The mock used to serve an ISO date, and the consumer cast it to a date.
    """
    for row in _first(client, "candidates", maxResults=20):
        value = row["attributes"]["availability"]
        assert isinstance(value, int), (
            f"availability = {value!r} ({type(value).__name__}) — expected an integer code"
        )


def test_a_resources_availability_stays_a_date(client):
    """Same name, different entity, different type — and the vendor is the
    one saying so.

    On a RESOURCE, `availability` is indeed a date (or "immediate"). Aligning
    both would smooth over a gap the mock must precisely carry.
    """
    for row in _first(client, "resources", maxResults=20):
        value = row["attributes"]["availability"]
        assert isinstance(value, str), (
            f'availability = {value!r} — on a resource, it is a date or "immediate"'
        )


# ── 6. The contract in `included` carries the salary ─────────────────────────


def test_the_included_contract_carries_the_salary(client):
    """`GET /contracts` answers 405: `included` is the ONLY path to the salary.

    The mock used to serve only three attributes there, on the idea of a
    "reduced shape". Probed in production on 2026-08-13: the sixteen
    attributes are there, including `monthlySalary`, filled.

    What the reduced shape cost: finding compensation nowhere, the consumer
    concluded — and wrote in SPEC-DEVIATIONS #5 — that no compensation
    endpoint was attested at BoondManager, then built a whole detour through
    a fixtures CSV. The vendor had been serving it all along.
    """
    resources = _first(client, "resources", maxResults=20)
    contracts = []
    for resource in resources:
        response = client.get(f"/api/resources/{resource['id']}/administrative", headers=JWT)
        assert response.status_code == 200
        contracts += [
            included
            for included in (response.json().get("included") or [])
            if included.get("type") == "contract"
        ]

    assert contracts, "no contract in `included` — the path to the salary is cut"
    for contract in contracts:
        attributes = contract["attributes"]
        assert "monthlySalary" in attributes, (
            "`monthlySalary` missing from `included`: the consumer canNOT reach "
            "it any other way, `GET /contracts` answering 405."
        )
        assert isinstance(attributes["monthlySalary"], (int, float))
        # The activity rate changes how the amount should be read: an 80%
        # rate at the same contractual salary does not weigh the same on
        # payroll.
        assert "activityRate" in attributes


def test_the_contracts_list_stays_a_405(client):
    """The inverse guard: it is the 405 that makes `included` indispensable.

    If the list became accessible, the detour through the resource profile —
    364 calls in production — would no longer be needed. This test says that
    is not the case, and it will say so the day it changes.
    """
    assert client.get("/api/contracts", headers=JWT).status_code == 405


# ═════════════════════════════════════════════════════════════════════════════
#  2026-09-10 probe — the salary package
# ═════════════════════════════════════════════════════════════════════════════
#
# Four gaps measured against a production tenant that day. Three concern
# fields the mock FILLED while the vendor does not feed them — the credible
# fiction, the one that makes a consumer green in CI and wrong in production.
# The fourth is a whole route that was missing.


def test_expenses_details_is_served_but_always_empty(client):
    """0 of 18 contracts in production. The mock used to fill 38 of 38.

    This is the exact family of `isDeleted`: the key exists, the array is
    empty, and a consumer building a model on it only notices in production.
    The key stays EMITTED — the vendor emits it — with the value it gives it.
    """
    for cid in ("1", "7", "12"):
        attrs = client.get(f"/api/contracts/{cid}", headers=JWT).json()["data"]["attributes"]
        assert "expensesDetails" in attrs, "the key must be emitted"
        assert attrs["expensesDetails"] == []
        assert attrs["dailyExpenses"] == 0
        assert attrs["monthlyExpenses"] == 0
        assert attrs["calendar"] == ""


def test_activity_rate_is_zero_everywhere(client):
    """0 of 18 contracts in production, and of the 800 on the consumer's tenant.

    The mock served 100. A consumer weighted an annual gross by this rate and
    shipped 800 zeroed compensation rows — with no error, because a zero
    salary reads as "this person earns nothing".
    """
    attrs = client.get("/api/contracts/1", headers=JWT).json()["data"]["attributes"]
    assert attrs["activityRate"] == 0


def test_advantage_types_carry_the_observed_shape(client):
    """`advantageTypes` used to be served EMPTY: its shape had never been observed.

    Observed 2026-09-10 — 16 of 18 contracts, 55 rows. It has nothing to do
    with `ContractExpenseDetail`, contrary to what one might have assumed.
    """
    seen = []
    for cid in [str(i) for i in range(1, 39)]:
        response = client.get(f"/api/contracts/{cid}", headers=JWT)
        if response.status_code == 200:
            seen += response.json()["data"]["attributes"]["advantageTypes"]
    assert seen, "the array must no longer be empty everywhere"
    for row in seen:
        assert set(row) == {
            "reference",
            "name",
            "frequency",
            "category",
            "participationQuota",
            "employeeQuota",
            "agencyQuota",
        }
        assert row["frequency"] in {"daily", "monthly", "semiAnnual", "annual"}
        assert row["category"] in {"variableSalaryBasis", "package", "fixedAmount"}


def test_category_does_not_say_what_is_vested(client):
    """The trap the dataset MUST carry, because the real API carries it.

    In production, the row named "Variable" is `fixedAmount` while "Prime de
    vacances" is `variableSalaryBasis`. `category` describes how the amount
    is expressed, not whether it is owed. A consumer who wires an
    "vested/conditional" flag onto this column must fall HERE.
    """
    by_name = {}
    for cid in [str(i) for i in range(1, 39)]:
        response = client.get(f"/api/contracts/{cid}", headers=JWT)
        if response.status_code == 200:
            for row in response.json()["data"]["attributes"]["advantageTypes"]:
                by_name[row["name"]] = row["category"]
    assert by_name.get("Variable") == "fixedAmount"
    assert by_name.get("Prime de vacances") == "variableSalaryBasis"


def test_the_reference_is_not_a_global_code(client):
    """In production, the same 21 designates both "Health Insurance" and "Variable".

    It is an agency-level CONFIGURATION key. A reference table joined on it
    would merge unrelated rows — the dataset reproduces the collision so it
    becomes visible.
    """
    names_by_reference: dict[int, set[str]] = {}
    for cid in [str(i) for i in range(1, 39)]:
        response = client.get(f"/api/contracts/{cid}", headers=JWT)
        if response.status_code == 200:
            for row in response.json()["data"]["attributes"]["advantageTypes"]:
                names_by_reference.setdefault(row["reference"], set()).add(row["name"])
    assert any(len(names) > 1 for names in names_by_reference.values()), (
        "no `reference` collision: the real trap is not reproduced"
    )


def test_paid_advantages_are_served_and_sparse(client):
    """The route that was missing — and that is where variable pay lives.

    `GET /resources/{id}/advantages`, observed 2026-09-10: 200 OK,
    `meta.totals.rows` = 54 on one resource, 2020 → 2026 history. SPARSE: six
    of eight resources have none.
    """
    totals = {}
    for rid in [str(i) for i in range(1, 35)]:
        body = client.get(f"/api/resources/{rid}/advantages", headers=JWT).json()
        totals[rid] = body["meta"]["totals"]["rows"]
    assert any(n == 0 for n in totals.values()), "sparseness is not reproduced"
    assert max(totals.values()) > 20, "no long history: pagination is not exercised"

    richest = max(totals, key=lambda r: totals[r])
    body = client.get(f"/api/resources/{richest}/advantages", headers=JWT).json()
    row = body["data"][0]
    assert row["type"] == "advantage"
    assert set(row["attributes"]) == {
        "date",
        "quantity",
        "costPaid",
        "returnDate",
        "currency",
        "currencyAgency",
        "exchangeRate",
        "exchangeRateAgency",
        "canReadAdvantage",
        "canWriteAdvantage",
        "advantageType",
    }
    assert set(row["attributes"]["advantageType"]) == {"reference", "name"}
    # Attached to the CONTRACT, not the resource: a person can have had eight
    # successive ones, and a 2020 payment does not belong to the 2026 one.
    assert row["relationships"]["contract"]["data"]["type"] == "contract"


def test_paid_advantages_have_no_cursor(client):
    """No `updateDate`: no incremental extraction is possible.

    Serving one would invite a consumer to set a cursor that would fetch
    nothing in production — the silent and costly failure.
    """
    for rid in [str(i) for i in range(1, 35)]:
        for row in client.get(f"/api/resources/{rid}/advantages", headers=JWT).json()["data"]:
            assert "updateDate" not in row["attributes"]


def test_no_bulk_advantages_collection(client):
    """`/advantages` does not exist — the cost of one call per resource is structural.

    Measured: 403 (WAF) on `/advantages`, 404 on `/resources-advantages` and
    `/contracts-advantages`. A consumer hoping for a bulk search must hit the
    same wall here as in production.
    """
    for path in ("/api/advantages", "/api/resources-advantages", "/api/contracts-advantages"):
        assert client.get(path, headers=JWT).status_code in (403, 404)


def test_the_daily_cost_does_not_derive_from_the_gross(client):
    """The plausible formula that production disproves.

    The dataset used to serve `contractAverageDailyCost = monthlySalary * 12 *
    chargeFactor / numberOfWorkingDays`. Tested 2026-09-10 against 25 real
    contracts: ONLY ONE checks out within 1%, the other 24 do not — median
    relative gap 11.7%, maximum 44.2%.

    A mock where the relationship holds exactly invites the consumer to
    recompute the cost instead of reading the field, and their figure is then
    off by 12% in production with no test turning red.
    """
    exact = testable = 0
    for cid in [str(i) for i in range(1, 39)]:
        response = client.get(f"/api/contracts/{cid}", headers=JWT)
        if response.status_code != 200:
            continue
        a = response.json()["data"]["attributes"]
        m, f, j, d = (
            a["monthlySalary"],
            a["chargeFactor"],
            a["numberOfWorkingDays"],
            a["contractAverageDailyCost"],
        )
        if not (m and f and j and d):
            continue
        testable += 1
        if abs(m * 12 * f / j - d) / d < 0.01:
            exact += 1

    assert testable > 10, "not enough contracts to conclude"
    # In production: 1 of 25. We simply require that the relationship not be
    # the rule — a mock that respected it everywhere would be the original trap.
    assert exact / testable < 0.2, (
        f"{exact}/{testable} contracts satisfy the formula: the dataset "
        "suggests a relationship the vendor does not honor"
    )


def test_every_agency_carries_a_package(client):
    """An empty business axis makes the consumer's test GREEN BY VACUITY.

    The advantages draw used to be done by modulo on the identifier — `% 7`
    for entitlements, `% 3` for payments. Both excluded exactly the same
    cohort, 7 · 14 · 28, i.e. the whole Nantes agency. That is the only
    entity distinguishing two BI roles at insights360: its perimeter-isolation
    gate saw both roles count the same number of rows, and could prove
    nothing.

    An identifier is not a random variable: here it is assigned per agency,
    so ANY modulo correlates with the agency. This test guarantees coverage
    instead of hoping for it.
    """
    by_agency: dict[str, dict[str, int]] = {}
    for rid in [str(i) for i in range(1, 35)]:
        adm = client.get(f"/api/resources/{rid}/administrative", headers=JWT)
        if adm.status_code != 200:
            continue
        body = adm.json()["data"]
        agency = ((body["relationships"].get("agency") or {}).get("data") or {}).get("id")
        refs = body["relationships"]["contracts"]["data"]
        if agency is None or not refs:
            continue
        count = by_agency.setdefault(agency, {"contracts": 0, "entitlements": 0, "payments": 0})
        count["contracts"] += len(refs)
        for ref in refs:
            attrs = client.get(f"/api/contracts/{ref['id']}", headers=JWT).json()["data"][
                "attributes"
            ]
            count["entitlements"] += len(attrs["advantageTypes"])
        count["payments"] += client.get(f"/api/resources/{rid}/advantages", headers=JWT).json()[
            "meta"
        ]["totals"]["rows"]

    assert len(by_agency) >= 3, f"too few agencies to conclude: {sorted(by_agency)}"
    empty = {a: c for a, c in by_agency.items() if not c["entitlements"] or not c["payments"]}
    assert not empty, (
        f"agencies without a salary package: {empty}. "
        "An empty business axis makes the consumer's perimeter-isolation gate green by vacuity."
    )


def test_the_contracts_agency_sometimes_diverges_from_the_profiles(client):
    """THE case the dataset did not carry, and which cost a wrong RLS perimeter.

    BoondManager expresses multi-affiliation through the CONTRACT's agency: a
    person can have several, in several agencies, with different roles. The
    profile only carries the primary affiliation agency.

    Measured 2026-09-11 on a production tenant, 70 multi-contract profiles
    and 388 contracts: 18 (4.6%) carry an agency different from their
    profile's, and 3 people have contracts across several agencies —
    including the CEO, spread across three entities.

    The dataset used to give every contract its resource's agency. A
    consumer taking the entity from the profile was therefore GREEN here and
    attached 4.6% of contracts to the wrong perimeter in production —
    readable by some, invisible to others. This is not a hypothesis: it
    happened.
    """
    divergent = 0
    total = 0
    by_person: dict[str, set[str]] = {}

    for rid in [str(i) for i in range(1, 35)]:
        adm = client.get(f"/api/resources/{rid}/administrative", headers=JWT)
        if adm.status_code != 200:
            continue
        body = adm.json()["data"]
        profile_agency = ((body["relationships"].get("agency") or {}).get("data") or {}).get("id")
        for ref in body["relationships"]["contracts"]["data"]:
            profile = client.get(f"/api/contracts/{ref['id']}", headers=JWT)
            if profile.status_code != 200:
                continue
            rels = profile.json()["data"].get("relationships") or {}
            agency = ((rels.get("agency") or {}).get("data") or {}).get("id")
            assert agency is not None, "the contract's agency is served on 388/388 in production"
            total += 1
            by_person.setdefault(rid, set()).add(agency)
            if agency != profile_agency:
                divergent += 1

    assert total > 20, "not enough contracts to conclude"
    assert divergent > 0, (
        "no contract diverges from its profile: multi-affiliation is not "
        "reproduced, and a consumer taking the entity from the profile passes "
        "green by vacuity"
    )
    assert any(len(v) > 1 for v in by_person.values()), (
        "no person has contracts across several agencies — yet that is "
        "precisely the shape of multi-affiliation"
    )
    # The frequency is denser than reality (≈16% versus 4.6%) but stays a
    # minority: a dataset where the majority diverges would be a different fiction.
    assert divergent < total / 2, "divergence must stay a minority, like reality"
