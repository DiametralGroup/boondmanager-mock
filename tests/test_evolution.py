"""Time evolution — what makes INCREMENTAL extraction testable.

An incremental extractor proves nothing against a frozen dataset: its cursor
would pass every test without ever having filtered. Here, the company's life
advances when the clock advances — and the clock is driven through
`/__admin/clock`, so tests fast-forward hours in a few milliseconds.

The interval is fixed at 3600s by the harness: ONE virtual hour = ONE event.
No event fires on the wall clock during the suite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import boondmanager_mock as mock
from tests.conftest import ADMIN, JWT

ONE_HOUR = 3600
#: Cursor placed AFTER the base dataset's cap (2026-07-12) and BEFORE the
#: events' epoch (2026-07-15): it isolates exactly what has evolved.
CURSOR = {
    "period": "updated",
    "startDate": "2026-07-14",
    "endDate": "2026-12-31",
    "maxResults": "500",
}


def _advance(client: TestClient, hours: int) -> None:
    client.post("/__admin/clock", headers=ADMIN, json={"advance_seconds": hours * ONE_HOUR})


def _rows(client: TestClient, path: str, **params: str) -> int:
    response = client.get(f"/api/{path}", headers=JWT, params={"maxResults": 500, **params})
    return response.json()["meta"]["totals"]["rows"]


def test_the_dataset_is_stable_without_clock_advances(client):
    before = _rows(client, "actions")
    assert _rows(client, "actions") == before
    assert _rows(client, "resources", **CURSOR) == 0


def test_new_actions_appear(client):
    before = _rows(client, "actions")
    _advance(client, 1)  # event 0: a CRM action
    assert _rows(client, "actions") == before + 1


def test_a_profile_is_updated_and_seen_by_the_cursor(client):
    _advance(client, 2)  # events 0-1: action + enriched profile
    body = client.get("/api/resources", headers=JWT, params=CURSOR).json()
    assert body["meta"]["totals"]["rows"] == 1
    assert body["data"][0]["attributes"]["updateDate"].startswith("2026-07-15")


def test_staffing_then_destaffing_visible_on_the_profile(client, boond_state):
    """The bench moves: delivery created, `availability` flipped, fresh `updateDate`.

    The bench is identified by `availability: "immediate"` — the field
    OBSERVED for real. `staffing` events land at indexes 2, 10, 18, 26…
    As long as consultants remain on the bench they get staffed; afterward
    the event DESTAFFS someone — both directions eventually occur.
    """
    deliveries_before = len(boond_state.dataset["deliveries"])
    bench_before = [
        r["id"]
        for r in boond_state.dataset["resources"]
        if r["attributes"]["availability"] == "immediate"
    ]
    assert bench_before, "the base dataset must have an intercontract bench"

    _advance(client, 3)  # includes the staffing event k=2
    assert len(boond_state.dataset["deliveries"]) == deliveries_before + 1
    staffed = next(r for r in boond_state.dataset["resources"] if r["id"] == bench_before[0])
    assert staffed["attributes"]["availability"] != "immediate"
    assert staffed["attributes"]["updateDate"].startswith("2026-07-15")

    # 4 more cycles: the bench (4 people) is exhausted → destaffing.
    # (35 virtual hours past the epoch, the day has rolled over: bound by ≥.)
    _advance(client, 8 * 4)
    on_bench = [
        r
        for r in boond_state.dataset["resources"]
        if r["attributes"]["availability"] == "immediate"
        and r["attributes"]["realAvailability"] >= "2026-07-15"
    ]
    assert on_bench, "at least one consultant must have been destaffed"
    destaffed = on_bench[0]
    closed_deliveries = [
        m
        for m in boond_state.dataset["deliveries"]
        if m["attributes"]["state"] == 2
        and m["attributes"]["endDate"] == destaffed["attributes"]["realAvailability"]
        and m["relationships"]["dependsOn"]["data"]["id"] == destaffed["id"]
    ]
    assert closed_deliveries, "the destaffed consultant's delivery must close at the event's date"


def test_invoice_settled_and_banking_transaction(client):
    transactions_before = _rows(client, "banking-transactions")
    settled_before = _rows(client, "invoices", period="performedPayment")  # ignored → total
    _advance(client, 4)  # includes the invoice event k=3
    assert _rows(client, "banking-transactions") == transactions_before + 1
    body = client.get("/api/invoices", headers=JWT, params=CURSOR).json()
    assert body["meta"]["totals"]["rows"] == 1
    invoice = body["data"][0]["attributes"]
    assert invoice["state"] == 2
    assert invoice["performedPaymentDate"] == "2026-07-15"
    assert settled_before  # guard rail: the collection was not empty


def test_end_to_end_incremental_extraction(client, monkeypatch):
    """The target scenario: full snapshot, cursor, delta — nothing else.

    This is THE flow consumers (ophelie, insights360) will replay against this
    mock: the incremental pass must see ONLY what has moved.
    """
    collections = ("resources", "contacts", "actions", "invoices", "opportunities")
    snapshot = {c: _rows(client, c) for c in collections}
    assert all(_rows(client, c, **CURSOR) == 0 for c in collections)

    _advance(client, 8)  # one full cycle of events

    delta = {c: _rows(client, c, **CURSOR) for c in collections}
    assert delta["actions"] >= 3, "new actions carry most of the delta"
    assert delta["contacts"] >= 1, "a contact was created at a client"
    assert delta["resources"] >= 2, "enriched profile + staffing"
    assert delta["invoices"] == 1, "an invoice was settled"
    assert delta["opportunities"] == 1, "an opportunity progressed"

    # The total moved where entities were BORN, nowhere else.
    assert _rows(client, "actions") > snapshot["actions"]
    assert _rows(client, "resources") == snapshot["resources"]

    # The fine-grained affordance (updatedSince, ISO-8601), turned back on on
    # request, sees the same delta — the vendor itself ignores it.
    monkeypatch.setattr(mock.settings, "updated_since_enabled", True)
    result = client.get(
        "/api/actions",
        headers=JWT,
        params={"updatedSince": "2026-07-14T00:00:00+0200", "maxResults": 500},
    ).json()
    assert result["meta"]["totals"]["rows"] == delta["actions"]


def test_the_timeline_is_deterministic(client):
    """Same seed, same clock → same company life, down to the detail.

    This is what lets an extraction incident be replayed: the sequence only
    depends on the seed, never on when the tests were launched.
    """
    _advance(client, 8)
    first = client.get("/__admin/state", headers=ADMIN).json()["evolution"]["journal"]

    mock.state.reset()
    _advance(client, 8)
    second = client.get("/__admin/state", headers=ADMIN).json()["evolution"]["journal"]

    assert first == second


def test_the_journal_exposes_the_delta(client):
    _advance(client, 3)
    evolution = client.get("/__admin/state", headers=ADMIN).json()["evolution"]
    assert evolution["applied"] == 3
    assert [e["kind"] for e in evolution["journal"]] == ["action", "profile", "staffing"]
    assert all(e["at"].startswith("2026-07-15") for e in evolution["journal"])


def test_evolution_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(mock.settings, "evolution_enabled", False)
    before = _rows(client, "actions")
    _advance(client, 5)
    assert _rows(client, "actions") == before


def test_reset_rearms_the_timeline(client):
    _advance(client, 2)
    assert client.get("/__admin/state", headers=ADMIN).json()["evolution"]["applied"] == 2
    client.post("/__admin/reset", headers=ADMIN)
    assert client.get("/__admin/state", headers=ADMIN).json()["evolution"]["applied"] == 0
    assert _rows(client, "resources", **CURSOR) == 0
