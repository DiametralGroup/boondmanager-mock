"""Does the committed contract tell the truth?

Two properties, and the second is the one that really matters.

**The contract does not drift.** `contracts/boondmanager.openapi.yaml` is
generated from the application, but it is COMMITTED — it is the only setup
where the file is both readable in a PR diff and guaranteed exact. Generated
at build time, it would be exact and invisible; written by hand, it would be
visible and wrong.

**The honesty inventory is complete.** insights360's spec is explicit: "Do
not invent BoondManager API fields. Mark unknowns TODO in the contract and
raise them rather than guessing." Marking is not enough — a marker nobody
checks is just a comment. This test requires that EVERY
`x-boond-confidence: unverified` field appear in docs/UNVERIFIED-FIELDS.md.

Honesty thus becomes a build constraint, not a good intention.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

import boondmanager_mock as mock

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "boondmanager.openapi.yaml"
REGISTRY = ROOT / "docs" / "UNVERIFIED-FIELDS.md"


def _marked_fields(schemas: dict[str, Any], marker: str) -> dict[str, str]:
    """Returns {field_name: note} for every field carrying this confidence level."""
    found: dict[str, str] = {}
    for schema in schemas.values():
        for name, prop in (schema.get("properties") or {}).items():
            if prop.get("x-boond-confidence") == marker:
                found[name] = prop.get("x-boond-note", "")
    return found


@pytest.fixture(scope="module")
def generated() -> dict[str, Any]:
    # `contract_openapi()` and not `app.openapi()`: the contract describes the
    # BoondManager dialect. Comparing against the raw application would fail
    # depending on whether BOOND_MOCK_ADMIN_ENABLED is true at run time — the
    # test would depend on the environment instead of testing the contract.
    return mock.contract_openapi()


def test_the_committed_contract_is_current(generated: dict[str, Any]) -> None:
    """The committed file == what the application produces."""
    assert CONTRACT.exists(), f"{CONTRACT} missing — run `make contract`"
    committed = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert committed == generated, (
        "The committed contract has drifted from the application. Run "
        "`make contract`, READ the diff — a changed response shape is a "
        "contract change for consumers — then commit."
    )


def test_the_contract_carries_real_shapes(generated: dict[str, Any]) -> None:
    """A contract without schemas is not a contract.

    That was the starting state: `(Request) -> JSONResponse` handlers, hence
    a `/docs` that listed paths and nothing else. This test prevents an
    inadvertent regression — by adding an untyped route, for instance.
    """
    schemas = generated.get("components", {}).get("schemas", {})
    assert len(schemas) > 40, f"only {len(schemas)} schemas — are the routes typed?"

    for path in (
        "/api/resources",
        "/api/invoices",
        "/api/times",
        "/api/absences",
        "/api/banking-transactions",
    ):
        content = generated["paths"][path]["get"]["responses"]["200"]["content"]
        schema = content["application/json"]["schema"]
        assert "$ref" in schema or "allOf" in schema, (
            f"{path} does not declare a usable response shape: {schema}"
        )


def test_the_contract_does_not_publish_mock_affordances(generated: dict[str, Any]) -> None:
    """Neither `/__admin` nor `/__fixtures` is BoondManager.

    Publishing them would pass off what is not the vendor's as the vendor's,
    and a consumer could come to rely on it — the failure control plane, in
    particular, does not exist in production.
    """
    intruders = [c for c in generated["paths"] if c.startswith(("/__admin", "/__fixtures"))]
    assert not intruders, (
        f"the contract publishes mock affordances: {intruders}. "
        "They are documented in the README, not in the contract."
    )


@pytest.mark.parametrize("code", ["401", "422", "429"])
def test_errors_are_documented(generated: dict[str, Any], code: str) -> None:
    """Error codes are part of the contract.

    They do NOT go through `response_model` (which only describes the
    nominal case): without an explicit declaration, a consumer would not know
    that a 422 is the expected authentication failure, nor that a 429 carries
    a `Retry-After`.
    """
    responses = generated["paths"]["/api/resources"]["get"]["responses"]
    assert code in responses, f"code {code} is not documented on /api/resources"


def test_every_unverified_field_is_registered(generated: dict[str, Any]) -> None:
    """THE test that makes honesty verifiable.

    Marking a field `unverified` without registering it is the same as
    writing a comment: nobody will check it, and it will ship to production
    as a certainty. This test turns the inventory into a build constraint.
    """
    schemas = generated.get("components", {}).get("schemas", {})
    marked = _marked_fields(schemas, "unverified")
    assert marked, (
        "NO field marked `unverified`. That would be good news if the "
        "dialect were fully attested — it is not (isDeleted, updateDate on "
        "modules that do not document it…). Was the marking removed?"
    )

    registry = REGISTRY.read_text(encoding="utf-8")
    missing = sorted(name for name in marked if name not in registry)
    assert not missing, (
        "Fields marked `unverified` but MISSING from docs/UNVERIFIED-FIELDS.md:\n  "
        + "\n  ".join(f"{n} — {marked[n]}" for n in missing)
        + "\n\nA marker nobody checks is just a comment. Register every field, "
        "with what it would take to lift the doubt."
    )


def test_invented_fields_are_flagged_as_such(generated: dict[str, Any]) -> None:
    """`invented` is more serious than `unverified` and must stay exceptional.

    `unverified` says "plausible, not proven". `invented` says "we know this
    does not exist". The latter must never slip in quietly: if it appears, it
    must be in the registry, with its justification.
    """
    schemas = generated.get("components", {}).get("schemas", {})
    invented = _marked_fields(schemas, "invented")
    if not invented:
        return
    registry = REGISTRY.read_text(encoding="utf-8")
    missing = sorted(name for name in invented if name not in registry)
    assert not missing, f"INVENTED fields missing from the registry: {missing}"
