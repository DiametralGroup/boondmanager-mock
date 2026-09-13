"""Construction du tableau `included` — formes réduites PAR MODULE.

La vraie API accompagne `data` d'un tableau `included` : pour chaque relation
`{id, type}`, l'entité cible y figure sous une forme RÉDUITE — et cette forme
varie selon le MODULE qui répond. Relevé RAML confirmé par les sondes réelles
du 2026-07-31 : la `company` incluse par /contacts porte
`{name, expertiseArea, thumbnail, state}`, celle d'/invoices `{name, thumbnail}` ;
l'`agency` d'/invoices ajoute `invoicesLockingStates` ; le `project` inclus par
/invoices porte SEPT relations.

Chaque module a donc sa table `{type → (attributs gardés, relations gardées)}` ;
un type absent de la table du module n'est PAS inclus (liste blanche stricte,
comme les schémas officiels). La clôture est transitive sur les relations
gardées, avec déduplication par (type, id).
"""

from __future__ import annotations

from typing import Any

#: type JSON:API → clé de collection dans le dataset.
TYPE_VERS_CLE: dict[str, str] = {
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

Forme = tuple[tuple[str, ...], tuple[str, ...]]

_PERSONNE: Forme = (("firstName", "lastName"), ())
_PERSONNE_RICHE: Forme = (("firstName", "lastName", "email1", "phone1", "phone2", "thumbnail"), ())
_NOM: Forme = (("name",), ())
_ACTION: Forme = (("startDate", "typeOf", "text"), ())
#: ┌─ LE CONTRAT DANS `included` N'EST PAS RÉDUIT ─────────────────────────────┐
#: │ Il ne portait que trois attributs, sur l'idée — écrite dans le docstring  │
#: │ de la route — qu'`included` livre une « forme réduite » et que le détail  │
#: │ vit sur `GET /contracts/{id}`.                                            │
#: │                                                                            │
#: │ Sondé le 2026-08-13 contre la production : `/resources/{id}/              │
#: │ administrative` rend les SEIZE attributs du contrat dans `included`,      │
#: │ `monthlySalary` compris et renseigné. La forme réduite était une          │
#: │ invention du mock.                                                        │
#: │                                                                            │
#: │ Ce que ça coûtait : `GET /contracts` répond 405 chez le fournisseur, donc │
#: │ `included` est le SEUL chemin praticable vers la rémunération. Un         │
#: │ consommateur qui s'y fie n'aurait rien trouvé en CI, et aurait conclu     │
#: │ — comme SPEC-DEVIATIONS #5 l'a fait — qu'aucun endpoint de rémunération   │
#: │ n'existe chez BoondManager.                                               │
#: │                                                                            │
#: │ ⚠️ Ces champs sont de la donnée RH. Le mock les sert parce que le          │
#: │    fournisseur les sert ; c'est au CONSOMMATEUR de minimiser à            │
#: │    l'extraction, et insights360 le fait par liste blanche.                │
#: └────────────────────────────────────────────────────────────────────────────┘
_CONTRAT: Forme = (
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

#: module (clé de dataset, ou `<clé>/profil` pour les détails) → {type → forme}.
#: Valeurs relevées dans les blocs `included` des schémas search/profile
#: officiels — cf. docs/UNVERIFIED-FIELDS.md pour la provenance.
FORMES_PAR_MODULE: dict[str, dict[str, Forme]] = {
    "actions": {
        "candidate": _PERSONNE_RICHE,
        "resource": _PERSONNE,
        "company": (("name", "phone1", "thumbnail"), ()),
        "contact": (
            ("firstName", "lastName", "email1", "phone1", "phone2", "thumbnail"),
            ("company",),
        ),
        "document": _NOM,
        "invoice": (("reference",), ("order",)),
        "opportunity": (("reference", "title"), ("contact", "company")),
        "order": (("reference", "number"), ("project",)),
        "project": (("reference",), ("contact", "company")),
    },
    "banking_transactions": {
        "bankingaccount": (("name", "title"), ("connection",)),
        "bankingconnection": (("bankName",), ()),
    },
    "business_units": {"resource": _PERSONNE},
    "candidates": {"action": _ACTION, "agency": _NOM, "pole": _NOM, "resource": _PERSONNE},
    "companies": {"action": _ACTION, "agency": _NOM, "pole": _NOM, "resource": _PERSONNE},
    "contacts": {
        "action": _ACTION,
        "agency": _NOM,
        "company": (("name", "expertiseArea", "thumbnail", "state"), ()),
        "pole": _NOM,
        "resource": _PERSONNE,
    },
    "invoices": {
        "agency": (("name", "invoicesLockingStates"), ()),
        "company": (("name", "thumbnail"), ()),
        "contact": _PERSONNE,
        "opportunity": (("title",), ()),
        "order": (("number", "reference"), ("mainManager", "project")),
        "pole": _NOM,
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
        "resource": _PERSONNE,
        "schedule": (("date", "title"), ()),
    },
    "opportunities": {
        "agency": _NOM,
        "company": (("name", "thumbnail", "canReadCompany"), ()),
        "contact": (("firstName", "lastName", "thumbnail", "canReadContact"), ()),
        "pole": _NOM,
        "resource": _PERSONNE,
    },
    "orders": {
        "agency": _NOM,
        "company": (("name", "thumbnail"), ()),
        "contact": _PERSONNE,
        "opportunity": (("title",), ()),
        "pole": _NOM,
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
        "resource": _PERSONNE,
    },
    "payments": {
        "agency": _NOM,
        "company": _NOM,
        "contact": _PERSONNE,
        "delivery": (("title",), ("dependsOn",)),
        "pole": _NOM,
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
        "resource": _PERSONNE,
    },
    "projects": {
        "agency": _NOM,
        "company": (("name", "thumbnail", "canReadCompany"), ()),
        "contact": (("firstName", "lastName", "canReadContact"), ()),
        "opportunity": (("title",), ()),
        "pole": _NOM,
        "resource": _PERSONNE,
    },
    "purchases": {
        "agency": _NOM,
        "company": _NOM,
        "contact": _PERSONNE,
        "delivery": (("title",), ("dependsOn",)),
        "pole": _NOM,
        "project": (("reference",), ()),
        "resource": _PERSONNE,
    },
    "resources": {"action": _ACTION, "agency": _NOM, "pole": _NOM, "resource": _PERSONNE},
    "times": {
        "agency": (("name", "workUnitRate"), ()),
        "batch": (("title",), ()),
        "company": _NOM,
        "delivery": (("title",), ()),
        "project": (("reference",), ("company",)),
        "resource": (("firstName", "lastName", "workUnitRate"), ()),
        "timesreport": (("term", "state", "workUnitRate"), ("agency", "resource")),
    },
    "times_reports": {"agency": _NOM, "resource": _PERSONNE},
    # ── Détails (profils) — listes blanches observées/RAML ───────────────────
    "resources/profil": {"agency": _NOM, "contract": _CONTRAT},
    "projects/profil": {
        "agency": _NOM,
        "company": (("name", "thumbnail", "canReadCompany"), ()),
        "opportunity": (("title",), ()),
    },
    "contracts/profil": {
        "agency": _NOM,
        "contract": (("typeOf", "startDate", "endDate"), ()),
        "document": _NOM,
        "resource": _PERSONNE,
    },
    "deliveries/profil": {
        "agency": _NOM,
        "company": _NOM,
        "contact": _PERSONNE,
        "contract": (("typeOf", "startDate", "endDate"), ()),
        "delivery": (("title",), ()),
        "document": _NOM,
        "opportunity": (("title",), ()),
        "project": (("reference",), ("company",)),
        "purchase": (("title",), ()),
        "resource": _PERSONNE,
    },
    "administrative": {
        "agency": _NOM,
        "candidate": _PERSONNE,
        "contract": _CONTRAT,
    },
    # `GET /companies/{id}/information` — TYPES observés en réel le 2026-09-13
    # (`agency`, `company`, `resource`) ; les attributs réduits de chaque type
    # ne l'ont PAS été : on reprend les formes minimales des autres modules.
    "companies/information": {
        "agency": _NOM,
        "company": _NOM,
        "resource": _PERSONNE,
    },
}

#: Repli pour les modules sans table dédiée (détails des modules secondaires).
FORMES_DEFAUT: dict[str, Forme] = {
    "resource": _PERSONNE,
    "agency": _NOM,
    "pole": _NOM,
    "businessunit": _NOM,
    "company": _NOM,
    "contact": _PERSONNE,
    "candidate": _PERSONNE,
    "action": _ACTION,
    "opportunity": (("title",), ()),
    "project": (("reference", "typeOf", "mode"), ("company",)),
    "order": (("number", "reference"), ("project",)),
    "invoice": (("reference",), ("order",)),
    "purchase": (("title", "subscription", "typeOf", "reference"), ("project", "company")),
    "delivery": (("title",), ("dependsOn",)),
    "timesreport": (("term", "state"), ("agency", "resource")),
    "contract": _CONTRAT,
    "bankingaccount": (("name", "title"), ("connection",)),
    "bankingconnection": (("bankName",), ()),
}


def _index(dataset: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """(type, id) → entité, sur toutes les collections du dataset."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for cle in TYPE_VERS_CLE.values():
        elements = dataset.get(cle)
        if isinstance(elements, list):
            for element in elements:
                index[(element["type"], element["id"])] = element
    return index


def _refs_de(item: dict[str, Any], gardees: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Les références {id, type} des relations d'un item (to-one et to-many)."""
    refs: list[dict[str, Any]] = []
    for nom, relation in (item.get("relationships") or {}).items():
        if gardees is not None and nom not in gardees:
            continue
        data = relation.get("data")
        for ref in data if isinstance(data, list) else ([data] if data else []):
            refs.append(ref)
    return refs


#: Attributs qui n'existent QUE dans les formes réduites (les items de base ne
#: les portent pas) — valeurs plausibles, clés observées en réel.
VALEURS_ABSENTES: dict[tuple[str, str], Any] = {
    ("agency", "invoicesLockingStates"): [],
    ("company", "canReadCompany"): True,
    ("contact", "canReadContact"): True,
    ("timesreport", "workUnitRate"): 1,
}


def _reduire(entite: dict[str, Any], forme: Forme) -> dict[str, Any]:
    """Projette une entité sur sa forme réduite `included`."""
    attrs_gardes, rels_gardees = forme
    attributs = entite.get("attributes", {})
    projetes: dict[str, Any] = {}
    for attr in attrs_gardes:
        if attr in attributs:
            projetes[attr] = attributs[attr]
        elif (entite["type"], attr) in VALEURS_ABSENTES:
            projetes[attr] = VALEURS_ABSENTES[(entite["type"], attr)]
    reduit: dict[str, Any] = {
        "id": entite["id"],
        "type": entite["type"],
        "attributes": projetes,
    }
    if rels_gardees:
        relations = {
            nom: rel
            for nom, rel in (entite.get("relationships") or {}).items()
            if nom in rels_gardees
        }
        if relations:
            reduit["relationships"] = relations
    return reduit


def construire_included(
    items: list[dict[str, Any]],
    dataset: dict[str, Any],
    module: str | None = None,
    index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Le tableau `included` d'une page (ou d'un détail), selon la table du module.

    Liste blanche stricte : un type absent de la table du module n'entre pas
    dans `included` — c'est le comportement des schémas officiels. Clôture
    transitive sur les relations gardées, tri stable par (type, id).
    """
    formes = FORMES_PAR_MODULE.get(module or "", FORMES_DEFAUT)
    if index is None:
        index = _index(dataset)
    inclus: dict[tuple[str, str], dict[str, Any]] = {}
    a_traiter = [ref for item in items for ref in _refs_de(item)]

    while a_traiter:
        ref = a_traiter.pop()
        cle = (ref["type"], ref["id"])
        if cle in inclus or ref["type"] not in formes:
            continue
        entite = index.get(cle)
        if entite is None:
            continue
        forme = formes[ref["type"]]
        inclus[cle] = _reduire(entite, forme)
        if forme[1]:
            a_traiter.extend(_refs_de(entite, forme[1]))

    def _cle_tri(entite: dict[str, Any]) -> tuple[str, int, str]:
        try:
            return (entite["type"], int(entite["id"]), "")
        except ValueError:
            return (entite["type"], 0, entite["id"])

    return sorted(inclus.values(), key=_cle_tri)
