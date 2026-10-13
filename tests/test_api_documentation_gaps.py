"""Where the REAL API diverges from its own documentation.

A mock has two possible loyalties, and they conflict: being faithful to the
DOCUMENTATION, or faithful to OBSERVED BEHAVIOR. This repository chooses the
latter, without exception.

The reason is concrete. A mock that "does the right thing" where the vendor
does not makes its consumer green on behavior that does not exist: sizing,
extraction cadence and the load placed on the API are then computed on a
fiction. This is exactly what happened to insights360 — its hourly cadence
assumed an incremental filter on /times, and actually represented ~25,000
calls a day at the vendor.

Every gap logged here was MEASURED against ui.boondmanager.com, with a date
and figures. None is deduced from the documentation.
"""

from __future__ import annotations

from typing import Any

from boondmanager_mock.app import COLLECTIONS
from tests.conftest import JWT


def _total(response: Any) -> int:
    return int(response.json()["meta"]["totals"]["rows"])


def test_times_ignores_out_of_contract_filters_like_the_real_api(client: Any) -> None:
    """`/times` accepts filter shapes OUTSIDE the contract and IGNORES them.

    Measured 2026-08-04 against ui.boondmanager.com, on a production tenant
    with 106,976 time rows:

        no filter                      → 106,976
        startDate + endDate            → 106,976
        startMonth + endMonth          → 106,976
        period=updated + startDate     → 106,976

    None of these shapes is rejected — a 422 would at least have signaled
    something. But none is the contract's shape either, which only documents
    `period=inProgress` on `/times`: that is the next test.
    """
    h = JWT

    reference = _total(client.get("/api/times", params={"maxResults": 1}, headers=h))
    assert reference > 0, "the reference dataset must contain time rows"

    for filter_ in (
        {"startDate": "2026-07-01", "endDate": "2026-07-31"},
        {"startMonth": "2026-07", "endMonth": "2026-07"},
        {"period": "updated", "startDate": "2026-07-01"},
        {"period": "created", "startDate": "2026-07-01", "endDate": "2026-07-31"},
    ):
        p = dict(filter_)
        p["maxResults"] = "1"
        response = client.get("/api/times", params=p, headers=h)
        assert response.status_code == 200, (
            f"{filter_} must be ACCEPTED, not rejected — the real API returns "
            f"no error on these parameters (got {response.status_code})"
        )
        assert _total(response) == reference, (
            f"{filter_} filtered {reference - _total(response)} row(s). The real "
            "API filters none: the mock must reproduce observed behavior, not "
            "the documentation."
        )


def test_times_honors_period_in_progress_like_the_real_api(client: Any) -> None:
    """The CONTRACT's shape filters, on the row's date.

    Probed 2026-09-29: 111,745 rows with no filter, 2,716 with
    `period=inProgress&startDate=2026-09-01&endDate=2026-09-29`, 2,575 for
    August. The 2026-08-04 conclusion ("no windowing possible") came from
    out-of-contract shapes.
    """
    h = JWT
    everything = client.get("/api/times", params={"maxResults": 500}, headers=h).json()["data"]
    days = sorted({t["attributes"]["startDate"][:10] for t in everything})
    assert len(days) > 2, "the dataset must span several days to exercise the filter"
    start, end = days[1], days[-2]

    response = client.get(
        "/api/times",
        params={"maxResults": 500, "period": "inProgress", "startDate": start, "endDate": end},
        headers=h,
    )
    assert response.status_code == 200
    window = response.json()["data"]
    expected = [t["id"] for t in everything if start <= t["attributes"]["startDate"][:10] <= end]
    assert 0 < len(window) < len(everything)
    assert sorted(t["id"] for t in window) == sorted(expected)


def test_only_times_restricts_its_periods(client: Any) -> None:
    """The gap is LOCAL to `/times` — not a property of the whole mock.

    Without this counter-check, a collection losing `period=updated` by
    mistake would go unnoticed, and a consumer would silently lose its
    incrementality.
    """
    restricted = {s.path: s.periods for s in COLLECTIONS if "updated" not in s.periods}
    assert restricted == {"times": ("inProgress",)}, (
        f"only /times restricts its `period` values; found: {restricted}. "
        "Changing this requires a MEASUREMENT against the real API, documented "
        "in docs/comparisons/."
    )

    h = JWT
    # `/actions` carries `creationDate` and honors the filter — a counter-check
    # on a collection whose behavior matches the documentation.
    total = _total(client.get("/api/actions", params={"maxResults": 1}, headers=h))
    filtered = _total(
        client.get(
            "/api/actions",
            params={"maxResults": 1, "period": "created", "endDate": "1900-01-01"},
            headers=h,
        )
    )
    assert filtered < total, (
        "a window closed in 1900 must empty /actions; if it does not, the "
        "period filter is broken for EVERY collection"
    )


def test_updated_since_is_ignored_everywhere(client: Any) -> None:
    """`updatedSince` is not in the contract, and the vendor ignores it on the
    11 modules that have `period=updated` (probed 2026-09-29). The mock
    therefore ignores it by default: applying it made a client that re-read
    everything look green."""
    h = JWT
    for path in ("resources", "companies", "contacts", "actions", "candidates", "invoices"):
        total = _total(client.get(f"/api/{path}", params={"maxResults": 1}, headers=h))
        future = _total(
            client.get(
                f"/api/{path}",
                params={"maxResults": 1, "updatedSince": "2099-01-01T00:00:00Z"},
                headers=h,
            )
        )
        official = _total(
            client.get(
                f"/api/{path}",
                params={
                    "maxResults": 1,
                    "period": "updated",
                    "startDate": "2099-01-01",
                    "endDate": "2099-12-31",
                },
                headers=h,
            )
        )
        assert future == total, f"{path}: updatedSince must filter nothing"
        assert official == 0, f"{path}: period=updated must filter"
