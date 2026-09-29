"""Enveloppes, pagination, tri, filtre incrémental — et les pannes associées.

L'enveloppe suit le schéma OFFICIEL (doc.boondmanager.com, RAML) :

    liste  : {"data": [...], "included": [...], "meta": {"totals": {"rows": N},
              "version": "…", "isLogged": true, "language": "fr"}}
    détail : {"data": {...}, "included": [...], "meta": {version, isLogged, language}}

`included` n'apparaît que sur les modules dont le schéma le déclare, et
seulement s'il est non vide.

Au-delà du chemin heureux, ce module reproduit ce que l'API réelle fait, tel
que sondé le 2026-09-29 :
  • la pagination `page`/`maxResults` : défaut 30, maximum 500 (100 sur
    `/actions`) et, au-delà du maximum, un retour SILENCIEUX aux 30 lignes par
    défaut ; `agencies`, `poles` et `business-units` ne se paginent pas ;
  • le tri : seules les clés du `sortList` officiel sont honorées, et l'ordre
    par défaut est une date décroissante sur les collections mesurées ;
  • les filtres de période officiels (`period=updated|created`, et
    `period=inProgress` sur `/times`) ;
  • en opt-in : l'ordre INSTABLE, la dérive de pagination (un enregistrement
    rendu sur deux pages) et le filtre `updatedSince`, que le fournisseur
    ignore (affordance du mock, cf. plus bas).
"""

from __future__ import annotations

import json
from typing import Any

from .injection import engine
from .settings import settings

#: Les versions que `meta` annonce — relevées sur la vraie API le 2026-07-31.
VERSION_BOOND = "9.1.78.1"
VERSION_ANDROID_MIN = "2.31.5"
VERSION_IOS_MIN = "2.28.6"


def _horodatage_ms() -> int:
    """`meta.timestamp` — epoch millisecondes, DÉTERMINISTE.

    Dérivé de l'horloge VIRTUELLE : époque du jeu de données + temps écoulé
    depuis le reset (y compris les avances de /__admin/clock). Deux serveurs au
    même âge rendent le même timestamp — la propriété que le réel n'a pas, et
    que le mock garde pour rester rejouable.
    """
    from .evolution import EPOQUE
    from .state import state

    ecoule = engine.now() - state.evolution.demarrage
    return int(EPOQUE.timestamp() * 1000 + ecoule * 1000)


def _meta_commun(connecte: bool) -> dict[str, Any]:
    """Le socle `meta` observé sur la vraie API — présent MÊME en erreur.

    Hors session (401, JWT invalide, route inconnue) : `isLogged: false`,
    `language: "en"`, sans `login` ni `customer`.
    """
    meta: dict[str, Any] = {
        "version": VERSION_BOOND,
        "androidMinVersion": VERSION_ANDROID_MIN,
        "iosMinVersion": VERSION_IOS_MIN,
        "isLogged": connecte,
        "language": "fr" if connecte else "en",
        "timestamp": _horodatage_ms(),
    }
    if connecte:
        meta["login"] = settings.basic_user
        meta["customer"] = settings.customer
    return meta


def meta_erreur(connecte: bool) -> dict[str, Any]:
    """Le meta des réponses d'erreur (importé par errors.py)."""
    return _meta_commun(connecte)


# ┌─ INCRÉMENTAL : LA VOIE OFFICIELLE, PUIS L'AFFORDANCE ──────────────────────┐
# │ La voie OFFICIELLE (RAML) : `period=updated&startDate=AAAA-MM-JJ&endDate=…`│
# │ — documentée sur 11 modules (actions, candidates, companies, contacts,    │
# │ invoices, opportunities, orders, payments, projects, purchases,           │
# │ resources), granularité JOUR. Sondée le 2026-09-29 : honorée sur les 11,  │
# │ y compris /orders, qui ne rend pourtant pas `updateDate`. `period=created`│
# │ fait de même sur la date de création.                                     │
# │                                                                            │
# │ Sur `/times`, la seule valeur documentée est `period=inProgress`. Elle    │
# │ filtre sur la DATE DE LA LIGNE (`startDate`), et elle marche : 111 745    │
# │ lignes au total, 2 716 pour septembre 2026.                               │
# │                                                                            │
# │ Hors de ces cas, le mock applique `period=updated|created` sur ses autres │
# │ collections (sur-ensemble, non mesuré) ; les autres valeurs de `period`   │
# │ et les filtres métier (`flags`, `states`…) sont ACCEPTÉS et ignorés.      │
# │                                                                            │
# │ L'affordance `updatedSince=<ISO-8601>` (ou `filter[updateDate][gte]`)     │
# │ n'existe PAS chez le fournisseur : il l'accepte et l'ignore, totaux       │
# │ identiques sur les 11 modules. Désactivée par défaut depuis 0.11.0 ;      │
# │ `BOOND_MOCK_UPDATED_SINCE=true` la rallume.                               │
# └─────────────────────────────────────────────────────────────────────────────┘
UPDATED_SINCE_PARAMS = ("updatedSince", "filter[updateDate][gte]")

UPDATED_AT_FIELD = "updateDate"

#: `period` → champ filtré, bornes [startDate, endDate] inclusives au jour.
PERIODES_SUPPORTEES = {
    "updated": "updateDate",
    "created": "creationDate",
    # /times : la date de la ligne de temps, pas une date de modification.
    "inProgress": "startDate",
}

#: Valeurs de `period` honorées par défaut : le sur-ensemble du mock.
PERIODES_PAR_DEFAUT: tuple[str, ...] = ("updated", "created")


def apply_period(
    items: list[dict[str, Any]],
    params: dict[str, str],
    periodes: tuple[str, ...] = PERIODES_PAR_DEFAUT,
) -> list[dict[str, Any]]:
    """Les filtres de période OFFICIELS : `period=<valeur>` + bornes en jours.

    Seules les valeurs de `periodes` s'appliquent : une autre est acceptée et
    IGNORÉE, comme le fait le fournisseur. Un item sans le champ visé est exclu
    quand le filtre est actif — une ligne sans date de création ne peut pas
    être « créée entre deux dates ».
    """
    periode = params.get("period", "")
    champ = PERIODES_SUPPORTEES.get(periode) if periode in periodes else None
    if champ is None:
        return items
    debut = params.get("startDate", "0000-00-00")
    fin = params.get("endDate", "9999-12-31")
    return [
        i
        for i in items
        if (jour := str(i.get("attributes", {}).get(champ, ""))[:10]) and debut <= jour <= fin
    ]


def apply_keywords(
    items: list[dict[str, Any]],
    keywords: str,
    blobs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Recherche plein-texte grossière — suffisante pour un mock.

    `blobs` : le texte de recherche précalculé par item (state.blobs), aligné
    sur la collection COMPLÈTE — évite de resérialiser le dataset à chaque
    requête."""
    if not keywords:
        return items
    needle = keywords.strip().lower()
    if blobs is not None and len(blobs) == len(items):
        return [i for i, blob in zip(items, blobs, strict=True) if needle in blob]
    return [i for i in items if needle in json.dumps(i, ensure_ascii=False).lower()]


def apply_incremental(items: list[dict[str, Any]], since: str | None) -> list[dict[str, Any]]:
    """Filtre sur l'horodatage de mise à jour : AFFORDANCE du mock.

    Le fournisseur accepte `updatedSince` et l'ignore (sondé le 2026-09-29) :
    le filtre ne s'applique donc que si `BOOND_MOCK_UPDATED_SINCE=true`.
    Appliqué d'office, il a rendu vert un client qui relisait en production
    toutes ses collections à chaque run.

    Comparaison lexicographique : les horodatages sont ISO-8601 (fuseau
    Europe/Paris, décalage sans deux-points, comme la vraie API), donc l'ordre
    lexicographique et l'ordre chronologique coïncident au jour près — assez
    pour un mock, sans parsing ni mode de défaillance sur une date malformée.
    """
    if not since or not settings.updated_since_enabled:
        return items
    return [i for i in items if str(i.get("attributes", {}).get(UPDATED_AT_FIELD, "")) >= since]


def extract_since(params: dict[str, str]) -> str | None:
    for name in UPDATED_SINCE_PARAMS:
        if (value := params.get(name)) is not None:
            return value
    return None


#: Les clés de tri OFFICIELLES : le `sortList` du trait `sortablePaginable`,
#: par module (RAML téléchargée le 2026-09-29). Une clé absente est ignorée
#: sans erreur — sondé : `sort=id` et une clé inventée rendent l'ordre par
#: défaut, en 200. Les modules absents (agencies, poles, business-units) n'ont
#: pas de tri au contrat.
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

#: Clés du `sortList` que le fournisseur ignore pourtant (sondé le 2026-09-29) :
#: `/resources?sort=creationDate` rend l'ordre par défaut, en asc comme en desc.
TRIS_IGNORES: frozenset[tuple[str, str]] = frozenset({("resources", "creationDate")})

#: Clés dont le fournisseur ignore `order` : toujours décroissant (sondé le
#: 2026-09-29 — `/resources?sort=updateDate&order=asc` rend la même séquence
#: qu'en desc, alors que companies et actions honorent les deux sens).
TRIS_TOUJOURS_DECROISSANTS: frozenset[tuple[str, str]] = frozenset({("resources", "updateDate")})

#: L'ordre SANS tri honoré, mesuré le 2026-09-29 : une date DÉCROISSANTE.
#:
#: ┌─ POURQUOI C'EST IMPORTANT POUR UN CONSOMMATEUR QUI PAGINE ────────────────┐
#: │ Sur une liste triée par date de modification, un enregistrement modifié  │
#: │ pendant le parcours remonte en tête : les pages suivantes glissent d'un  │
#: │ cran, et une ligne est servie deux fois. Une suppression fait l'inverse  │
#: │ et fait sauter une ligne. Le mock servait les identifiants dans l'ordre  │
#: │ croissant, ce qui masquait tout ça — et laissait croire qu'un `sort=id`, │
#: │ ignoré par le fournisseur, stabilisait la pagination.                    │
#: └───────────────────────────────────────────────────────────────────────────┘
#: Les collections absentes n'ont pas été mesurées : ordre d'insertion, stable.
ORDRE_PAR_DEFAUT: dict[str, str] = {
    "resources": "updateDate",
    "companies": "updateDate",
    "actions": "startDate",
}


def _valeur_triable(item: dict[str, Any], chemin: str) -> tuple[int, float, str]:
    """Clé de tri, chemin pointé accepté (`workUnitType.reference`).

    Un nombre se trie comme un nombre (`10` après `9`), le reste comme du
    texte ; une valeur absente vaut une chaîne vide."""
    noeud: Any = item.get("attributes", {})
    for segment in chemin.split("."):
        if not isinstance(noeud, dict):
            return (1, 0.0, "")
        noeud = noeud.get(segment)
    if noeud is None:
        return (1, 0.0, "")
    if isinstance(noeud, int | float) and not isinstance(noeud, bool):
        return (0, float(noeud), "")
    return (1, 0.0, str(noeud))


def _tri_honore(collection: str | None, cle: str) -> bool:
    """La clé `sort` est-elle honorée par le fournisseur sur ce module ?

    Sans collection nommée (appel interne), toute clé est honorée."""
    if collection is None:
        return True
    if (collection, cle) in TRIS_IGNORES:
        return False
    return cle in SORT_LISTS.get(collection, frozenset())


def apply_order(
    items: list[dict[str, Any]],
    params: dict[str, str],
    request_index: int,
    collection: str | None = None,
) -> list[dict[str, Any]]:
    """L'ordre tel que MESURÉ sur l'API réelle (2026-09-29).

    1. `sort` n'est honoré que s'il figure au `sortList` officiel du module ;
       sinon il est ignoré sans erreur, comme chez le fournisseur.
    2. Sans tri honoré, l'ordre par défaut s'applique : une date décroissante
       sur les collections mesurées (ORDRE_PAR_DEFAUT), l'ordre d'insertion
       ailleurs. Deux appels identiques rendent la même séquence.
    3. L'instabilité reste disponible, en OPT-IN, pour éprouver les pipelines
       (`BOOND_MOCK_STABLE_ORDER=false` ou une injection `unstable_order`).
       Elle est DÉTERMINISTE dans un test donné — `hash((rang de requête,
       id))` — donc reproductible.
    """
    sort_field = params.get("sort")
    if sort_field and _tri_honore(collection, sort_field):
        if (collection, sort_field) in TRIS_TOUJOURS_DECROISSANTS:
            reverse = True
        else:
            reverse = params.get("order", "asc").lower() == "desc"
        return sorted(items, key=lambda i: _valeur_triable(i, sort_field), reverse=reverse)

    instable = not settings.stable_order or engine.first("unstable_order", "*") is not None
    if instable:
        return sorted(items, key=lambda i: hash((request_index, i.get("id"))))

    if champ := ORDRE_PAR_DEFAUT.get(collection or ""):
        return sorted(items, key=lambda i: _valeur_triable(i, champ), reverse=True)
    return items


def apply_page_drift(
    tous: list[dict[str, Any]], page: int, page_size: int, path: str
) -> list[dict[str, Any]] | None:
    """Simule une donnée qui bouge EN COURS de pagination.

    Le scénario réel : un enregistrement est inséré (ou supprimé) entre la
    récupération de la page 1 et celle de la page 2. Tout glisse d'un cran, et
    un enregistrement se retrouve rendu deux fois — ou pas du tout.

    C'est la cause classique de duplication silencieuse, et la raison pour
    laquelle un pipeline doit dédupliquer sur sa clé de merge plutôt que faire
    confiance à la pagination.

    Opère sur la liste COMPLÈTE et rend la tranche décalée — ou None si aucune
    règle ne s'applique. (Le mock d'origine décalait la tranche déjà découpée :
    `items[:n] + items[n:]`, une identité — la panne ne s'appliquait jamais.)
    """
    rule = engine.first("page_drift", path)
    if rule is None or page <= rule.after_page:
        return None
    if not rule.consume():
        return None
    if rule.mode == "insert":
        # Une insertion en amont décale tout vers l'arrière : le dernier
        # élément de la page précédente réapparaît en tête de celle-ci.
        debut = max(0, (page - 1) * page_size - 1)
    else:
        # Une suppression en amont fait tout remonter d'un cran : le premier
        # élément attendu de cette page a déjà été servi… ou est perdu.
        debut = (page - 1) * page_size + 1
    return tous[debut : debut + page_size]


#: Plafond de `maxResults` par collection, quand il diffère du plafond général.
#:
#: ┌─ MESURÉ, PAS SUPPOSÉ — 2026-09-29, contre un tenant de production ────────┐
#: │ `/actions` honore `maxResults` jusqu'à 100 (100 → 100 lignes) et revient  │
#: │ aux 30 par défaut dès 101. Ailleurs le plafond est 500 : `/companies`     │
#: │ rend 500 lignes pour 500, et 30 pour 501.                                 │
#: │                                                                           │
#: │ Le relevé du 2026-08-12 en avait conclu que `/actions` IGNORAIT le        │
#: │ paramètre : la seule valeur testée, 500, dépassait son plafond. Le mock   │
#: │ rendait donc 30 lignes quoi qu'on demande, et un client qui aurait        │
#: │ demandé 100 n'avait aucun moyen de voir qu'il aurait été servi : 50 777   │
#: │ actions font 508 pages à 100, contre 1 693 à 30.                          │
#: └───────────────────────────────────────────────────────────────────────────┘
PLAFONDS_MAXRESULTS: dict[str, int] = {"actions": 100}

#: Modules SANS pagination au contrat (pas de trait `sortablePaginable`) : le
#: fournisseur ignore `page` et `maxResults` et rend tout (sondé le 2026-09-29 :
#: 11 agences, 8 pôles, 2 unités, y compris avec `page=2&maxResults=1`).
COLLECTIONS_NON_PAGINABLES: frozenset[str] = frozenset({"agencies", "poles", "business-units"})


def paginate(
    items: list[dict[str, Any]], params: dict[str, str], collection: str | None = None
) -> tuple[list[dict[str, Any]], int, int] | None:
    """Rend (tranche, page, taille) ou None si les paramètres sont invalides.

    `collection` est le NOM NU de la collection (`actions`, pas `/api/actions`).
    Il sert aux deux comportements par module : le plafond propre à `/actions`
    et les modules non paginables. Il reste optionnel.

    Au-delà du plafond, le fournisseur ne PLAFONNE PAS : il revient en silence
    à la taille par défaut (30). Pas de 422, pas de signal — un consommateur
    qui demande trop reçoit moins qu'une page ordinaire.
    """
    if collection in COLLECTIONS_NON_PAGINABLES:
        return items, 1, max(1, len(items))
    try:
        page = max(1, int(params.get("page", 1)))
        requested = int(params.get("maxResults", settings.default_max_results))
    except ValueError:
        return None
    plafond = PLAFONDS_MAXRESULTS.get(collection or "", settings.max_results_cap)
    if requested > plafond:
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
    """L'enveloppe de liste — meta complet observé + clés propres au module."""
    corps: dict[str, Any] = {"data": data}
    if included:
        corps["included"] = included
    corps["meta"] = {**_meta_commun(True), **(meta_extra or {}), "totals": {"rows": total}}
    return corps


def envelope_detail(
    item: dict[str, Any], included: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """L'enveloppe de détail — même `meta`, sans `totals`, comme les profils réels."""
    corps: dict[str, Any] = {"data": item}
    if included:
        corps["included"] = included
    corps["meta"] = _meta_commun(True)
    return corps
