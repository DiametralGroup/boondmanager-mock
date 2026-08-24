"""Plan de contrôle `/__admin` — piloter les pannes par HTTP.

Pourquoi il existe : le mock d'origine ne s'injectait des pannes qu'en mutant un
`set` Python depuis le même processus. Cela marche quand les tests montent
l'application en process (le cas d'ophelie), et pas du tout quand le mock tourne
en conteneur — le cas d'insights360, en docker compose comme en sidecar Tekton.

Deux décisions de conception :

  • le préfixe `/__admin` est HORS de `/api`. D'une part aucune collision n'est
    possible avec un vrai chemin BoondManager ; d'autre part une NetworkPolicy
    ou une règle d'ingress peut le bloquer en bloc, sans connaître les routes ;

  • le routeur n'est PAS MONTÉ quand `BOOND_MOCK_ADMIN_ENABLED` est faux. Pas
    « monté puis interdit » : absent. Le déploiement d'ophelie le laisse à
    false, donc la surface n'existe simplement pas sur le cluster.
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
    # L'observation avance le monde : l'état rendu reflète les événements
    # d'évolution devenus dus, même si aucune requête de données n'a eu lieu.
    state.avancer_evolution(engine.now())
    return JSONResponse(
        {
            "seed": state.seed,
            "totals": state.totals(),
            "request_counts_by_path": dict(engine.request_counts),
            "last_query_params_by_path": dict(engine.last_query_params),
            "query_params_by_path": {
                chemin: list(appels) for chemin, appels in engine.query_params_history.items()
            },
            "injections": engine.snapshot(),
            "fail_collections": sorted(state.fail_collections),
            "clock_offset": engine.clock_offset,
            # L'évolution temporelle : combien d'événements ont eu lieu, et
            # lesquels — c'est ce qui permet de VÉRIFIER qu'une extraction
            # incrémentale a vu exactement le delta attendu.
            "evolution": state.evolution.apercu(),
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

    Les RELATIONS sont patchables au même titre que les attributs, et ce n'est
    pas un raffinement : chez BoondManager, le manager d'une ressource
    (`mainManager`) et son agence (`agency`) sont des relations JSON:API, pas
    des attributs. Sans elles, ce plan de contrôle ne sait simuler ni une
    réaffectation d'entité ni un changement de hiérarchie — c'est-à-dire
    précisément les deux mutations qu'un consommateur qui dérive des DROITS
    D'ACCÈS d'un organigramme a besoin d'éprouver.

    Un patch qui ne correspond à RIEN est refusé (400) plutôt qu'accepté :
    voir `_verifier_clefs`.
    """
    if (denied := _guard(x_mock_admin_token)) is not None:
        return denied
    body = await request.json()
    collection = body.get("collection")
    item_id = str(body.get("id"))
    patch_attributs = body.get("attributes", {})
    patch_relations = body.get("relationships", {})

    if not patch_attributs and not patch_relations:
        return error(400, "nothing to patch: give 'attributes' and/or 'relationships'")

    items = state.dataset.get(collection)
    if not isinstance(items, list):
        return error(404, f"collection {collection!r} not found")
    for item in items:
        if item["id"] == item_id:
            if (refus := _verifier_clefs(item, patch_attributs, patch_relations)) is not None:
                return refus
            item.setdefault("attributes", {}).update(patch_attributs)
            _fusionner_relations(item, patch_relations)
            # L'avancée de l'horodatage n'est pas cosmétique : sans elle, le
            # curseur incrémental ne reverrait jamais l'enregistrement modifié,
            # et le test d'incrémentalité passerait en ne testant rien.
            item["attributes"][_UPDATED_AT] = _horodate_apres_tous(items, item)
            state.invalider_caches()
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
            item["attributes"][_UPDATED_AT] = _horodate_apres_tous(items, item)
            state.invalider_caches()
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
    state.avancer_evolution(engine.now())
    return JSONResponse({"clock_offset": engine.clock_offset})


def _verifier_clefs(
    item: dict[str, Any],
    patch_attributs: dict[str, Any],
    patch_relations: dict[str, Any],
) -> JSONResponse | None:
    """Refuse un patch dont une clef n'existe pas sur l'enregistrement.

    Le mode de panne que cette garde ferme, et il a coûté une demi-journée :
    patcher `attributes: {"main_manager_id": …}` — le nom de la COLONNE vue à
    l'arrivée du pipeline, pas celui de la relation JSON:API — renvoyait
    `{"status": "mutated"}` en ne changeant rien. Le scénario de test aval
    passait au VERT en n'ayant rien éprouvé : le pire résultat possible pour
    un plan de contrôle dont la raison d'être est justement de faire bouger
    quelque chose.

    Le refus nomme les clefs disponibles : dans ce cas précis, la réponse
    contient `mainManager` et le testeur voit immédiatement son erreur.
    """
    relations_connues = item.get("relationships", {})
    inconnues_a = [c for c in patch_attributs if c not in item.get("attributes", {})]
    inconnues_r = [c for c in patch_relations if c not in relations_connues]
    if not inconnues_a and not inconnues_r:
        return None

    details = []
    if inconnues_a:
        details.append(f"unknown attribute(s) {sorted(inconnues_a)}")
    if inconnues_r:
        details.append(f"unknown relationship(s) {sorted(inconnues_r)}")
    return error(
        400,
        f"{'; '.join(details)} — available relationships: {sorted(relations_connues)}",
    )


def _fusionner_relations(item: dict[str, Any], patch: dict[str, Any]) -> None:
    """Applique un patch de relations, clef par clef.

    Clef par clef et non en bloc : patcher `mainManager` ne doit pas emporter
    `agency` avec lui — symétrique du `.update()` des attributs.

    Deux écritures sont acceptées, et c'est délibéré :

      • la forme canonique JSON:API, `{"agency": {"data": {"id": "2",
        "type": "agency"}}}`, quand le test veut être explicite ;
      • l'identifiant nu, `{"agency": "2"}`, qui REPREND le `type` déjà porté
        par l'enregistrement. Plus court à écrire, et surtout impossible à
        désaccorder : le type ne passe jamais par la main du testeur.
    """
    relations = item.setdefault("relationships", {})
    for nom, valeur in patch.items():
        if isinstance(valeur, dict):
            relations[nom] = valeur
            continue
        type_courant = relations[nom].get("data", {}).get("type")
        relations[nom] = {"data": {"id": str(valeur), "type": type_courant}}


_UPDATED_AT = "updateDate"


def _horodate_apres_tous(items: list[dict[str, Any]], item: dict[str, Any]) -> str:
    """Le nouvel horodatage dépasse le MAXIMUM de la collection.

    Pas seulement celui de l'enregistrement modifié, et c'est la différence qui
    compte : un curseur incrémental avance sur le maximum VU. Un `updateDate`
    bumpé depuis la valeur propre à l'item retombe presque toujours SOUS ce
    maximum, la modification devient invisible au run suivant, et le test
    d'incrémentalité passe en ne testant rien.

    C'est aussi le comportement réel : une API horodate la mutation à l'instant
    où elle a lieu, donc au-dessus de tout ce qui précède.
    """
    courant = item.get("attributes", {}).get(_UPDATED_AT)
    maximum = max(
        (i.get("attributes", {}).get(_UPDATED_AT) or "" for i in items),
        default=courant,
    )
    return _bump(maximum or courant)


def _bump(current: str | None) -> str:
    """Avance l'horodatage d'une seconde, de façon déterministe.

    Pas de `datetime.now()` : la mutation doit rester reproductible d'un run à
    l'autre. Le décalage du fuseau est CONSERVÉ au format fournisseur
    (`+0200`, sans deux-points) — c'est celui que sert tout le jeu de données.
    """
    import contextlib
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, tzinfo=UTC)
    if current:
        # Un horodatage illisible retombe sur la base fixe plutôt que de faire
        # échouer la mutation : le mock doit rester utilisable même si un test a
        # écrit n'importe quoi dans le champ.
        with contextlib.suppress(ValueError):
            base = datetime.fromisoformat(current.replace("Z", "+00:00"))
    return (base + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S%z")
