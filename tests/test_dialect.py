"""The cross-cutting dialect: authentication, envelopes, pagination, filters.

These properties hold for EVERY collection — they are checked on one or two,
the route factory handles the rest.
"""

from __future__ import annotations

import base64

import boondmanager_mock as mock
from tests.conftest import JWT


def _basic(user: str, password: str) -> dict[str, str]:
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


# ── Authentication — the exact dialect ───────────────────────────────────────


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_no_credentials_401_with_errors_envelope(client):
    """Real shape: meta OUTSIDE A SESSION + status/code/detail/title entry."""
    response = client.get("/api/resources")
    assert response.status_code == 401
    body = response.json()
    error = body["errors"][0]
    assert error == {
        "status": "401",
        "code": "401",
        "detail": "HTTP 401 (GET /api/resources)",
        "title": "401",
    }
    assert body["meta"]["isLogged"] is False
    assert body["meta"]["language"] == "en"
    assert "login" not in body["meta"]


def test_invalid_jwt_422_like_the_real_api(client):
    """Real shape observed: prefixed detail and `source.parameter: xJwtClient`."""
    fake = mock.build_client_jwt("mock-user-token", "mock-client-token", "WRONG-KEY")
    response = client.get("/api/resources", headers={mock.JWT_HEADER_NAME: fake})
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["detail"] == "422 - Signature verification failed"
    assert error["source"] == {"parameter": "xJwtClient"}
    assert "title" not in error


def test_forged_tokens_rejected(client):
    forged = mock.build_client_jwt("other-user", "mock-client-token", "mock-client-key")
    assert client.get("/api/resources", headers={mock.JWT_HEADER_NAME: forged}).status_code == 422


def test_basic_auth_accepted_and_rejected(client):
    ok = client.get(
        "/api/companies", headers=_basic("demo@boreal-conseil.example", "mock-password")
    )
    assert ok.status_code == 200
    refused = client.get("/api/companies", headers=_basic("demo@boreal-conseil.example", "non"))
    assert refused.status_code == 401


def test_current_user(client):
    """Real type `currentuser` (observed), with the account's login."""
    body = client.get("/api/application/current-user", headers=JWT).json()
    assert body["data"]["type"] == "currentuser"
    assert body["data"]["attributes"]["login"] == "demo@boreal-conseil.example"


# ── Envelopes ─────────────────────────────────────────────────────────────────


def test_full_list_envelope(client):
    """The full meta observed for real: totals + version + session + tenant."""
    body = client.get("/api/resources", headers=JWT).json()
    assert set(body) == {"data", "included", "meta"}
    meta = body["meta"]
    assert meta["totals"]["rows"] == 34
    assert meta["isLogged"] is True
    assert meta["language"] == "fr"
    assert meta["customer"] == "boreal-conseil"
    assert meta["login"] == "demo@boreal-conseil.example"
    assert isinstance(meta["timestamp"], int)
    assert meta["version"] == "9.1.78.1"


def test_detail_envelope_without_totals(client):
    body = client.get("/api/resources/7", headers=JWT).json()
    assert body["data"]["id"] == "7"
    assert "totals" not in body["meta"]
    # The real profile only includes the agency and the contracts (observed whitelist).
    included_types = {e["type"] for e in body["included"]}
    assert included_types == {"agency", "contract"}


def test_included_reduced_shape(client):
    """An included agency only carries `name` — the official schema's shape."""
    body = client.get("/api/resources", headers=JWT).json()
    agencies = [e for e in body["included"] if e["type"] == "agency"]
    assert agencies
    assert set(agencies[0]["attributes"]) == {"name"}
    resources = [e for e in body["included"] if e["type"] == "resource"]
    assert set(resources[0]["attributes"]) == {"firstName", "lastName"}


# ── Pagination ────────────────────────────────────────────────────────────────


def test_pagination_slices_and_totals(client):
    page1 = client.get("/api/times?page=1&maxResults=30", headers=JWT).json()
    page3 = client.get("/api/times?page=3&maxResults=30", headers=JWT).json()
    total = page1["meta"]["totals"]["rows"]
    assert total > 60, "more than two pages are needed to test pagination"
    assert len(page1["data"]) == 30
    assert len(page3["data"]) == total - 60
    assert page1["meta"]["totals"]["rows"] == page3["meta"]["totals"]["rows"]


def test_times_reports_requires_its_window(client):
    """`startMonth`/`endMonth` mandatory — 422 business code 1017, one entry
    per missing parameter with `source.parameter` (real shape observed)."""
    response = client.get("/api/times-reports", headers=JWT)
    assert response.status_code == 422
    entries = response.json()["errors"]
    assert [e["code"] for e in entries] == ["1017", "1017"]
    assert [e["source"]["parameter"] for e in entries] == ["endMonth", "startMonth"]

    window = client.get(
        "/api/times-reports?startMonth=2026-06&endMonth=2026-06&maxResults=500", headers=JWT
    ).json()
    assert window["meta"]["totals"]["rows"] > 0
    assert all(t["attributes"]["term"] == "2026-06" for t in window["data"])


def test_contracts_and_deliveries_lists_are_405(client):
    """Search does not exist for real (observed: 405) — data goes through
    details and relationships."""
    for path in ("contracts", "deliveries"):
        response = client.get(f"/api/{path}", headers=JWT)
        assert response.status_code == 405
        error = response.json()["errors"][0]
        assert error["detail"] == f"HTTP 405 (GET /api/{path})"
        assert error["title"] == "405"


def test_pagination_defaults_and_cap_overflow(client):
    """Default 30, max 500 — and beyond, a FALLBACK to the default 30.

    Probed 2026-09-29: `/companies?maxResults=500` renders 500 rows,
    `maxResults=501` renders 30. The vendor does not cap, it silently falls
    back to the default size."""
    default = client.get("/api/invoices", headers=JWT).json()
    assert len(default["data"]) == 30  # default maxResults=30
    total = default["meta"]["totals"]["rows"]
    at_cap = client.get("/api/invoices?maxResults=500", headers=JWT).json()
    assert len(at_cap["data"]) == min(500, total)
    beyond = client.get("/api/invoices?maxResults=5000", headers=JWT).json()
    assert len(beyond["data"]) == min(30, total)
    assert beyond["meta"]["totals"]["rows"] == total, "the total, itself, does not move"


def test_modules_without_pagination_render_everything(client):
    """agencies, poles, business-units have no pagination in the contract: the
    vendor ignores `page` and `maxResults` (probed 2026-09-29)."""
    for path in ("agencies", "poles", "business-units"):
        everything = client.get(f"/api/{path}", headers=JWT).json()
        page2 = client.get(f"/api/{path}?page=2&maxResults=1", headers=JWT).json()
        assert len(everything["data"]) == everything["meta"]["totals"]["rows"] > 1
        assert [i["id"] for i in page2["data"]] == [i["id"] for i in everything["data"]]


def test_invalid_pagination_422(client):
    assert client.get("/api/resources?page=abc", headers=JWT).status_code == 422


# ── Filters ───────────────────────────────────────────────────────────────────


def test_keywords_filter(client):
    body = client.get("/api/companies?keywords=Lumina", headers=JWT).json()
    assert body["meta"]["totals"]["rows"] >= 1
    assert all("Lumina" in str(item) for item in body["data"])


def test_official_sort_on_updateDate(client):
    """`sort=updateDate` is an OFFICIAL sort key (resources, candidates,
    companies, contacts, opportunities) — the incremental diff's tool."""
    body = client.get(
        "/api/resources?sort=updateDate&order=desc&maxResults=500", headers=JWT
    ).json()
    dates = [item["attributes"]["updateDate"] for item in body["data"]]
    assert dates == sorted(dates, reverse=True)


def test_sort_dotted_path(client):
    body = client.get("/api/times?sort=workUnitType.reference&maxResults=500", headers=JWT).json()
    references = [t["attributes"]["workUnitType"]["reference"] for t in body["data"]]
    assert references == sorted(references)


def test_stable_order_by_default(client):
    """Observed for real: two identical calls render the same sequence."""
    a = client.get("/api/resources?maxResults=10", headers=JWT).json()["data"]
    b = client.get("/api/resources?maxResults=10", headers=JWT).json()["data"]
    assert [d["id"] for d in a] == [d["id"] for d in b]


def test_default_order_is_descending_date(client):
    """Without a sort, the vendor serves a DESCENDING date (probed 2026-09-29):
    `updateDate` on resources and companies, `startDate` on actions."""
    for path, field in (
        ("resources", "updateDate"),
        ("companies", "updateDate"),
        ("actions", "startDate"),
    ):
        body = client.get(f"/api/{path}?maxResults=500", headers=JWT).json()
        values = [i["attributes"].get(field) or "" for i in body["data"]]
        assert values == sorted(values, reverse=True), path


def test_key_outside_sortlist_ignored(client):
    """`sort=id` is in no official `sortList`: ignored without error, both asc
    and desc (probed 2026-09-29). A made-up key too."""
    default = client.get("/api/companies?maxResults=10", headers=JWT).json()["data"]
    for params in ("sort=id&order=asc", "sort=id&order=desc", "sort=unknownKey"):
        response = client.get(f"/api/companies?maxResults=10&{params}", headers=JWT)
        assert response.status_code == 200
        assert [i["id"] for i in response.json()["data"]] == [i["id"] for i in default], params


def test_official_key_honored_both_ways(client):
    """`sort=updateDate` on companies and `sort=startDate` on actions honor
    `order` (probed 2026-09-29)."""
    for path, field in (("companies", "updateDate"), ("actions", "startDate")):
        for direction in ("asc", "desc"):
            body = client.get(
                f"/api/{path}?sort={field}&order={direction}&maxResults=500", headers=JWT
            ).json()
            values = [i["attributes"].get(field) or "" for i in body["data"]]
            assert values == sorted(values, reverse=(direction == "desc")), (path, direction)


def test_resources_sort_like_the_real_api(client):
    """Two quirks measured 2026-09-29 on /resources: `creationDate` is in the
    `sortList` but ignored, and `updateDate&order=asc` renders descending
    order. `lastName`, on the other hand, honors both directions."""
    default = client.get("/api/resources?maxResults=500", headers=JWT).json()["data"]
    for direction in ("asc", "desc"):
        by_creation = client.get(
            f"/api/resources?sort=creationDate&order={direction}&maxResults=500", headers=JWT
        ).json()["data"]
        assert [i["id"] for i in by_creation] == [i["id"] for i in default]
    asc = client.get("/api/resources?sort=updateDate&order=asc&maxResults=500", headers=JWT).json()[
        "data"
    ]
    dates = [i["attributes"]["updateDate"] for i in asc]
    assert dates == sorted(dates, reverse=True)
    names = client.get(
        "/api/resources?sort=lastName&order=desc&maxResults=500", headers=JWT
    ).json()["data"]
    values = [i["attributes"].get("lastName") or "" for i in names]
    assert values == sorted(values, reverse=True)


def test_period_updated_official(client):
    """`period=updated&startDate&endDate` — the OFFICIAL incremental filter."""
    everything = client.get("/api/companies?maxResults=500", headers=JWT).json()
    window = client.get(
        "/api/companies?period=updated&startDate=2026-01-01&endDate=2026-12-31&maxResults=500",
        headers=JWT,
    ).json()
    nothing = client.get(
        "/api/companies?period=updated&startDate=2099-01-01&endDate=2099-12-31&maxResults=500",
        headers=JWT,
    ).json()
    assert window["meta"]["totals"]["rows"] == everything["meta"]["totals"]["rows"]
    assert nothing["meta"]["totals"]["rows"] == 0


def test_period_created_official(client):
    recent = client.get(
        "/api/candidates?period=created&startDate=2026-01-01&endDate=2026-12-31&maxResults=500",
        headers=JWT,
    ).json()
    assert recent["meta"]["totals"]["rows"] >= 1
    for item in recent["data"]:
        assert item["attributes"]["creationDate"][:4] == "2026"


def test_updated_since_ignored_by_default_like_the_real_api(client):
    """The vendor accepts `updatedSince` and IGNORES it (probed 2026-09-29, 11
    modules): by default, the mock does the same."""
    everything = client.get("/api/resources?maxResults=500", headers=JWT).json()
    for param in ("updatedSince", "filter[updateDate][gte]"):
        future = client.get(
            "/api/resources", headers=JWT, params={param: "2099-01-01T00:00:00Z", "maxResults": 500}
        ).json()
        assert future["meta"]["totals"]["rows"] == everything["meta"]["totals"]["rows"], param


def test_updated_since_affordance_on_demand(client, monkeypatch):
    """`BOOND_MOCK_UPDATED_SINCE=true` turns the affordance back on (see
    UNVERIFIED-FIELDS)."""
    monkeypatch.setattr(mock.settings, "updated_since_enabled", True)
    for param in ("updatedSince", "filter[updateDate][gte]"):
        future = client.get(
            "/api/resources", headers=JWT, params={param: "2099-01-01T00:00:00Z", "maxResults": 500}
        ).json()
        assert future["meta"]["totals"]["rows"] == 0


def test_unknown_business_filters_ignored(client):
    """`period=hired`, `flags`, `keywordsType`…: accepted, with no effect — a
    stub does not break a real client that sends its usual filters."""
    body = client.get(
        "/api/resources?period=hired&startDate=2020-01-01&endDate=2020-12-31&keywordsType=fullName",
        headers=JWT,
    ).json()
    assert body["meta"]["totals"]["rows"] == 34


# ── Fetching contracts — the official path ──────────────────────────────────


def test_the_resource_profile_exposes_its_contracts(client):
    """`GET /resources/{id}` carries the `contracts` relationship (official
    profile schema) — ABSENT from search. This is the list/detail divergence
    the real API has, and the documented starting point for fetching
    contracts.
    """
    list_body = client.get("/api/resources?maxResults=1", headers=JWT).json()
    assert "contracts" not in list_body["data"][0]["relationships"]

    detail = client.get("/api/resources/7", headers=JWT).json()
    refs = detail["data"]["relationships"]["contracts"]["data"]
    assert refs, "an employee carries at least one contract"
    included = {(e["type"], e["id"]) for e in detail["included"]}
    assert all(("contract", r["id"]) in included for r in refs)


def test_administrative_lists_contracts_and_contracts_id_details_them(client):
    """The full flow: administrative → contract refs → employee detail.

    `GET /resources/{id}/administrative` → `relationships.contracts` +
    `included`, then `GET /contracts/{id}` for the detail — the path an
    extractor will replay against the real API.

    ⚠️ `included` is NOT reduced, contrary to what this test asserted until
    2026-08-13. Probed in production: the contract's sixteen attributes are
    there, `monthlySalary` included and filled. The reduced shape was a mock
    invention, and it was costly: finding compensation nowhere, the consumer
    concluded no endpoint exposed it (SPEC-DEVIATIONS #5) and built a detour
    through a fixtures CSV.
    """
    adm = client.get("/api/resources/7/administrative", headers=JWT).json()
    body = adm["data"]
    assert body["type"] == "resource"
    assert body["attributes"]["reference"] == "BC-0007"
    assert body["attributes"]["seniorityDate"], "seniority comes from the first contract"

    refs = body["relationships"]["contracts"]["data"]
    assert refs
    included_contract = next(e for e in adm["included"] if e["type"] == "contract")
    # `included` carries the FULL shape — it is the only practicable path to
    # the salary, `GET /contracts` answering 405 at the vendor.
    assert {"typeOf", "startDate", "endDate", "monthlySalary", "activityRate"} <= set(
        included_contract["attributes"]
    )
    assert included_contract["attributes"]["monthlySalary"] > 1500
    assert included_contract["relationships"]["agency"]["data"]["type"] == "agency"

    for ref in refs:
        full = client.get(f"/api/contracts/{ref['id']}", headers=JWT).json()["data"]
        assert full["attributes"]["monthlySalary"] > 1500
        assert full["relationships"]["dependsOn"]["data"]["id"] == "7"

    assert client.get("/api/resources/999/administrative", headers=JWT).status_code == 404


def test_administrative_of_a_subcontractor(client):
    """No employment contract, but a supplying company."""
    adm = client.get("/api/resources/23/administrative", headers=JWT).json()
    assert adm["data"]["relationships"]["contracts"]["data"] == []
    supplier = adm["data"]["relationships"]["providerCompany"]["data"]
    assert supplier is not None and supplier["type"] == "company"


# ── The group linkage — a company's information tab ────────────────────────

#: Observed in production on 2026-09-13 (read-only probe, names only).
COMPANY_INFORMATION_RELATIONS = {
    "agency",
    "createdBy",
    "files",
    "influencers",
    "mainManager",
    "parentCompany",
    "pole",
    "subsidiaries",
}


def test_the_companies_list_does_not_carry_the_group(client):
    """Observed for real: search only serves `agency`, `mainManager`, `pole`.

    Adding `parentCompany` there would make a consumer green on a
    relationship the vendor's list does not serve — they would only discover
    in production that a per-profile call is needed.
    """
    items = client.get("/api/companies?maxResults=500", headers=JWT).json()
    for company in items["data"]:
        assert set(company["relationships"]) == {"agency", "mainManager", "pole"}


def test_information_a_subsidiary_points_to_its_parent(client):
    body = client.get("/api/companies/3/information", headers=JWT).json()
    assert body["data"]["type"] == "company"
    assert body["data"]["relationships"]["parentCompany"]["data"] == {
        "id": "9",
        "type": "company",
    }
    assert body["data"]["relationships"]["subsidiaries"]["data"] == []
    # The referenced parent is resolved in `included`.
    assert ("company", "9") in {(e["type"], e["id"]) for e in body["included"]}


def test_information_the_parent_lists_its_subsidiaries_and_both_directions_agree(client):
    """Measured for real: one group listed 16 subsidiaries, each pointing back to it."""
    parent = client.get("/api/companies/9/information", headers=JWT).json()["data"]
    assert parent["relationships"]["parentCompany"]["data"] is None
    subsidiaries = parent["relationships"]["subsidiaries"]["data"]
    assert {f["id"] for f in subsidiaries} == {"3", "5"}
    assert all(f["type"] == "company" for f in subsidiaries)

    for subsidiary in subsidiaries:
        profile = client.get(f"/api/companies/{subsidiary['id']}/information", headers=JWT).json()
        assert profile["data"]["relationships"]["parentCompany"]["data"]["id"] == "9"

    # Reverse direction, across ALL companies: every declared parent lists its child.
    ids = [s["id"] for s in client.get("/api/companies?maxResults=500", headers=JWT).json()["data"]]
    profiles = {
        i: client.get(f"/api/companies/{i}/information", headers=JWT).json()["data"] for i in ids
    }
    for i, profile in profiles.items():
        ref = profile["relationships"]["parentCompany"]["data"]
        if ref is not None:
            siblings = profiles[ref["id"]]["relationships"]["subsidiaries"]["data"]
            assert {"id": i, "type": "company"} in siblings
        for child in profile["relationships"]["subsidiaries"]["data"]:
            assert profiles[child["id"]]["relationships"]["parentCompany"]["data"]["id"] == i


def test_information_of_a_company_without_a_group(client):
    rels = client.get("/api/companies/1/information", headers=JWT).json()["data"]["relationships"]
    assert rels["parentCompany"] == {"data": None}
    assert rels["subsidiaries"] == {"data": []}


def test_information_observed_shape_and_404(client):
    """The eight relationships and twenty-seven attributes observed — no more, no less."""
    body = client.get("/api/companies/9/information", headers=JWT).json()
    assert set(body["data"]["relationships"]) == COMPANY_INFORMATION_RELATIONS
    assert len(body["data"]["attributes"]) == 27
    assert {e["type"] for e in body["included"]} <= {"agency", "company", "resource"}

    absent = client.get("/api/companies/999/information", headers=JWT)
    assert absent.status_code == 404
    assert absent.json()["errors"][0]["detail"] == "HTTP 404 (GET /api/companies/999/information)"


# ── Affordances kept ─────────────────────────────────────────────────────────


def test_technical_data(client):
    """Real shape observed: type `resource`, fifteen attributes, no included."""
    body = client.get("/api/resources/7/technical-data", headers=JWT).json()
    data = body["data"]
    assert data["type"] == "resource"
    attrs = data["attributes"]
    assert set(attrs) == {
        "activityAreas",
        "description",
        "diplomas",
        "experience",
        "expertiseAreas",
        "languages",
        "references",
        "resourceCanModifyTechnicalData",
        "skills",
        "summary",
        "tdId",
        "tdLink",
        "title",
        "tools",
        "training",
    }
    references = attrs["references"]
    assert references and {"title", "company", "startYear", "description", "skills"} <= set(
        references[0]
    )
    assert isinstance(references[0]["skills"], list)
    absent = client.get("/api/resources/999/technical-data", headers=JWT)
    assert absent.status_code == 404
    assert (
        absent.json()["errors"][0]["detail"] == "HTTP 404 (GET /api/resources/999/technical-data)"
    )


def test_remuneration_csv_derived_from_contracts(client, boond_state):
    response = client.get("/__fixtures/remuneration.csv", headers=JWT)
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0] == "collaborateur_id,upn,entite,periode,montant_brut_annuel"
    permanent = [c for c in boond_state.dataset["contracts"] if c["attributes"]["typeOf"] == 0]
    assert len(lines) - 1 == len(permanent)


def test_unknown_route_enveloped(client):
    """The real API also envelopes its routing 404s (meta outside a session)."""
    response = client.get("/api/times/regular_1", headers=JWT)
    assert response.status_code == 404
    body = response.json()
    assert body["errors"][0]["detail"] == "HTTP 404 (GET /api/times/regular_1)"
    assert body["meta"]["isLogged"] is False


def test_in_process_historical_outage(client, boond_state):
    boond_state.fail_collections.add("projects")
    assert client.get("/api/projects", headers=JWT).status_code == 500
    assert client.get("/api/companies", headers=JWT).status_code == 200
