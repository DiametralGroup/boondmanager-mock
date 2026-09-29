"""Modèles pydantic — la SOURCE du contrat OpenAPI.

┌─ POURQUOI TYPER, ET CE QUE ÇA COÛTE ────────────────────────────────────────┐
│ Avant, tous les handlers étaient `(request: Request) -> JSONResponse`. FastAPI │
│ générait donc un `/docs` qui documentait des CHEMINS et rien d'autre : aucune  │
│ forme de réponse, aucun champ. Un contrat vide n'est pas un contrat.          │
│                                                                                │
│ En typant, on obtient d'un coup : le contrat, la validation des réponses (le   │
│ générateur ne peut plus dériver en silence de la forme déclarée), et des types │
│ exploitables par les consommateurs.                                            │
│                                                                                │
│ Le coût est réel et il faut le nommer : **typer pousse à inventer des          │
│ champs**, ce que la spec d'insights360 interdit en toutes lettres. La parade   │
│ est structurelle, pas disciplinaire :                                          │
│                                                                                │
│   • `extra="allow"` partout — un champ inconnu de l'API réelle passe, il n'est │
│     simplement pas documenté. Le modèle décrit ce qu'on SAIT, pas ce qui EST.  │
│   • `x-boond-confidence` sur tout champ non adossé à une preuve de production. │
│   • un test échoue si un champ `unverified` n'est pas inscrit dans             │
│     docs/UNVERIFIED-FIELDS.md. L'honnêteté devient une contrainte de build.    │
└────────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


def unverified(description: str) -> dict[str, Any]:
    """Marque un champ dont le nom ou la forme n'est PAS attesté.

    À utiliser via `json_schema_extra`. Tout champ ainsi marqué DOIT figurer
    dans `docs/UNVERIFIED-FIELDS.md` — `tests/test_contract_is_current.py` le
    vérifie, pour que l'inventaire ne se dégrade pas en bonne intention.
    """
    return {"x-boond-confidence": "unverified", "x-boond-note": description}


def invented(description: str) -> dict[str, Any]:
    """Marque un champ ou un endpoint qui n'existe PAS chez le fournisseur.

    Distinct de `unverified` : ici on sait qu'on a fabriqué la forme, faute
    d'endpoint attesté. Le mode `stub` de la rémunération en est le seul usage.
    """
    return {"x-boond-confidence": "invented", "x-boond-note": description}


class Permissif(BaseModel):
    """Common base: unknown fields are accepted rather than rejected.

    A strict model would turn every evolution of the real API into a mock
    outage. The models describe what is emitted, not everything BoondManager
    may expose.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ── Enveloppe JSON:API ───────────────────────────────────────────────────────


class RefDonnee(Permissif):
    """The `{id, type}` reference of a JSON:API relationship."""

    id: str
    type: str


class Relation(Permissif):
    """A relationship. `data` may be null — an employee without a manager, say."""

    data: RefDonnee | None = None


class Totaux(Permissif):
    rows: int = Field(description="Total number of items BEFORE pagination.")


class Meta(Permissif):
    """The list `meta`, as the official schema describes it: `totals.rows`
    plus the server version, session state and language."""

    totals: Totaux
    version: str | None = Field(default=None, description="BoondManager version.")
    isLogged: bool | None = None
    language: str | None = Field(default=None, description="fr | en | es")


class MetaDetail(Permissif):
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


# ── Erreurs ──────────────────────────────────────────────────────────────────


class Erreur(Permissif):
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

    errors: list[Erreur]


# Réponses d'erreur déclarées sur chaque route : elles apparaissent au contrat
# sans passer par `response_model`, qui ne décrit que le cas nominal.
REPONSES_ERREUR: dict[int | str, dict[str, Any]] = {
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

# Paramètres de requête partagés par toutes les collections.
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


# ── Le dictionnaire des énumérations ─────────────────────────────────────────


class EntreeDictionnaire(Permissif):
    """Une correspondance code -> libellé, telle que l'INSTANCE la configure.

    C'est la seule source connue du rattachement : partout ailleurs l'API rend
    des entiers nus, et les libellés ne sont pas des constantes du produit.
    """

    id: int = Field(description="Le code numérique que l'API rend sur les autres routes.")
    value: str = Field(description="Le libellé configuré, tel qu'il s'affiche dans l'outil.")


class SettingDictionnaire(Permissif):
    """Les nomenclatures, groupées par famille.

    `state` est un DICT de sous-domaines (opportunity, candidate, resource) ;
    les autres familles sont des listes plates. Les deux formes coexistent chez
    l'éditeur — les uniformiser ici ferait diverger le mock du dialecte réel.

    `action` et `actionOnOpportunity` sont deux nomenclatures DISTINCTES qui
    partagent des libellés sous des codes différents. Les fondre ferait traduire
    un type d'action de besoin par un libellé général.
    """

    state: dict[str, list[EntreeDictionnaire]] = Field(
        json_schema_extra=invented(
            "Sous-domaines du dictionnaire. La ROUTE n'est attestee par aucun rapport "
            "de comparaison ; la forme est de notre fabrication."
        )
    )
    action: list[EntreeDictionnaire]
    actionOnCandidate: list[EntreeDictionnaire] = Field(
        json_schema_extra=invented(
            "Cle INFEREE de la convention de `action` et `actionOnOpportunity`. "
            "Ce qui est atteste : une nomenclature d'actions sur candidat existe "
            "dans l'instance (feuille Dashb du fichier de mappings)."
        )
    )
    actionOnOpportunity: list[EntreeDictionnaire]
    origin: list[EntreeDictionnaire]
    typeOf: dict[str, list[EntreeDictionnaire]] = Field(
        default_factory=dict,
        json_schema_extra=invented(
            "Symetrique de `state`. Ce qui est atteste : l'API rend un `typeOf` "
            "entier sur resource, candidate, opportunity, project et purchase, "
            "et n'en donne le libelle nulle part ailleurs. La FORME est de notre "
            "fabrication, comme celle de `state`."
        ),
    )


class DonneesDictionnaire(Permissif):
    setting: SettingDictionnaire


class EnveloppeDictionnaire(Permissif):
    """`{"data": {"setting": {...}}}` — objet unique, sans pagination ni `meta`."""

    data: DonneesDictionnaire
