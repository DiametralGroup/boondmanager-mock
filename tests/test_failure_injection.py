"""Failure modes — controlled over HTTP, hence usable from a container.

"The point of the mock is to reproduce failure modes, not just happy paths."
One test per listed mode, plus the two properties that make these modes
useful: a transient failure exhausts itself, a persistent one does not.
"""

from __future__ import annotations

import boondmanager_mock as mock
from tests.conftest import ADMIN, JWT

TOTAL_RESOURCES = 34


# ── The control plane itself ─────────────────────────────────────────────────


def test_admin_requires_a_token(client) -> None:
    """Without a token, /__admin is closed — even when mounted."""
    assert client.get("/__admin/state").status_code == 401
    assert client.post("/__admin/inject", json={"kind": "status"}).status_code == 401


def test_admin_mounts_conditionally(client) -> None:
    """The admin router is not "mounted then forbidden": it is absent.

    The condition is checked at the source rather than re-importing the
    package in another state, which would pollute the session. The proof
    mounting happened is behavioral: the endpoint responds.
    """
    import inspect
    import sys

    app_module = sys.modules["boondmanager_mock.app"]
    source = inspect.getsource(app_module)
    assert "if settings.admin_enabled:" in source, (
        "mounting the admin router is no longer conditional"
    )
    assert client.get("/__admin/state", headers=ADMIN).status_code == 200


# ── 429 + Retry-After ─────────────────────────────────────────────────────────


def test_rate_limit_with_retry_after(client) -> None:
    """After N requests: 429 with a usable Retry-After header."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={
            "kind": "rate_limit",
            "scope": "/api/resources",
            "after_requests": 2,
            "retry_after_seconds": 3,
        },
    )
    assert client.get("/api/resources", headers=JWT).status_code == 200
    assert client.get("/api/resources", headers=JWT).status_code == 200
    too_many = client.get("/api/resources", headers=JWT)
    assert too_many.status_code == 429
    assert too_many.headers["Retry-After"] == "3"


def test_rate_limit_does_not_affect_other_collections(client) -> None:
    """`scope` is honored: another collection is still served."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={"kind": "rate_limit", "scope": "/api/resources", "after_requests": 0},
    )
    assert client.get("/api/resources", headers=JWT).status_code == 429
    assert client.get("/api/companies", headers=JWT).status_code == 200


# ── 500 / 503 transient ───────────────────────────────────────────────────────


def test_transient_status_exhausts_itself(client) -> None:
    """`times: 2` → two failures, then it recovers.

    This is what lets a RETRY be tested. Without a counter, only a failure
    would be tested — and "the run completes despite a 503" would be
    impossible to write.
    """
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={"kind": "status", "scope": "/api/projects", "status": 503, "times": 2},
    )
    assert client.get("/api/projects", headers=JWT).status_code == 503
    assert client.get("/api/projects", headers=JWT).status_code == 503
    assert client.get("/api/projects", headers=JWT).status_code == 200


def test_persistent_status_never_exhausts(client) -> None:
    """Without `times`, the failure lasts — the run MUST fail, not half-complete."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={"kind": "status", "scope": "/api/projects", "status": 500},
    )
    for _ in range(5):
        assert client.get("/api/projects", headers=JWT).status_code == 500


# ── Unstable order ────────────────────────────────────────────────────────────


def test_unstable_order_by_injection(client) -> None:
    """Order instability is an opt-in CHAOS mode — the default is stable, like
    the real API (observed 2026-07-31)."""
    client.post("/__admin/inject", headers=ADMIN, json={"kind": "unstable_order", "scope": "*"})
    page1 = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    page2 = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    assert [d["id"] for d in page1] != [d["id"] for d in page2]


def test_stable_order_with_sort(client) -> None:
    """With `sort`, order is reproducible — and actually sorted."""
    params = {"maxResults": 10, "sort": "lastName"}
    a = client.get("/api/resources", headers=JWT, params=params).json()["data"]
    b = client.get("/api/resources", headers=JWT, params=params).json()["data"]
    assert [d["id"] for d in a] == [d["id"] for d in b]
    names = [d["attributes"]["lastName"] for d in a]
    assert names == sorted(names)


def test_unstable_order_by_environment(client, monkeypatch) -> None:
    monkeypatch.setattr(mock.settings, "stable_order", False)
    a = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    b = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    assert [d["id"] for d in a] != [d["id"] for d in b]


# ── Page drift ────────────────────────────────────────────────────────────────


def test_page_drift_duplicates_a_record(client) -> None:
    """A record rendered on two consecutive pages — the classic cause of
    silent duplication when data moves while paginating."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={
            "kind": "page_drift",
            "scope": "/api/times-reports",
            "after_page": 1,
            "mode": "insert",
        },
    )
    params = {"maxResults": 10, "sort": "term", "startMonth": "2026-05", "endMonth": "2026-07"}
    page1 = client.get("/api/times-reports", headers=JWT, params={**params, "page": 1}).json()
    page2 = client.get("/api/times-reports", headers=JWT, params={**params, "page": 2}).json()
    ids1 = [d["id"] for d in page1["data"]]
    ids2 = [d["id"] for d in page2["data"]]
    assert set(ids1) & set(ids2), "a record must appear on both pages"


# ── Incremental filter + mutations ───────────────────────────────────────────


def test_mutate_bumps_the_timestamp_and_makes_the_record_visible(client) -> None:
    """The exact path of a consumer-side incrementality test.

    Without the `updateDate` bump, the incremental cursor would never see the
    modified record again — and the test "a modification updates exactly one
    row" would pass while testing nothing.
    """
    cursor = {
        "period": "updated",
        "startDate": "2026-07-14",
        "endDate": "2026-12-31",
        "maxResults": 500,
    }
    before = client.get("/api/resources", headers=JWT, params=cursor).json()
    assert before["meta"]["totals"]["rows"] == 0, "the base dataset is older than the cursor"

    response = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={"collection": "resources", "id": "3", "attributes": {"title": "Modified"}},
    )
    assert response.status_code == 200

    modified = client.get("/api/resources/3", headers=JWT).json()["data"]
    assert modified["attributes"]["title"] == "Modified"
    # `_bump` advances by one second while preserving the timezone: the
    # record stays within the base dataset's window, but ITS updateDate moved.
    after = client.get("/api/resources?maxResults=500", headers=JWT).json()
    it = next(d for d in after["data"] if d["id"] == "3")
    all_sorted = client.get(
        "/api/resources?maxResults=500&sort=updateDate&order=desc", headers=JWT
    ).json()
    assert it["attributes"]["updateDate"] >= all_sorted["data"][-1]["attributes"]["updateDate"]


# ── RELATIONSHIP mutations ───────────────────────────────────────────────────
#
# At BoondManager, a resource's manager and its agency are JSON:API
# RELATIONSHIPS, not attributes. A consumer who derives access rights from an
# org chart (insights360/iris) needs to be able to simulate both
# corresponding mutations: a hierarchy change and an entity reassignment.


def test_mutate_changes_one_relation_without_touching_others(client) -> None:
    """The patch is key by key, like the attributes' one.

    Without this, exercising a manager change would carry the agency along
    with it, and the downstream test would observe TWO mutations while
    believing it measured one.
    """
    before = client.get("/api/resources/3", headers=JWT).json()["data"]
    agency_before = before["relationships"]["agency"]["data"]["id"]

    response = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={
            "collection": "resources",
            "id": "3",
            "relationships": {"mainManager": {"data": {"id": "5", "type": "resource"}}},
        },
    )
    assert response.status_code == 200

    after = client.get("/api/resources/3", headers=JWT).json()["data"]
    assert after["relationships"]["mainManager"]["data"]["id"] == "5"
    assert after["relationships"]["agency"]["data"]["id"] == agency_before


def test_mutate_accepts_the_bare_identifier_and_keeps_the_type(client) -> None:
    """`{"agency": "2"}` is equivalent to the canonical shape, and the `type`
    does not come from the tester's hand, so it cannot be misspelled."""
    response = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={"collection": "resources", "id": "3", "relationships": {"agency": "2"}},
    )
    assert response.status_code == 200

    relations = client.get("/api/resources/3", headers=JWT).json()["data"]["relationships"]
    assert relations["agency"]["data"] == {"id": "2", "type": "agency"}


def test_mutate_refuses_an_unknown_key_instead_of_lying(client) -> None:
    """THE regression that motivates this batch.

    Patching `attributes: {"main_manager_id": …}` — the column name seen on
    arrival in the pipeline, not the relationship's name — used to return 200
    and change nothing. The downstream scenario passed green without having
    exercised anything. The refusal must also NAME the available
    relationships, so the error can be fixed without reading the mock's code.
    """
    response = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={
            "collection": "resources",
            "id": "3",
            "attributes": {"main_manager_id": "5"},
        },
    )
    assert response.status_code == 400
    body = response.text
    assert "main_manager_id" in body
    assert "mainManager" in body, "the message must show the correct key"


def test_mutate_refuses_an_empty_patch(client) -> None:
    """ "Mutated" with nothing to mutate is the same lie, in another shape."""
    response = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={"collection": "resources", "id": "3"},
    )
    assert response.status_code == 400


def test_soft_delete_sets_a_flag_without_deleting(client) -> None:
    """LOGICAL deletion, never physical.

    An incremental pipeline running a `merge` strategy cannot observe a
    physical deletion without a full refresh.
    """
    total_before = client.get("/api/resources", headers=JWT).json()["meta"]["totals"]["rows"]
    client.post("/__admin/delete", headers=ADMIN, json={"collection": "resources", "id": "8"})
    # The flag lives on the SEARCH item (the real profile does not carry it).
    items = client.get("/api/resources?maxResults=500", headers=JWT).json()["data"]
    marked = next(d for d in items if d["id"] == "8")
    assert marked["attributes"]["isDeleted"] is True
    total_after = client.get("/api/resources", headers=JWT).json()["meta"]["totals"]["rows"]
    assert total_after == total_before, "the record stays served, with its flag"


# ── Control plane observability ──────────────────────────────────────────────


def test_state_exposes_the_received_parameters(client) -> None:
    """The property that lets a consumer PROVE it sends its cursor.

    A pipeline that forgot its incremental parameter would otherwise pass all
    its tests: the mock would simply render everything, and the result would
    be correct.
    """
    client.get(
        "/api/resources",
        headers=JWT,
        params={
            "period": "updated",
            "startDate": "2026-03-01",
            "endDate": "2026-03-31",
            "sort": "updateDate",
            "maxResults": 100,
        },
    )
    state = client.get("/__admin/state", headers=ADMIN).json()
    received = state["last_query_params_by_path"]["/api/resources"]
    assert received["period"] == "updated"
    assert received["startDate"] == "2026-03-01"
    assert received["sort"] == "updateDate"
    assert state["request_counts_by_path"]["/api/resources"] >= 1


def test_the_params_history_keeps_every_call(client) -> None:
    """Two consumers of the same path no longer overwrite each other in the state.

    Observed on 2026-08-13 at the consumer: resources are extracted
    incrementally (updatedSince), then collecting contracts re-lists the same
    path with no cursor — and `last_query_params_by_path` only showed the
    second call. The history keeps both, in order.
    """
    client.get(
        "/api/resources",
        headers=JWT,
        params={"updatedSince": "2026-01-01T00:00:00Z", "sort": "id"},
    )
    client.get("/api/resources", headers=JWT, params={"sort": "id"})
    state = client.get("/__admin/state", headers=ADMIN).json()
    calls = state["query_params_by_path"]["/api/resources"]
    assert len(calls) >= 2
    assert calls[-2].get("updatedSince") == "2026-01-01T00:00:00Z"
    assert "updatedSince" not in calls[-1]
    assert state["last_query_params_by_path"]["/api/resources"] == calls[-1]


def test_reset_changes_the_seed(client) -> None:
    """The seed is settable over HTTP — and reset confirms it."""
    response = client.post("/__admin/reset", headers=ADMIN, json={"seed": 7})
    assert response.json() == {"status": "reset", "seed": 7}
    assert (
        client.get("/api/resources", headers=JWT).json()["meta"]["totals"]["rows"]
        == TOTAL_RESOURCES
    )
    mock.state.reset()  # back to the environment's seed for the rest of the suite
