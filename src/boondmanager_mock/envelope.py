"""Envelopes, pagination, sorting, incremental filter — and their failures.

The envelope follows the OFFICIAL schema (doc.boondmanager.com, RAML):

    list   : {"data": [...], "included": [...], "meta": {"totals": {"rows": N},
              "version": "…", "isLogged": true, "language": "fr"}}
    detail : {"data": {...}, "included": [...], "meta": {version, isLogged, language}}

`included` only appears on modules whose schema declares it, and only when
non-empty.

Beyond the happy path, this module reproduces what the real API does, as
probed on 2026-09-29:
  • `page`/`maxResults` pagination: default 30, max 500 (100 on `/actions`)
    and, beyond the max, a SILENT fallback to the default 30 rows;
    `agencies`, `poles` and `business-units` are not paginated;
  • sorting: only the official `sortList` keys are honored, and the default
    order is a descending date on the measured collections;
  • the official period filters (`period=updated|created`, and
    `period=inProgress` on `/times`);
  • opt-in: UNSTABLE order, page drift (a record rendered on two pages) and
    the `updatedSince` filter, which the vendor ignores (mock affordance, see
    below).
"""

from __future__ import annotations

import json
from typing import Any

from .injection import engine
from .settings import settings

#: The versions `meta` announces — observed on the real API on 2026-07-31.
VERSION_BOOND = "9.1.78.1"
VERSION_ANDROID_MIN = "2.31.5"
VERSION_IOS_MIN = "2.28.6"


def _timestamp_ms() -> int:
    """`meta.timestamp` — epoch milliseconds, DETERMINISTIC.

    Derived from the VIRTUAL clock: the dataset's epoch plus elapsed time
    since the reset (including /__admin/clock advances). Two servers at the
    same age render the same timestamp — the property the real API lacks, and
    that the mock keeps to stay replayable.
    """
    from .evolution import EPOCH
    from .state import state

    elapsed = engine.now() - state.evolution.started_at
    return int(EPOCH.timestamp() * 1000 + elapsed * 1000)


def _common_meta(logged_in: bool) -> dict[str, Any]:
    """The `meta` baseline observed on the real API — present EVEN on error.

    Outside a session (401, invalid JWT, unknown route): `isLogged: false`,
    `language: "en"`, with no `login` nor `customer`.
    """
    meta: dict[str, Any] = {
        "version": VERSION_BOOND,
        "androidMinVersion": VERSION_ANDROID_MIN,
        "iosMinVersion": VERSION_IOS_MIN,
        "isLogged": logged_in,
        "language": "fr" if logged_in else "en",
        "timestamp": _timestamp_ms(),
    }
    if logged_in:
        meta["login"] = settings.basic_user
        meta["customer"] = settings.customer
    return meta


def error_meta(logged_in: bool) -> dict[str, Any]:
    """The meta of error responses (imported by errors.py)."""
    return _common_meta(logged_in)


# ┌─ INCREMENTAL: THE OFFICIAL PATH, THEN THE AFFORDANCE ───────────────────────┐
# │ The OFFICIAL path (RAML): `period=updated&startDate=YYYY-MM-DD&endDate=…`  │
# │ — documented on 11 modules (actions, candidates, companies, contacts,      │
# │ invoices, opportunities, orders, payments, projects, purchases,            │
# │ resources), DAY granularity. Probed 2026-09-29: honored on all 11,         │
# │ including /orders, which does not even render `updateDate`. `period=created`│
# │ does the same on the creation date.                                        │
# │                                                                            │
# │ On `/times`, the only documented value is `period=inProgress`. It filters  │
# │ on the ROW'S DATE (`startDate`), and it works: 111 745 rows in total,      │
# │ 2 716 for September 2026.                                                   │
# │                                                                            │
# │ Outside these cases, the mock applies `period=updated|created` on its      │
# │ other collections (a superset, unmeasured); other `period` values and      │
# │ business filters (`flags`, `states`…) are ACCEPTED and ignored.            │
# │                                                                            │
# │ The `updatedSince=<ISO-8601>` affordance (or `filter[updateDate][gte]`)    │
# │ does NOT exist at the vendor: it accepts it and ignores it, identical      │
# │ totals on the 11 modules. Disabled by default since 0.11.0;                │
# │ `BOOND_MOCK_UPDATED_SINCE=true` turns it back on.                          │
# └─────────────────────────────────────────────────────────────────────────────┘
UPDATED_SINCE_PARAMS = ("updatedSince", "filter[updateDate][gte]")

UPDATED_AT_FIELD = "updateDate"

#: `period` → filtered field, [startDate, endDate] bounds, inclusive by day.
SUPPORTED_PERIODS = {
    "updated": "updateDate",
    "created": "creationDate",
    # /times: the time row's date, not a modification date.
    "inProgress": "startDate",
}

#: `period` values honored by default: the mock's superset.
DEFAULT_PERIODS: tuple[str, ...] = ("updated", "created")


def apply_period(
    items: list[dict[str, Any]],
    params: dict[str, str],
    periods: tuple[str, ...] = DEFAULT_PERIODS,
) -> list[dict[str, Any]]:
    """The OFFICIAL period filters: `period=<value>` + day bounds.

    Only the values in `periods` apply: any other is accepted and IGNORED,
    like the vendor does. An item without the targeted field is excluded when
    the filter is active — a row without a creation date cannot be "created
    between two dates".
    """
    period = params.get("period", "")
    field_name = SUPPORTED_PERIODS.get(period) if period in periods else None
    if field_name is None:
        return items
    start = params.get("startDate", "0000-00-00")
    end = params.get("endDate", "9999-12-31")
    return [
        i
        for i in items
        if (day := str(i.get("attributes", {}).get(field_name, ""))[:10]) and start <= day <= end
    ]


def apply_keywords(
    items: list[dict[str, Any]],
    keywords: str,
    blobs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Coarse full-text search — good enough for a mock.

    `blobs`: the precomputed search text per item (state.blobs), aligned with
    the FULL collection — avoids re-serializing the dataset on every
    request."""
    if not keywords:
        return items
    needle = keywords.strip().lower()
    if blobs is not None and len(blobs) == len(items):
        return [i for i, blob in zip(items, blobs, strict=True) if needle in blob]
    return [i for i in items if needle in json.dumps(i, ensure_ascii=False).lower()]


def apply_incremental(items: list[dict[str, Any]], since: str | None) -> list[dict[str, Any]]:
    """Filter on the update timestamp: a mock AFFORDANCE.

    The vendor accepts `updatedSince` and ignores it (probed 2026-09-29): the
    filter therefore only applies if `BOOND_MOCK_UPDATED_SINCE=true`. Applied
    unconditionally, it made a client that re-read all its collections in
    production on every run look green.

    Lexicographic comparison: timestamps are ISO-8601 (Europe/Paris timezone,
    offset without a colon, like the real API), so lexicographic and
    chronological order coincide to the day — good enough for a mock, with no
    parsing nor failure mode on a malformed date.
    """
    if not since or not settings.updated_since_enabled:
        return items
    return [i for i in items if str(i.get("attributes", {}).get(UPDATED_AT_FIELD, "")) >= since]


def extract_since(params: dict[str, str]) -> str | None:
    for name in UPDATED_SINCE_PARAMS:
        if (value := params.get(name)) is not None:
            return value
    return None


#: The OFFICIAL sort keys: the `sortablePaginable` trait's `sortList`, per
#: module (RAML pulled 2026-09-29). An absent key is ignored without error —
#: probed: `sort=id` and a made-up key both render the default order, with a
#: 200. Absent modules (agencies, poles, business-units) have no sort in the
#: contract.
SORT_LISTS: dict[str, frozenset[str]] = {
    "absences": frozenset({"resource.lastName"}),
    "actions": frozenset(
        {
            "startDate", "typeOf", "mainManager.lastName", "dependsOn.email1",
            "dependsOn.lastName", "dependsOn.reference", "dependsOn.name",
            "dependsOn.title", "dependsOn.id", "dependsOn.number",
        }
    ),
    "banking-transactions": frozenset({"amount", "description", "date", "state"}),
    "candidates": frozenset(
        {
            "lastName", "firstName", "title", "availability", "availabilityType",
            "numberOfActivePositionings", "mainManager.lastName", "updateDate", "state",
            "experience", "creationDate", "evaluation", "hrManager.lastName", "source",
            "distance",
        }
    ),
    "companies": frozenset(
        {
            "name", "information", "town", "state", "expertiseArea",
            "mainManager.lastName", "updateDate",
        }
    ),
    "contacts": frozenset(
        {
            "company.name", "town", "lastName", "firstName", "function", "state",
            "company.expertiseArea", "mainManager.lastName", "updateDate",
        }
    ),
    "expenses": frozenset({"category", "startDate", "resource.lastName"}),
    "invoices": frozenset(
        {
            "turnoverInvoicedIncludingTax", "date", "reference", "turnoverInvoicedExcludingTax",
            "expectedPaymentDate", "state", "order.number", "order.project.reference",
            "order.project.company.name", "order.mainManager.lastName", "closed", "startDate",
            "endDate", "intermediaryCompany.name",
        }
    ),
    "opportunities": frozenset(
        {
            "creationDate", "title", "company.name", "place", "numberOfActivePositionings",
            "startDate", "endDate", "duration", "state", "alertCount", "closingDate",
            "updateDate", "answerDate", "totalWeightedTurnOverExcludingTax",
            "mainManager.lastName",
        }
    ),
    "orders": frozenset(
        {
            "date", "number", "state", "project.reference", "customerAgreement",
            "turnoverInvoicedExcludingTax", "turnoverOrderedExcludingTax",
            "deltaInvoicedExcludingTax", "project.company.name", "mainManager.lastName",
            "intermediaryCompany.name", "exceededOrderedTurnover",
        }
    ),
    "payments": frozenset(
        {
            "expectedDate", "performedDate", "state", "date", "purchase.title",
            "project.reference", "purchase.company.name", "mainManager.lastName",
        }
    ),
    "projects": frozenset(
        {
            "startDate", "endDate", "reference", "company.name", "mainManager.lastName",
            "intermediaryCompany.name",
        }
    ),
    "purchases": frozenset(
        {"title", "state", "date", "project.reference", "company.name", "mainManager.lastName"}
    ),
    "resources": frozenset(
        {
            "lastName", "firstName", "title", "state", "availability", "nextAvailability",
            "numberOfActivePositionings", "mainManager.lastName", "priceExcludingTax",
            "creationDate", "updateDate", "distance",
        }
    ),
    "roles": frozenset({"name"}),
    "times": frozenset(
        {
            "category", "startDate", "workUnitType.reference", "timesReport.resource.lastName",
            "timesReport.state", "delivery.project.company.name", "delivery.project.reference",
            "recovering", "processed",
        }
    ),
    "times-reports": frozenset({"term", "state", "resource.lastName", "closed"}),
}  # fmt: skip

#: `sortList` keys the vendor ignores anyway (probed 2026-09-29):
#: `/resources?sort=creationDate` renders the default order, both asc and desc.
IGNORED_SORTS: frozenset[tuple[str, str]] = frozenset({("resources", "creationDate")})

#: Keys for which the vendor ignores `order`: always descending (probed
#: 2026-09-29 — `/resources?sort=updateDate&order=asc` renders the same
#: sequence as desc, while companies and actions honor both directions).
ALWAYS_DESCENDING_SORTS: frozenset[tuple[str, str]] = frozenset({("resources", "updateDate")})

#: The order honored WITHOUT a sort, measured 2026-09-29: a DESCENDING date.
#:
#: ┌─ WHY THIS MATTERS FOR A CONSUMER THAT PAGINATES ──────────────────────────┐
#: │ On a list sorted by modification date, a record modified during the walk │
#: │ moves to the front: subsequent pages shift by one, and a row is served   │
#: │ twice. A deletion does the opposite and skips a row. The mock used to    │
#: │ serve ids in ascending order, which masked all of this — and suggested   │
#: │ that `sort=id`, ignored by the vendor, stabilized pagination.            │
#: └───────────────────────────────────────────────────────────────────────────┘
#: Absent collections have not been measured: insertion order, stable.
DEFAULT_ORDER: dict[str, str] = {
    "resources": "updateDate",
    "companies": "updateDate",
    "actions": "startDate",
}


def _sortable_value(item: dict[str, Any], path: str) -> tuple[int, float, str]:
    """Sort key, dotted path accepted (`workUnitType.reference`).

    A number sorts as a number (`10` after `9`), everything else as text; a
    missing value counts as an empty string."""
    node: Any = item.get("attributes", {})
    for segment in path.split("."):
        if not isinstance(node, dict):
            return (1, 0.0, "")
        node = node.get(segment)
    if node is None:
        return (1, 0.0, "")
    if isinstance(node, int | float) and not isinstance(node, bool):
        return (0, float(node), "")
    return (1, 0.0, str(node))


def _sort_honored(collection: str | None, key: str) -> bool:
    """Is the `sort` key honored by the vendor on this module?

    Without a named collection (internal call), every key is honored."""
    if collection is None:
        return True
    if (collection, key) in IGNORED_SORTS:
        return False
    return key in SORT_LISTS.get(collection, frozenset())


def apply_order(
    items: list[dict[str, Any]],
    params: dict[str, str],
    request_index: int,
    collection: str | None = None,
) -> list[dict[str, Any]]:
    """The order as MEASURED on the real API (2026-09-29).

    1. `sort` is only honored if it appears in the module's official
       `sortList`; otherwise it is ignored without error, like the vendor
       does.
    2. Without an honored sort, the default order applies: a descending date
       on the measured collections (DEFAULT_ORDER), insertion order elsewhere.
       Two identical calls render the same sequence.
    3. Instability stays available, OPT-IN, to exercise pipelines
       (`BOOND_MOCK_STABLE_ORDER=false` or an `unstable_order` injection). It
       is DETERMINISTIC within a given test — `hash((request rank, id))` — so
       reproducible.
    """
    sort_field = params.get("sort")
    if sort_field and _sort_honored(collection, sort_field):
        if (collection, sort_field) in ALWAYS_DESCENDING_SORTS:
            reverse = True
        else:
            reverse = params.get("order", "asc").lower() == "desc"
        return sorted(items, key=lambda i: _sortable_value(i, sort_field), reverse=reverse)

    unstable = not settings.stable_order or engine.first("unstable_order", "*") is not None
    if unstable:
        return sorted(items, key=lambda i: hash((request_index, i.get("id"))))

    if field_name := DEFAULT_ORDER.get(collection or ""):
        return sorted(items, key=lambda i: _sortable_value(i, field_name), reverse=True)
    return items


def apply_page_drift(
    all_items: list[dict[str, Any]], page: int, page_size: int, path: str
) -> list[dict[str, Any]] | None:
    """Simulates data that moves WHILE pagination is in progress.

    The real-world scenario: a record is inserted (or deleted) between
    fetching page 1 and page 2. Everything shifts by one, and a record ends up
    rendered twice — or not at all.

    This is the classic cause of silent duplication, and the reason a
    pipeline must deduplicate on its merge key rather than trust pagination.

    Operates on the FULL list and returns the shifted slice — or None if no
    rule applies. (The original mock shifted the already-sliced page:
    `items[:n] + items[n:]`, an identity — the failure never actually
    applied.)
    """
    rule = engine.first("page_drift", path)
    if rule is None or page <= rule.after_page:
        return None
    if not rule.consume():
        return None
    if rule.mode == "insert":
        # An upstream insertion shifts everything backward: the previous
        # page's last element reappears at the front of this one.
        start = max(0, (page - 1) * page_size - 1)
    else:
        # An upstream deletion makes everything move up by one: this page's
        # expected first element has already been served… or is lost.
        start = (page - 1) * page_size + 1
    return all_items[start : start + page_size]


#: `maxResults` cap per collection, when it differs from the general cap.
#:
#: ┌─ MEASURED, NOT ASSUMED — 2026-09-29, against a production tenant ────────┐
#: │ `/actions` honors `maxResults` up to 100 (100 → 100 rows) and falls back │
#: │ to the default 30 at 101. Elsewhere the cap is 500: `/companies` renders │
#: │ 500 rows for 500, and 30 for 501.                                        │
#: │                                                                           │
#: │ The 2026-08-12 survey had concluded that `/actions` IGNORED the          │
#: │ parameter: the only value tested, 500, exceeded its cap. The mock then   │
#: │ rendered 30 rows no matter what was asked, and a client that had asked   │
#: │ for 100 had no way to see it would have been served: 50 777 actions make │
#: │ 508 pages at 100, against 1 693 at 30.                                   │
#: └───────────────────────────────────────────────────────────────────────────┘
MAXRESULTS_CAPS: dict[str, int] = {"actions": 100}

#: Modules WITHOUT pagination in the contract (no `sortablePaginable` trait):
#: the vendor ignores `page` and `maxResults` and renders everything (probed
#: 2026-09-29: 11 agencies, 8 poles, 2 units, even with `page=2&maxResults=1`).
NON_PAGINATED_COLLECTIONS: frozenset[str] = frozenset({"agencies", "poles", "business-units"})


def paginate(
    items: list[dict[str, Any]], params: dict[str, str], collection: str | None = None
) -> tuple[list[dict[str, Any]], int, int] | None:
    """Returns (slice, page, size) or None if the parameters are invalid.

    `collection` is the BARE collection name (`actions`, not `/api/actions`).
    It serves the two per-module behaviors: the `/actions`-specific cap and
    the non-paginated modules. It stays optional.

    Beyond the cap, the vendor does NOT cap: it silently falls back to the
    default size (30). No 422, no signal — a consumer asking for too much
    receives less than an ordinary page.
    """
    if collection in NON_PAGINATED_COLLECTIONS:
        return items, 1, max(1, len(items))
    try:
        page = max(1, int(params.get("page", 1)))
        requested = int(params.get("maxResults", settings.default_max_results))
    except ValueError:
        return None
    cap = MAXRESULTS_CAPS.get(collection or "", settings.max_results_cap)
    if requested > cap:
        requested = settings.default_max_results
    page_size = max(1, requested)
    start = (page - 1) * page_size
    return items[start : start + page_size], page, page_size


def envelope(
    data: list[dict[str, Any]],
    total: int,
    included: list[dict[str, Any]] | None = None,
    meta_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The list envelope — full observed meta + module-specific keys."""
    body: dict[str, Any] = {"data": data}
    if included:
        body["included"] = included
    body["meta"] = {**_common_meta(True), **(meta_extra or {}), "totals": {"rows": total}}
    return body


def envelope_detail(
    item: dict[str, Any], included: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The detail envelope — same `meta`, without `totals`, like real profiles."""
    body: dict[str, Any] = {"data": item}
    if included:
        body["included"] = included
    body["meta"] = _common_meta(True)
    return body
