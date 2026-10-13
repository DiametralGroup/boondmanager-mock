"""Pydantic models — the SOURCE of the OpenAPI contract.

┌─ WHY TYPE, AND WHAT IT COSTS ────────────────────────────────────────────────┐
│ Before, every handler was `(request: Request) -> JSONResponse`. FastAPI      │
│ therefore generated a `/docs` that documented PATHS and nothing else: no      │
│ response shape, no fields. An empty contract is not a contract.              │
│                                                                                │
│ Typing gets us, in one move: the contract, response validation (the          │
│ generator can no longer silently drift from the declared shape), and types   │
│ consumers can actually use.                                                   │
│                                                                                │
│ The cost is real and worth naming: **typing pushes toward inventing          │
│ fields**, which insights360's spec forbids in so many words. The guard is    │
│ structural, not a matter of discipline:                                      │
│                                                                                │
│   • `extra="allow"` everywhere — a field unknown to the real API passes      │
│     through, it is simply undocumented. The model describes what we KNOW,    │
│     not what IS.                                                             │
│   • `x-boond-confidence` on every field not backed by production evidence.   │
│   • a test fails if an `unverified` field is not registered in               │
│     docs/UNVERIFIED-FIELDS.md. Honesty becomes a build constraint.           │
└────────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


def unverified(description: str) -> dict[str, Any]:
    """Marks a field whose name or shape is NOT attested.

    Used via `json_schema_extra`. Every field so marked MUST appear in
    `docs/UNVERIFIED-FIELDS.md` — `tests/test_contract_is_current.py` checks
    it, so the inventory cannot quietly degrade into a good intention.
    """
    return {"x-boond-confidence": "unverified", "x-boond-note": description}


def invented(description: str) -> dict[str, Any]:
    """Marks a field or endpoint that does NOT exist at the vendor.

    Distinct from `unverified`: here we know the shape was fabricated, for
    lack of an attested endpoint. The compensation `stub` mode is its only use.
    """
    return {"x-boond-confidence": "invented", "x-boond-note": description}


class Permissive(BaseModel):
    """Common base: unknown fields are accepted rather than rejected.

    A strict model would turn every evolution of the real API into a mock
    outage. The models describe what is emitted, not everything BoondManager
    may expose.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ── JSON:API envelope ────────────────────────────────────────────────────────


class DataRef(Permissive):
    """The `{id, type}` reference of a JSON:API relationship."""

    id: str
    type: str


class Relation(Permissive):
    """A relationship. `data` may be null — an employee without a manager, say."""

    data: DataRef | None = None


class Totals(Permissive):
    rows: int = Field(description="Total number of items BEFORE pagination.")


class Meta(Permissive):
    """The list `meta`, as the official schema describes it: `totals.rows`
    plus the server version, session state and language."""

    totals: Totals
    version: str | None = Field(default=None, description="BoondManager version.")
    isLogged: bool | None = None
    language: str | None = Field(default=None, description="fr | en | es")


class MetaDetail(Permissive):
    """The profile `meta` — same as the list one, without `totals`."""

    version: str | None = None
    isLogged: bool | None = None
    language: str | None = None


class ListEnvelope[T](BaseModel):
    """`{"data": [...], "included": [...], "meta": {...}}` — the list envelope.

    `meta.totals.rows` counts BEFORE pagination: it is what lets a client know
    when to stop. A client stopping on "empty page" would issue one request
    too many on every run.

    `included` carries related entities in reduced shape (agency → `name`,
    resource → `firstName`/`lastName`…), like the real API. Absent from
    modules whose official schema does not declare it (absences, expenses,
    agencies, poles, roles).
    """

    model_config = ConfigDict(extra="allow")

    data: list[T]
    included: list[dict[str, Any]] | None = Field(
        default=None, description="Related entities, reduced per-module shape."
    )
    meta: Meta


class ItemEnvelope[T](BaseModel):
    """`{"data": {...}, "included": [...], "meta": {...}}` — the profile envelope."""

    model_config = ConfigDict(extra="allow")

    data: T
    included: list[dict[str, Any]] | None = None
    meta: MetaDetail | None = None


# ── Errors ───────────────────────────────────────────────────────────────────


class Error(Permissive):
    """One error entry — the real dialect: `status`/`code`/`detail` plus
    either `title` or `source.parameter`."""

    code: str = Field(description="HTTP or business code, as a string — like the real API.")
    detail: str


class ErrorEnvelope(BaseModel):
    """`{"meta": {...}, "errors": [{status, code, detail, title|source}]}`.

    The real API keeps `meta` even on errors (with `isLogged:false` outside a
    session). Consumers typically read `errors[0].detail || errors[0].title`.
    """

    model_config = ConfigDict(extra="allow")

    errors: list[Error]


# Error responses declared on every route: they appear in the contract
# without going through `response_model`, which only describes the nominal
# case.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope, "description": "No credentials provided."},
    404: {"model": ErrorEnvelope, "description": "Unknown entity."},
    422: {
        "model": ErrorEnvelope,
        "description": (
            "Token present but invalid, missing required parameter (business "
            "code 1017), or unreadable pagination parameter. **422, not 401** — "
            "that is what the real API does, and the status code is what retry "
            "logic keys on."
        ),
    },
    429: {
        "model": ErrorEnvelope,
        "description": "Rate limit reached. `Retry-After` header in seconds.",
    },
    500: {"model": ErrorEnvelope, "description": "Injected failure."},
    503: {"model": ErrorEnvelope, "description": "Injected transient failure."},
}

# Query parameters shared by every collection.
ParamPage = Annotated[int, Field(ge=1, description="Page number, 1-based.")]
ParamMaxResults = Annotated[
    int,
    Field(
        ge=1,
        le=500,
        description=(
            "Page size. Default 30, max 500 (100 on /actions); "
            "above the max the API falls back to 30."
        ),
    ),
]


# ── The enumeration dictionary ───────────────────────────────────────────────


class DictionaryEntry(Permissive):
    """A code -> label mapping, as the INSTANCE configures it.

    This is the only known source for that mapping: everywhere else the API
    renders bare integers, and the labels are not product constants.
    """

    id: int = Field(description="The numeric code the API renders on other routes.")
    value: str = Field(description="The configured label, as shown in the tool.")


class DictionarySetting(Permissive):
    """The nomenclatures, grouped by family.

    `state` is a DICT of sub-domains (opportunity, candidate, resource); the
    other families are flat lists. Both shapes coexist at the vendor —
    uniformizing them here would make the mock diverge from the real dialect.

    `action` and `actionOnOpportunity` are two DISTINCT nomenclatures that
    share labels under different codes. Merging them would translate a need's
    action type with a general label.
    """

    state: dict[str, list[DictionaryEntry]] = Field(
        json_schema_extra=invented(
            "Dictionary sub-domains. The ROUTE is not attested by any "
            "comparison report; the shape is of our own making."
        )
    )
    action: list[DictionaryEntry]
    actionOnCandidate: list[DictionaryEntry] = Field(
        json_schema_extra=invented(
            "Key INFERRED from the convention of `action` and "
            "`actionOnOpportunity`. What is attested: an action nomenclature "
            "on candidates exists in the instance (the Dashb sheet of the "
            "mappings file)."
        )
    )
    actionOnOpportunity: list[DictionaryEntry]
    origin: list[DictionaryEntry]
    typeOf: dict[str, list[DictionaryEntry]] = Field(
        default_factory=dict,
        json_schema_extra=invented(
            "Symmetric to `state`. What is attested: the API renders an "
            "integer `typeOf` on resource, candidate, opportunity, project "
            "and purchase, and gives its label nowhere else. The SHAPE is of "
            "our own making, like `state`'s."
        ),
    )


class DictionaryData(Permissive):
    setting: DictionarySetting


class DictionaryEnvelope(Permissive):
    """`{"data": {"setting": {...}}}` — a single object, no pagination nor `meta`."""

    data: DictionaryData
