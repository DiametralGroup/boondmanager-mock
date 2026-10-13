"""Assembling the FastAPI application.

A SINGLE dispatch point for failures (`_dispatch_injections`), evaluated
before authentication so that `auth_reject` can preempt it. Every collection
route goes through it: there can therefore be no "forgotten" route where
failures would not apply.

The surface reproduces the vendor's modules, CONFRONTED with the real API
(real tenant, version 9.1.78.1, probes from 2026-07-30/31):

  • 20 collections queryable as a list — `/absences`, `/expenses` and
    `/times` with no `/{id}` detail, like for real;
  • `GET /contracts` and `GET /deliveries` (lists) answer **405**, like for
    real — the data is fetched through `/{id}` and through relationships
    (`resources/{id}` → `contracts`, `purchases` → `delivery`, `times` →
    `delivery`…);
  • `times-reports` REQUIRES `startMonth`/`endMonth` (422, business code 1017);
  • DETAILS serve the official *profile* shapes when they are attested
    (resources, projects, contracts, technical-data, administrative);
  • unknown routes render the Boond error envelope, not FastAPI's 404.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import basic_is_valid, jwt_is_valid
from .envelope import (
    DEFAULT_PERIODS,
    apply_incremental,
    apply_keywords,
    apply_order,
    apply_page_drift,
    apply_period,
    envelope,
    envelope_detail,
    extract_since,
    paginate,
)
from .errors import error, error_entry, error_response
from .included import build_included
from .injection import engine
from .models import (
    ERROR_RESPONSES,
    Absence,
    Advantage,
    Agency,
    BankingTransaction,
    BusinessUnit,
    Candidate,
    Company,
    CompanyInformation,
    Contact,
    Contract,
    CrmAction,
    CurrentUser,
    Delivery,
    DictionaryEnvelope,
    Expense,
    Invoice,
    ItemEnvelope,
    ListEnvelope,
    Opportunity,
    Order,
    Payment,
    Pole,
    Project,
    Purchase,
    Resource,
    ResourceAdministrative,
    Role,
    TechnicalData,
    Time,
    TimesReport,
)
from .settings import settings
from .state import state


@dataclass(frozen=True)
class CollectionSpec:
    """What is needed to know about a collection to both serve it AND document it.

    The route factory reads this table: adding a collection means an entry
    here plus a key in the dataset. `model` is what takes the OpenAPI contract
    from "list of paths" to an actual contract.
    """

    path: str  # URL segment — `times-reports` carries a hyphen
    dataset_key: str  # key in the dataset dict
    model: type  # pydantic model of the item
    singular: str  # entity name, singular (documentation)
    has_detail: bool = True  # /absences, /expenses and /times are search-only
    has_included: bool = True  # modules without `included` in the official schema
    list_405: bool = False  # GET list absent for real (contracts, deliveries)
    required_params: tuple[str, ...] = ()  # 422 code 1017 otherwise
    #: The `period` values HONORED by this collection.
    #:
    #: `updated`/`created` everywhere EXCEPT `/times`, which only honors
    #: `inProgress` — see the block above its declaration. A value absent here
    #: does not cause an error response: the collection accepts the
    #: parameter and IGNORES it, exactly like the vendor.
    periods: tuple[str, ...] = DEFAULT_PERIODS
    meta_extra: tuple[str, ...] = ()  # module-specific meta keys (observed for real)


#: Per-module meta key values — KEYS observed for real, plausible values
#: (the exact content is not documented; see docs/UNVERIFIED-FIELDS.md).
META_EXTRAS: dict[str, Any] = {
    "solr": True,
    "conditionalFields": [],
    "resetCache": False,
    "hasOpportunityAlerts": False,
}


COLLECTIONS: tuple[CollectionSpec, ...] = (
    CollectionSpec(
        "absences", "absences", Absence, "absence", has_detail=False, has_included=False
    ),
    CollectionSpec("actions", "actions", CrmAction, "action", meta_extra=("solr",)),
    CollectionSpec(
        "agencies", "agencies", Agency, "agency", has_included=False, meta_extra=("resetCache",)
    ),
    CollectionSpec(
        "banking-transactions", "banking_transactions", BankingTransaction, "bankingTransaction"
    ),
    CollectionSpec("business-units", "business_units", BusinessUnit, "businessUnit"),
    CollectionSpec(
        "candidates",
        "candidates",
        Candidate,
        "candidate",
        meta_extra=("conditionalFields", "solr"),
    ),
    CollectionSpec(
        "companies", "companies", Company, "company", meta_extra=("conditionalFields", "solr")
    ),
    CollectionSpec(
        "contacts", "contacts", Contact, "contact", meta_extra=("conditionalFields", "solr")
    ),
    CollectionSpec("contracts", "contracts", Contract, "contract", list_405=True),
    CollectionSpec("deliveries", "deliveries", Delivery, "delivery", list_405=True),
    CollectionSpec(
        "expenses", "expenses", Expense, "expense", has_detail=False, has_included=False
    ),
    CollectionSpec("invoices", "invoices", Invoice, "invoice"),
    CollectionSpec(
        "opportunities",
        "opportunities",
        Opportunity,
        "opportunity",
        meta_extra=("conditionalFields", "hasOpportunityAlerts", "solr"),
    ),
    CollectionSpec("orders", "orders", Order, "order"),
    CollectionSpec("payments", "payments", Payment, "payment"),
    CollectionSpec("poles", "poles", Pole, "pole", has_included=False),
    CollectionSpec("projects", "projects", Project, "project"),
    CollectionSpec("purchases", "purchases", Purchase, "purchase"),
    CollectionSpec(
        "resources", "resources", Resource, "resource", meta_extra=("conditionalFields", "solr")
    ),
    CollectionSpec("roles", "roles", Role, "role", has_included=False),
    # ┌─ `/times`: THE CONTRACT'S FILTER IS `period=inProgress` ────────────────┐
    # │ The contract (RAML) only documents one `period` value on `/times`:      │
    # │ `inProgress`, which filters rows whose DATE (`startDate`) falls          │
    # │ between `startDate` and `endDate`. Probed 2026-09-29: it works.          │
    # │                                                                          │
    # │     no filter                                      → 111 745             │
    # │     period=inProgress, 2026-09-01 → 2026-09-29     →   2 716             │
    # │     period=inProgress, August 2026                 →   2 575             │
    # │                                                                          │
    # │ The 2026-08-04 survey had tested three OTHER shapes — dates alone,       │
    # │ `startMonth/endMonth`, `period=updated` —, all ignored, and had          │
    # │ concluded no windowing existed at all. These three shapes remain         │
    # │ ignored here, like at the vendor; only the contract's shape filters.     │
    # │                                                                          │
    # │ `/times` still has NO `updateDate` (see models/entities.py): it is       │
    # │ windowed on the time row's date, not on its modification. A fix to an    │
    # │ old row is only seen by re-reading its period.                           │
    # │                                                                          │
    # │ See docs/comparisons/2026-09-29.md and docs/UNVERIFIED-FIELDS.md.        │
    # └──────────────────────────────────────────────────────────────────────────┘
    CollectionSpec("times", "times", Time, "time", has_detail=False, periods=("inProgress",)),
    CollectionSpec(
        "times-reports",
        "times_reports",
        TimesReport,
        "timesReport",
        required_params=("startMonth", "endMonth"),
    ),
)


def _check_auth(request: Request) -> JSONResponse | None:
    """401 with no credentials, **422** with an invalid JWT — the real shapes.

    The real 422: `"422 - Signature verification failed"` with
    `source: {"parameter": "xJwtClient"}`, and a meta OUTSIDE A SESSION
    (`isLogged: false`, `language: "en"`).
    """
    jwt_token = request.headers.get("X-Jwt-Client-Boondmanager")
    if jwt_token is not None:
        if jwt_is_valid(jwt_token):
            return None
        return error(
            422,
            "422 - Signature verification failed",
            source={"parameter": "xJwtClient"},
            logged_in=False,
        )
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Basic ") and basic_is_valid(authorization[6:]):
        return None
    return error(401, request=request, logged_in=False)


def _dispatch_injections(path: str, params: dict[str, str]) -> JSONResponse | None:
    """The single dispatch point. Returns a response if a failure fires.

    Meaningful order:
      1. auth_reject  — must preempt real authentication;
      2. latency      — applies even when the request ultimately succeeds;
      3. rate_limit   — depends on the counter, hence after observation;
      4. status       — the outright failure.

    This is also where the company's life advances: every request gives time
    evolution the chance to apply events that have become due
    (`engine.now()` incorporates /__admin/clock's virtual clock).
    """
    state.advance_evolution(engine.now())
    index = engine.observe(path, params)

    if (rule := engine.first("auth_reject", path)) is not None and rule.consume():
        return error(rule.status or 401, f"HTTP {rule.status or 401} (GET {path})", logged_in=False)

    if (rule := engine.first("latency", path)) is not None and rule.consume():
        # A real `sleep`: it is the only way to exercise a client-side
        # timeout. The virtual clock serves time windows, not this.
        time.sleep(rule.seconds)

    if (
        (rule := engine.first("rate_limit", path)) is not None
        and index > rule.after_requests
        and rule.consume()
    ):
        # `Retry-After` in seconds, like the real API. A client that ignores
        # it and retries immediately must keep getting 429s.
        return error(
            429,
            "Too many requests",
            headers={"Retry-After": str(rule.retry_after_seconds)},
        )

    if (rule := engine.first("status", path)) is not None and rule.consume():
        return error(rule.status, f"mock: injected {rule.status} on {path}")

    return None


def _collection_items(dataset_key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = state.dataset.get(dataset_key, [])
    return items


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="BoondManager mock", version="0.11.0", docs_url="/docs")
api = APIRouter(prefix="/api")


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Unknown routes and methods: the Boond envelope, not FastAPI's 404.

    Observed real behavior: `/times/{id}` → enveloped 404, `GET /deliveries`
    → enveloped 405 — with a meta OUTSIDE A SESSION (routing precedes auth).
    """
    if exc.status_code in (404, 405):
        return error(exc.status_code, request=request, logged_in=False)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Unauthenticated — it is a probe, not an entity."""
    return {"status": "ok", "service": "boondmanager-mock"}


def _missing_params(spec: CollectionSpec, params: dict[str, str]) -> JSONResponse | None:
    """`times-reports`'s mandatory window — 422 business code 1017.

    Real shape: one error entry PER missing parameter, each with
    `source: {"parameter": ...}` (alphabetical order observed)."""
    missing = sorted(p for p in spec.required_params if p not in params)
    if not missing:
        return None
    return error_response(
        422,
        [
            error_entry(
                422,
                "1017 - Missing required attribute",
                code="1017",
                source={"parameter": name},
            )
            for name in missing
        ],
    )


def _guard_after_auth(
    request: Request, spec: CollectionSpec, params: dict[str, str]
) -> JSONResponse | None:
    """Post-authentication refusals, in the order observed for real:
    restricted perimeter (403), in-process historical outage, mandatory window."""
    if spec.path in settings.forbidden_collections:
        # BOOND_MOCK_FORBIDDEN_COLLECTIONS — the 403 of a `narrowPerimeter` user token.
        return error(403, request=request)
    if spec.dataset_key in state.fail_collections or spec.path in state.fail_collections:
        return error(500, f"mock: simulated outage on /{spec.path}")
    return _missing_params(spec, params)


def _paginated(request: Request, spec: CollectionSpec) -> JSONResponse:
    path_name, dataset_key = spec.path, spec.dataset_key
    params = dict(request.query_params)
    path = f"/api/{path_name}"

    if (injected := _dispatch_injections(path, params)) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if (refused := _guard_after_auth(request, spec, params)) is not None:
        return refused

    items = _collection_items(dataset_key)
    if spec.path == "times-reports":
        # The term window is MANDATORY and effective (YYYY-MM format).
        start, end = params["startMonth"], params["endMonth"]
        items = [i for i in items if start <= i["attributes"].get("term", "") <= end]
    items = apply_keywords(items, params.get("keywords", ""), state.blobs(dataset_key))
    # A `period` value absent from `spec.periods` is accepted and IGNORED, as
    # the vendor does. Do NOT turn this into a 422: the real API rejects
    # nothing, it simply renders everything, and a consumer seeing an error
    # here would be fixing a problem that does not exist.
    items = apply_period(items, params, spec.periods)
    items = apply_incremental(items, extract_since(params))

    total = len(items)
    items = apply_order(items, params, engine.request_counts.get(path, 1), path_name)

    paged = paginate(items, params, path_name)
    if paged is None:
        return error(422, "Wrong or missing attribute: page/maxResults")
    page_slice, page, page_size = paged
    if (drift := apply_page_drift(items, page, page_size, path)) is not None:
        page_slice = drift

    included = (
        build_included(page_slice, state.dataset, dataset_key, state.entity_index())
        if spec.has_included
        else None
    )
    extras = {key: META_EXTRAS[key] for key in spec.meta_extra}
    return JSONResponse(envelope(page_slice, total, included, extras))


# ─────────────────────────────────────────────────────────────────────────────
#  Detail projections — the official *profile* shapes
# ─────────────────────────────────────────────────────────────────────────────


def _contracts_of(resource_id: str) -> list[dict[str, str]]:
    """A resource's contract references — via `dependsOn`, like the API."""
    refs = []
    for contract in state.dataset.get("contracts", []):
        data = (contract.get("relationships") or {}).get("dependsOn", {}).get("data")
        if data and data.get("type") == "resource" and data.get("id") == resource_id:
            refs.append({"id": contract["id"], "type": "contract"})
    return refs


def _seniority(contract_refs: list[dict[str, str]]) -> str:
    ids = {ref["id"] for ref in contract_refs}
    starts = [c["attributes"]["startDate"] for c in state.dataset["contracts"] if c["id"] in ids]
    return min(starts) if starts else ""


def _birth_date(rid: int) -> str:
    """Synthetic DETERMINISTIC civil status — the base dataset does not carry it."""
    return f"{1978 + (rid * 7) % 18}-{1 + (rid % 12):02d}-{1 + (rid * 3) % 28:02d}"


def _resource_profile(item: dict[str, Any]) -> dict[str, Any]:
    """`GET /resources/{id}` — the real PROFILE shape (18 attributes observed),
    distinct from search, with the `contracts` relationship."""
    rid = int(item["id"])
    attrs = item["attributes"]
    rels = item.get("relationships") or {}
    contracts = _contracts_of(item["id"])
    seniority = _seniority(contracts)
    level = "administrator" if rid == 1 else ("manager" if rid <= 6 else "resource")
    return {
        "id": item["id"],
        "type": "resource",
        "attributes": {
            "creationDate": attrs.get("creationDate"),
            "updateDate": attrs.get("updateDate"),
            "civility": attrs.get("civility"),
            "thumbnail": attrs.get("thumbnail", ""),
            "firstName": attrs["firstName"],
            "lastName": attrs["lastName"],
            "typeOf": attrs.get("typeOf"),
            "level": level,
            "title": attrs.get("title"),
            "dateOfBirth": _birth_date(rid),
            "numberOfResumes": attrs.get("numberOfResumes"),
            "seniorityDate": seniority,
            "forceSeniorityDate": False,
            "originalSeniorityDate": seniority,
            "validitySeniorityDate": "",
            "tdLink": f"/api/resources/{item['id']}/technical-data",
            "tdId": item["id"],
            "creationSource": None,
        },
        "relationships": {
            "mainManager": rels.get("mainManager", {"data": None}),
            "hrManager": rels.get("hrManager", {"data": None}),
            "agency": rels.get("agency", {"data": None}),
            "pole": rels.get("pole", {"data": None}),
            "contracts": {"data": contracts},
        },
    }


def _project_profile(item: dict[str, Any]) -> dict[str, Any]:
    """`GET /projects/{id}` — the real PROFILE shape (13 attributes observed)."""
    attrs = item["attributes"]
    rels = item.get("relationships") or {}
    return {
        "id": item["id"],
        "type": "project",
        "attributes": {
            "creationDate": attrs.get("creationDate"),
            "currency": attrs.get("currency"),
            "currencyAgency": attrs.get("currencyAgency"),
            "deliverySuggestFilters": [],
            "exchangeRate": attrs.get("exchangeRate"),
            "exchangeRateAgency": attrs.get("exchangeRateAgency"),
            "isProjectManager": True,
            "mode": attrs.get("mode"),
            "reference": attrs.get("reference"),
            "startDate": attrs.get("startDate"),
            "typeOf": attrs.get("typeOf"),
            "updateDate": attrs.get("updateDate"),
            "workUnitRate": 1,
        },
        "relationships": {
            "agency": rels.get("agency", {"data": None}),
            "company": rels.get("company", {"data": None}),
            "mainManager": rels.get("mainManager", {"data": None}),
            "opportunity": rels.get("opportunity", {"data": None}),
            "pole": rels.get("pole", {"data": None}),
        },
    }


#: Modules whose detail projects a dedicated profile shape; the others serve
#: the search item as-is (documented simplification).
PROFILE_PROJECTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "resources": _resource_profile,
    "projects": _project_profile,
}

#: `included` table dedicated to details that have one (real whitelists).
MODULE_INCLUDED_DETAIL: dict[str, str] = {
    "resources": "resources/profile",
    "projects": "projects/profile",
    "contracts": "contracts/profile",
    "deliveries": "deliveries/profile",
}


def _detail(request: Request, spec: CollectionSpec, item_id: str) -> JSONResponse:
    path_name, dataset_key = spec.path, spec.dataset_key
    params = dict(request.query_params)
    if (injected := _dispatch_injections(f"/api/{path_name}/{item_id}", params)) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if path_name in settings.forbidden_collections:
        return error(403, request=request)
    for item in _collection_items(dataset_key):
        if item["id"] == item_id:
            projection = PROFILE_PROJECTIONS.get(path_name)
            enriched = projection(item) if projection else item
            module = MODULE_INCLUDED_DETAIL.get(path_name, dataset_key)
            included = (
                build_included([enriched], state.dataset, module, state.entity_index())
                if spec.has_included
                else None
            )
            return JSONResponse(envelope_detail(enriched, included))
    # Real generic message: "HTTP 404 (GET /api/resources/999999999)".
    return error(404, request=request)


def _register(spec: CollectionSpec) -> None:
    """Route factory.

    The function exists to bind `spec` AT EACH ITERATION: without it, the
    closure would capture the loop variable and every route would serve the
    last collection.

    `response_model` is declared but the handlers return a `JSONResponse`:
    FastAPI then documents the shape WITHOUT revalidating the output. This is
    deliberate — a mock must be able to serve deliberately abnormal payloads
    (page drift, missing fields) without its own validation getting in the way.
    """

    if spec.list_405:
        # Search does not exist for real (POST only in the RAML): enveloped
        # 405, outside the OpenAPI contract — the route is only there to
        # mimic reality.
        @api.get(f"/{spec.path}", name=f"list_{spec.dataset_key}", include_in_schema=False)
        def _forbidden_list(request: Request) -> JSONResponse:
            return error(405, request=request, logged_in=False)

    else:

        @api.get(
            f"/{spec.path}",
            name=f"list_{spec.dataset_key}",
            response_model=ListEnvelope[spec.model],  # type: ignore[name-defined]
            responses=ERROR_RESPONSES,
            summary=f"Paginated search: {spec.path}",
        )
        def _list(request: Request) -> JSONResponse:
            return _paginated(request, spec)

    if not spec.has_detail:
        return

    @api.get(
        f"/{spec.path}/{{item_id}}",
        name=f"get_{spec.dataset_key}",
        response_model=ItemEnvelope[spec.model],  # type: ignore[name-defined]
        responses=ERROR_RESPONSES,
        summary=f"Profile: {spec.singular}",
    )
    def _get(request: Request, item_id: str) -> JSONResponse:
        return _detail(request, spec, item_id)


for _spec in COLLECTIONS:
    _register(_spec)


@api.get(
    "/resources/{item_id}/administrative",
    response_model=ItemEnvelope[ResourceAdministrative],
    responses=ERROR_RESPONSES,
    summary="Administrative tab — THE official path to contracts",
)
def administrative(request: Request, item_id: str) -> JSONResponse:
    """`GET /resources/{id}/administrative` — official schema, VALIDATED live.

    The documented way to fetch a resource's contracts: the `contracts`
    relationship lists the identifiers, `included` carries their reduced
    shape, and `GET /contracts/{id}` returns the full detail (salaries, costs,
    working time).
    """
    if (
        injected := _dispatch_injections(
            "/api/resources/administrative", dict(request.query_params)
        )
    ) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    resource = next((r for r in _collection_items("resources") if r["id"] == item_id), None)
    if resource is None:
        return error(404, request=request)

    rid = int(item_id)
    attrs = resource["attributes"]
    contracts = _contracts_of(item_id)
    seniority = _seniority(contracts)
    subcontractor = attrs.get("typeOf") == 1

    relations: dict[str, Any] = {
        "agency": (resource.get("relationships") or {}).get("agency", {"data": None}),
        "candidate": {"data": None},
        "contracts": {"data": contracts},
        "files": {"data": []},
    }
    if subcontractor:
        # The real API only emits the provider* keys when they make sense.
        relations["providerCompany"] = {"data": {"id": "11", "type": "company"}}
        relations["providerContact"] = {"data": None}

    item = {
        "id": item_id,
        "type": "resource",
        "attributes": {
            "reference": attrs.get("reference", ""),
            "dateOfBirth": _birth_date(rid),
            "placeOfBirth": "",
            "nationality": "French",
            "healthCareNumber": "",
            "address": "",
            "postcode": "",
            "town": "",
            "country": "France",
            "subDivision": "",
            "situation": 1,
            "administrativeComments": "",
            "function": attrs.get("title", ""),
            "seniorityDate": seniority,
            "originalSeniorityDate": seniority,
            "forceSeniorityDate": False,
            "validitySeniorityDate": "",
        },
        "relationships": relations,
    }
    included = build_included([item], state.dataset, "administrative", state.entity_index())
    return JSONResponse(envelope_detail(item, included))


#: Legal forms and APE codes — PLAUSIBLE values, deterministic per id: only
#: the NAMES of these attributes have been observed (see UNVERIFIED-FIELDS).
_LEGAL_FORMS = ("SAS", "SA", "SARL", "SE")
_APE_CODES = ("6202A", "6420Z", "3514Z", "6512Z", "4941A", "2120Z", "4939B")
_POSTAL_CODES = {
    "Paris": "75008",
    "Lyon": "69003",
    "Nantes": "44000",
    "Lille": "59000",
    "Bordeaux": "33000",
    "Bruxelles": "1000",
}


def _company_ref(company_id: str | None) -> dict[str, str] | None:
    return {"id": company_id, "type": "company"} if company_id else None


@api.get(
    "/companies/{item_id}/information",
    response_model=ItemEnvelope[CompanyInformation],
    responses=ERROR_RESPONSES,
    summary="Information tab — THE only place the company group lives",
)
def company_information(request: Request, item_id: str) -> JSONResponse:
    """`GET /companies/{id}/information` — OBSERVED live 2026-09-13.

    Read-only probe on a production tenant, field NAMES only (no values):

    * **the group lives here and nowhere else** — `GET /companies` and
      `GET /companies/{id}` only carry `agency`, `mainManager`, `pole`. This
      tab adds `createdBy`, `files`, `influencers`, `parentCompany` and
      `subsidiaries` (eight relationships in all).
    * **`parentCompany`** is `data: null` or `{id, type: "company"}` — set on
      about 6 of 20 sampled companies.
    * **`subsidiaries`** is a LIST of `{id, type: "company"}`, empty when the
      company has none. Both directions are CONSISTENT: one group listed 16
      subsidiaries, each pointing back to it. The mock derives `subsidiaries`
      from `parentCompany` so the property holds by construction.
    * **27 attributes**; `included` carries types `agency`, `company`,
      `resource`. Attribute types beyond those of the search are NOT observed
      (`x-boond-confidence: unverified`).
    """
    if (
        injected := _dispatch_injections("/api/companies/information", dict(request.query_params))
    ) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if "information" in state.fail_collections:
        return error(500, "mock: simulated outage on /companies/{id}/information")
    company = next((s for s in _collection_items("companies") if s["id"] == item_id), None)
    if company is None:
        return error(404, request=request)

    cid = int(item_id)
    attrs = company["attributes"]
    rels = company.get("relationships") or {}
    parents: dict[str, str] = state.dataset.get("company_parents", {})
    subsidiaries = sorted((f for f, m in parents.items() if m == item_id), key=int)

    item = {
        "id": item_id,
        "type": "company",
        "attributes": {
            "address": f"{1 + (cid * 17) % 120} avenue des Entreprises",
            "apeCode": _APE_CODES[cid % len(_APE_CODES)],
            "billingDetails": [],
            "country": attrs.get("country"),
            "creationDate": attrs.get("creationDate"),
            "creationSource": None,
            "departments": [],
            "expertiseArea": attrs.get("expertiseArea"),
            "fax": "",
            "informationComments": attrs.get("informationComments", ""),
            "legalStatus": _LEGAL_FORMS[cid % len(_LEGAL_FORMS)],
            "name": attrs["name"],
            "number": f"CLI-{cid:05d}",
            "origin": {"typeOf": 0, "detail": ""},
            "phone1": attrs.get("phone1"),
            "postcode": _POSTAL_CODES.get(attrs.get("town", ""), ""),
            "registeredOffice": True,
            "registrationNumber": f"{400000000 + cid * 7919:09d}",
            "socialNetworks": attrs.get("socialNetworks", []),
            "staff": 50 * (1 + (cid * 13) % 40),
            "state": attrs.get("state"),
            "subDivision": "",
            "thumbnail": attrs.get("thumbnail", ""),
            "town": attrs.get("town"),
            "updateDate": attrs.get("updateDate"),
            "vatNumber": f"FR{(cid * 37) % 100:02d}{400000000 + cid * 7919:09d}",
            "website": attrs.get("website"),
        },
        "relationships": {
            "agency": rels.get("agency", {"data": None}),
            "createdBy": rels.get("mainManager", {"data": None}),
            "files": {"data": []},
            "influencers": {"data": []},
            "mainManager": rels.get("mainManager", {"data": None}),
            "parentCompany": {"data": _company_ref(parents.get(item_id))},
            "pole": rels.get("pole", {"data": None}),
            "subsidiaries": {"data": [_company_ref(f) for f in subsidiaries]},
        },
    }
    included = build_included([item], state.dataset, "companies/information", state.entity_index())
    return JSONResponse(envelope_detail(item, included))


@api.get(
    "/resources/{item_id}/advantages",
    response_model=ListEnvelope[Advantage],
    responses=ERROR_RESPONSES,
    summary="Avantages versés — where variable pay actually lives",
)
def advantages(request: Request, item_id: str) -> JSONResponse:
    """`GET /resources/{id}/advantages` — OBSERVED live 2026-09-10.

    The « Avantages versés » tab: one row per payment, dated, with its type,
    quantity and cost. Probed on a production tenant: 200 OK, `meta.totals.rows`
    = 54 on one resource, history running 2020 → 2026, carrying « Prime sur
    lettre d'Objectifs », « Prime exceptionnelle » and « Prime de vacances ».

    Four measured properties this route reproduces, because each one changes
    what a consumer must do:

    * **no `updateDate`** — no cursor exists, so no incremental path. Serving
      one would invite an extraction that fetches nothing in production.
    * **no bulk collection** — `/advantages` answers 403 (WAF),
      `/resources-advantages` and `/contracts-advantages` 404. One call per
      resource, and that cost is structural.
    * **sparse** — six of eight resources probed had none at all. An empty
      `data` with `totals.rows: 0` is the NORMAL answer here.
    * **`contract` relationship** — a payment belongs to the contract in force
      on its date, not to the current one. One person had eight successive
      contracts and 54 payments spread across them.
    """
    if (
        injected := _dispatch_injections("/api/resources/advantages", dict(request.query_params))
    ) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if "advantages" in state.fail_collections:
        return error(500, "mock: simulated outage on /resources/{id}/advantages")
    if not any(r["id"] == item_id for r in _collection_items("resources")):
        return error(404, request=request)

    own = [
        a
        for a in state.dataset["advantages"]
        if a["relationships"]["contract"]["data"] is not None
        and a["relationships"]["contract"]["data"]["id"]
        in {c["id"] for c in _contracts_of(item_id)}
    ]
    # Stable sort: without it, two identical calls can render different
    # pages, and a consumer that paginates skips rows.
    own.sort(key=lambda a: (a["attributes"]["date"], int(a["id"])))

    page = paginate(own, dict(request.query_params))
    if page is None:
        return error(422, request=request)
    page_slice, _page_number, _page_size = page
    return JSONResponse(envelope(page_slice, len(own)))


@api.get(
    "/resources/{item_id}/technical-data",
    response_model=ItemEnvelope[TechnicalData],
    responses=ERROR_RESPONSES,
    summary="Résumé tab — the real profile shape (type `resource`)",
)
def technical_data(request: Request, item_id: str) -> JSONResponse:
    """The résumé tab — observed live: type `resource`, fifteen attributes, no
    relationships nor included. Detailed references live here."""
    if (
        injected := _dispatch_injections(
            "/api/resources/technical-data", dict(request.query_params)
        )
    ) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if "technical-data" in state.fail_collections:
        return error(500, "mock: simulated outage on /resources/{id}/technical-data")
    resource = next((r for r in _collection_items("resources") if r["id"] == item_id), None)
    record = state.dataset["technical_data"].get(item_id)
    if resource is None or record is None:
        return error(404, request=request)
    attrs = resource["attributes"]
    item = {
        "id": item_id,
        "type": "resource",
        "attributes": {
            "activityAreas": attrs.get("activityAreas", []),
            "description": record["attributes"].get("description", ""),
            "diplomas": attrs.get("diplomas", []),
            "experience": attrs.get("experience"),
            "expertiseAreas": attrs.get("expertiseAreas", []),
            "languages": attrs.get("languages", []),
            "references": record["attributes"].get("references", []),
            "resourceCanModifyTechnicalData": True,
            "skills": attrs.get("skills", ""),
            "summary": record["attributes"].get("summary", ""),
            "tdId": item_id,
            "tdLink": f"/api/resources/{item_id}/technical-data",
            "title": attrs.get("title", ""),
            "tools": attrs.get("tools", []),
            "training": [],
        },
    }
    return JSONResponse(envelope_detail(item))


@api.get(
    "/application/dictionary",
    response_model=DictionaryEnvelope,
    responses=ERROR_RESPONSES,
    summary="Enumeration dictionary — instance-configured labels",
)
def application_dictionary(request: Request) -> JSONResponse:
    """The INSTANCE-CONFIGURED enumeration labels.

    Single object, no pagination nor `meta`. Everywhere else the API renders
    bare integers: this route is the only known source for the code-to-label
    mapping, and labels are not product constants — two instances may code
    the same notion differently.
    """
    # Three gestures carried over from the existing pattern, and none is
    # optional: `_dispatch_injections` — without it this endpoint would
    # escape the control plane and injectable failure modes; `_check_auth`
    # BEFORE any data; and reading from `state.dataset` rather than a
    # constant, which is what keeps the dataset as the single source of truth.
    injected = _dispatch_injections("/api/application/dictionary", dict(request.query_params))
    if injected is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    return JSONResponse({"data": {"setting": state.dataset["dictionary"]}})


@api.get(
    "/application/current-user",
    response_model=ItemEnvelope[CurrentUser],
    responses=ERROR_RESPONSES,
    summary="Identity check — credentials smoke test",
)
def current_user(request: Request) -> JSONResponse:
    """`GET /application/current-user` — real type `currentuser` (observed),
    with the attribute subset consumers rely on."""
    if (denied := _check_auth(request)) is not None:
        return denied
    return JSONResponse(
        envelope_detail(
            {
                "id": "1",
                "type": "currentuser",
                "attributes": {
                    "firstName": "Demo",
                    "lastName": "Boréal",
                    "login": settings.basic_user,
                    "email1": settings.basic_user,
                    "level": "manager",
                    "isOwner": True,
                    "narrowPerimeter": False,
                    "language": "fr",
                },
                "relationships": {
                    "agency": {"data": {"id": "1", "type": "agency"}},
                    "role": {"data": {"id": "1", "type": "role"}},
                },
            }
        )
    )


app.include_router(api)

# The control plane is not "mounted then forbidden": when it is disabled, the
# surface does not exist.
if settings.admin_enabled:
    from .admin import router as admin_router

    app.include_router(admin_router)


# ─────────────────────────────────────────────────────────────────────────────
#  Compensation — DELIBERATELY OUTSIDE OF /api
# ─────────────────────────────────────────────────────────────────────────────
#
# Served as a FILE, outside of `/api`, so nobody mistakes it for a vendor
# endpoint. Since the alignment on the official schemas, the amounts are
# DERIVED from `/api/contracts/{id}` (the attested `monthlySalary` field) —
# the CSV is now only a convenience view.


# `response_model=None`: the return type is a union of two Response classes,
# which FastAPI would otherwise try to interpret as a Pydantic model.
@app.get("/__fixtures/remuneration.csv", response_class=PlainTextResponse, response_model=None)
def remuneration_csv(request: Request) -> PlainTextResponse | JSONResponse:
    if settings.compensation_mode == "absent":
        return error(404, "compensation fixture disabled (BOOND_MOCK_COMPENSATION_MODE=absent)")
    if (denied := _check_auth(request)) is not None:
        return denied
    lines = ["collaborateur_id,upn,entite,periode,montant_brut_annuel"]
    for row in state.dataset.get("remuneration", []):
        lines.append(
            f"{row['collaborateur_id']},{row['upn']},{row['entite']},"
            f"{row['periode']},{row['montant_brut_annuel']}"
        )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
#  The contract
# ─────────────────────────────────────────────────────────────────────────────


def contract_openapi() -> dict[str, Any]:
    """The OpenAPI contract — the BoondManager DIALECT, and nothing else.

    The `/__admin` (failure control plane) and `/__fixtures` (compensation,
    served outside /api) paths are REMOVED. Two reasons:

      • these are mock affordances, not the vendor's. Publishing them in the
        contract would pass off what is not BoondManager as BoondManager —
        and a consumer could come to rely on it;

      • `/__admin` is only mounted if `BOOND_MOCK_ADMIN_ENABLED` is true. The
        contract would then depend on the generation environment, and the
        anti-drift test would fail depending on how it was launched.

    They stay documented — in the README — but outside the contract.
    """
    spec = app.openapi()
    spec["paths"] = {
        path: op
        for path, op in spec["paths"].items()
        if not path.startswith(("/__admin", "/__fixtures"))
    }
    _prune_orphan_schemas(spec)
    return spec


def _prune_orphan_schemas(spec: dict[str, Any]) -> None:
    """Removes schemas no path references any more.

    Removing paths leaves their schemas behind. The symptom is confusing: the
    contract contains `HTTPValidationError` and `ValidationError` ONLY when
    `/__admin` was mounted at generation time — so the committed file differs
    depending on an environment variable's value, and the anti-drift test
    fails without anything meaningful having changed.

    `$ref`s are resolved transitively: a kept schema may reference another.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    if not schemas:
        return

    def refs(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    found.add(value.rsplit("/", 1)[-1])
                else:
                    found |= refs(value)
        elif isinstance(node, list):
            for element in node:
                found |= refs(element)
        return found

    kept = refs(spec["paths"])
    # Transitive closure: a kept schema may reference others.
    to_explore = set(kept)
    while to_explore:
        name = to_explore.pop()
        for next_name in refs(schemas.get(name, {})):
            if next_name not in kept:
                kept.add(next_name)
                to_explore.add(next_name)

    spec["components"]["schemas"] = {n: c for n, c in schemas.items() if n in kept}
