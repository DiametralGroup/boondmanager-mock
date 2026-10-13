"""Building the `included` array — reduced shapes PER MODULE.

The real API accompanies `data` with an `included` array: for every `{id,
type}` relation, the target entity appears there in a REDUCED shape — and
this shape varies by the responding MODULE. RAML survey confirmed by the real
probes of 2026-07-31: the `company` included by /contacts carries
`{name, expertiseArea, thumbnail, state}`, the one from /invoices
`{name, thumbnail}`; /invoices' `agency` adds `invoicesLockingStates`; the
`project` included by /invoices carries SEVEN relationships.

Each module therefore has its own `{type → (kept attributes, kept
relationships)}` table; a type absent from a module's table is NOT included
(strict whitelist, like the official schemas). Closure is transitive over kept
relationships, deduplicated by (type, id).
"""

from __future__ import annotations

from typing import Any

#: JSON:API type → collection key in the dataset.
TYPE_TO_KEY: dict[str, str] = {
    "absence": "absences",
    "action": "actions",
    "agency": "agencies",
    "bankingaccount": "banking_accounts",
    "bankingconnection": "banking_connections",
    "bankingtransaction": "banking_transactions",
    "businessunit": "business_units",
    "candidate": "candidates",
    "company": "companies",
    "contact": "contacts",
    "contract": "contracts",
    "delivery": "deliveries",
    "expense": "expenses",
    "invoice": "invoices",
    "opportunity": "opportunities",
    "order": "orders",
    "payment": "payments",
    "pole": "poles",
    "project": "projects",
    "purchase": "purchases",
    "resource": "resources",
    "role": "roles",
    "time": "times",
    "timesreport": "times_reports",
}

Shape = tuple[tuple[str, ...], tuple[str, ...]]

_PERSON: Shape = (("firstName", "lastName"), ())
_RICH_PERSON: Shape = (("firstName", "lastName", "email1", "phone1", "phone2", "thumbnail"), ())
_NAME: Shape = (("name",), ())
_ACTION: Shape = (("startDate", "typeOf", "text"), ())
#: ┌─ THE CONTRACT IN `included` IS NOT REDUCED ───────────────────────────────┐
#: │ It used to carry only three attributes, on the idea — written in the     │
#: │ route's docstring — that `included` delivers a "reduced shape" and that  │
#: │ the detail lives on `GET /contracts/{id}`.                               │
#: │                                                                           │
#: │ Probed 2026-08-13 against production: `/resources/{id}/administrative`   │
#: │ renders the contract's SIXTEEN attributes in `included`, `monthlySalary` │
#: │ included and filled. The reduced shape was a mock invention.             │
#: │                                                                           │
#: │ What it cost: `GET /contracts` answers 405 at the vendor, so `included`  │
#: │ is the ONLY practicable path to compensation. A consumer relying on it   │
#: │ would have found nothing in CI, and would have concluded — as            │
#: │ SPEC-DEVIATIONS #5 did — that no compensation endpoint exists at         │
#: │ BoondManager.                                                            │
#: │                                                                           │
#: │ ⚠️ These fields are HR data. The mock serves them because the vendor      │
#: │    serves them; it is up to the CONSUMER to minimize at extraction time, │
#: │    and insights360 does so via a whitelist.                              │
#: └───────────────────────────────────────────────────────────────────────────┘
_CONTRACT: Shape = (
    (
        "typeOf",
        "startDate",
        "endDate",
        "monthlySalary",
        "employeeType",
        "activityRate",
        "classification",
        "calendar",
        "currency",
        "currencyAgency",
        "exchangeRate",
        "exchangeRateAgency",
        "contractAverageDailyCost",
        "contractAverageDailyProductionCost",
        "advantageTypes",
        "informationComments",
    ),
    ("agency",),
)

#: module (dataset key, or `<key>/profile` for details) → {type → shape}.
#: Values observed in the official search/profile schemas' `included` blocks —
#: see docs/UNVERIFIED-FIELDS.md for provenance.
SHAPES_BY_MODULE: dict[str, dict[str, Shape]] = {
    "actions": {
        "candidate": _RICH_PERSON,
        "resource": _PERSON,
        "company": (("name", "phone1", "thumbnail"), ()),
        "contact": (
            ("firstName", "lastName", "email1", "phone1", "phone2", "thumbnail"),
            ("company",),
        ),
        "document": _NAME,
        "invoice": (("reference",), ("order",)),
        "opportunity": (("reference", "title"), ("contact", "company")),
        "order": (("reference", "number"), ("project",)),
        "project": (("reference",), ("contact", "company")),
    },
    "banking_transactions": {
        "bankingaccount": (("name", "title"), ("connection",)),
        "bankingconnection": (("bankName",), ()),
    },
    "business_units": {"resource": _PERSON},
    "candidates": {"action": _ACTION, "agency": _NAME, "pole": _NAME, "resource": _PERSON},
    "companies": {"action": _ACTION, "agency": _NAME, "pole": _NAME, "resource": _PERSON},
    "contacts": {
        "action": _ACTION,
        "agency": _NAME,
        "company": (("name", "expertiseArea", "thumbnail", "state"), ()),
        "pole": _NAME,
        "resource": _PERSON,
    },
    "invoices": {
        "agency": (("name", "invoicesLockingStates"), ()),
        "company": (("name", "thumbnail"), ()),
        "contact": _PERSON,
        "opportunity": (("title",), ()),
        "order": (("number", "reference"), ("mainManager", "project")),
        "pole": _NAME,
        "project": (
            ("reference", "typeOf", "mode"),
            (
                "opportunity",
                "contact",
                "company",
                "agency",
                "pole",
                "intermediaryContact",
                "intermediaryCompany",
            ),
        ),
        "resource": _PERSON,
        "schedule": (("date", "title"), ()),
    },
    "opportunities": {
        "agency": _NAME,
        "company": (("name", "thumbnail", "canReadCompany"), ()),
        "contact": (("firstName", "lastName", "thumbnail", "canReadContact"), ()),
        "pole": _NAME,
        "resource": _PERSON,
    },
    "orders": {
        "agency": _NAME,
        "company": (("name", "thumbnail"), ()),
        "contact": _PERSON,
        "opportunity": (("title",), ()),
        "pole": _NAME,
        "project": (
            (
                "reference",
                "typeOf",
                "mode",
                "currency",
                "exchangeRate",
                "currencyAgency",
                "exchangeRateAgency",
            ),
            (
                "opportunity",
                "contact",
                "company",
                "intermediaryContact",
                "intermediaryCompany",
                "agency",
                "pole",
            ),
        ),
        "resource": _PERSON,
    },
    "payments": {
        "agency": _NAME,
        "company": _NAME,
        "contact": _PERSON,
        "delivery": (("title",), ("dependsOn",)),
        "pole": _NAME,
        "project": (("reference",), ()),
        "purchase": (
            (
                "title",
                "subscription",
                "typeOf",
                "reference",
                "currency",
                "exchangeRate",
                "currencyAgency",
                "exchangeRateAgency",
            ),
            ("mainManager", "project", "delivery", "contact", "company", "agency", "pole"),
        ),
        "resource": _PERSON,
    },
    "projects": {
        "agency": _NAME,
        "company": (("name", "thumbnail", "canReadCompany"), ()),
        "contact": (("firstName", "lastName", "canReadContact"), ()),
        "opportunity": (("title",), ()),
        "pole": _NAME,
        "resource": _PERSON,
    },
    "purchases": {
        "agency": _NAME,
        "company": _NAME,
        "contact": _PERSON,
        "delivery": (("title",), ("dependsOn",)),
        "pole": _NAME,
        "project": (("reference",), ()),
        "resource": _PERSON,
    },
    "resources": {"action": _ACTION, "agency": _NAME, "pole": _NAME, "resource": _PERSON},
    "times": {
        "agency": (("name", "workUnitRate"), ()),
        "batch": (("title",), ()),
        "company": _NAME,
        "delivery": (("title",), ()),
        "project": (("reference",), ("company",)),
        "resource": (("firstName", "lastName", "workUnitRate"), ()),
        "timesreport": (("term", "state", "workUnitRate"), ("agency", "resource")),
    },
    "times_reports": {"agency": _NAME, "resource": _PERSON},
    # ── Details (profiles) — whitelists observed/RAML ────────────────────────
    "resources/profile": {"agency": _NAME, "contract": _CONTRACT},
    "projects/profile": {
        "agency": _NAME,
        "company": (("name", "thumbnail", "canReadCompany"), ()),
        "opportunity": (("title",), ()),
    },
    "contracts/profile": {
        "agency": _NAME,
        "contract": (("typeOf", "startDate", "endDate"), ()),
        "document": _NAME,
        "resource": _PERSON,
    },
    "deliveries/profile": {
        "agency": _NAME,
        "company": _NAME,
        "contact": _PERSON,
        "contract": (("typeOf", "startDate", "endDate"), ()),
        "delivery": (("title",), ()),
        "document": _NAME,
        "opportunity": (("title",), ()),
        "project": (("reference",), ("company",)),
        "purchase": (("title",), ()),
        "resource": _PERSON,
    },
    "administrative": {
        "agency": _NAME,
        "candidate": _PERSON,
        "contract": _CONTRACT,
    },
    # `GET /companies/{id}/information` — TYPES observed for real on
    # 2026-09-13 (`agency`, `company`, `resource`); each type's reduced
    # attributes have NOT been — the minimal shapes from the other modules are
    # reused.
    "companies/information": {
        "agency": _NAME,
        "company": _NAME,
        "resource": _PERSON,
    },
}

#: Fallback for modules without a dedicated table (secondary modules' details).
DEFAULT_SHAPES: dict[str, Shape] = {
    "resource": _PERSON,
    "agency": _NAME,
    "pole": _NAME,
    "businessunit": _NAME,
    "company": _NAME,
    "contact": _PERSON,
    "candidate": _PERSON,
    "action": _ACTION,
    "opportunity": (("title",), ()),
    "project": (("reference", "typeOf", "mode"), ("company",)),
    "order": (("number", "reference"), ("project",)),
    "invoice": (("reference",), ("order",)),
    "purchase": (("title", "subscription", "typeOf", "reference"), ("project", "company")),
    "delivery": (("title",), ("dependsOn",)),
    "timesreport": (("term", "state"), ("agency", "resource")),
    "contract": _CONTRACT,
    "bankingaccount": (("name", "title"), ("connection",)),
    "bankingconnection": (("bankName",), ()),
}


def _index(dataset: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """(type, id) → entity, across every collection in the dataset."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for key in TYPE_TO_KEY.values():
        elements = dataset.get(key)
        if isinstance(elements, list):
            for element in elements:
                index[(element["type"], element["id"])] = element
    return index


def _refs_of(item: dict[str, Any], kept: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """The {id, type} references of an item's relationships (to-one and to-many)."""
    refs: list[dict[str, Any]] = []
    for name, relation in (item.get("relationships") or {}).items():
        if kept is not None and name not in kept:
            continue
        data = relation.get("data")
        for ref in data if isinstance(data, list) else ([data] if data else []):
            refs.append(ref)
    return refs


#: Attributes that only exist in the reduced shapes (base items do not carry
#: them) — plausible values, keys observed for real.
MISSING_VALUES: dict[tuple[str, str], Any] = {
    ("agency", "invoicesLockingStates"): [],
    ("company", "canReadCompany"): True,
    ("contact", "canReadContact"): True,
    ("timesreport", "workUnitRate"): 1,
}


def _reduce(entity: dict[str, Any], shape: Shape) -> dict[str, Any]:
    """Projects an entity onto its `included` reduced shape."""
    kept_attrs, kept_rels = shape
    attributes = entity.get("attributes", {})
    projected: dict[str, Any] = {}
    for attr in kept_attrs:
        if attr in attributes:
            projected[attr] = attributes[attr]
        elif (entity["type"], attr) in MISSING_VALUES:
            projected[attr] = MISSING_VALUES[(entity["type"], attr)]
    reduced: dict[str, Any] = {
        "id": entity["id"],
        "type": entity["type"],
        "attributes": projected,
    }
    if kept_rels:
        relations = {
            name: rel
            for name, rel in (entity.get("relationships") or {}).items()
            if name in kept_rels
        }
        if relations:
            reduced["relationships"] = relations
    return reduced


def build_included(
    items: list[dict[str, Any]],
    dataset: dict[str, Any],
    module: str | None = None,
    index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The `included` array of a page (or a detail), per the module's table.

    Strict whitelist: a type absent from the module's table does not enter
    `included` — that is the official schemas' behavior. Transitive closure
    over kept relationships, stable sort by (type, id).
    """
    shapes = SHAPES_BY_MODULE.get(module or "", DEFAULT_SHAPES)
    if index is None:
        index = _index(dataset)
    included: dict[tuple[str, str], dict[str, Any]] = {}
    to_process = [ref for item in items for ref in _refs_of(item)]

    while to_process:
        ref = to_process.pop()
        key = (ref["type"], ref["id"])
        if key in included or ref["type"] not in shapes:
            continue
        entity = index.get(key)
        if entity is None:
            continue
        shape = shapes[ref["type"]]
        included[key] = _reduce(entity, shape)
        if shape[1]:
            to_process.extend(_refs_of(entity, shape[1]))

    def _sort_key(entity: dict[str, Any]) -> tuple[str, int, str]:
        try:
            return (entity["type"], int(entity["id"]), "")
        except ValueError:
            return (entity["type"], 0, entity["id"])

    return sorted(included.values(), key=_sort_key)
