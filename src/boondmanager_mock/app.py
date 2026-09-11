"""Assemblage de l'application FastAPI.

Un SEUL point de dispatch pour les pannes (`_dispatch_injections`), évalué avant
l'authentification pour que `auth_reject` puisse préempter. Toute route de
collection passe par lui : il ne peut donc pas y avoir de route « oubliée » où
les pannes ne s'appliqueraient pas.

La surface reproduit les modules du fournisseur, CONFRONTÉE à la vraie API
(tenant réel, version 9.1.78.1, relevés des 2026-07-30/31) :

  • 20 collections interrogeables en liste — `/absences`, `/expenses` et
    `/times` sans détail `/{id}`, comme en réel ;
  • `GET /contracts` et `GET /deliveries` (listes) répondent **405**, comme en
    réel — les données se récupèrent par `/{id}` et par les relations
    (`resources/{id}` → `contracts`, `purchases` → `delivery`, `times` →
    `delivery`…) ;
  • `times-reports` EXIGE `startMonth`/`endMonth` (422 code métier 1017) ;
  • les DÉTAILS servent les formes *profile* officielles quand elles sont
    attestées (resources, projects, contracts, technical-data, administrative) ;
  • les routes inconnues rendent l'enveloppe d'erreur Boond, pas le 404 FastAPI.
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
from .errors import entree_erreur, error, reponse_erreurs
from .included import construire_included
from .injection import engine
from .models import (
    REPONSES_ERREUR,
    Absence,
    Achat,
    ActionCrm,
    AdministratifRessource,
    Agence,
    AvantageVerse,
    Candidat,
    Commande,
    Contact,
    Contrat,
    Cra,
    DonneesTechniques,
    EnveloppeDictionnaire,
    Facture,
    Frais,
    ItemEnvelope,
    ListEnvelope,
    Mission,
    Opportunite,
    Paiement,
    Pole,
    Projet,
    Ressource,
    Role,
    Societe,
    Temps,
    TransactionBancaire,
    UniteOperationnelle,
    UtilisateurCourant,
)
from .settings import settings
from .state import state


@dataclass(frozen=True)
class CollectionSpec:
    """Ce qu'il faut savoir d'une collection pour la servir ET la documenter.

    La fabrique de routes lit cette table : ajouter une collection, c'est une
    entrée ici plus une clé dans le jeu de données. Le `modele` est ce qui fait
    passer le contrat OpenAPI de « liste de chemins » à contrat véritable.
    """

    chemin: str  # segment d'URL — `times-reports` porte un tiret
    cle_dataset: str  # clé dans le dict du jeu de données
    modele: type  # modèle pydantic de l'élément
    singulier: str  # nom d'entité au singulier (documentation)
    avec_detail: bool = True  # /absences, /expenses et /times sont search-only
    avec_included: bool = True  # les modules sans `included` au schéma officiel
    liste_405: bool = False  # GET liste absent en réel (contracts, deliveries)
    parametres_obligatoires: tuple[str, ...] = ()  # 422 code 1017 sinon
    #: Le filtre `period=updated|created` est-il HONORÉ par cette collection ?
    #:
    #: `True` partout SAUF `/times` — cf. le bloc « ÉCART DOCUMENTÉ » ci-dessous.
    #: Mettre `False` ne fait pas répondre en erreur : la collection accepte les
    #: paramètres et les IGNORE, exactement comme le fournisseur.
    filtre_periode: bool = True
    meta_extra: tuple[str, ...] = ()  # clés meta propres au module (relevé réel)


#: Valeurs des clés meta par module — CLÉS observées en réel, valeurs plausibles
#: (le contenu exact n'est pas documenté ; cf. docs/UNVERIFIED-FIELDS.md).
META_EXTRAS: dict[str, Any] = {
    "solr": True,
    "conditionalFields": [],
    "resetCache": False,
    "hasOpportunityAlerts": False,
}


COLLECTIONS: tuple[CollectionSpec, ...] = (
    CollectionSpec(
        "absences", "absences", Absence, "absence", avec_detail=False, avec_included=False
    ),
    CollectionSpec("actions", "actions", ActionCrm, "action", meta_extra=("solr",)),
    CollectionSpec(
        "agencies", "agencies", Agence, "agency", avec_included=False, meta_extra=("resetCache",)
    ),
    CollectionSpec(
        "banking-transactions", "banking_transactions", TransactionBancaire, "bankingTransaction"
    ),
    CollectionSpec("business-units", "business_units", UniteOperationnelle, "businessUnit"),
    CollectionSpec(
        "candidates",
        "candidates",
        Candidat,
        "candidate",
        meta_extra=("conditionalFields", "solr"),
    ),
    CollectionSpec(
        "companies", "companies", Societe, "company", meta_extra=("conditionalFields", "solr")
    ),
    CollectionSpec(
        "contacts", "contacts", Contact, "contact", meta_extra=("conditionalFields", "solr")
    ),
    CollectionSpec("contracts", "contracts", Contrat, "contract", liste_405=True),
    CollectionSpec("deliveries", "deliveries", Mission, "delivery", liste_405=True),
    CollectionSpec(
        "expenses", "expenses", Frais, "expense", avec_detail=False, avec_included=False
    ),
    CollectionSpec("invoices", "invoices", Facture, "invoice"),
    CollectionSpec(
        "opportunities",
        "opportunities",
        Opportunite,
        "opportunity",
        meta_extra=("conditionalFields", "hasOpportunityAlerts", "solr"),
    ),
    CollectionSpec("orders", "orders", Commande, "order"),
    CollectionSpec("payments", "payments", Paiement, "payment"),
    CollectionSpec("poles", "poles", Pole, "pole", avec_included=False),
    CollectionSpec("projects", "projects", Projet, "project"),
    CollectionSpec("purchases", "purchases", Achat, "purchase"),
    CollectionSpec(
        "resources", "resources", Ressource, "resource", meta_extra=("conditionalFields", "solr")
    ),
    CollectionSpec("roles", "roles", Role, "role", avec_included=False),
    # ┌─ ÉCART DOCUMENTÉ ENTRE L'API RÉELLE ET SA DOCUMENTATION ───────────────┐
    # │ La documentation BoondManager présente `period=updated|created` +       │
    # │ `startDate`/`endDate` comme un filtre GÉNÉRAL des collections.          │
    # │ Sur `/times`, l'API RÉELLE ne l'honore pas : elle rend le jeu complet.  │
    # │                                                                          │
    # │ Mesuré le 2026-08-04 contre ui.boondmanager.com, sur un tenant de       │
    # │ production comptant 106 976 lignes de temps :                            │
    # │                                                                          │
    # │     sans filtre                       → 106 976                          │
    # │     startDate=2026-07-01&endDate=…    → 106 976                          │
    # │     startMonth=2026-07&endMonth=…     → 106 976                          │
    # │     period=updated&startDate=…        → 106 976                          │
    # │                                                                          │
    # │ Les trois formes sont acceptées — aucune n'est rejetée — et les trois    │
    # │ rendent le même total. Il n'y a donc AUCUN fenêtrage côté serveur sur    │
    # │ cette collection.                                                        │
    # │                                                                          │
    # │ Pourquoi le mock le reproduit plutôt que de « bien faire » :             │
    # │   un mock qui filtre là où le fournisseur ne filtre pas rend le          │
    # │   consommateur VERT sur un comportement qui n'existe pas. Le             │
    # │   dimensionnement, la cadence d'extraction et la charge imposée à l'API  │
    # │   se calculent alors sur une fiction. C'est précisément ce qui est       │
    # │   arrivé : la cadence horaire d'insights360 supposait un incrémental,    │
    # │   et représentait en réalité ~25 000 appels par jour.                    │
    # │                                                                          │
    # │ `/times` n'a par ailleurs PAS d'`updateDate` (cf. models/entities.py) :  │
    # │ les deux faits se renforcent — pas d'horodatage à filtrer, pas de        │
    # │ filtre. Un consommateur n'a d'autre choix qu'un rafraîchissement         │
    # │ complet, et doit en tirer les conséquences sur sa cadence.               │
    # │                                                                          │
    # │ Cf. docs/comparisons/ et docs/UNVERIFIED-FIELDS.md.                      │
    # └──────────────────────────────────────────────────────────────────────────┘
    CollectionSpec("times", "times", Temps, "time", avec_detail=False, filtre_periode=False),
    CollectionSpec(
        "times-reports",
        "times_reports",
        Cra,
        "timesReport",
        parametres_obligatoires=("startMonth", "endMonth"),
    ),
)


def _check_auth(request: Request) -> JSONResponse | None:
    """401 sans identifiants, **422** avec un JWT invalide — formes réelles.

    Le 422 réel : `"422 - Signature verification failed"` avec
    `source: {"parameter": "xJwtClient"}`, et un meta HORS SESSION
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
            connecte=False,
        )
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Basic ") and basic_is_valid(authorization[6:]):
        return None
    return error(401, request=request, connecte=False)


def _dispatch_injections(path: str, params: dict[str, str]) -> JSONResponse | None:
    """Le point de dispatch unique. Rend une réponse si une panne se déclenche.

    Ordre significatif :
      1. auth_reject  — doit préempter l'authentification réelle ;
      2. latency      — s'applique même quand la requête finit par réussir ;
      3. rate_limit   — dépend du compteur, donc après l'observation ;
      4. status       — la panne franche.

    C'est aussi ici que la vie de l'entreprise avance : chaque requête donne à
    l'évolution temporelle l'occasion d'appliquer les événements devenus dus
    (`engine.now()` intègre l'horloge virtuelle de /__admin/clock).
    """
    state.avancer_evolution(engine.now())
    index = engine.observe(path, params)

    if (rule := engine.first("auth_reject", path)) is not None and rule.consume():
        return error(rule.status or 401, f"HTTP {rule.status or 401} (GET {path})", connecte=False)

    if (rule := engine.first("latency", path)) is not None and rule.consume():
        # Un vrai `sleep` : c'est le seul moyen d'éprouver un timeout côté
        # client. L'horloge virtuelle sert aux fenêtres temporelles, pas ici.
        time.sleep(rule.seconds)

    if (
        (rule := engine.first("rate_limit", path)) is not None
        and index > rule.after_requests
        and rule.consume()
    ):
        # `Retry-After` en secondes, comme la vraie API. Un client qui l'ignore
        # et retente immédiatement doit continuer à recevoir des 429.
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

app = FastAPI(title="BoondManager mock", version="0.5.4", docs_url="/docs")
api = APIRouter(prefix="/api")


@app.exception_handler(StarletteHTTPException)
async def _erreur_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Routes et méthodes inconnues : l'enveloppe Boond, pas le 404 FastAPI.

    Comportement réel relevé : `/times/{id}` → 404 enveloppé, `GET /deliveries`
    → 405 enveloppé — avec un meta HORS SESSION (le routage précède l'auth).
    """
    if exc.status_code in (404, 405):
        return error(exc.status_code, request=request, connecte=False)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Unauthenticated — it is a probe, not an entity."""
    return {"status": "ok", "service": "boondmanager-mock"}


def _parametres_manquants(spec: CollectionSpec, params: dict[str, str]) -> JSONResponse | None:
    """La fenêtre obligatoire de `times-reports` — 422 code métier 1017.

    Forme réelle : une entrée d'erreur PAR paramètre manquant, chacune avec
    `source: {"parameter": ...}` (ordre alphabétique observé)."""
    manquants = sorted(p for p in spec.parametres_obligatoires if p not in params)
    if not manquants:
        return None
    return reponse_erreurs(
        422,
        [
            entree_erreur(
                422,
                "1017 - Missing required attribute",
                code="1017",
                source={"parameter": nom},
            )
            for nom in manquants
        ],
    )


def _garde_apres_auth(
    request: Request, spec: CollectionSpec, params: dict[str, str]
) -> JSONResponse | None:
    """Les refus post-authentification, dans l'ordre observé en réel :
    périmètre restreint (403), panne historique en process, fenêtre obligatoire."""
    if spec.chemin in settings.forbidden_collections:
        # BOOND_MOCK_FORBIDDEN_COLLECTIONS — le 403 d'un user token `narrowPerimeter`.
        return error(403, request=request)
    if spec.cle_dataset in state.fail_collections or spec.chemin in state.fail_collections:
        return error(500, f"mock: simulated outage on /{spec.chemin}")
    return _parametres_manquants(spec, params)


def _paginated(request: Request, spec: CollectionSpec) -> JSONResponse:
    path_name, dataset_key = spec.chemin, spec.cle_dataset
    params = dict(request.query_params)
    path = f"/api/{path_name}"

    if (injected := _dispatch_injections(path, params)) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if (refuse := _garde_apres_auth(request, spec, params)) is not None:
        return refuse

    items = _collection_items(dataset_key)
    if spec.chemin == "times-reports":
        # La fenêtre de termes est OBLIGATOIRE et effective (format AAAA-MM).
        debut, fin = params["startMonth"], params["endMonth"]
        items = [i for i in items if debut <= i["attributes"].get("term", "") <= fin]
    items = apply_keywords(items, params.get("keywords", ""), state.blobs(dataset_key))
    # `filtre_periode=False` → les paramètres sont acceptés et IGNORÉS, comme
    # le fournisseur le fait sur /times. Ne PAS transformer ça en 422 : l'API
    # réelle ne rejette rien, elle rend simplement tout, et un consommateur qui
    # verrait une erreur ici corrigerait un problème qui n'existe pas.
    if spec.filtre_periode:
        items = apply_period(items, params)
    items = apply_incremental(items, extract_since(params))

    total = len(items)
    items = apply_order(items, params, engine.request_counts.get(path, 1))

    paged = paginate(items, params, path_name)
    if paged is None:
        return error(422, "Wrong or missing attribute: page/maxResults")
    slice_, page, page_size = paged
    if (drift := apply_page_drift(items, page, page_size, path)) is not None:
        slice_ = drift

    included = (
        construire_included(slice_, state.dataset, dataset_key, state.index_entites())
        if spec.avec_included
        else None
    )
    extras = {cle: META_EXTRAS[cle] for cle in spec.meta_extra}
    return JSONResponse(envelope(slice_, total, included, extras))


# ─────────────────────────────────────────────────────────────────────────────
#  Projections de détail — les formes *profile* officielles
# ─────────────────────────────────────────────────────────────────────────────


def _contrats_de(resource_id: str) -> list[dict[str, str]]:
    """Les références de contrats d'une ressource — via `dependsOn`, comme l'API."""
    refs = []
    for contrat in state.dataset.get("contracts", []):
        data = (contrat.get("relationships") or {}).get("dependsOn", {}).get("data")
        if data and data.get("type") == "resource" and data.get("id") == resource_id:
            refs.append({"id": contrat["id"], "type": "contract"})
    return refs


def _anciennete(refs_contrats: list[dict[str, str]]) -> str:
    ids = {ref["id"] for ref in refs_contrats}
    debuts = [c["attributes"]["startDate"] for c in state.dataset["contracts"] if c["id"] in ids]
    return min(debuts) if debuts else ""


def _date_naissance(rid: int) -> str:
    """État civil synthétique DÉTERMINISTE — le jeu de base ne le porte pas."""
    return f"{1978 + (rid * 7) % 18}-{1 + (rid % 12):02d}-{1 + (rid * 3) % 28:02d}"


def _profil_ressource(item: dict[str, Any]) -> dict[str, Any]:
    """`GET /resources/{id}` — la forme PROFILE réelle (18 attributs relevés),
    distincte de la recherche, avec la relation `contracts`."""
    rid = int(item["id"])
    attrs = item["attributes"]
    rels = item.get("relationships") or {}
    contrats = _contrats_de(item["id"])
    anciennete = _anciennete(contrats)
    niveau = "administrator" if rid == 1 else ("manager" if rid <= 6 else "resource")
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
            "level": niveau,
            "title": attrs.get("title"),
            "dateOfBirth": _date_naissance(rid),
            "numberOfResumes": attrs.get("numberOfResumes"),
            "seniorityDate": anciennete,
            "forceSeniorityDate": False,
            "originalSeniorityDate": anciennete,
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
            "contracts": {"data": contrats},
        },
    }


def _profil_projet(item: dict[str, Any]) -> dict[str, Any]:
    """`GET /projects/{id}` — la forme PROFILE réelle (13 attributs relevés)."""
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


#: Les modules dont le détail projette une forme profile dédiée ; les autres
#: servent l'item de recherche tel quel (simplification documentée).
PROJECTIONS_PROFIL: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "resources": _profil_ressource,
    "projects": _profil_projet,
}

#: Table `included` dédiée aux détails qui en ont une (listes blanches réelles).
MODULE_INCLUDED_DETAIL: dict[str, str] = {
    "resources": "resources/profil",
    "projects": "projects/profil",
    "contracts": "contracts/profil",
    "deliveries": "deliveries/profil",
}


def _detail(request: Request, spec: CollectionSpec, item_id: str) -> JSONResponse:
    path_name, dataset_key = spec.chemin, spec.cle_dataset
    params = dict(request.query_params)
    if (injected := _dispatch_injections(f"/api/{path_name}/{item_id}", params)) is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    if path_name in settings.forbidden_collections:
        return error(403, request=request)
    for item in _collection_items(dataset_key):
        if item["id"] == item_id:
            projection = PROJECTIONS_PROFIL.get(path_name)
            enrichi = projection(item) if projection else item
            module = MODULE_INCLUDED_DETAIL.get(path_name, dataset_key)
            included = (
                construire_included([enrichi], state.dataset, module, state.index_entites())
                if spec.avec_included
                else None
            )
            return JSONResponse(envelope_detail(enrichi, included))
    # Message générique réel : "HTTP 404 (GET /api/resources/999999999)".
    return error(404, request=request)


def _register(spec: CollectionSpec) -> None:
    """Fabrique de routes.

    La fonction existe pour lier `spec` À CHAQUE ITÉRATION : sans elle, la
    fermeture capturerait la variable de boucle et toutes les routes serviraient
    la dernière collection.

    `response_model` est déclaré mais les handlers rendent une `JSONResponse` :
    FastAPI documente alors la forme SANS revalider la sortie. C'est délibéré —
    un mock doit pouvoir servir des charges volontairement anormales (dérive de
    pagination, champs manquants) sans que sa propre validation l'en empêche.
    """

    if spec.liste_405:
        # La recherche n'existe pas en réel (POST seul au RAML) : 405 enveloppé,
        # hors contrat OpenAPI — la route n'est là que pour mimer le réel.
        @api.get(f"/{spec.chemin}", name=f"list_{spec.cle_dataset}", include_in_schema=False)
        def _liste_interdite(request: Request) -> JSONResponse:
            return error(405, request=request, connecte=False)

    else:

        @api.get(
            f"/{spec.chemin}",
            name=f"list_{spec.cle_dataset}",
            response_model=ListEnvelope[spec.modele],  # type: ignore[name-defined]
            responses=REPONSES_ERREUR,
            summary=f"Paginated search: {spec.chemin}",
        )
        def _list(request: Request) -> JSONResponse:
            return _paginated(request, spec)

    if not spec.avec_detail:
        return

    @api.get(
        f"/{spec.chemin}/{{item_id}}",
        name=f"get_{spec.cle_dataset}",
        response_model=ItemEnvelope[spec.modele],  # type: ignore[name-defined]
        responses=REPONSES_ERREUR,
        summary=f"Profile: {spec.singulier}",
    )
    def _get(request: Request, item_id: str) -> JSONResponse:
        return _detail(request, spec, item_id)


for _spec in COLLECTIONS:
    _register(_spec)


@api.get(
    "/resources/{item_id}/administrative",
    response_model=ItemEnvelope[AdministratifRessource],
    responses=REPONSES_ERREUR,
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
    ressource = next((r for r in _collection_items("resources") if r["id"] == item_id), None)
    if ressource is None:
        return error(404, request=request)

    rid = int(item_id)
    attrs = ressource["attributes"]
    contrats = _contrats_de(item_id)
    anciennete = _anciennete(contrats)
    sous_traitant = attrs.get("typeOf") == 1

    relations: dict[str, Any] = {
        "agency": (ressource.get("relationships") or {}).get("agency", {"data": None}),
        "candidate": {"data": None},
        "contracts": {"data": contrats},
        "files": {"data": []},
    }
    if sous_traitant:
        # Le réel n'émet les clés provider* que lorsqu'elles ont un sens.
        relations["providerCompany"] = {"data": {"id": "11", "type": "company"}}
        relations["providerContact"] = {"data": None}

    item = {
        "id": item_id,
        "type": "resource",
        "attributes": {
            "reference": attrs.get("reference", ""),
            "dateOfBirth": _date_naissance(rid),
            "placeOfBirth": "",
            "nationality": "Française",
            "healthCareNumber": "",
            "address": "",
            "postcode": "",
            "town": "",
            "country": "France",
            "subDivision": "",
            "situation": 1,
            "administrativeComments": "",
            "function": attrs.get("title", ""),
            "seniorityDate": anciennete,
            "originalSeniorityDate": anciennete,
            "forceSeniorityDate": False,
            "validitySeniorityDate": "",
        },
        "relationships": relations,
    }
    included = construire_included([item], state.dataset, "administrative", state.index_entites())
    return JSONResponse(envelope_detail(item, included))


@api.get(
    "/resources/{item_id}/advantages",
    response_model=ListEnvelope[AvantageVerse],
    responses=REPONSES_ERREUR,
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

    siens = [
        a
        for a in state.dataset["advantages"]
        if a["relationships"]["contract"]["data"] is not None
        and a["relationships"]["contract"]["data"]["id"] in {c["id"] for c in _contrats_de(item_id)}
    ]
    # Tri stable : sans lui, deux appels identiques peuvent rendre des pages
    # différentes, et un consommateur qui pagine saute des lignes.
    siens.sort(key=lambda a: (a["attributes"]["date"], int(a["id"])))

    tranche = paginate(siens, dict(request.query_params))
    if tranche is None:
        return error(422, request=request)
    page, _numero, _taille = tranche
    return JSONResponse(envelope(page, len(siens)))


@api.get(
    "/resources/{item_id}/technical-data",
    response_model=ItemEnvelope[DonneesTechniques],
    responses=REPONSES_ERREUR,
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
    ressource = next((r for r in _collection_items("resources") if r["id"] == item_id), None)
    dossier = state.dataset["technical_data"].get(item_id)
    if ressource is None or dossier is None:
        return error(404, request=request)
    attrs = ressource["attributes"]
    item = {
        "id": item_id,
        "type": "resource",
        "attributes": {
            "activityAreas": attrs.get("activityAreas", []),
            "description": dossier["attributes"].get("description", ""),
            "diplomas": attrs.get("diplomas", []),
            "experience": attrs.get("experience"),
            "expertiseAreas": attrs.get("expertiseAreas", []),
            "languages": attrs.get("languages", []),
            "references": dossier["attributes"].get("references", []),
            "resourceCanModifyTechnicalData": True,
            "skills": attrs.get("skills", ""),
            "summary": dossier["attributes"].get("summary", ""),
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
    response_model=EnveloppeDictionnaire,
    responses=REPONSES_ERREUR,
    summary="Dictionnaire des énumérations — libellés configurés de l'instance",
)
def application_dictionary(request: Request) -> JSONResponse:
    """Les libellés d'énumération CONFIGURÉS DE L'INSTANCE.

    Objet unique, sans pagination ni `meta`. Partout ailleurs l'API rend des
    entiers nus : cette route est la seule source connue du rattachement code
    vers libellé, et les libellés ne sont pas des constantes du produit — deux
    instances peuvent coder la même notion différemment.
    """
    # Trois gestes repris du motif existant, et aucun n'est optionnel :
    # `_dispatch_injections` — sans lui l'endpoint échapperait au plan de
    # contrôle et aux modes d'échec injectables ; `_check_auth` AVANT toute
    # donnée ; et la lecture depuis `state.dataset` plutôt qu'une constante,
    # c'est ce qui garde le jeu de données comme source unique.
    injected = _dispatch_injections("/api/application/dictionary", dict(request.query_params))
    if injected is not None:
        return injected
    if (denied := _check_auth(request)) is not None:
        return denied
    return JSONResponse({"data": {"setting": state.dataset["dictionary"]}})


@api.get(
    "/application/current-user",
    response_model=ItemEnvelope[UtilisateurCourant],
    responses=REPONSES_ERREUR,
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

# Le plan de contrôle n'est pas « monté puis interdit » : quand il est
# désactivé, la surface n'existe pas.
if settings.admin_enabled:
    from .admin import router as admin_router

    app.include_router(admin_router)


# ─────────────────────────────────────────────────────────────────────────────
#  Rémunération — DÉLIBÉRÉMENT HORS DE /api
# ─────────────────────────────────────────────────────────────────────────────
#
# Servie comme un FICHIER, hors de `/api`, pour que personne ne la prenne pour
# un endpoint fournisseur. Depuis l'alignement sur les schémas officiels, les
# montants sont DÉRIVÉS de `/api/contracts/{id}` (champ `monthlySalary`,
# attesté) — le CSV n'est plus qu'une vue de commodité.


# `response_model=None` : le type de retour est une union de deux Response, que
# FastAPI tenterait sinon d'interpréter comme un modèle Pydantic.
@app.get("/__fixtures/remuneration.csv", response_class=PlainTextResponse, response_model=None)
def remuneration_csv(request: Request) -> PlainTextResponse | JSONResponse:
    if settings.compensation_mode == "absent":
        return error(404, "compensation fixture disabled (BOOND_MOCK_COMPENSATION_MODE=absent)")
    if (denied := _check_auth(request)) is not None:
        return denied
    lignes = ["collaborateur_id,upn,entite,periode,montant_brut_annuel"]
    for row in state.dataset.get("remuneration", []):
        lignes.append(
            f"{row['collaborateur_id']},{row['upn']},{row['entite']},"
            f"{row['periode']},{row['montant_brut_annuel']}"
        )
    return PlainTextResponse("\n".join(lignes) + "\n", media_type="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
#  Le contrat
# ─────────────────────────────────────────────────────────────────────────────


def contrat_openapi() -> dict[str, Any]:
    """Le contrat OpenAPI — le DIALECTE BoondManager, et lui seul.

    Les chemins `/__admin` (plan de contrôle des pannes) et `/__fixtures`
    (rémunération, servie hors de /api) sont RETIRÉS. Deux raisons :

      • ce sont des affordances du mock, pas du fournisseur. Les publier au
        contrat ferait passer pour du BoondManager ce qui n'en est pas — et un
        consommateur pourrait s'y adosser ;

      • `/__admin` n'est monté que si `BOOND_MOCK_ADMIN_ENABLED` est vrai. Le
        contrat dépendrait alors de l'environnement de génération, et le test
        anti-dérive échouerait selon la façon dont on l'a lancé.

    Elles restent documentées — dans le README — mais hors du contrat.
    """
    spec = app.openapi()
    spec["paths"] = {
        chemin: op
        for chemin, op in spec["paths"].items()
        if not chemin.startswith(("/__admin", "/__fixtures"))
    }
    _elaguer_schemas_orphelins(spec)
    return spec


def _elaguer_schemas_orphelins(spec: dict[str, Any]) -> None:
    """Retire les schémas que plus aucun chemin ne référence.

    Retirer des chemins laisse leurs schémas derrière eux. Le symptôme est
    déroutant : le contrat contient `HTTPValidationError` et `ValidationError`
    UNIQUEMENT quand `/__admin` était monté au moment de la génération — donc le
    fichier committé diffère selon la valeur d'une variable d'environnement, et
    le test anti-dérive échoue sans que rien de significatif n'ait changé.

    On résout les `$ref` de façon transitive : un schéma gardé peut en
    référencer un autre.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    if not schemas:
        return

    def refs(noeud: Any) -> set[str]:
        trouves: set[str] = set()
        if isinstance(noeud, dict):
            for cle, valeur in noeud.items():
                if cle == "$ref" and isinstance(valeur, str):
                    trouves.add(valeur.rsplit("/", 1)[-1])
                else:
                    trouves |= refs(valeur)
        elif isinstance(noeud, list):
            for element in noeud:
                trouves |= refs(element)
        return trouves

    gardes = refs(spec["paths"])
    # Fermeture transitive : un schéma gardé peut en référencer d'autres.
    a_explorer = set(gardes)
    while a_explorer:
        nom = a_explorer.pop()
        for suivant in refs(schemas.get(nom, {})):
            if suivant not in gardes:
                gardes.add(suivant)
                a_explorer.add(suivant)

    spec["components"]["schemas"] = {n: c for n, c in schemas.items() if n in gardes}
