"""`/__admin` control plane — controlling failures over HTTP.

Why it exists: the original mock could only inject failures by mutating a
Python `set` from the same process. That works when tests mount the
application in-process (ophelie's case), and not at all when the mock runs in
a container — insights360's case, in docker compose as in a Tekton sidecar.

Two design decisions:

  • the `/__admin` prefix is OUTSIDE of `/api`. On one hand no collision is
    possible with a real BoondManager path; on the other, a NetworkPolicy or
    an ingress rule can block it wholesale, with no route-level knowledge;

  • the router is NOT MOUNTED when `BOOND_MOCK_ADMIN_ENABLED` is false. Not
    "mounted then forbidden": absent. Ophelie's deployment leaves it at
    false, so the surface simply does not exist on the cluster.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from .errors import error
from .injection import engine
from .settings import settings
from .state import state

router = APIRouter(prefix="/__admin", tags=["admin"])


def _authorized(token: str | None) -> bool:
    return bool(token) and token == settings.admin_token


def _guard(token: str | None) -> JSONResponse | None:
    if not _authorized(token):
        return error(401, "invalid or missing X-Mock-Admin-Token")
    return None


@router.post("/reset")
async def reset(
    request: Request,
    x_mock_admin_token: str | None = Header(default=None),
) -> JSONResponse:
    """Rebuild the dataset and reset all counters.

    Injection rules return to the BASELINE declared by the environment, not to
    empty — see state.MockState.reset.
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    body: dict[str, Any] = {}
    if request.headers.get("content-length") not in (None, "0"):
        body = await request.json()
    seed = body.get("seed", request.query_params.get("seed"))
    state.reset(seed=int(seed) if seed is not None else None)
    return JSONResponse({"status": "reset", "seed": state.seed})


@router.get("/state")
def get_state(x_mock_admin_token: str | None = Header(default=None)) -> JSONResponse:
    """What the mock has seen and what it will do.

    `last_query_params` is the load-bearing part: it lets a consumer PROVE it
    sent its incremental parameter and its sort, instead of merely tolerating
    their absence. A pipeline that forgot its cursor would otherwise pass all
    its incrementality tests.
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    # Observing advances the world: the rendered state reflects evolution
    # events that have become due, even if no data request has occurred.
    state.advance_evolution(engine.now())
    return JSONResponse(
        {
            "seed": state.seed,
            "totals": state.totals(),
            "request_counts_by_path": dict(engine.request_counts),
            "last_query_params_by_path": dict(engine.last_query_params),
            "query_params_by_path": {
                path: list(calls) for path, calls in engine.query_params_history.items()
            },
            "injections": engine.snapshot(),
            "fail_collections": sorted(state.fail_collections),
            "clock_offset": engine.clock_offset,
            # Time evolution: how many events have occurred, and which ones —
            # this is what lets an incremental extraction be VERIFIED to have
            # seen exactly the expected delta.
            "evolution": state.evolution.overview(),
        }
    )


@router.post("/inject")
async def inject(
    request: Request,
    x_mock_admin_token: str | None = Header(default=None),
) -> JSONResponse:
    """Add an injection rule.

    Body: a union discriminated on `kind` —
      {"kind":"rate_limit","scope":"/api/resources","after_requests":10,"retry_after_seconds":2}
      {"kind":"status","scope":"/api/times-reports","status":503,"times":2}
      {"kind":"latency","scope":"*","seconds":2.5,"times":1}
      {"kind":"page_drift","scope":"/api/resources","after_page":1,"mode":"insert"}
      {"kind":"auth_reject","scope":"*","status":401}
      {"kind":"unstable_order","scope":"*"}
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    body = await request.json()
    kind = body.pop("kind", None)
    if kind not in {
        "rate_limit",
        "status",
        "latency",
        "page_drift",
        "auth_reject",
        "unstable_order",
    }:
        return error(422, f"unknown injection kind: {kind!r}")
    try:
        rule = engine.add(kind=kind, **body)
    except TypeError as exc:
        return error(422, f"invalid injection payload: {exc}")
    return JSONResponse({"rule_id": rule.id, "kind": rule.kind, "scope": rule.scope})


@router.delete("/inject/{rule_id}")
def delete_inject(
    rule_id: str, x_mock_admin_token: str | None = Header(default=None)
) -> JSONResponse:
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    if not engine.remove(rule_id):
        return error(404, f"rule {rule_id} not found")
    return JSONResponse({"status": "removed", "rule_id": rule_id})


@router.post("/inject/clear")
def clear_inject(x_mock_admin_token: str | None = Header(default=None)) -> JSONResponse:
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    engine.clear()
    return JSONResponse({"status": "cleared"})


@router.post("/mutate")
async def mutate(
    request: Request,
    x_mock_admin_token: str | None = Header(default=None),
) -> JSONResponse:
    """Patch one record and bump its `updateDate`.

    ESSENTIAL to incrementality testing: "after a run, modifying one record in
    the mock and re-running updates exactly one row and touches no others".
    Once the mock runs in a container, this is the only way to simulate a
    source-side change.

    Body: {"collection": "resources", "id": "3",
           "attributes": {...}, "relationships": {...}}

    RELATIONSHIPS are patchable just like attributes, and this is not a nice-
    to-have: at BoondManager, a resource's manager (`mainManager`) and its
    agency (`agency`) are JSON:API relationships, not attributes. Without
    this, the control plane could not simulate either an entity reassignment
    or a hierarchy change — precisely the two mutations a consumer deriving
    ACCESS RIGHTS from an org chart needs to exercise.

    A patch that matches NOTHING is refused (400) rather than accepted: see
    `_check_keys`.
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    body = await request.json()
    collection = body.get("collection")
    item_id = str(body.get("id"))
    patch_attributes = body.get("attributes", {})
    patch_relations = body.get("relationships", {})

    if not patch_attributes and not patch_relations:
        return error(400, "nothing to patch: give 'attributes' and/or 'relationships'")

    items = state.dataset.get(collection)
    if not isinstance(items, list):
        return error(404, f"collection {collection!r} not found")
    for item in items:
        if item["id"] == item_id:
            if (refusal := _check_keys(item, patch_attributes, patch_relations)) is not None:
                return refusal
            item.setdefault("attributes", {}).update(patch_attributes)
            _merge_relations(item, patch_relations)
            # Bumping the timestamp is not cosmetic: without it, the
            # incremental cursor would never see the modified record again,
            # and the incrementality test would pass while testing nothing.
            item["attributes"][_UPDATED_AT] = _timestamp_after_all(items, item)
            state.invalidate_caches()
            return JSONResponse({"status": "mutated", "id": item_id})
    return error(404, f"{collection}/{item_id} not found")


@router.post("/delete")
async def soft_delete(
    request: Request,
    x_mock_admin_token: str | None = Header(default=None),
) -> JSONResponse:
    """LOGICAL deletion — a flag plus a timestamp bump.

    Never a physical deletion, and that is a decision, not a shortcut: an
    incremental pipeline running a `merge` strategy CANNOT observe a physical
    deletion without a full refresh. Pretending otherwise is exactly how ACL
    tables keep granting access to leavers.
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    body = await request.json()
    collection = body.get("collection")
    item_id = str(body.get("id"))
    items = state.dataset.get(collection)
    if not isinstance(items, list):
        return error(404, f"collection {collection!r} not found")
    for item in items:
        if item["id"] == item_id:
            item.setdefault("attributes", {})["isDeleted"] = True
            item["attributes"][_UPDATED_AT] = _timestamp_after_all(items, item)
            state.invalidate_caches()
            return JSONResponse({"status": "soft-deleted", "id": item_id})
    return error(404, f"{collection}/{item_id} not found")


@router.post("/clock")
async def clock(
    request: Request,
    x_mock_admin_token: str | None = Header(default=None),
) -> JSONResponse:
    """Advance the virtual clock — time windows without `sleep`.

    Also fast-forwards COMPANY LIFE: due evolution events are applied
    immediately, so the next response — data or control plane — already
    reflects the new world.
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    body = await request.json()
    engine.clock_offset += float(body.get("advance_seconds", 0))
    state.advance_evolution(engine.now())
    return JSONResponse({"clock_offset": engine.clock_offset})


def _check_keys(
    item: dict[str, Any],
    patch_attributes: dict[str, Any],
    patch_relations: dict[str, Any],
) -> JSONResponse | None:
    """Refuses a patch whose key does not exist on the record.

    The failure mode this guard closes cost half a day: patching
    `attributes: {"main_manager_id": …}` — the COLUMN name seen on arrival in
    the pipeline, not the JSON:API relationship's name — returned
    `{"status": "mutated"}` while changing nothing. The downstream test
    scenario passed GREEN having exercised nothing: the worst possible
    outcome for a control plane whose whole point is to make something move.

    The refusal names the available keys: in this exact case, the response
    carries `mainManager` and the tester sees their mistake immediately.
    """
    known_relations = item.get("relationships", {})
    unknown_attrs = [c for c in patch_attributes if c not in item.get("attributes", {})]
    unknown_rels = [c for c in patch_relations if c not in known_relations]
    if not unknown_attrs and not unknown_rels:
        return None

    details = []
    if unknown_attrs:
        details.append(f"unknown attribute(s) {sorted(unknown_attrs)}")
    if unknown_rels:
        details.append(f"unknown relationship(s) {sorted(unknown_rels)}")
    return error(
        400,
        f"{'; '.join(details)} — available relationships: {sorted(known_relations)}",
    )


def _merge_relations(item: dict[str, Any], patch: dict[str, Any]) -> None:
    """Applies a relationship patch, key by key.

    Key by key and not in bulk: patching `mainManager` must not carry
    `agency` along with it — symmetric to the attributes' `.update()`.

    Two notations are accepted, and this is deliberate:

      • the canonical JSON:API shape, `{"agency": {"data": {"id": "2",
        "type": "agency"}}}`, when the test wants to be explicit;
      • the bare identifier, `{"agency": "2"}`, which REUSES the `type`
        already carried by the record. Shorter to write, and above all
        impossible to get wrong: the type never passes through the tester's
        hand.
    """
    relations = item.setdefault("relationships", {})
    for name, value in patch.items():
        if isinstance(value, dict):
            relations[name] = value
            continue
        current_type = relations[name].get("data", {}).get("type")
        relations[name] = {"data": {"id": str(value), "type": current_type}}


_UPDATED_AT = "updateDate"


def _timestamp_after_all(items: list[dict[str, Any]], item: dict[str, Any]) -> str:
    """The new timestamp exceeds the collection's MAXIMUM.

    Not just the modified record's own value, and that difference is what
    matters: an incremental cursor advances on the maximum SEEN. An
    `updateDate` bumped from the item's own value almost always falls BELOW
    that maximum, the modification becomes invisible on the next run, and the
    incrementality test passes while testing nothing.

    It is also the real behavior: a real API timestamps a mutation at the
    moment it happens, hence above everything that precedes it.
    """
    current = item.get("attributes", {}).get(_UPDATED_AT)
    maximum = max(
        (i.get("attributes", {}).get(_UPDATED_AT) or "" for i in items),
        default=current,
    )
    return _bump(maximum or current)


def _bump(current: str | None) -> str:
    """Advances a timestamp by one second, deterministically.

    No `datetime.now()`: the mutation must stay reproducible from one run to
    the next. The timezone offset is KEPT in the vendor's format (`+0200`, no
    colon) — the one the whole dataset serves.
    """
    import contextlib
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, tzinfo=UTC)
    if current:
        # An unreadable timestamp falls back to the fixed base rather than
        # failing the mutation: the mock must stay usable even if a test wrote
        # garbage into the field.
        with contextlib.suppress(ValueError):
            base = datetime.fromisoformat(current.replace("Z", "+00:00"))
    return (base + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S%z")
