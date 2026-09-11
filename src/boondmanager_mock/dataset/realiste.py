"""Le jeu de données : « Boréal Conseil », ESN française de 34 personnes.

UN SEUL jeu de données, complet et cohérent — les anciens profils `ophelie` et
`insights360` sont supprimés. Chaque collection suit la forme de réponse de la
documentation OFFICIELLE BoondManager (RAML + schémas JSON de
https://doc.boondmanager.com/api-externe/, relevés le 2026-07-30) :

  • les `type` JSON:API sont ceux du fournisseur, en minuscules
    (`timesreport`, `bankingtransaction`, `businessunit`…) ;
  • les noms d'attributs viennent des schémas `search.json` de chaque module —
    y compris la coquille officielle `numberbOfActiveOpportunity` des sociétés ;
  • les horodatages suivent le format du fournisseur
    (`2026-03-12T09:24:00+0100`, décalage SANS deux-points) ;
  • `/absences`, `/expenses` et `/times` portent leur contexte IMBRIQUÉ dans
    `attributes` (rapport, agence, ressource) — c'est le dialecte réel, pas une
    relation JSON:API.

La COHÉRENCE est la propriété centrale, parce que c'est elle qui rend le mock
comparable à une vraie instance :

  ressources ← contrats ; clients ← contacts ; opportunités gagnées → projets
  → missions (deliveries) → commandes → factures mensuelles (jours travaillés x
  TJM de la mission) → transactions bancaires des règlements ; achats →
  paiements fournisseurs ; CRA ← lignes de temps des mêmes jours travaillés que
  les factures ; absences et frais rattachés à leurs rapports.

Ce qui reste VOLONTAIREMENT approximatif, et documenté dans
docs/UNVERIFIED-FIELDS.md : la sémantique des entiers de dictionnaire
(`typeOf`, `state`…), propre à chaque instance BoondManager — les valeurs
choisies ici sont plausibles, pas attestées.

Déterminisme : `random.Random(seed)` et une ancre temporelle FIXE (15 juillet
2026). Jamais `datetime.now()` — deux exécutions produisent le même jeu de
données à l'octet près, c'est ce qui rend les tests aval reproductibles.
"""

from __future__ import annotations

import calendar
import random
from datetime import date, timedelta
from typing import Any

# ── Ancre temporelle ─────────────────────────────────────────────────────────

AUJOURDHUI = date(2026, 7, 15)
#: Mois couverts par les CRA, lignes de temps, frais et absences détaillés.
MOIS_ACTIVITE: tuple[tuple[int, int], ...] = ((2026, 5), (2026, 6), (2026, 7))
#: Premier mois facturé de l'exercice courant.
DEBUT_FACTURATION = date(2026, 1, 1)
#: Plafond de tous les `updateDate` — un curseur incrémental postérieur doit
#: rendre zéro ligne (cf. tests d'incrémentalité).
DERNIERE_MAJ = date(2026, 7, 12)

TVA = 0.20


def _tz(mois: int) -> str:
    """Décalage Europe/Paris, SANS deux-points — le format du fournisseur."""
    return "+0200" if 4 <= mois <= 10 else "+0100"


def _dt(d: date, h: int = 9, mn: int = 0, s: int = 0) -> str:
    return f"{d:%Y-%m-%d}T{h:02d}:{mn:02d}:{s:02d}{_tz(d.month)}"


def _d(d: date) -> str:
    return f"{d:%Y-%m-%d}"


def _fin_mois(annee: int, mois: int) -> date:
    return date(annee, mois, calendar.monthrange(annee, mois)[1])


def _jours_ouvres(annee: int, mois: int) -> int:
    """Jours ouvrés du mois (hors week-ends ; les fériés sont ignorés — mock)."""
    dernier = calendar.monthrange(annee, mois)[1]
    return sum(1 for j in range(1, dernier + 1) if date(annee, mois, j).weekday() < 5)


def _maj(rng: random.Random, apres: date) -> str:
    """Un `updateDate` plausible : postérieur à la création, jamais après l'ancre."""
    if apres >= DERNIERE_MAJ:
        return _dt(DERNIERE_MAJ, 8, 30)
    delta = (DERNIERE_MAJ - apres).days
    jour = apres + timedelta(days=rng.randint(0, delta))
    return _dt(jour, rng.randint(8, 18), rng.randint(0, 59), rng.randint(0, 59))


def _rel(type_: str, ident: Any) -> dict[str, Any]:
    """Une relation JSON:API. `ident` à None rend `{"data": null}` — le dialecte réel."""
    if ident is None:
        return {"data": None}
    return {"data": {"id": str(ident), "type": type_}}


# ── Catalogues ───────────────────────────────────────────────────────────────

_PRENOMS = [
    "Camille",
    "Jules",
    "Sofia",
    "Hugo",
    "Amara",
    "Louis",
    "Priya",
    "Arthur",
    "Emma",
    "Mateo",
    "Lina",
    "Gabriel",
    "Aïcha",
    "Rafael",
    "Yuki",
    "Nathan",
    "Olivia",
    "Diego",
    "Nina",
    "Youssef",
    "Ana",
    "Lars",
    "Wei",
    "Adam",
    "Chloé",
    "Théo",
    "Inès",
    "Maxime",
    "Sarah",
    "Paul",
    "Alice",
    "Antoine",
    "Clara",
    "Romain",
    "Léa",
    "Bastien",
    "Manon",
    "Kevin",
    "Julie",
    "Thomas",
]
_NOMS = [
    "Martin",
    "Silva",
    "Nakamura",
    "Okafor",
    "Rossi",
    "Muller",
    "Santos",
    "Dubois",
    "Moreau",
    "Laurent",
    "Kim",
    "Ivanov",
    "Fernandez",
    "Andersson",
    "Nguyen",
    "Costa",
    "Bertrand",
    "Haddad",
    "Meyer",
    "Garcia",
    "Patel",
    "Schmidt",
    "Lambert",
    "Oliveira",
    "Roux",
    "Fontaine",
    "Girard",
    "Blanc",
    "Perrin",
    "Chevalier",
    "Lemoine",
    "Renard",
    "Colin",
    "Marchand",
    "Dupuis",
    "Gauthier",
    "Meunier",
    "Brunet",
    "Faure",
    "Bourgeois",
]
#: Les fonctions SUPPORT, par identifiant de ressource.
#:
#: Le jeu ne produisait que des consultants et des managers : les seize types
#: de la feuille INDEX n'en voyaient que trois. Le fichier de mappings decrit
#: pourtant une organisation ou le STAFF pese un tiers de l'effectif —
#: recrutement, RH, finance, marketing, administratif.
#:
#: Les INTITULES sont ceux du referentiel `ref_type_collaborateur` cote
#: insights360 : c'est lui qui rattache un intitule de poste a son type, et la
#: correspondance se fait sur la CHAINE. Changer un libelle ici sans le changer
#: la-bas casse le rattachement en silence — le collaborateur ressort avec un
#: type nul, et rien ne le signale.
#:
#: ⚠️ IDENTIFIANTS CHOISIS HORS DE TOUTE FIXTURE. 11 est `kevin.silva` cote
#: insights360, 12 et 17 portent des etats particuliers, 1 et 2-6 sont la
#: direction et les managers, 22-34 sont reserves cote mock. 0.5.3 avait pose
#: un etat sur 11 et fait tomber un test negatif sans rapport : l'inventaire se
#: refait a chaque patch.
_TITRES_SUPPORT = {
    8: "Responsable acquisition de talents",
    10: "Chargé de recrutement",
    13: "Responsable ressources humaines",
    16: "Contrôleur de gestion",
    19: "Chargé de communication",
    20: "Assistant administratif",
}

_TITRES_CONSULTANT = [
    "Data Engineer",
    "Data Engineer senior",
    "Data Scientist",
    "ML Engineer",
    "Architecte cloud",
    "Consultant DevOps",
    "Développeur full-stack",
    "Tech Lead",
    "Consultant cybersécurité",
    "Product Owner",
    "Consultant data gouvernance",
    "Ingénieur plateforme",
]
_COMPETENCES = [
    "Python",
    "Spark",
    "dbt",
    "Snowflake",
    "Kafka",
    "Airflow",
    "Terraform",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "React",
    "FastAPI",
    "Power BI",
    "SQL",
    "Databricks",
]
_EXPERTISES = [
    "Data Engineering",
    "Data Science",
    "Cloud & Infrastructure",
    "Cybersécurité",
    "Product & Agilité",
    "Gouvernance des données",
]
_SECTEURS = [
    "Banque & Assurance",
    "Retail & Distribution",
    "Énergie & Utilities",
    "Industrie",
    "Télécoms & Médias",
    "Transport & Logistique",
    "Secteur public",
    "Santé & Pharma",
]
_DIPLOMES = [
    "Diplôme d'ingénieur — CentraleSupélec (2017)",
    "Master Informatique — Université de Nantes (2019)",
    "Master Data Science — Université Paris-Saclay (2020)",
    "Diplôme d'ingénieur — INSA Lyon (2016)",
    "Master MIAGE — Université Lyon 1 (2018)",
    "MSc Computer Science — EPFL (2015)",
]
_LANGUES = [
    ("FR", "Langue maternelle"),
    ("EN", "Courant"),
    ("ES", "Intermédiaire"),
    ("DE", "Notions"),
]

#: (nom, ville, code postal, adresse, SIREN+NIC, TVA, effectif)
_AGENCES = [
    (
        "Boréal Conseil Paris",
        "Paris",
        "75009",
        "24 rue de Châteaudun",
        "482 154 796 00031",
        "FR 62 482154796",
        21,
    ),
    (
        "Boréal Conseil Lyon",
        "Lyon",
        "69002",
        "18 quai Saint-Antoine",
        "482 154 796 00049",
        "FR 62 482154796",
        8,
    ),
    (
        "Boréal Conseil Nantes",
        "Nantes",
        "44000",
        "5 allée Duguay-Trouin",
        "482 154 796 00056",
        "FR 62 482154796",
        5,
    ),
    # ── Les deux entites etrangeres, et le DOUBLON deliberé ──────────────────
    #
    # ⚠️ CES DEUX PREMIERES LIGNES SONT UN CAS DE TEST, PAS DU REMPLISSAGE.
    # Le fichier de mappings montre la meme mecanique sur l'organisation
    # reelle : une entite majeure et son alias minoritaire, separes par un
    # suffixe juridique. `acl_role_perimetre` visant l'entite PAR SON LIBELLE,
    # une regle ecrite sur l'une exclut silencieusement les personnes de
    # l'autre — elles ne voient rien, personne ne les voit, et aucun compteur
    # ne bouge.
    #
    # `obs_entites_similaires` existe pour attraper ca et rendait ZERO paire,
    # faute de doublon dans le jeu. Il en a un maintenant.
    #
    # Les NOMS sont ceux du monde fictif : DATA-01 interdit le nom d'une
    # entite juridique reelle dans le depot. Seule la MECANIQUE est reprise.
    (
        "Boreal Conseil Bogota S.A.S",
        "Bogota",
        "110111",
        "Carrera 11 #93-46",
        "901 254 883-1",
        "CO 901254883",
        6,
    ),
    (
        "Boreal Conseil Bogota",
        "Bogota",
        "110111",
        "Carrera 11 #93-46",
        "901 254 883-1",
        "CO 901254883",
        2,
    ),
    # Une troisieme zone, pour que l'isolement entre PAYS cesse d'etre vacant :
    # tant qu'il n'y a qu'un pays, aucun test d'etancheite geographique ne
    # prouve quoi que ce soit — il passe faute de contre-exemple.
    (
        "Boreal Conseil Montreal",
        "Montreal",
        "H3B 2S2",
        "1250 boulevard Rene-Levesque O",
        "1148765432 RC0001",
        "CA 114876543",
        4,
    ),
]
_BUSINESS_UNITS = ["Data & IA", "Cloud & Plateformes", "Cybersécurité", "Transformation digitale"]
_POLES = [
    "Pôle Data Engineering",
    "Pôle Data Science & IA",
    "Pôle Cloud & SRE",
    "Pôle Sécurité opérationnelle",
    "Pôle Produit & Design",
    "Pôle Pilotage & PMO",
]

#: (nom, ville, secteur, site, prospect) — 10 clients puis 3 fournisseurs.
_CLIENTS = [
    ("Lumina Retail", "Paris", "Retail & Distribution", "https://lumina-retail.example", False),
    ("Banque Hexagone", "Paris", "Banque & Assurance", "https://banque-hexagone.example", False),
    ("Voltalis Énergie", "Lyon", "Énergie & Utilities", "https://voltalis-energie.example", False),
    ("Mutuelle Armor", "Nantes", "Banque & Assurance", "https://mutuelle-armor.example", False),
    (
        "TransEuropa Fret",
        "Lille",
        "Transport & Logistique",
        "https://transeuropa-fret.example",
        False,
    ),
    ("Pharmadis", "Lyon", "Santé & Pharma", "https://pharmadis.example", False),
    ("Citymob", "Bordeaux", "Transport & Logistique", "https://citymob.example", False),
    ("Assurial", "Bruxelles", "Banque & Assurance", "https://assurial.example", False),
    ("Groupe Ardentes", "Nantes", "Industrie", "https://groupe-ardentes.example", False),
    ("MediaQuartz", "Paris", "Télécoms & Médias", "https://mediaquartz.example", True),
    (
        "Fivetech Partners",
        "Paris",
        "Conseil & Services numériques",
        "https://fivetech-partners.example",
        False,
    ),
    ("Softalliance", "Paris", "Éditeur de logiciels", "https://softalliance.example", False),
    ("Foncière Beaumont", "Paris", "Immobilier", "https://fonciere-beaumont.example", False),
]
_ID_FOURNISSEUR_SOUSTRAITANCE = 11  # Fivetech Partners
_ID_FOURNISSEUR_LICENCES = 12  # Softalliance
_ID_FOURNISSEUR_LOYER = 13  # Foncière Beaumont

_FONCTIONS_CONTACT = [
    "DSI",
    "CTO",
    "Directeur Data",
    "Head of Data",
    "Responsable BI",
    "Directrice de la transformation",
    "Responsable achats IT",
    "CISO",
    "CFO",
    "Chef de projet MOA",
]
_SERVICES_CONTACT = [
    "Direction des systèmes d'information",
    "Direction Data",
    "Direction financière",
    "Direction digitale",
    "Achats",
    "Direction générale",
]

#: (titre-type de mission, outils dominants)
_SUJETS = [
    ("Refonte de la plateforme data", ["Snowflake", "dbt", "Airflow"]),
    ("Migration cloud des applications métier", ["AWS", "Terraform", "Kubernetes"]),
    ("Mise en place du socle MLOps", ["Databricks", "Python", "Kubernetes"]),
    ("Tableau de bord de pilotage finance", ["Power BI", "SQL", "dbt"]),
    ("Industrialisation des pipelines de données", ["Spark", "Kafka", "Airflow"]),
    ("Audit sécurité et remédiation", ["Kubernetes", "Terraform", "AWS"]),
    ("Data mesh — pilote domaine client", ["Snowflake", "dbt", "Kafka"]),
    ("Modernisation du SI e-commerce", ["React", "FastAPI", "GCP"]),
]

_TYPES_ABSENCE = [
    (20, "Congés payés"),
    (21, "RTT"),
    (22, "Maladie"),
    (23, "Congé exceptionnel"),
]
_TYPES_FRAIS = [
    (1, "Restauration", 10.0),
    (2, "Transport", 10.0),
    (3, "Hébergement", 10.0),
    (4, "Péage & carburant", 20.0),
]

# Sémantique de dictionnaire PLAUSIBLE (propre à l'instance — non attestée) :
# Les SIX états de l'instance (feuille INDEX du fichier de mappings, colonne
# IN/OUT/NEW). Un seul est sortant — « OFF » : un collaborateur en congé longue
# durée ou en préavis compte toujours dans l'effectif.
#
# ⚠️ LES ENTIERS RESTENT CEUX DU MOCK, ET ILS NE SONT PAS ATTESTÉS — pas plus
# qu'avant. Ce que ce bloc apporte, c'est le NOMBRE d'états et leur SÉMANTIQUE,
# les deux sourcés par la feuille INDEX. La correspondance code ↔ libellé, elle,
# ne se lit que dans `GET /application/dictionary`.
#
# La tentation était d'aligner sur le préfixe des libellés (« 06 - OFF » → 6),
# comme pour les opportunités. Elle est écartée : `stg_collaborateur.sql` a déjà
# tranché que ce préfixe est une convention d'AFFICHAGE. Pour les opportunités,
# deux sources indépendantes concordaient — le process Confluence ET l'export ;
# ici il n'y a que le préfixe, et une concordance ne fait pas une règle.
#
# Ce qui compte pour un mock : être cohérent avec son propre dictionnaire. Il
# l'est — le bloc ② déclare ces six entiers-là.
ETAT_RESSOURCE_SORTIE = 0  # OFF                      -> OUT
ETAT_RESSOURCE_ACTIVE = 1  # STAFFED                  -> IN
ETAT_RESSOURCE_INTEGRATION = 2  # HIRED - ONBOADING PHASE  -> NEW
ETAT_RESSOURCE_INTERCONTRAT = 3  # UN/IC - UNASIGNED [8 W]  -> IN
ETAT_RESSOURCE_CONGE_LONG = 4  # LONG TERM LEAVE          -> IN
ETAT_RESSOURCE_PREAVIS = 5  # LEAVING COMPANY          -> IN

#: Le regroupement IN de la feuille INDEX : tout sauf OFF. C'est la population
#: qui produit des faits — temps, absences, frais. Distinct de
#: `ETATS_STAFFABLES` (evolution.py), qui exclut en plus le conge longue duree :
#: on ne staffe pas quelqu'un en conge, mais il a bien une absence.
ETATS_DANS_L_EFFECTIF = (
    ETAT_RESSOURCE_ACTIVE,
    ETAT_RESSOURCE_INTEGRATION,
    ETAT_RESSOURCE_INTERCONTRAT,
    ETAT_RESSOURCE_CONGE_LONG,
    ETAT_RESSOURCE_PREAVIS,
)

#: Qui porte une mission a la construction du jeu. Distinct des deux autres
#: regroupements, et il faut les trois :
#:   ETATS_DANS_L_EFFECTIF  produit des faits (temps, absences, frais)
#:   ETATS_STAFFABLES       peut etre staffe par l'evolution (evolution.py)
#:   ETATS_AVEC_MISSION     porte deja une mission dans le jeu de depart
#:
#: Le conge longue duree est exclu — on ne staffe pas quelqu'un en conge. Le
#: PREAVIS ne l'est pas : il travaille jusqu'a son terme, et c'est ce que
#: `ETATS_STAFFABLES` affirmait deja. L'intercontrat garde son exclusion
#: explicite plus bas : il est AU BANC, c'est sa definition.
ETATS_AVEC_MISSION = (ETAT_RESSOURCE_ACTIVE, ETAT_RESSOURCE_PREAVIS)


# ═════════════════════════════════════════════════════════════════════════════
#  Référentiels : agences, BU, pôles, rôles
# ═════════════════════════════════════════════════════════════════════════════


def _agences() -> list[dict[str, Any]]:
    agences: list[dict[str, Any]] = []
    for i, (nom, ville, cp, adresse, immat, tva, effectif) in enumerate(_AGENCES, start=1):
        agences.append(
            {
                "id": str(i),
                "type": "agency",
                "attributes": {
                    "name": nom,
                    "calendar": "Standard",
                    "currency": 0,
                    "numberOfWorkingDays": 218,
                    "chargeFactor": 1.47,
                    "vatNumber": tva,
                    "registrationNumber": immat,
                    "address": adresse,
                    "postcode": cp,
                    "town": ville,
                    "country": "France",
                    "staff": effectif,
                    "state": True,
                    "workUnitRate": 1,
                    "workUnitRateOnProjectsAndOpportunities": 1,
                    "subDivision": "",
                },
            }
        )
    return agences


def _business_units(ressources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les BU. `includedManagers` : les managers rattachés (relation officielle)."""
    unites: list[dict[str, Any]] = []
    for i, nom in enumerate(_BUSINESS_UNITS, start=1):
        managers = [r for r in ressources if r["attributes"]["_bu"] == i and int(r["id"]) <= 6]
        unites.append(
            {
                "id": str(i),
                "type": "businessunit",
                "attributes": {
                    "name": nom,
                },
                "relationships": {
                    "includedManagers": {
                        "data": [{"id": m["id"], "type": "resource"} for m in managers]
                    }
                },
            }
        )
    return unites


def _poles() -> list[dict[str, Any]]:
    return [
        {
            "id": str(i),
            "type": "pole",
            "attributes": {
                "name": nom,
                "state": True,
            },
        }
        for i, nom in enumerate(_POLES, start=1)
    ]


def _roles() -> list[dict[str, Any]]:
    lignes = [
        # (nom, comptes, actifs, agences secondaires, pôles secondaires, typeOf, système)
        ("Administrateur", 2, 2, True, True, "manager", True),
        ("Direction", 3, 3, True, True, "manager", False),
        ("Manager d'agence", 5, 5, False, True, "manager", False),
        ("Responsable RH", 2, 2, False, False, "manager", False),
        ("Consultant intranet", 28, 26, False, False, "intranet", True),
    ]
    return [
        {
            "id": str(i),
            "type": "role",
            "attributes": {
                "name": nom,
                "numberOfAccounts": comptes,
                "numberOfActiveAccounts": actifs,
                "isSecondaryAgenciesAllowed": ag,
                "isSecondaryPolesAllowed": po,
                "typeOf": type_of,
                "isSystem": systeme,
            },
        }
        for i, (nom, comptes, actifs, ag, po, type_of, systeme) in enumerate(lignes, start=1)
    ]


# ═════════════════════════════════════════════════════════════════════════════
#  Ressources et contrats
# ═════════════════════════════════════════════════════════════════════════════

#: ids 1-6 : direction et managers ; 7-30 consultants ; 31-32 en intégration ;
#: 33-34 sortis. Les sous-traitants portent typeOf 1.
_NB_RESSOURCES = 34
_IDS_MANAGERS = (2, 3, 4, 5, 6)
_IDS_SOUS_TRAITANTS = (23, 24)
_IDS_INTEGRATION = (31, 32)
_IDS_SORTIS = (33, 34)

#: ┌─ CAS LIMITES D'AUTORISATION ───────────────────────────────────────────────┐
#: │ Ces cohortes ne servent pas la vraisemblance : elles servent à ce qu'un    │
#: │ modèle d'autorisation construit sur ce jeu de données PUISSE ÉCHOUER.      │
#: │ Un jeu uniforme rend un test de visibilité vrai par vacuité — il passe     │
#: │ aussi bien avec un modèle correct qu'avec un modèle cassé.                 │
#: └────────────────────────────────────────────────────────────────────────────┘

#: Deux personnes de MÊME prénom et MÊME nom, dans deux agences différentes.
#: C'est le cas limite le plus dangereux du lot : un consommateur qui dérive un
#: identifiant d'annuaire (UPN, e-mail) du seul « prénom.nom » leur attribue la
#: même identité, et FUSIONNE leurs périmètres de visibilité. Ce n'est pas un
#: défaut cosmétique, c'est une escalade de privilège silencieuse. Leurs
#: adresses sont donc délibérément distinctes — la résolution de collision par
#: ordinal est ce que le consommateur doit reproduire.
_IDS_HOMONYMES = (27, 28)

#: Une personne dont l'agence de rattachement a changé en cours d'année. Ses
#: faits (temps, missions) restent portés par l'agence où ils ont été produits,
#: pas par son agence actuelle. Un modèle qui rattache les faits au
#: collaborateur plutôt qu'à la ligne de fait réécrit rétroactivement
#: l'historique — invisible tant qu'aucun collaborateur ne bouge.
_ID_MUTATION = 22
_AGENCE_AVANT_MUTATION = 2
#: Mois de la mutation : les CRA ANTÉRIEURS portent l'ancienne agence.
#: Choisi DANS la fenêtre MOIS_ACTIVITE (mai-juillet 2026), sans quoi le cas
#: n'existe pas : aucun CRA ne tomberait du bon côté de la bascule.
_MOIS_MUTATION = 6

#: Mois de sortie des ressources sorties. Elles conservent leur historique
#: JUSQU'À ce mois, et rien après. Également choisi dans MOIS_ACTIVITE, pour
#: que « a produit puis est parti » soit observable et non seulement déclaré.
_MOIS_SORTIE = 5


def _etat_ressource(i: int, *, sorti: bool, integration: bool) -> int:
    """L'etat d'une ressource, dans la nomenclature a SIX valeurs de l'instance.

    Un seul etat est sortant. Un collaborateur en intercontrat, en conge longue
    duree ou en preavis compte toujours dans l'effectif — c'est le regroupement
    IN/OUT/NEW de la feuille INDEX.

    Les identifiants d'intercontrat sont ceux sur lesquels `en_intercontrat` est
    deja calcule plus bas : l'information existait dans le jeu sans que l'API la
    rende jamais.
    """
    if sorti:
        return ETAT_RESSOURCE_SORTIE
    if integration:
        return ETAT_RESSOURCE_INTEGRATION
    if i in (25, 26, 29, 30):
        return ETAT_RESSOURCE_INTERCONTRAT
    # 17 et non 11 : l'identifiant 11 est `kevin.silva`, la fixture
    # « connu du SIRH, dans aucun groupe Entra » des tests d'autorisation
    # d'insights360. Lui donner un etat particulier casse un cas limite qui
    # n'a rien a voir. 12 et 17 ne portent aucune fixture, des deux cotes.
    if i == 17:
        return ETAT_RESSOURCE_CONGE_LONG
    if i == 12:
        return ETAT_RESSOURCE_PREAVIS
    return ETAT_RESSOURCE_ACTIVE


def _ressources(rng: random.Random) -> list[dict[str, Any]]:
    ressources: list[dict[str, Any]] = []
    for i in range(1, _NB_RESSOURCES + 1):
        if i in _IDS_HOMONYMES:
            # Même prénom ET même nom pour les deux : cf. _IDS_HOMONYMES.
            prenom, nom = "Camille", "Fontaine"
        else:
            prenom = _PRENOMS[(i * 7) % len(_PRENOMS)]
            nom = _NOMS[(i * 11) % len(_NOMS)]
        est_direction = i == 1
        est_manager = i in _IDS_MANAGERS
        sorti = i in _IDS_SORTIS
        integration = i in _IDS_INTEGRATION
        sous_traitant = i in _IDS_SOUS_TRAITANTS

        agence = 1 if i in (1, 2, 3) else (2 if i % 3 == 0 else (3 if i % 7 == 0 else 1))
        if i in _IDS_HOMONYMES:
            # Deux agences distinctes : c'est ce qui rend le cas discriminant.
            # Homonymes dans la même agence, une fusion d'identité ne changerait
            # aucun périmètre et le test resterait vert à tort.
            agence = 1 if i == _IDS_HOMONYMES[0] else 3
        pole = ((i - 1) % len(_POLES)) + 1
        bu = ((i - 1) % len(_BUSINESS_UNITS)) + 1
        if est_direction:
            titre = "Directeur général"
        elif est_manager:
            titre = rng.choice(["Directeur d'agence", "Manager de BU", "Directrice des opérations"])
        else:
            # Le STAFF d'abord, le consultant en repli. Ecrit en TERNAIRE et non
            # en `elif` : la branche supplementaire faisait passer la fonction a
            # 13 embranchements, au-dessus du seuil PLR0912 du depot. Le `if`
            # garde l'appel a rng.choice hors du chemin support — l'appeler pour
            # rien decalerait la sequence aleatoire et changerait les titres de
            # TOUS les autres consultants.
            titre = _TITRES_SUPPORT[i] if i in _TITRES_SUPPORT else rng.choice(_TITRES_CONSULTANT)

        if integration:
            embauche = date(2026, 7, 1)
        elif sorti:
            embauche = date(2019 + i % 4, rng.randint(1, 12), 1)
        else:
            embauche = date(rng.randint(2016, 2025), rng.randint(1, 12), 1)
        experience = max(1, 2026 - embauche.year + rng.randint(0, 6))

        tjm = 0.0
        if not est_direction and not est_manager:
            senior = "senior" in titre or "Lead" in titre or experience >= 8
            tjm = float(rng.choice([780, 850, 920] if senior else [520, 580, 640, 700]))

        etat = _etat_ressource(i, sorti=sorti, integration=integration)
        courriel = f"{prenom.lower()}.{nom.lower()}@boreal-conseil.example"
        if i == _IDS_HOMONYMES[1]:
            # Résolution de collision par ordinal. Le SECOND porte le suffixe :
            # c'est la convention des annuaires, et elle rend le cas asymétrique
            # — un consommateur qui suffixerait les deux passerait quand même.
            courriel = f"{prenom.lower()}.{nom.lower()}2@boreal-conseil.example"
        competences = rng.sample(_COMPETENCES, k=rng.randint(4, 6))
        en_intercontrat = i in (25, 26, 29, 30)

        ressources.append(
            {
                "id": str(i),
                "type": "resource",
                "attributes": {
                    "creationDate": _dt(embauche - timedelta(days=rng.randint(20, 90)), 11, 5),
                    "civility": i % 2,
                    "thumbnail": "",
                    "firstName": prenom,
                    "lastName": nom,
                    "reference": f"BC-{i:04d}",
                    "typeOf": 1 if sous_traitant else 0,
                    "state": etat,
                    "isVisible": not sorti,
                    "skills": ", ".join(competences),
                    "mobilityAreas": rng.choice(
                        [
                            ["Île-de-France"],
                            ["Île-de-France", "Télétravail total"],
                            ["Auvergne-Rhône-Alpes"],
                            ["Pays de la Loire", "Bretagne"],
                        ]
                    ),
                    "title": titre,
                    "availability": "immediate" if en_intercontrat else _d(date(2026, 9, 1)),
                    "forceAvailability": False,
                    "realAvailability": _d(AUJOURDHUI) if en_intercontrat else "",
                    "averageDailyPriceExcludingTax": tjm,
                    "email1": courriel,
                    "email2": f"{prenom.lower()}.{nom.lower()}@courriel.example",
                    "email3": "",
                    "phone1": f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} "
                    f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
                    "phone2": "",
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "numberOfResumes": rng.randint(1, 3),
                    "numberOfActivePositionings": rng.randint(1, 3) if en_intercontrat else 0,
                    "updateDate": _maj(rng, date(2026, rng.randint(1, 6), rng.randint(1, 28))),
                    "tools": [{"tool": c, "level": rng.randint(3, 5)} for c in competences[:4]],
                    "expertiseAreas": rng.sample(_EXPERTISES, k=2),
                    "activityAreas": rng.sample(_SECTEURS, k=2),
                    "diplomas": [rng.choice(_DIPLOMES)],
                    "experience": experience,
                    "references": [],  # rempli après création des projets
                    "languages": [
                        {"language": code, "level": niveau}
                        for code, niveau in rng.sample(_LANGUES, k=2)
                    ],
                    "canShowTechnicalData": True,
                    "canShowActions": True,
                    "socialNetworks": [
                        {
                            "network": "linkedin",
                            "url": f"https://www.linkedin.com/in/{prenom.lower()}-{nom.lower()}",
                        }
                    ],
                    # Clé INTERNE au générateur (retirée avant publication).
                    "_bu": bu,
                },
                "relationships": {
                    "mainManager": _rel(
                        "resource",
                        None
                        if est_direction
                        else (1 if est_manager else rng.choice(_IDS_MANAGERS)),
                    ),
                    # Le réel émet toujours la clé hrManager ; le RH (id 4) suit
                    # les consultants, la direction n'en a pas.
                    "hrManager": _rel("resource", 4 if i >= 7 else None),
                    "agency": _rel("agency", agence),
                    "pole": _rel("pole", pole),
                },
            }
        )
    return ressources


def _contrats(
    ressources: list[dict[str, Any]], rng: random.Random, graine: int
) -> list[dict[str, Any]]:
    """Un contrat par salarié, plus six historiques CDD → CDI chaînés."""
    contrats: list[dict[str, Any]] = []
    ident = 1

    def _salaire(res: dict[str, Any]) -> float:
        tjm = res["attributes"]["averageDailyPriceExcludingTax"]
        if res["attributes"]["title"] == "Directeur général":
            return 9800.0
        if int(res["id"]) in _IDS_MANAGERS:
            return float(rng.choice([6200, 6800, 7400]))
        return round((tjm or 600) * 4.6 + rng.randint(-150, 150), 0)

    avec_cdd = {7, 9, 12, 15, 18, 21}
    for res in ressources:
        if res["attributes"]["typeOf"] == 1:
            continue  # les sous-traitants n'ont pas de contrat de travail ici
        rid = int(res["id"])
        embauche = date.fromisoformat(res["attributes"]["creationDate"][:10]) + timedelta(days=30)
        sortie = rid in _IDS_SORTIS
        mensuel = _salaire(res)

        precedent: int | None = None
        if rid in avec_cdd:
            fin_cdd = embauche + timedelta(days=180)
            contrats.append(
                _contrat(
                    ident,
                    res,
                    "CDD",
                    embauche,
                    fin_cdd,
                    mensuel=mensuel * 0.92,
                    rng=rng,
                    graine=graine,
                    enfant=ident + 1,
                )
            )
            precedent = ident
            ident += 1
            embauche = fin_cdd + timedelta(days=1)

        fin = _fin_mois(2026, 5) if sortie else None
        contrats.append(
            _contrat(
                ident,
                res,
                "CDI",
                embauche,
                fin,
                mensuel=mensuel,
                rng=rng,
                graine=graine,
                parent=precedent,
            )
        )
        ident += 1
    return contrats


def _contrat(
    ident: int,
    res: dict[str, Any],
    nature: str,
    debut: date,
    fin: date | None,
    *,
    mensuel: float,
    rng: random.Random,
    graine: int,
    parent: int | None = None,
    enfant: int | None = None,
) -> dict[str, Any]:
    # ┌─ LE COÛT JOURNALIER N'EST PAS DÉRIVABLE DU BRUT ────────────────────────┐
    # │ Il valait `mensuel * 12 * 1.47 / 218` — le brut annuel chargé, étalé sur │
    # │ les jours travaillés. La formule est plausible, et elle est FAUSSE.      │
    # │                                                                          │
    # │ Éprouvée le 2026-09-10 contre 25 contrats de production :                │
    # │   1 vérifie à moins de 1 %, 24 non. Écart relatif médian 11,7 %,         │
    # │   maximum 44,2 %.                                                        │
    # │                                                                          │
    # │ Le fournisseur calcule autre chose — vraisemblablement charges patronales │
    # │ réelles et avantages compris. Servir une valeur qui se dérive             │
    # │ exactement du brut inviterait un consommateur à « retrouver » une         │
    # │ relation qui n'existe pas, puis à recalculer le coût lui-même plutôt      │
    # │ qu'à lire le champ. Le décalage ci-dessous est DÉTERMINISTE (dérivé de    │
    # │ l'identifiant) et suffisant pour casser la formule.                       │
    # └──────────────────────────────────────────────────────────────────────────┘
    cout_jour = round(mensuel * 12 * 1.47 / 218 * (0.88 + (ident * 37 % 45) / 100), 2)
    # Le réel émet TOUJOURS les clés parentContract/childContract (data null).
    rels: dict[str, Any] = {
        "dependsOn": _rel("resource", res["id"]),
        "createdBy": _rel("resource", 4),
        "agency": res["relationships"]["agency"],
        "parentContract": _rel("contract", parent),
        "childContract": _rel("contract", enfant),
        "files": {"data": []},
    }
    return {
        "id": str(ident),
        "type": "contract",
        "attributes": {
            "typeOf": 0 if nature == "CDI" else 1,
            "creationDate": _dt(debut - timedelta(days=15), 14, 30),
            "updateDate": _maj(rng, debut),
            "employeeType": 0,
            "workingTimeType": 0,
            "numberOfHoursPerWeek": 38.5,
            "classification": rng.choice(
                ["Syntec 2.1 coef 115", "Syntec 2.2 coef 130", "Syntec 3.1 coef 170"]
            ),
            "startDate": _d(debut),
            "endDate": _d(fin) if fin else "",
            "endReason": 3 if fin and nature == "CDI" else 0,
            "probationState": 2,
            "monthlySalary": mensuel,
            "hourlySalary": round(mensuel / 151.67, 2),
            "forceHourlySalary": False,
            "contractAverageDailyCost": cout_jour,
            # ┌─ TROIS CHAMPS QUE LE MOCK REMPLISSAIT ET QUE LA PROD LAISSE ──┐
            # │ Mesuré le 2026-09-10 sur 18 contrats : `dailyExpenses`,        │
            # │ `monthlyExpenses`, `expensesDetails` et `calendar` sont SERVIS │
            # │ mais renseignés ZÉRO fois. Le mock les remplissait sur 38 sur  │
            # │ 38 — la fiction la plus crédible qui soit, et donc la plus     │
            # │ coûteuse : un consommateur qui bâtissait dessus était vert en  │
            # │ CI et trouvait une colonne vide en production. Même famille    │
            # │ qu'`isDeleted`.                                                 │
            # │                                                                 │
            # │ Les clés restent émises — le fournisseur les émet — avec la    │
            # │ valeur qu'il leur donne : vide.                                 │
            # └─────────────────────────────────────────────────────────────────┘
            "dailyExpenses": 0,
            "monthlyExpenses": 0,
            "numberOfWorkingDays": 218,
            "chargeFactor": 1.47,
            "expensesDetails": [],
            "advantageTypes": _types_avantages(res, graine),
            "informationComments": "",
            "currency": 0,
            "currencyAgency": 0,
            "exchangeRate": 1.0,
            "exchangeRateAgency": 1.0,
            "calendar": "",
            # Renseigné ZÉRO fois sur 18 en production. Le servir à 100 laissait
            # croire qu'on pouvait pondérer un brut par ce taux — ce qui a
            # coûté 800 lignes de rémunération à zéro chez un consommateur.
            "activityRate": 0,
            "partialWorkTimes": [],
            "isPartialWorkTimeEvenOdd": False,
            # Émission ÉPARSE, comme le réel : la clé est absente sur un tiers
            # des contrats, elle n'est pas nulle. Un consommateur qui suppose
            # la clé présente doit tomber ici, pas en production.
            **(
                {
                    "probationEndDate": _d(debut + timedelta(days=120)),
                    "renewalProbationEndDate": "",
                }
                if ident % 3
                else {}
            ),
        },
        "relationships": rels,
    }


#: Le catalogue d'avantages de Boréal Conseil — configuration d'instance, donc
#: propre au monde fictif du mock. Sa FORME, elle, est celle relevée en
#: production le 2026-09-10, pièges compris :
#:
#:   • `reference` n'est PAS un code global — le même 21 sert ici deux libellés
#:     différents, exactement comme chez le fournisseur ;
#:   • `category` ne dit pas ce qui est acquis : « Variable » est `fixedAmount`
#:     et « Prime de vacances » est `variableSalaryBasis` ;
#:   • les trois quotas ne sont pas interchangeables, et aucun n'est « le
#:     montant » — selon la ligne, un seul est renseigné, ou deux.
#:
#: (reference, name, frequency, category, participation, employee, agency)
CATALOGUE_AVANTAGES: tuple[tuple[int, str, str, str, float, float, float], ...] = (
    (7, "Titre restaurant", "daily", "package", 5.83, 5.83, 0.0),
    (6, "Abonnement transport", "monthly", "package", 0.0, 45.4, 0.0),
    (8, "Prime de vacances", "semiAnnual", "variableSalaryBasis", 0.0, 800.0, 12.0),
    (21, "Variable", "annual", "fixedAmount", 0.0, 3000.0, 1.5),
    (21, "Mutuelle", "monthly", "fixedAmount", 0.0, 38.5, 38.5),
    (4, "Prime exceptionnelle", "annual", "fixedAmount", 0.0, 500.0, 0.0),
)


#: Décalage de graine des flux AUXILIAIRES.
#:
#: ┌─ POURQUOI CES GÉNÉRATEURS NE TIRENT PAS DANS `rng` ──────────────────────┐
#: │ Le jeu de données est déterministe par construction : `random.Random(42)` │
#: │ et une ancre temporelle fixe. Mais le déterminisme n'est pas la seule     │
#: │ propriété qui compte — la STABILITÉ entre deux versions du mock en est    │
#: │ une autre, et elle est plus fragile.                                      │
#: │                                                                           │
#: │ Un tirage ajouté au MILIEU du flux partagé décale tout ce qui est généré  │
#: │ après lui. Mesuré en ajoutant les avantages : les lignes de temps         │
#: │ passaient de 61 à 60, sans qu'une seule ligne de leur générateur ait      │
#: │ bougé, et un test de pagination tombait à l'autre bout du dépôt. Chez le  │
#: │ consommateur, c'est pire : insights360 compare des ENSEMBLES              │
#: │ D'IDENTIFIANTS (le gate `inner ⊆ outer`), qui n'ont plus de sens si le    │
#: │ monde bouge sous eux.                                                     │
#: │                                                                           │
#: │ Les générateurs ajoutés après coup tirent donc dans un flux DÉRIVÉ de la  │
#: │ graine, jamais dans le flux principal. Tout ce qui existait déjà reste    │
#: │ octet pour octet identique.                                               │
#: └───────────────────────────────────────────────────────────────────────────┘
DECALAGE_AVANTAGES = 1_000_003


def _types_avantages(res: dict[str, Any], graine: int) -> list[dict[str, Any]]:
    """Le package contractuel d'une ressource — de zéro à quatre lignes.

    La cardinalité est VARIABLE parce qu'elle l'est en production (de 0 à 5 sur
    l'échantillon) : un jeu où chaque contrat porte exactement une ligne laisse
    passer vert un modèle qui ne sait traiter que ce cas.
    """
    ident = int(res["id"])
    rng = random.Random(graine * DECALAGE_AVANTAGES + ident)
    # ┌─ NE PAS SÉLECTIONNER PAR MODULO SUR L'IDENTIFIANT ──────────────────────┐
    # │ Ce test valait `ident % 7 == 0`, et `_avantages_verses` gardait les      │
    # │ `ident % 3 == 0`. Les deux ont écarté EXACTEMENT la même cohorte : les   │
    # │ ressources 7, 14 et 28 — c'est-à-dire toute l'agence de Nantes, la seule │
    # │ entité qui distingue deux rôles BI chez le consommateur.                 │
    # │                                                                          │
    # │ Conséquence : son gate de cloisonnement voyait les deux rôles compter    │
    # │ le même nombre de lignes et ne pouvait rien prouver. Un jeu de données   │
    # │ qui laisse un axe métier vide rend le test VERT PAR VACUITÉ.             │
    # │                                                                          │
    # │ Un identifiant n'est pas une variable aléatoire : ici il est attribué    │
    # │ par agence, donc tout modulo se corrèle à l'agence. Le tirage passe donc │
    # │ par le flux dédié, et `test_chaque_agence_porte_du_package` garantit la  │
    # │ couverture plutôt que de l'espérer.                                      │
    # └──────────────────────────────────────────────────────────────────────────┘
    if rng.random() < 0.15:  # quelques contrats n'ont aucun avantage
        return []
    combien = rng.randint(1, 4)
    return [
        {
            "reference": reference,
            "name": nom,
            "frequency": frequence,
            "category": categorie,
            "participationQuota": participation,
            "employeeQuota": employe,
            "agencyQuota": agence,
        }
        for reference, nom, frequence, categorie, participation, employe, agence in rng.sample(
            CATALOGUE_AVANTAGES, combien
        )
    ]


def _avantages_verses(
    ressources: list[dict[str, Any]],
    contrats: list[dict[str, Any]],
    graine: int,
) -> list[dict[str, Any]]:
    """L'onglet « Avantages versés » — une ligne par versement, datée.

    ┌─ C'EST ICI QUE VIT LE VARIABLE ────────────────────────────────────────┐
    │ Relevé en production le 2026-09-10 : `GET /resources/{id}/advantages`   │
    │ rend 200 et `meta.totals.rows` = 54 sur une ressource, avec un          │
    │ historique 2020 → 2026. On y lit « Prime sur lettre d'Objectifs »,      │
    │ « Prime exceptionnelle », « Prime de vacances ».                        │
    │                                                                         │
    │ Trois propriétés que le jeu de données REPRODUIT, parce qu'elles        │
    │ décident de la stratégie d'un consommateur :                            │
    │   1. ÉPARSE — six ressources sur huit n'ont aucune ligne. C'est le cas  │
    │      normal, pas le cas dégradé.                                        │
    │   2. TRÈS INÉGALE — une poignée de personnes concentre des dizaines de  │
    │      lignes. Un jeu uniforme cacherait le coût de la pagination.        │
    │   3. RATTACHÉE AU CONTRAT en vigueur À LA DATE du versement, pas au     │
    │      contrat courant : une personne peut en avoir huit successifs, et   │
    │      un versement de 2020 ne se rattache pas au contrat de 2026.        │
    └─────────────────────────────────────────────────────────────────────────┘

    Pas d'`updateDate` : le fournisseur n'en rend pas, donc aucun curseur n'est
    possible. Le servir ici inviterait à bâtir une extraction incrémentale qui
    ne rapatrierait rien en production.
    """
    # Flux DÉDIÉ — cf. l'encadré de `DECALAGE_AVANTAGES` : tirer dans le flux
    # partagé décalerait tout ce qui est généré ensuite.
    rng = random.Random(graine * DECALAGE_AVANTAGES + 7)

    par_ressource: dict[str, list[dict[str, Any]]] = {}
    for contrat in contrats:
        rid = contrat["relationships"]["dependsOn"]["data"]["id"]
        par_ressource.setdefault(rid, []).append(contrat)

    # ┌─ CHAQUE AGENCE PORTE DES VERSEMENTS, PAR CONSTRUCTION ─────────────────┐
    # │ Le tirage était `ident % 3 == 0`, et il a vidé toute l'agence de        │
    # │ Nantes (7, 14, 28) — cf. l'encadré de `_types_avantages`. On force donc │
    # │ au moins un bénéficiaire par agence AVANT le tirage aléatoire : la      │
    # │ couverture d'un axe métier ne se laisse pas au hasard.                  │
    # └─────────────────────────────────────────────────────────────────────────┘
    # Le TÉMOIN : la ressource au long historique, analogue de la fiche 583 en
    # production (54 versements, 2020 → 2026). C'est elle qui éprouve la
    # pagination chez le consommateur — un tirage aléatoire ne doit pas
    # pouvoir la faire disparaître.
    obligatoires: set[str] = {"3"}
    agences_couvertes: set[str] = set()
    for res in ressources:
        if not par_ressource.get(res["id"]):
            continue
        agence = ((res["relationships"].get("agency") or {}).get("data") or {}).get("id")
        if agence is not None and agence not in agences_couvertes:
            agences_couvertes.add(agence)
            obligatoires.add(res["id"])

    avantages: list[dict[str, Any]] = []
    suivant = 9000
    for res in ressources:
        rid = res["id"]
        siens = par_ressource.get(rid) or []
        if not siens:
            continue
        ident = int(rid)
        # Un tiers environ reçoit quelque chose, plus les obligatoires. Le
        # témoin — la ressource 3 — en concentre plusieurs dizaines, comme la
        # fiche 583 en production.
        if rid not in obligatoires and rng.random() >= 0.35:
            continue
        combien = 42 if ident == 3 else rng.randint(1, 6)

        for _ in range(combien):
            porteur = rng.choice(siens)
            debut = date.fromisoformat(porteur["attributes"]["startDate"])
            fin_txt = porteur["attributes"]["endDate"]
            fin = date.fromisoformat(fin_txt) if fin_txt else AUJOURDHUI
            if fin <= debut:
                continue
            # Versé PENDANT le contrat porteur : c'est ce qui rend la relation
            # `contract` vérifiable plutôt que décorative.
            verse = debut + timedelta(days=rng.randint(0, (fin - debut).days))
            reference, nom, _freq, _cat, _p, employe, _a = rng.choice(CATALOGUE_AVANTAGES)
            quantite = rng.choice([1, 1, 1, 1, 15, 20, 21, 23])
            suivant += 1
            avantages.append(
                {
                    "id": str(suivant),
                    "type": "advantage",
                    "attributes": {
                        "date": _d(verse),
                        "quantity": quantite,
                        "costPaid": round(employe * quantite, 2),
                        # Vide sur tout l'échantillon de production.
                        "returnDate": "",
                        "currency": 0,
                        "currencyAgency": 0,
                        "exchangeRate": 1,
                        "exchangeRateAgency": 1,
                        "canReadAdvantage": True,
                        "canWriteAdvantage": True,
                        "advantageType": {"reference": reference, "name": nom},
                    },
                    "relationships": {
                        "contract": _rel("contract", int(porteur["id"])),
                        "agency": res["relationships"]["agency"],
                    },
                }
            )
    return avantages


# ═════════════════════════════════════════════════════════════════════════════
#  Candidats
# ═════════════════════════════════════════════════════════════════════════════


def _candidats(rng: random.Random) -> list[dict[str, Any]]:
    sources = [
        (1, "LinkedIn"),
        (2, "Cooptation"),
        (3, "Site carrière"),
        (4, "Chasse"),
        (5, "Salon Big Data Paris"),
    ]
    candidats: list[dict[str, Any]] = []
    for i in range(1, 13):
        prenom = _PRENOMS[(i * 13 + 3) % len(_PRENOMS)]
        nom = _NOMS[(i * 17 + 5) % len(_NOMS)]
        creation = date(2026, rng.randint(1, 6), rng.randint(1, 28))
        etat = [0, 1, 1, 2, 2, 3, 4, 5][i % 8]
        titre = rng.choice(_TITRES_CONSULTANT)
        competences = rng.sample(_COMPETENCES, k=4)
        type_source, detail_source = rng.choice(sources)
        candidats.append(
            {
                "id": str(i),
                "type": "candidate",
                "attributes": {
                    "creationDate": _dt(creation, 10, 12),
                    "updateDate": _maj(rng, creation),
                    "civility": i % 2,
                    "thumbnail": "",
                    "firstName": prenom,
                    "lastName": nom,
                    "typeOf": 0,
                    "state": etat,
                    "isVisible": True,
                    "skills": ", ".join(competences),
                    "mobilityAreas": rng.choice(
                        [["Île-de-France"], ["Télétravail total"], ["Auvergne-Rhône-Alpes"]]
                    ),
                    "title": titre,
                    # ┌─ SUR UN CANDIDAT, `availability` EST UN CODE ──────────┐
                    # │ Pas une date. Relevé le 2026-08-12 sur les 26 814      │
                    # │ candidats d'un tenant de production : des ENTIERS,     │
                    # │ dont `-1` sur 24 289 d'entre eux, puis 0, 1, 3, 4…     │
                    # │ Le mock servait une date ISO, et `stg_candidat` la     │
                    # │ castait donc en date — d'où, au premier run réel,      │
                    # │ « invalid input syntax for type bigint: "" ».          │
                    # │                                                         │
                    # │ ⚠️ Ne pas confondre avec `availability` d'une          │
                    # │    RESSOURCE, qui est bien une date de disponibilité.  │
                    # │    Même nom, deux types, deux entités : c'est          │
                    # │    précisément le genre d'écart qu'un mock doit porter │
                    # │    plutôt que lisser.                                  │
                    # │                                                         │
                    # │ La correspondance code → libellé n'est PAS établie :   │
                    # │ elle vit dans le dictionnaire de l'instance, famille   │
                    # │ `availability`. Le mock rend donc des codes bruts, et  │
                    # │ le consommateur qui veut un libellé passe par lui.     │
                    # └─────────────────────────────────────────────────────────┘
                    "availability": rng.choice([-1, -1, -1, -1, 0, 1, 3, 4]),
                    "email1": f"{prenom.lower()}.{nom.lower()}@courriel.example",
                    "email2": "",
                    "email3": "",
                    "phone1": f"+33 7 {rng.randint(10, 99)} {rng.randint(10, 99)} "
                    f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
                    "phone2": "",
                    "town": rng.choice(["Paris", "Lyon", "Nantes", "Bordeaux"]),
                    "country": "France",
                    "source": {"typeOf": type_source, "detail": detail_source},
                    "numberOfResumes": rng.randint(1, 2),
                    "numberOfActivePositionings": 1 if etat in (2, 3) else 0,
                    "socialNetworks": [
                        {
                            "network": "linkedin",
                            "url": f"https://www.linkedin.com/in/{prenom.lower()}-{nom.lower()}",
                        }
                    ],
                    "diplomas": [rng.choice(_DIPLOMES)],
                    "activityAreas": rng.sample(_SECTEURS, k=2),
                    # Le guide utilisateur signale MOINS DE 2 % de candidats notes en
                    # production. Une chaine vide n'est PAS un nul : elle compte
                    # comme une note pour qui teste la presence, et masque le
                    # defaut de qualite que le modele doit exposer.
                    "globalEvaluation": "4.0" if i == 1 else ("3.5" if i == 5 else None),
                    "languages": [
                        {"language": code, "level": niveau}
                        for code, niveau in rng.sample(_LANGUES, k=2)
                    ],
                    "expertiseAreas": rng.sample(_EXPERTISES, k=1),
                    "experience": rng.randint(2, 12),
                    "references": [
                        {
                            "id": str(i * 10 + n),
                            "title": rng.choice(_TITRES_CONSULTANT),
                            "company": rng.choice(_CLIENTS)[0],
                            "location": rng.choice(["Paris", "Lyon", "Télétravail"]),
                            "startMonth": f"{rng.randint(1, 12):02d}",
                            "startYear": str(2020 + n),
                            "endMonth": f"{rng.randint(1, 12):02d}",
                            "endYear": str(2021 + n),
                            "skills": ", ".join(rng.sample(_COMPETENCES, k=3)),
                            "description": "Mission de conseil et de mise en œuvre.",
                            "startDate": "",
                            "endDate": "",
                            "row": n,
                        }
                        for n in range(1, rng.randint(2, 3))
                    ],
                    "evaluations": (
                        [
                            {
                                "id": str(i),
                                "notations": [
                                    {"criteria": 1, "evaluation": str(rng.randint(3, 5))},
                                    {"criteria": 2, "evaluation": str(rng.randint(3, 5))},
                                ],
                                "date": _d(creation + timedelta(days=10)),
                                "comments": "Bon entretien technique, à suivre.",
                                "manager": {"id": "4", "firstName": "Hugo", "lastName": "Dubois"},
                            }
                        ]
                        if etat >= 2
                        else []
                    ),
                    "tools": [{"tool": c, "level": rng.randint(2, 5)} for c in competences[:3]],
                    "canShowTechnicalData": True,
                    "canShowActions": True,
                },
                "relationships": {
                    "mainManager": _rel("resource", rng.choice((2, 4, 6))),
                    "agency": _rel("agency", rng.randint(1, 3)),
                    "pole": _rel("pole", rng.randint(1, len(_POLES))),
                },
            }
        )
    return candidats


# ═════════════════════════════════════════════════════════════════════════════
#  CRM : sociétés, contacts, opportunités
# ═════════════════════════════════════════════════════════════════════════════


def _societes(rng: random.Random) -> list[dict[str, Any]]:
    societes: list[dict[str, Any]] = []
    for i, (nom, ville, secteur, site, prospect) in enumerate(_CLIENTS, start=1):
        creation = date(2022 + i % 3, ((i * 5) % 12) + 1, 15)
        societes.append(
            {
                "id": str(i),
                "type": "company",
                "attributes": {
                    "name": nom,
                    "expertiseArea": secteur,
                    "state": 0 if prospect else 1,
                    "informationComments": (
                        "Prospect qualifié — première proposition en cours."
                        if prospect
                        else "Client actif."
                    ),
                    "thumbnail": "",
                    "website": site,
                    "phone1": f"+33 {rng.randint(1, 5)} {rng.randint(10, 99)} "
                    f"{rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
                    "town": ville,
                    "country": "Belgique" if ville == "Bruxelles" else "France",
                    "creationDate": _dt(creation, 9, 45),
                    "updateDate": _maj(rng, date(2026, 1, 10)),
                    "socialNetworks": [
                        {
                            "network": "linkedin",
                            "url": "https://www.linkedin.com/company/"
                            f"{nom.lower().replace(' ', '-')}",
                        }
                    ],
                },
                "relationships": {
                    "mainManager": _rel("resource", rng.choice((2, 3, 5))),
                    "agency": _rel(
                        "agency", 2 if ville == "Lyon" else (3 if ville == "Nantes" else 1)
                    ),
                    "pole": _rel("pole", rng.randint(1, len(_POLES))),
                },
            }
        )
    return societes


def _contacts(societes: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    ident = 1
    for societe in societes[:10]:  # les contacts vivent chez les clients
        for _ in range(2 if int(societe["id"]) % 2 == 0 else 3):
            if ident > 22:
                break
            prenom = _PRENOMS[(ident * 19 + 7) % len(_PRENOMS)]
            nom = _NOMS[(ident * 23 + 2) % len(_NOMS)]
            domaine = societe["attributes"]["website"].removeprefix("https://")
            creation = date(2024 + ident % 2, ((ident * 3) % 12) + 1, 10)
            contacts.append(
                {
                    "id": str(ident),
                    "type": "contact",
                    "attributes": {
                        "creationDate": _dt(creation, 11, 20),
                        "civility": ident % 2,
                        "thumbnail": "",
                        "firstName": prenom,
                        "lastName": nom,
                        "state": 1,
                        "function": rng.choice(_FONCTIONS_CONTACT),
                        "department": rng.choice(_SERVICES_CONTACT),
                        "email1": f"{prenom.lower()}.{nom.lower()}@{domaine}",
                        "email2": "",
                        "email3": "",
                        "phone1": f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} "
                        f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
                        "phone2": "",
                        "town": societe["attributes"]["town"],
                        "country": societe["attributes"]["country"],
                        "canReadContact": True,
                        "canWriteContact": True,
                        "canShowAction": True,
                        "typesOf": [],
                        "socialNetworks": [],
                        "updateDate": _maj(rng, creation),
                    },
                    "relationships": {
                        "mainManager": societe["relationships"]["mainManager"],
                        "company": _rel("company", societe["id"]),
                        "agency": societe["relationships"]["agency"],
                        "pole": societe["relationships"]["pole"],
                    },
                }
            )
            ident += 1
    return contacts


def _opportunites(
    societes: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """15 opportunités : 6 gagnées (→ projets), 5 en cours, 3 perdues, 1 en veille.

    États alignés sur l'INSTANCE RÉELLE, observés dans l'export « Besoins »
    du fichier de mappings (08 - LOST, 09 - POSTPONED / ABANDONED) et conformes
    au process Confluence « BOOND - Need creation & Management » :
    1 Open · 2 Qualified · 3 Proposed solution · 7 WON · 8 LOST · 9 POSTPONED.

    Le mock codait 4/5/6, ce qui n'existe nulle part dans l'instance : un
    consommateur qui écrivait « état = 4 → gagnée » produisait un chiffre juste
    en dev et faux en production, sans que rien ne le signale.
    """
    plan = [7, 7, 7, 7, 7, 7, 1, 2, 2, 3, 1, 8, 8, 8, 9]
    opportunites: list[dict[str, Any]] = []
    for i, etat in enumerate(plan, start=1):
        societe = societes[(i * 3) % 10]
        contacts_societe = [
            c for c in contacts if c["relationships"]["company"]["data"]["id"] == societe["id"]
        ]
        contact = rng.choice(contacts_societe) if contacts_societe else None
        sujet, outils = _SUJETS[(i * 5) % len(_SUJETS)]
        creation = date(2025, ((i * 7) % 12) + 1, rng.randint(2, 26))
        perdue = etat == 8
        mode = 1 if i % 3 else 2  # 1 = assistance technique, 2 = forfait
        jours = rng.choice([120, 180, 240, 300])
        tjm_moyen = rng.choice([620, 680, 750, 820])
        estime = float(jours * tjm_moyen)
        proba = {1: 0.3, 2: 0.5, 3: 0.7, 7: 1.0, 8: 0.0, 9: 0.1}[etat]
        cloture = creation + timedelta(days=rng.randint(30, 120))
        opportunites.append(
            {
                "id": str(i),
                "type": "opportunity",
                "attributes": {
                    "creationDate": _dt(creation, 9, 30),
                    "title": f"{sujet} — {societe['attributes']['name']}",
                    "reference": f"AO-{creation.year}-{i:03d}",
                    "typeOf": 1,
                    "mode": mode,
                    "state": etat,
                    "place": societe["attributes"]["town"],
                    "isVisible": True,
                    # ┌─ `startDate` N'EST PAS TOUJOURS UNE DATE ───────────┐
                    # │ Sur un BESOIN, le fournisseur rend la chaîne         │
                    # │ littérale « immediate » quand le démarrage est       │
                    # │ immédiat. Et ce n'est pas un cas limite : 1 523 des  │
                    # │ 1 850 besoins de production, soit 82 %.              │
                    # │                                                      │
                    # │ Le mock ne servait que des dates, si bien que        │
                    # │ `stg_opportunite` castait sans filet et tombait sur  │
                    # │ « invalid input syntax for type date: "immediate" ». │
                    # │                                                      │
                    # │ Même valeur, même sens que l'`availability` d'une    │
                    # │ RESSOURCE — le dialecte réutilise ce littéral pour   │
                    # │ « tout de suite » partout où une date est attendue.  │
                    # │ Un consommateur doit donc le prévoir sur TOUT champ  │
                    # │ de date de démarrage, pas seulement ici.             │
                    # │                                                      │
                    # │ Proportion volontairement majoritaire : un jeu où le │
                    # │ cas dominant est minoritaire laisse passer les       │
                    # │ modèles qui ne le gèrent pas.                        │
                    # └──────────────────────────────────────────────────────┘
                    "startDate": (
                        ""
                        if perdue
                        else ("immediate" if i % 5 else _d(cloture + timedelta(days=30)))
                    ),
                    "endDate": _d(cloture + timedelta(days=30 + jours)) if not perdue else "",
                    "closingDate": _d(cloture) if etat in (4, 5) else "",
                    "answerDate": _d(creation + timedelta(days=21)),
                    "duration": jours,
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "turnoverWeightedExcludingTax": round(estime * proba, 2),
                    "estimatesExcludingTax": estime,
                    "turnoverEstimatedExcludingTax": estime,
                    "expertiseArea": rng.choice(_EXPERTISES),
                    "activityAreas": [societe["attributes"]["expertiseArea"]],
                    "origin": {
                        "typeOf": rng.randint(1, 4),
                        "detail": rng.choice(
                            [
                                "Appel entrant",
                                "Recommandation",
                                "Consultation cadre",
                                "Réponse à appel d'offres",
                            ]
                        ),
                    },
                    "tools": outils,
                    "numberOfActivePositionings": 0 if etat in (4, 5, 6) else rng.randint(1, 3),
                    "canShowContact": True,
                    "canShowCompany": True,
                    "stateReason": (
                        {
                            "typeOf": 2,
                            "detail": rng.choice(["Prix", "Concurrent retenu", "Projet reporté"]),
                        }
                        if perdue
                        else {"typeOf": 0, "detail": ""}
                    ),
                    "updateDate": _maj(rng, cloture if etat in (4, 5) else creation),
                },
                "relationships": {
                    "mainManager": societe["relationships"]["mainManager"],
                    "agency": societe["relationships"]["agency"],
                    "pole": societe["relationships"]["pole"],
                    "contact": _rel("contact", contact["id"] if contact else None),
                    "company": _rel("company", societe["id"]),
                    "parsingJob": _rel("opportunityparsingjob", None),
                },
            }
        )
    return opportunites


# ═════════════════════════════════════════════════════════════════════════════
#  Production : projets, missions, jours travaillés
# ═════════════════════════════════════════════════════════════════════════════


def _debut_besoin(attributs: dict[str, Any]) -> date:
    """La date de démarrage d'un besoin, `immediate` résolu.

    Le fournisseur rend soit une date, soit la chaîne littérale « immediate » —
    cette dernière sur 82 % des besoins en production. Toute lecture de ce champ
    doit donc prévoir les deux formes ; ce helper existe pour que le mock lui-même
    ne l'oublie pas dans ses dérivations internes.
    """
    valeur = attributs.get("startDate") or ""
    if valeur and valeur != "immediate":
        return date.fromisoformat(valeur)
    # « immediate » : le démarrage suit la création du besoin sans délai.
    return date.fromisoformat(str(attributs["creationDate"])[:10])


def _projets(
    opportunites: list[dict[str, Any]],
    societes: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """12 projets : 6 issus des opportunités gagnées, 6 historiques (2025).

    8 sont en cours à l'ancre (juillet 2026), 4 sont terminés — leurs bornes
    pilotent missions, CRA et factures.
    """
    projets = []
    gagnees = [o for o in opportunites if o["attributes"]["state"] == 7]
    for i in range(1, 13):
        if i <= len(gagnees):
            opp = gagnees[i - 1]
            societe_id = opp["relationships"]["company"]["data"]["id"]
            societe = societes[int(societe_id) - 1]
            # `startDate` vaut « immediate » sur la majorité des besoins : le
            # projet démarre alors tout de suite, et l'ancre la plus proche
            # dont on dispose ici est la date de création du besoin. C'est
            # exactement l'arbitrage qu'un consommateur doit faire — le mock
            # le fait donc aussi, plutôt que d'exclure ces besoins et de
            # rendre le littéral inatteignable en aval.
            debut = _debut_besoin(opp["attributes"])
            mode = opp["attributes"]["mode"]
            reference_annee = debut.year
        else:
            opp = None
            societe = societes[(i * 7) % 10]
            debut = date(2025, ((i * 5) % 10) + 1, 1)
            mode = 1 if i % 2 else 2
            reference_annee = debut.year
        en_cours = i <= 8
        fin = date(2026, 12, 31) if en_cours else _fin_mois(2026, (i % 4) + 1)
        if not en_cours and fin <= debut:
            fin = _fin_mois(debut.year, min(12, debut.month + 6))
        projets.append(
            {
                "id": str(i),
                "type": "project",
                "attributes": {
                    "startDate": _d(debut),
                    "endDate": _d(fin),
                    "typeOf": mode,
                    "mode": mode,
                    "reference": f"PRJ-{reference_annee}-{i:03d}",
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    # Recalculés depuis les missions juste après.
                    "turnoverSimulatedExcludingTax": 0.0,
                    "marginSimulatedExcludingTax": 0.0,
                    "profitabilitySimulated": 0.0,
                    "canReadProject": True,
                    "canShowContact": True,
                    "canShowCompany": True,
                    "canShowIntermediaryContact": True,
                    "canShowIntermediaryCompany": True,
                    "canShowCurrency": True,
                    "canShowCurrencyAgency": True,
                    "canShowExchangeRate": True,
                    "canShowExchangeRateAgency": True,
                    "canShowProfitabilitySimulated": True,
                    "canShowTurnoverSimulatedExcludingTax": True,
                    "canShowMarginSimulatedExcludingTax": True,
                    "creationDate": _dt(debut - timedelta(days=20), 15, 10),
                    "updateDate": _maj(rng, debut),
                },
                "relationships": {
                    "mainManager": societe["relationships"]["mainManager"],
                    "opportunity": _rel("opportunity", opp["id"] if opp else None),
                    "contact": opp["relationships"]["contact"] if opp else _rel("contact", None),
                    "company": _rel("company", societe["id"]),
                    "agency": societe["relationships"]["agency"],
                    "pole": societe["relationships"]["pole"],
                    "intermediaryCompany": _rel("company", None),
                    "intermediaryContact": _rel("contact", None),
                },
            }
        )
    return projets


def _missions(
    projets: list[dict[str, Any]],
    ressources: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """20 missions (deliveries) — le lien consultant ↔ projet.

    La liste GET /deliveries n'est pas documentée au RAML externe (POST
    uniquement) : les items suivent la forme du schéma PROFILE officiel,
    allégée des barèmes (tableaux vides, comme une instance jeune).
    """
    consultants = [
        r
        for r in ressources
        if int(r["id"]) >= 7
        and r["attributes"]["state"] in ETATS_AVEC_MISSION
        and int(r["id"]) not in (25, 26, 29, 30)  # l'intercontrat reste au banc
    ]
    missions: list[dict[str, Any]] = []
    ident = 1
    file_consultants = consultants.copy()
    for projet in projets:
        nb = 2 if int(projet["id"]) % 2 == 0 else 1
        if projet["id"] in ("1", "2"):
            nb = 3
        for _ in range(nb):
            if not file_consultants:
                file_consultants = consultants.copy()
            consultant = file_consultants.pop(0)
            if ident > 20:
                break
            debut_projet = date.fromisoformat(projet["attributes"]["startDate"])
            fin_projet = date.fromisoformat(projet["attributes"]["endDate"])
            tjm = consultant["attributes"]["averageDailyPriceExcludingTax"] or 650.0
            cout = round(tjm * 0.58, 2)
            jours_prevus = max(20, min(((fin_projet - debut_projet).days * 5) // 7 - 10, 220))
            ca = round(tjm * jours_prevus, 2)
            couts = round(cout * jours_prevus, 2)
            sous_traite = int(consultant["id"]) in _IDS_SOUS_TRAITANTS
            missions.append(
                {
                    "id": str(ident),
                    "type": "delivery",
                    "attributes": {
                        "startDate": _d(debut_projet),
                        "endDate": _d(fin_projet),
                        "title": consultant["attributes"]["title"],
                        "typeOf": 1 if sous_traite else 0,
                        "state": 1 if fin_projet >= AUJOURDHUI else 2,
                        "canShowAverageDailyContractCost": True,
                        "averageDailyPriceExcludingTax": tjm,
                        "forceAverageDailyPriceExcludingTax": False,
                        "subscriptionQuantityCharged": 0,
                        "subscriptionQuantityFree": 0,
                        "subscriptionPriceExcludingTax": 0.0,
                        "averageDailyCost": cout,
                        "averageDailyContractCost": cout,
                        "numberOfDaysInvoicedOrQuantity": float(jours_prevus),
                        "numberOfDaysFree": 0,
                        "informationComments": "",
                        "conditions": "",
                        "turnoverSimulatedExcludingTax": ca,
                        "costsSimulatedExcludingTax": couts,
                        "marginSimulatedExcludingTax": round(ca - couts, 2),
                        "profitabilitySimulated": round((ca - couts) / ca * 100, 2) if ca else 0.0,
                        "occupationRate": 100.0,
                        "dailyExpenses": 9.05,
                        "monthlyExpenses": 75.0,
                        "numberOfWorkingDays": 218,
                        "weeklyWorkingHours": 38.5,
                        "averageHourlyPriceExcludingTax": 0.0,
                        "forceAverageHourlyPriceExcludingTax": False,
                        "additionalTurnoverAndCosts": [],
                        "expensesDetails": [],
                        "advantageTypes": [],
                        "exceptionalScales": [],
                        "creationDate": _dt(debut_projet - timedelta(days=12), 16, 40),
                        "updateDate": _maj(rng, debut_projet),
                        "calendar": "Standard",
                        "isTurnoverProductionIncluded": True,
                    },
                    "relationships": {
                        "project": _rel("project", projet["id"]),
                        "dependsOn": _rel("resource", consultant["id"]),
                        "purchase": _rel("purchase", None),  # renseigné pour la sous-traitance
                    },
                }
            )
            ident += 1
    return missions


def _jours_travailles(
    missions: list[dict[str, Any]], rng: random.Random
) -> dict[tuple[str, int, int], float]:
    """Jours travaillés par (mission, année, mois) — la matrice qui fait tenir
    factures et lignes de temps ENSEMBLE : les deux la consomment telle quelle."""
    matrice: dict[tuple[str, int, int], float] = {}
    for mission in missions:
        debut = date.fromisoformat(mission["attributes"]["startDate"])
        fin = date.fromisoformat(mission["attributes"]["endDate"])
        mois_courant = date(2026, 1, 1)
        while mois_courant <= min(fin, date(2026, 7, 31)):
            annee, mois = mois_courant.year, mois_courant.month
            if _fin_mois(annee, mois) >= debut:
                ouvres = _jours_ouvres(annee, mois)
                if (annee, mois) == (2026, 7):
                    travailles = 9.0  # mois en cours à l'ancre du 15 juillet
                else:
                    travailles = float(ouvres - rng.choice([0, 0, 1, 1, 2]))
                matrice[(mission["id"], annee, mois)] = travailles
            mois_courant = _fin_mois(annee, mois) + timedelta(days=1)
    return matrice


# ═════════════════════════════════════════════════════════════════════════════
#  Facturation : commandes, factures, transactions bancaires
# ═════════════════════════════════════════════════════════════════════════════


def _commandes(
    projets: list[dict[str, Any]],
    missions: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    commandes: list[dict[str, Any]] = []
    ident = 1
    for projet in projets:
        missions_projet = [
            m for m in missions if m["relationships"]["project"]["data"]["id"] == projet["id"]
        ]
        if not missions_projet:
            continue
        commande_ca = round(
            sum(m["attributes"]["turnoverSimulatedExcludingTax"] for m in missions_projet), 2
        )
        debut = date.fromisoformat(projet["attributes"]["startDate"])
        commandes.append(
            {
                "id": str(ident),
                "type": "order",
                "attributes": {
                    "date": _d(debut - timedelta(days=5)),
                    "number": f"CMD-{debut.year}-{ident:03d}",
                    "reference": f"PO-{rng.randint(40000, 99999)}",
                    "customerAgreement": True,
                    # turnoverInvoiced/delta recalculés après les factures.
                    "turnoverInvoicedExcludingTax": 0.0,
                    "turnoverOrderedExcludingTax": commande_ca,
                    "deltaInvoicedExcludingTax": commande_ca,
                    "state": 1,
                    # ┌─ NI `creationDate` NI `updateDate` SUR LES COMMANDES ───┐
                    # │ Le fournisseur ne rend AUCUN des deux. Sondé le          │
                    # │ 2026-08-12 : `/orders` est la seule des dix-huit         │
                    # │ collections à manquer `updateDate`, et son atterrissage  │
                    # │ dlt en production ne porte pas non plus `creation_date`. │
                    # │                                                          │
                    # │ `updateDate` d'abord : il porte la STRATÉGIE            │
                    # │ d'extraction. Le voyant ici, insights360 a déclaré la   │
                    # │ collection incrémentale, et dlt a levé                  │
                    # │ `IncrementalCursorPathMissing` au premier run réel —    │
                    # │ emportant les six collections déclarées après elle.     │
                    # │                                                          │
                    # │ `creationDate` ensuite, et c'est une erreur qu'il vaut  │
                    # │ la peine de nommer : le registre des écarts le donnait  │
                    # │ déjà pour absent du tenant, et 0.6.0 a choisi de le     │
                    # │ servir quand même au motif qu'« il ne pilote aucune     │
                    # │ stratégie, donc le servir ne coûte rien ». C'était      │
                    # │ faux. Un modèle qui LIT une colonne a besoin qu'elle    │
                    # │ EXISTE : `stg_commande` est tombé sur « column          │
                    # │ o.creation_date does not exist » au run suivant.        │
                    # │                                                          │
                    # │ La règle n'admet donc pas d'exception « inoffensive » : │
                    # │ un champ que le fournisseur ne rend pas ne doit pas     │
                    # │ être rendu ici, quel qu'en soit l'usage supposé.        │
                    # │ `date` reste, elle : c'est la date de commande, et      │
                    # │ elle est bien rendue en réel.                           │
                    # └──────────────────────────────────────────────────────────┘
                },
                "relationships": {
                    "mainManager": projet["relationships"]["mainManager"],
                    "project": _rel("project", projet["id"]),
                },
            }
        )
        ident += 1
    return commandes


def _factures(
    commandes: list[dict[str, Any]],
    missions: list[dict[str, Any]],
    matrice: dict[tuple[str, int, int], float],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Une facture par commande et par mois échu — montant = somme des jours x TJM.

    Mai et avant : réglées. Juin : envoyées, échéance à 30 jours. Juillet : un
    brouillon. Une facture d'avoir (`isCreditNote`) corrige un trop-facturé.
    """
    factures: list[dict[str, Any]] = []
    ident = 1
    for commande in commandes:
        projet_id = commande["relationships"]["project"]["data"]["id"]
        missions_projet = [
            m for m in missions if m["relationships"]["project"]["data"]["id"] == projet_id
        ]
        for annee, mois in [(2026, m) for m in range(1, 8)]:
            montant = sum(
                matrice.get((m["id"], annee, mois), 0.0)
                * m["attributes"]["averageDailyPriceExcludingTax"]
                for m in missions_projet
            )
            if montant <= 0:
                continue
            emission = _fin_mois(annee, mois) + timedelta(days=2)
            if emission > AUJOURDHUI:
                if mois != 7 or int(commande["id"]) % 4 != 1:
                    continue
                emission = AUJOURDHUI  # brouillon du mois en cours
                etat, envoi, payee_le = 0, 0, None
            elif mois <= 5:
                etat, envoi = 2, 2
                payee_le = emission + timedelta(days=rng.randint(18, 32))
            else:
                etat, envoi, payee_le = 1, 1, None
            montant = round(montant, 2)
            ttc = round(montant * (1 + TVA), 2)
            factures.append(
                {
                    "id": str(ident),
                    "type": "invoice",
                    "attributes": {
                        "date": _d(emission),
                        "expectedPaymentDate": _d(emission + timedelta(days=30)),
                        "turnoverInvoicedExcludingTax": montant,
                        "turnoverInvoicedIncludingTax": ttc,
                        "isCreditNote": False,
                        "reference": f"FAC-{annee}-{ident:04d}",
                        "state": etat,
                        "selfBilling": False,
                        "sendingState": envoi,
                        "refuseReason": "",
                        "providerId": "",
                        "providerUrl": "",
                        "taxReportState": 0,
                        "currency": 0,
                        "exchangeRate": 1.0,
                        "currencyAgency": 0,
                        "exchangeRateAgency": 1.0,
                        "paymentMethod": 1,
                        "closed": etat == 2,
                        "totalPayableIncludingTax": ttc,
                        "creationDate": _dt(emission, 8, 5),
                        "updateDate": _dt(min(payee_le or emission, DERNIERE_MAJ), 14, 10),
                        "startDate": _d(date(annee, mois, 1)),
                        "endDate": _d(_fin_mois(annee, mois)),
                        "performedPaymentDate": _d(payee_le) if payee_le else "",
                        "canSendWithPeppol": True,
                        "canSendWithDgfip": False,
                        "canSendWithPennylane": False,
                    },
                    "relationships": {
                        "order": _rel("order", commande["id"]),
                        "schedule": _rel("schedule", None),
                    },
                }
            )
            ident += 1

    # L'avoir : correction d'un trop-facturé sur la première facture réglée.
    reglees = [f for f in factures if f["attributes"]["state"] == 2]
    if reglees:
        origine = reglees[0]
        montant = round(-0.1 * origine["attributes"]["turnoverInvoicedExcludingTax"], 2)
        avoir_date = date.fromisoformat(origine["attributes"]["date"]) + timedelta(days=14)
        factures.append(
            {
                "id": str(ident),
                "type": "invoice",
                "attributes": {
                    **origine["attributes"],
                    "date": _d(avoir_date),
                    "expectedPaymentDate": _d(avoir_date),
                    "turnoverInvoicedExcludingTax": montant,
                    "turnoverInvoicedIncludingTax": round(montant * (1 + TVA), 2),
                    "totalPayableIncludingTax": round(montant * (1 + TVA), 2),
                    "isCreditNote": True,
                    "reference": f"AV-2026-{ident:04d}",
                    "performedPaymentDate": "",
                    "closed": False,
                    "state": 1,
                    "sendingState": 1,
                    "creationDate": _dt(avoir_date, 9, 55),
                    "updateDate": _dt(avoir_date, 9, 55),
                },
                "relationships": dict(origine["relationships"]),
            }
        )

    # Recalage des cumuls de commande — la cohérence qui se voit au premier diff.
    for commande in commandes:
        facture_total = round(
            sum(
                f["attributes"]["turnoverInvoicedExcludingTax"]
                for f in factures
                if f["relationships"]["order"]["data"]["id"] == commande["id"]
                and f["attributes"]["state"] > 0
            ),
            2,
        )
        commande["attributes"]["turnoverInvoicedExcludingTax"] = facture_total
        commande["attributes"]["deltaInvoicedExcludingTax"] = round(
            commande["attributes"]["turnoverOrderedExcludingTax"] - facture_total, 2
        )
    return factures


def _banque(
    factures: list[dict[str, Any]],
    societes: list[dict[str, Any]],
    commandes: list[dict[str, Any]],
    projets: list[dict[str, Any]],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Comptes, connexions et transactions : les encaissements des factures réglées."""
    connexions = [
        {"id": "1", "type": "bankingconnection", "attributes": {"bankName": "BNP Paribas"}},
        {"id": "2", "type": "bankingconnection", "attributes": {"bankName": "Qonto"}},
    ]
    comptes = [
        {
            "id": "1",
            "type": "bankingaccount",
            "attributes": {
                "name": "Compte courant principal",
                "title": "FR76 3000 4028 3700 0104 5678 921",
            },
            "relationships": {"connection": _rel("bankingconnection", 1)},
        },
        {
            "id": "2",
            "type": "bankingaccount",
            "attributes": {"name": "Compte dépenses", "title": "FR76 1695 8000 0187 6543 2109 876"},
            "relationships": {"connection": _rel("bankingconnection", 2)},
        },
    ]

    def _client_de(facture: dict[str, Any]) -> str:
        commande = next(
            c for c in commandes if c["id"] == facture["relationships"]["order"]["data"]["id"]
        )
        projet = next(
            p for p in projets if p["id"] == commande["relationships"]["project"]["data"]["id"]
        )
        societe = next(
            s for s in societes if s["id"] == projet["relationships"]["company"]["data"]["id"]
        )
        return str(societe["attributes"]["name"])

    transactions: list[dict[str, Any]] = []
    reglees = [f for f in factures if f["attributes"]["performedPaymentDate"]]
    for i, facture in enumerate(reglees[:14], start=1):
        attrs = facture["attributes"]
        jour = date.fromisoformat(attrs["performedPaymentDate"])
        rapprochee = i <= 11
        transactions.append(
            {
                "id": str(i),
                "type": "bankingtransaction",
                "attributes": {
                    "amount": attrs["totalPayableIncludingTax"],
                    "currency": 0,
                    "date": _dt(jour, rng.randint(3, 7), rng.randint(0, 59)),
                    "numberOfInvoices": 1 if rapprochee else 0,
                    "title": f"VIR SEPA {_client_de(facture).upper()} {attrs['reference']}",
                    "state": 2 if rapprochee else 0,
                    "totalAmountToReconcile": 0.0
                    if rapprochee
                    else attrs["totalPayableIncludingTax"],
                    "canReadTransaction": True,
                    "canWriteTransaction": True,
                    "canReconcile": True,
                },
                "relationships": {"account": _rel("bankingaccount", 1)},
            }
        )
    # Deux débits fournisseurs sur le second compte, non rapprochés.
    for n, (libelle, montant) in enumerate(
        [
            ("PRLV SEPA SOFTALLIANCE ABONNEMENT DATA-2026-07", 1068.0),
            ("PRLV SEPA FONCIERE BEAUMONT LOYER 2026-07", 9960.0),
        ],
        start=len(transactions) + 1,
    ):
        transactions.append(
            {
                "id": str(n),
                "type": "bankingtransaction",
                "attributes": {
                    "amount": montant,
                    "currency": 0,
                    "date": _dt(date(2026, 7, 5), 4, 45),
                    "numberOfInvoices": 0,
                    "title": libelle,
                    "state": 0,
                    "totalAmountToReconcile": montant,
                    "canReadTransaction": True,
                    "canWriteTransaction": True,
                    "canReconcile": True,
                },
                "relationships": {"account": _rel("bankingaccount", 2)},
            }
        )
    return comptes, connexions, transactions


# ═════════════════════════════════════════════════════════════════════════════
#  Achats et paiements fournisseurs
# ═════════════════════════════════════════════════════════════════════════════


def _achats(
    missions: list[dict[str, Any]],
    ressources: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """8 achats : sous-traitance adossée aux missions, licences, loyer, matériel."""
    achats: list[dict[str, Any]] = []
    ident = 1

    missions_st = [
        m
        for m in missions
        if int(m["relationships"]["dependsOn"]["data"]["id"]) in _IDS_SOUS_TRAITANTS
    ][:2]
    for mission in missions_st:
        consultant = next(
            r for r in ressources if r["id"] == mission["relationships"]["dependsOn"]["data"]["id"]
        )
        tjm_achat = round(mission["attributes"]["averageDailyPriceExcludingTax"] * 0.72, 2)
        jours = mission["attributes"]["numberOfDaysInvoicedOrQuantity"]
        debut = date.fromisoformat(mission["attributes"]["startDate"])
        achats.append(
            {
                "id": str(ident),
                "type": "purchase",
                "attributes": {
                    "date": _d(debut - timedelta(days=8)),
                    "title": f"Sous-traitance {consultant['attributes']['firstName']} "
                    f"{consultant['attributes']['lastName']} — Fivetech Partners",
                    "subscription": 0,
                    "typeOf": 0,
                    "reference": f"ACH-2026-{ident:03d}",
                    "state": 1,
                    "taxRate": 20.0,
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "amountExcludingTax": tjm_achat,
                    "quantity": jours,
                    "totalAmountExcludingTax": round(tjm_achat * jours, 2),
                    "deltaExcludingTax": 0.0,  # recalculé après les paiements
                    "engagedPaymentsAmountExcludingTax": 0.0,
                    "creationDate": _dt(debut - timedelta(days=8), 11, 45),
                    "updateDate": _maj(rng, debut),
                },
                "relationships": {
                    "mainManager": _rel("resource", 2),
                    "project": mission["relationships"]["project"],
                    "delivery": _rel("delivery", mission["id"]),
                    "contact": _rel("contact", None),
                    "company": _rel("company", _ID_FOURNISSEUR_SOUSTRAITANCE),
                    "agency": _rel("agency", 1),
                    "pole": _rel("pole", None),
                },
            }
        )
        mission["relationships"]["purchase"] = _rel("purchase", ident)
        ident += 1

    generaux = [
        ("Licences plateforme data — Softalliance", 1, 2, 890.0, 12, _ID_FOURNISSEUR_LICENCES),
        ("Abonnement observabilité — Softalliance", 1, 2, 340.0, 12, _ID_FOURNISSEUR_LICENCES),
        ("Postes de travail consultants", 0, 4, 1650.0, 6, _ID_FOURNISSEUR_LICENCES),
        ("Loyer agence Paris", 1, 3, 8300.0, 12, _ID_FOURNISSEUR_LOYER),
        ("Loyer agence Lyon", 1, 3, 2900.0, 12, _ID_FOURNISSEUR_LOYER),
        ("Mobilier salle projet Nantes", 0, 4, 4200.0, 1, _ID_FOURNISSEUR_LOYER),
    ]
    for titre, abonnement, type_of, montant, quantite, fournisseur in generaux:
        jour = date(2026, 1, rng.randint(3, 20))
        achats.append(
            {
                "id": str(ident),
                "type": "purchase",
                "attributes": {
                    "date": _d(jour),
                    "title": titre,
                    "subscription": abonnement,
                    "typeOf": type_of,
                    "reference": f"ACH-2026-{ident:03d}",
                    "state": 1,
                    "taxRate": 20.0,
                    "currency": 0,
                    "exchangeRate": 1.0,
                    "currencyAgency": 0,
                    "exchangeRateAgency": 1.0,
                    "amountExcludingTax": montant,
                    "quantity": float(quantite),
                    "totalAmountExcludingTax": round(montant * quantite, 2),
                    "deltaExcludingTax": 0.0,
                    "engagedPaymentsAmountExcludingTax": 0.0,
                    "creationDate": _dt(jour, 10, 25),
                    "updateDate": _maj(rng, jour),
                },
                "relationships": {
                    "mainManager": _rel("resource", 1),
                    "project": _rel("project", None),
                    "delivery": _rel("delivery", None),
                    "contact": _rel("contact", None),
                    "company": _rel("company", fournisseur),
                    "agency": _rel("agency", 1),
                    "pole": _rel("pole", None),
                },
            }
        )
        ident += 1
    return achats


def _paiements(achats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Échéanciers de règlement des achats — passés réglés, à venir prévus."""
    paiements: list[dict[str, Any]] = []
    ident = 1
    for achat in achats:
        attrs = achat["attributes"]
        if attrs["subscription"] == 1:
            echeances = [(date(2026, mois, 5), attrs["amountExcludingTax"]) for mois in (5, 6, 7)]
        else:
            total = attrs["totalAmountExcludingTax"]
            echeances = [
                (date(2026, 4, 15), round(total * 0.4, 2)),
                (date(2026, 7, 25), round(total * 0.6, 2)),
            ]
        for jour, montant in echeances:
            effectue = jour <= AUJOURDHUI
            paiements.append(
                {
                    "id": str(ident),
                    "type": "payment",
                    "attributes": {
                        "date": _d(jour),
                        "performedDate": _d(jour + timedelta(days=1)) if effectue else "",
                        "expectedDate": _d(jour),
                        "state": 1 if effectue else 0,
                        "number": f"VIR-2026-{ident:03d}",
                        "amountExcludingTax": montant,
                        "amountIncludingTax": round(montant * (1 + TVA), 2),
                        "numberOfFiles": 0,
                        "canWritePayment": True,
                        "creationDate": _dt(jour - timedelta(days=10), 9, 20),
                        "updateDate": _dt(min(jour, DERNIERE_MAJ), 15, 40),
                    },
                    "relationships": {"purchase": _rel("purchase", achat["id"])},
                }
            )
            ident += 1
        engages = round(
            sum(
                p["attributes"]["amountExcludingTax"]
                for p in paiements
                if p["relationships"]["purchase"]["data"]["id"] == achat["id"]
            ),
            2,
        )
        attrs["engagedPaymentsAmountExcludingTax"] = engages
        attrs["deltaExcludingTax"] = round(attrs["totalAmountExcludingTax"] - engages, 2)
    return paiements


# ═════════════════════════════════════════════════════════════════════════════
#  Activité : CRA, temps, absences, frais
# ═════════════════════════════════════════════════════════════════════════════


def _cras(
    ressources: list[dict[str, Any]], rng: random.Random
) -> tuple[list[dict[str, Any]], dict[tuple[str, int, int], str]]:
    """Un CRA par consultant actif et par mois d'activité. Rend aussi l'index
    (resource_id, année, mois) → cra_id que les lignes de temps consomment."""
    cras: list[dict[str, Any]] = []
    index: dict[tuple[str, int, int], str] = {}
    ident = 1
    for res in ressources:
        rid = int(res["id"])
        if rid <= 6:
            continue
        sorti = res["attributes"]["state"] == ETAT_RESSOURCE_SORTIE
        for annee, mois in MOIS_ACTIVITE:
            if rid in _IDS_INTEGRATION and mois < 7:
                continue
            # Un SORTI conserve son historique jusqu'à son départ, et rien
            # après. Ne lui donner AUCUN CRA effacerait le passé : un ancien
            # collaborateur doit rester visible dans les faits historiques
            # (rémunération, temps produits) tout en n'ayant plus aucune
            # visibilité applicative. Ce sont deux propriétés distinctes, et
            # les confondre est ce qui fait qu'un partant garde des droits —
            # ou qu'on perd la trace de ce qu'il a produit.
            if sorti and mois > _MOIS_SORTIE:
                continue
            if mois == 7:
                etat = rng.choice(["waitingForValidation", "savedAndNoValidation"])
                clos = False
            else:
                etat = "validated"
                clos = True
            cras.append(
                {
                    "id": str(ident),
                    "type": "timesreport",
                    "attributes": {
                        "term": f"{annee:04d}-{mois:02d}",
                        "state": etat,
                        "closed": clos,
                    },
                    "relationships": {
                        # L'agence vient de la LIGNE DE FAIT, pas du
                        # collaborateur : cf. _ID_MUTATION. Un mutant garde ses
                        # CRA antérieurs sous son ancienne agence.
                        "agency": (
                            _rel("agency", _AGENCE_AVANT_MUTATION)
                            if rid == _ID_MUTATION and mois < _MOIS_MUTATION
                            else res["relationships"]["agency"]
                        ),
                        "resource": _rel("resource", res["id"]),
                    },
                }
            )
            index[(res["id"], annee, mois)] = str(ident)
            ident += 1
    return cras, index


def _temps(
    missions: list[dict[str, Any]],
    ressources: list[dict[str, Any]],
    matrice: dict[tuple[str, int, int], float],
    index_cra: dict[tuple[str, int, int], str],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Lignes de temps : production par mission (les MÊMES jours que les
    factures), intercontrat pour le banc, et quelques astreintes."""
    temps: list[dict[str, Any]] = []
    # Les ids réels sont composites et séquentiels PAR CATÉGORIE :
    # `regular_1`, `exceptional_1`… (relevé tenant : premier id `regular_1`).
    compteurs = {"regular": 0, "exceptional": 0}

    def _id_temps(categorie: str) -> str:
        compteurs[categorie] += 1
        return f"{categorie}_{compteurs[categorie]}"

    for mission in missions:
        res_id = mission["relationships"]["dependsOn"]["data"]["id"]
        for annee, mois in MOIS_ACTIVITE:
            jours = matrice.get((mission["id"], annee, mois))
            cra_id = index_cra.get((res_id, annee, mois))
            if not jours or cra_id is None:
                continue
            temps.append(
                {
                    "id": _id_temps("regular"),
                    "type": "time",
                    "attributes": {
                        "category": "regular",
                        "workUnitType": {
                            "reference": 1,
                            "activityType": "production",
                            "name": "Journée de production",
                        },
                        "row": 1,
                        "startDate": _d(date(annee, mois, 1)),
                        "duration": jours,
                    },
                    "relationships": {
                        "timesReport": _rel("timesreport", cra_id),
                        "delivery": _rel("delivery", mission["id"]),
                        "batch": _rel("batch", None),
                        "project": mission["relationships"]["project"],
                    },
                }
            )
            if rng.random() < 0.12:
                temps.append(
                    {
                        "id": _id_temps("exceptional"),
                        "type": "time",
                        "attributes": {
                            "category": "exceptional",
                            "workUnitType": {
                                "reference": 40,
                                "activityType": "exceptionalTime",
                                "name": "Astreinte week-end",
                            },
                            "row": 2,
                            "startDate": _d(date(annee, mois, rng.choice([7, 14, 21]))),
                            "duration": 1.0,
                        },
                        "relationships": {
                            "timesReport": _rel("timesreport", cra_id),
                            "delivery": _rel("delivery", mission["id"]),
                            "batch": _rel("batch", None),
                            "project": mission["relationships"]["project"],
                        },
                    }
                )

    # Le banc saisit de l'intercontrat — sans mission ni projet, le dialecte réel.
    for res in ressources:
        if res["attributes"]["availability"] != "immediate":
            continue
        for annee, mois in MOIS_ACTIVITE:
            cra_id = index_cra.get((res["id"], annee, mois))
            if cra_id is None or mois < 6:
                continue
            temps.append(
                {
                    "id": _id_temps("regular"),
                    "type": "time",
                    "attributes": {
                        "category": "regular",
                        "workUnitType": {
                            "reference": 10,
                            "activityType": "internal",
                            "name": "Intercontrat",
                        },
                        "row": 1,
                        "startDate": _d(date(annee, mois, 1)),
                        "duration": 9.0 if mois == 7 else float(_jours_ouvres(annee, mois)),
                    },
                    "relationships": {
                        "timesReport": _rel("timesreport", cra_id),
                        "delivery": _rel("delivery", None),
                        "batch": _rel("batch", None),
                        "project": _rel("project", None),
                    },
                }
            )
    return temps


def _absences_et_rapports(
    ressources: list[dict[str, Any]],
    agences: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Lignes d'absence, contexte IMBRIQUÉ (rapport, agence, ressource) — le
    dialecte réel de /absences : tout vit dans `attributes`, pas de relations."""
    absences: list[dict[str, Any]] = []
    ident = 1
    rapport_id = 1
    for res in ressources:
        rid = int(res["id"])
        # Les faits suivent l'EFFECTIF, pas le seul etat STAFFED. Une personne
        # en intercontrat prend des conges et engage des frais ; une personne
        # en conge longue duree a, par definition, une absence. Filtrer sur
        # `state == 1` les privait de tout fait — meme defaut que le banc.
        if rid <= 2 or res["attributes"]["state"] not in ETATS_DANS_L_EFFECTIF:
            continue
        agence = next(a for a in agences if a["id"] == res["relationships"]["agency"]["data"]["id"])
        plages: list[tuple[date, date, tuple[int, str]]] = [
            # Les congés d'été, posés à l'avance — rapport en attente.
            (date(2026, 8, 3), date(2026, 8, 14), _TYPES_ABSENCE[0]),
        ]
        if rid % 2 == 0:
            rtt = date(2026, 5, rng.choice([15, 22]))  # deux vendredis de mai
            plages.append((rtt, rtt, _TYPES_ABSENCE[1]))
        if rid % 5 == 0:
            # Deux jours ouvrés consécutifs : on recule jusqu'à un lundi-jeudi.
            debut_maladie = date(2026, 6, rng.randint(8, 18))
            while debut_maladie.weekday() > 3:
                debut_maladie -= timedelta(days=1)
            plages.append((debut_maladie, debut_maladie + timedelta(days=1), _TYPES_ABSENCE[2]))
        if rid % 9 == 0:
            jour = date(2026, 6, 26)
            plages.append((jour, jour, _TYPES_ABSENCE[3]))

        for debut, fin, (reference, libelle) in plages:
            jours = sum(
                1
                for n in range((fin - debut).days + 1)
                if (debut + timedelta(days=n)).weekday() < 5
            )
            futur = debut > AUJOURDHUI
            creation = debut - timedelta(days=rng.randint(15, 45))
            absences.append(
                {
                    "id": str(ident),
                    "type": "absence",
                    "attributes": {
                        "startDate": _d(debut),
                        "endDate": _d(fin),
                        "duration": float(jours),
                        "title": libelle,
                        "workUnitType": {
                            "reference": reference,
                            "activityType": "absence",
                            "name": libelle,
                        },
                        "absencesReport": {
                            "id": str(rapport_id),
                            "creationDate": _dt(creation, 8, 40),
                            "state": "waitingForValidation" if futur else "validated",
                            "agency": {
                                "id": agence["id"],
                                "name": agence["attributes"]["name"],
                                "workUnitRate": 1,
                            },
                            "resource": {
                                "id": res["id"],
                                "lastName": res["attributes"]["lastName"],
                                "firstName": res["attributes"]["firstName"],
                                "workUnitRate": 1,
                            },
                        },
                    },
                }
            )
            ident += 1
            rapport_id += 1
    return absences


def _frais(
    missions: list[dict[str, Any]],
    ressources: list[dict[str, Any]],
    projets: list[dict[str, Any]],
    agences: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Notes de frais — contexte imbriqué (rapport, mission, projet), comme
    /absences. Un rapport par (consultant, mois), km et frais réels mêlés."""
    frais: list[dict[str, Any]] = []
    ident = 1
    rapport_id = 1
    missions_frais = [m for m in missions if int(m["id"]) % 2 == 1][:10]
    for mission in missions_frais:
        res = next(
            r for r in ressources if r["id"] == mission["relationships"]["dependsOn"]["data"]["id"]
        )
        projet = next(
            p for p in projets if p["id"] == mission["relationships"]["project"]["data"]["id"]
        )
        agence = next(a for a in agences if a["id"] == res["relationships"]["agency"]["data"]["id"])
        for annee, mois in MOIS_ACTIVITE:
            if mois == 7 and int(res["id"]) % 3 == 0:
                continue
            rapport = {
                "id": str(rapport_id),
                "term": f"{annee:04d}-{mois:02d}",
                "state": "validated" if mois < 7 else "waitingForValidation",
                "ratePerKilometerType": {"reference": 3, "name": "Barème 5 CV", "amount": 0.548},
                "advance": 0.0,
                "agency": {"id": agence["id"], "name": agence["attributes"]["name"]},
                "resource": {
                    "id": res["id"],
                    "lastName": res["attributes"]["lastName"],
                    "firstName": res["attributes"]["firstName"],
                },
            }
            rapport_id += 1
            lignes: list[tuple[tuple[int, str, float], float, bool, int]] = [
                (_TYPES_FRAIS[0][:3], round(rng.uniform(18, 52), 2), False, 0),
                (_TYPES_FRAIS[1][:3], round(rng.uniform(30, 120), 2), True, 0),
            ]
            if int(res["id"]) % 4 == 0:
                lignes.append((_TYPES_FRAIS[3][:3], 0.0, False, rng.choice([180, 240, 320])))
            for row, ((type_ref, type_nom, taux), montant_base, refacture, km) in enumerate(
                lignes, start=1
            ):
                kilometrique = km > 0
                montant_ttc = round(km * 0.548, 2) if kilometrique else montant_base
                jour = date(annee, mois, rng.randint(2, 26))
                frais.append(
                    {
                        "id": str(ident),
                        "type": "expense",
                        "attributes": {
                            "category": "actual",
                            "activityType": "production",
                            "expenseType": {
                                "reference": type_ref,
                                "taxRate": taux,
                                "name": type_nom,
                            },
                            "row": row,
                            "startDate": _d(jour),
                            "reinvoiced": refacture,
                            "amountIncludingTax": montant_ttc,
                            "tax": 0.0
                            if kilometrique
                            else round(montant_ttc - montant_ttc / (1 + taux / 100), 2),
                            "numberOfKilometers": float(km),
                            "number": 1,
                            "title": f"{type_nom} — {projet['attributes']['reference']}",
                            "currency": 0,
                            "exchangeRate": 1.0,
                            "isKilometricExpense": kilometrique,
                            "expensesReport": rapport,
                            "delivery": {
                                "id": mission["id"],
                                "title": mission["attributes"]["title"],
                                "startDate": mission["attributes"]["startDate"],
                                "endDate": mission["attributes"]["endDate"],
                            },
                            "project": {
                                "id": projet["id"],
                                "reference": projet["attributes"]["reference"],
                            },
                        },
                    }
                )
                ident += 1
    return frais


# ═════════════════════════════════════════════════════════════════════════════
#  Actions CRM
# ═════════════════════════════════════════════════════════════════════════════


def _actions(
    candidats: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
    opportunites: list[dict[str, Any]],
    projets: list[dict[str, Any]],
    *,
    ressources: list[dict[str, Any]],
    factures: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """~45 actions rattachées à leurs entités via `dependsOn` — le dialecte réel."""
    actions: list[dict[str, Any]] = []
    ident = 1

    def _ajouter(
        cible_type: str,
        cible_id: str,
        type_of: int,
        texte: str,
        *,
        jour: date,
        manager: int,
        societe_id: str | None,
    ) -> None:
        nonlocal ident
        actions.append(
            {
                "id": str(ident),
                "type": "action",
                "attributes": {
                    "startDate": _dt(jour, rng.randint(9, 18), rng.choice([0, 15, 30, 45])),
                    "creationDate": _dt(jour, 8, 5),
                    "typeOf": type_of,
                    "text": texte,
                    "numberOfFiles": 0,
                    "canReadAction": True,
                    "canWriteAction": True,
                    "updateDate": _dt(min(jour, DERNIERE_MAJ), 18, 55),
                },
                "relationships": {
                    "mainManager": _rel("resource", manager),
                    "dependsOn": _rel(cible_type, cible_id),
                    "company": _rel("company", societe_id),
                    "relatedActions": {"data": []},
                },
            }
        )
        ident += 1

    # Une seule action par candidat, toujours du même type, ne laisse RIEN à
    # reconstituer : ni dates d'étape, ni durées, ni « time to hire ». Un
    # consommateur calcule alors une durée de parcours de zéro jour sur tous les
    # candidats — et une colonne pleine de zéros se lit comme une donnée, pas
    # comme un manque.
    #
    # Les rythmes VARIENT délibérément : des délais identiques rendraient toute
    # moyenne artificielle. C'est la dispersion qui rend un jeu d'essai utile.
    _ETAPES = [
        (1, "Prequalification telephonique — profil coherent avec le besoin."),
        (2, "ITW 1 — parcours et motivations, retour favorable."),
        (3, "ITW 2 technique — mise en situation sur un cas data."),
        (4, "Prise de references aupres de l'ancien manager."),
        (5, "ITW 3 avec la direction de practice."),
        (6, "Proposition transmise."),
    ]
    # Délais en jours depuis la création. La LONGUEUR de la liste décide où le
    # parcours s'arrête : 3 complets, 2 stoppés en ITW 2, 2 en cours, 1 vivier.
    _RYTHMES = {
        1: [7, 14, 22, 30, 38, 52],
        2: [5, 19, 33, 47, 61, 90],
        3: [9, 16, 24, 31, 40, 55],
        4: [6, 13, 21],
        5: [11, 25, 38],
        6: [8, 20],
        7: [12],
        8: [7, 15, 23, 29],
    }
    for candidat in candidats:
        cid = int(candidat["id"])
        creation = date.fromisoformat(candidat["attributes"]["creationDate"][:10])
        rythme = _RYTHMES.get(cid)
        if rythme is None:
            # Les autres gardent une action unique : un jeu où TOUS ont un
            # parcours complet serait aussi irréaliste qu'un jeu où aucun n'en a.
            _ajouter(
                "candidate",
                candidat["id"],
                1,
                "Prequalification telephonique — a recontacter.",
                jour=creation + timedelta(days=7),
                manager=rng.choice((2, 4, 6)),
                societe_id=None,
            )
            continue
        for (type_of, texte), delai in zip(_ETAPES, rythme, strict=False):
            _ajouter(
                "candidate",
                candidat["id"],
                type_of,
                texte,
                jour=creation + timedelta(days=delai),
                manager=rng.choice((2, 4, 6)),
                societe_id=None,
            )
    for contact in contacts[:12]:
        jour = date(2026, rng.randint(2, 7), rng.randint(1, 26))
        _ajouter(
            "contact",
            contact["id"],
            rng.choice([1, 2, 3]),
            rng.choice(
                [
                    "Appel de suivi — points d'attention budgétaires évoqués.",
                    "Déjeuner de suivi de compte, prochaines échéances passées en revue.",
                    "Envoi de la plaquette d'offres data & IA.",
                ]
            ),
            jour=min(jour, AUJOURDHUI),
            manager=rng.choice((2, 3, 5)),
            societe_id=contact["relationships"]["company"]["data"]["id"],
        )
    for opportunite in opportunites[:10]:
        jour = date.fromisoformat(opportunite["attributes"]["creationDate"][:10]) + timedelta(
            days=rng.randint(5, 40)
        )
        _ajouter(
            "opportunity",
            opportunite["id"],
            rng.choice([3, 5]),
            rng.choice(
                [
                    "Soutenance de la proposition devant le comité de sélection.",
                    "Relance sur la proposition envoyée — décision attendue sous quinzaine.",
                    "Cadrage du besoin avec l'équipe métier.",
                ]
            ),
            jour=jour,
            manager=rng.choice((2, 3, 5)),
            societe_id=opportunite["relationships"]["company"]["data"]["id"],
        )
    for projet in projets[:8]:
        jour = date(2026, rng.randint(4, 7), rng.randint(1, 26))
        _ajouter(
            "project",
            projet["id"],
            6,
            "Comité de pilotage mensuel — avancement conforme au plan de charge.",
            jour=min(jour, AUJOURDHUI),
            manager=rng.choice((2, 3, 5)),
            societe_id=projet["relationships"]["company"]["data"]["id"],
        )
    for res in [r for r in ressources if 7 <= int(r["id"]) <= 14]:
        jour = date(2026, rng.randint(1, 6), rng.randint(2, 26))
        _ajouter(
            "resource",
            res["id"],
            7,
            "Entretien annuel — objectifs et plan de formation actualisés.",
            jour=jour,
            manager=4,
            societe_id=None,
        )
    en_retard = [
        f for f in factures if f["attributes"]["state"] == 1 and not f["attributes"]["isCreditNote"]
    ][:3]
    for facture in en_retard:
        jour = date.fromisoformat(facture["attributes"]["expectedPaymentDate"])
        _ajouter(
            "invoice",
            facture["id"],
            2,
            f"Relance règlement {facture['attributes']['reference']} auprès du service comptable.",
            jour=min(jour, AUJOURDHUI),
            manager=2,
            societe_id=None,
        )
    return actions


# ═════════════════════════════════════════════════════════════════════════════
#  Dossier technique et rémunération (affordances conservées)
# ═════════════════════════════════════════════════════════════════════════════


def _donnees_techniques(
    ressources: list[dict[str, Any]],
    projets: list[dict[str, Any]],
    societes: list[dict[str, Any]],
    rng: random.Random,
) -> dict[str, dict[str, Any]]:
    donnees = {}
    for res in ressources:
        attrs = res["attributes"]
        nb = rng.randint(1, 3)
        references: list[dict[str, Any]] = []
        for n in range(nb):
            projet = rng.choice(projets)
            societe = next(
                s for s in societes if s["id"] == projet["relationships"]["company"]["data"]["id"]
            )
            debut = date.fromisoformat(projet["attributes"]["startDate"])
            competences = rng.sample(_COMPETENCES, k=3)
            references.append(
                {
                    "id": f"{int(res['id']) * 100 + n + 1}",
                    "title": attrs["title"],
                    "company": societe["attributes"]["name"],
                    "description": (
                        f"Intervention {attrs['title']} pour {societe['attributes']['name']} : "
                        "cadrage, mise en œuvre et industrialisation de la solution cible."
                    ),
                    "location": societe["attributes"]["town"],
                    "startMonth": debut.month,
                    "startYear": debut.year,
                    "endMonth": min(12, debut.month + 6),
                    "endYear": debut.year,
                    "skills": competences,
                }
            )
        donnees[res["id"]] = {
            "id": res["id"],
            "type": "resource",
            "attributes": {
                "description": (
                    f"{attrs['title']} — {attrs['experience']} ans d'expérience, "
                    f"interventions {', '.join(attrs['expertiseAreas'])}."
                ),
                "summary": f"{attrs['title']}, {attrs['experience']} ans d'expérience.",
                "references": references,
            },
        }
    return donnees


def _remuneration(
    ressources: list[dict[str, Any]],
    contrats: list[dict[str, Any]],
    agences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """La fixture CSV hors /api — désormais DÉRIVÉE des contrats officiels."""
    lignes: list[dict[str, Any]] = []
    for contrat in contrats:
        if contrat["attributes"]["typeOf"] != 0:  # CDI uniquement
            continue
        res = next(
            r for r in ressources if r["id"] == contrat["relationships"]["dependsOn"]["data"]["id"]
        )
        agence = next(a for a in agences if a["id"] == res["relationships"]["agency"]["data"]["id"])
        lignes.append(
            {
                "collaborateur_id": res["id"],
                "upn": res["attributes"]["email1"],
                "entite": agence["attributes"]["name"],
                "periode": contrat["attributes"]["startDate"],
                "montant_brut_annuel": int(contrat["attributes"]["monthlySalary"] * 12),
            }
        )
    return lignes


# ═════════════════════════════════════════════════════════════════════════════
#  Assemblage
# ═════════════════════════════════════════════════════════════════════════════


def _dictionnaire() -> dict[str, Any]:
    """Les libellés d'énumération CONFIGURÉS DE L'INSTANCE.

    L'API rend des entiers ; les libellés ne sont pas des constantes du produit.
    `GET /application/dictionary` est le seul endroit qui les donne, et sans lui
    aucun consommateur ne peut traduire un code.

    Deux formes coexistent volontairement — dict de sous-domaines pour `state`,
    liste pour le reste. C'est ce que décrit la documentation de l'éditeur.

    ⚠️ `action` et `actionOnOpportunity` sont DEUX clés distinctes. L'instance
    porte deux nomenclatures d'actions qui partagent des libellés sous des codes
    différents (« TOUCH POINT » existe en 01 et en 09, avec deux sens) : les
    fondre ferait traduire un type d'action de besoin par un libellé général.

    Les valeurs décrivent les codes que le mock REND — un dictionnaire qui ne
    correspond pas au jeu ferait passer les tests avec des traductions fausses,
    ce qui est pire qu'un mock muet. Le test de couverture l'assure.
    """
    return {
        "state": {
            "opportunity": [
                {"id": 1, "value": "Open"},
                {"id": 2, "value": "Qualified (working on solution)"},
                {"id": 3, "value": "Proposed solution"},
                {"id": 7, "value": "WON"},
                {"id": 8, "value": "LOST"},
                {"id": 9, "value": "POSTPONED / ABANDONED"},
            ],
            "candidate": [
                {"id": 0, "value": "SOURCED"},
                {"id": 1, "value": "PREQUAL [1ST CONTACT]"},
                {"id": 2, "value": "ITW 1 [TA/BM]"},
                {"id": 3, "value": "ITW 2 [TECH/BUSINESS]"},
                {"id": 4, "value": "REFERENCE CHECK"},
                {"id": 5, "value": "ITW 3 [DIR/PARTNER]"},
            ],
            # LES SIX ÉTATS, parce que le jeu en rend six depuis le bloc ③.
            # Il n'en déclarait que trois : un dictionnaire qui ne couvre pas
            # son propre jeu fait passer les tests avec des traductions
            # manquantes — le défaut que cette docstring interdit deux lignes
            # plus haut.
            #
            # ⚠️ LA NUMÉROTATION RESTE CELLE DU MOCK, ET ELLE N'EST PAS
            # ATTESTÉE. La feuille INDEX numérote les libellés de 01 à 06, mais
            # `stg_collaborateur.sql` a déjà tranché que ce préfixe est une
            # CONVENTION D'AFFICHAGE de l'instance, pas l'entier rendu par
            # l'API. Pour les opportunités, deux sources indépendantes
            # concordaient — le process Confluence ET l'export. Ici il n'y a
            # que le préfixe : une concordance ne fait pas une règle.
            #
            # Cette route est précisément ce qui tranchera la question le jour
            # où elle interrogera l'instance réelle. D'ici là, le mock est
            # cohérent avec lui-même, et c'est tout ce qu'un mock doit garantir.
            "resource": [
                {"id": 0, "value": "OFF"},
                {"id": 1, "value": "STAFFED"},
                {"id": 2, "value": "HIRED - ONBOADING PHASE"},
                {"id": 3, "value": "UN/IC - UNASIGNED [From 8 W to now]"},
                {"id": 4, "value": "LONG TERM LEAVE"},
                {"id": 5, "value": "LEAVING COMPANY"},
            ],
            # ── Les sous-domaines ajoutes en 0.5.5 ───────────────────────────
            # Le mock rendait ces entiers sans que rien ne puisse les traduire.
            # Chaque libelle vient d'une branche du jeu, citee en commentaire.
            #
            # `"state": 0 if prospect else 1` dans _societes.
            "company": [
                {"id": 0, "value": "Prospect"},
                {"id": 1, "value": "Client"},
            ],
            # ⚠️ CONSTANTE MUETTE. _contacts pose `"state": 1` pour tous les
            # contacts, sans branche qui en donne le sens. Le libelle est de
            # notre fabrication : il rend le code traduisible, il ne l'atteste
            # pas. Le guide Boond decrit une qualification de contact
            # (Decision maker / Influencer / Buyer / Inactive) mais ne donne
            # AUCUN code — la colonne `code` du referentiel de repli est vide,
            # et le rester est deliberé.
            "contact": [
                {"id": 1, "value": "Active"},
            ],
            # ⚠️ CONSTANTE MUETTE — _commandes pose `"state": 1` partout.
            "order": [
                {"id": 1, "value": "Validated"},
            ],
            # ⚠️ CONSTANTE MUETTE — _achats pose `"state": 1` sur les deux
            # familles d'achats, ceux rattaches a une mission et les generaux.
            "purchase": [
                {"id": 1, "value": "Validated"},
            ],
            # `reglees = [f for f in factures if f["attributes"]["state"] == 2]`
            # et `"closed": etat == 2` dans _factures : 2 est l'etat terminal.
            # 0 est l'etat des factures ni envoyees ni payees, 1 celui des
            # factures envoyees en attente de reglement.
            "invoice": [
                {"id": 0, "value": "Draft"},
                {"id": 1, "value": "Sent"},
                {"id": 2, "value": "Paid"},
            ],
            # `"state": 1 if effectue else 0` dans _paiements.
            "payment": [
                {"id": 0, "value": "Pending"},
                {"id": 1, "value": "Executed"},
            ],
            # `"state": 2 if rapprochee else 0` dans _banque. Le 1 n'est jamais
            # rendu : on ne le declare donc pas. Un dictionnaire qui annonce
            # des codes que le jeu ne produit pas est aussi trompeur que
            # l'inverse — il laisse croire a une couverture qui n'existe pas.
            "bankingTransaction": [
                {"id": 0, "value": "Not reconciled"},
                {"id": 2, "value": "Reconciled"},
            ],
            # `"state": 1 if fin_projet >= AUJOURDHUI else 2` dans _missions.
            # La ROUTE de liste des livraisons repond 405 chez l'editeur — seul
            # le detail existe — mais l'objet porte bien cet etat, et les marts
            # le consomment via le projet.
            "delivery": [
                {"id": 1, "value": "In progress"},
                {"id": 2, "value": "Completed"},
            ],
        },
        # ── `typeOf`, symetrique de `state` ─────────────────────────────────
        #
        # ⚠️ LA FORME EST DE NOTRE FABRICATION, comme `state` avant elle. Ce qui
        # est atteste : l'API rend un `typeOf` entier sur cinq familles d'objets
        # et n'en donne le libelle nulle part ailleurs. Marquee `invented` dans
        # le modele et dans docs/UNVERIFIED-FIELDS.md.
        "typeOf": {
            # PROUVE, et c'est le seul de ce bloc a l'etre : six tests du mock
            # etablissent que `typeOf` porte salarie/sous-traitant et pilote la
            # generation des contrats. Ce n'est PAS la nomenclature des seize
            # types de la feuille INDEX — une premiere version de ce patch le
            # supposait, les tests l'ont dementie.
            "resource": [
                {"id": 0, "value": "Employee"},
                {"id": 1, "value": "Subcontractor"},
            ],
            # ⚠️ CONSTANTE MUETTE — _candidats pose `"typeOf": 0` partout.
            "candidate": [
                {"id": 0, "value": "Default"},
            ],
            # ⚠️ CONSTANTE MUETTE — _opportunites pose `"typeOf": 1` sur la
            # route de liste.
            "opportunity": [
                {"id": 1, "value": "Default"},
            ],
            # `mode = 1 if i % 3 else 2` et le commentaire du jeu, mot pour
            # mot : « 1 = assistance technique, 2 = forfait ». _projets recopie
            # ce mode dans `typeOf`.
            "project": [
                {"id": 1, "value": "Technical assistance"},
                {"id": 2, "value": "Fixed price"},
            ],
            # La table `generaux` de _achats porte le type en 3e colonne :
            # licences et abonnements en 2, loyers en 3, materiel en 4. Le 0
            # est celui des achats rattaches a une mission, donc de la
            # sous-traitance.
            "purchase": [
                {"id": 0, "value": "Subcontracting"},
                {"id": 2, "value": "Software and licenses"},
                {"id": 3, "value": "Premises"},
                {"id": 4, "value": "Equipment"},
            ],
        },
        "action": [
            {"id": 1, "value": "TODO / Reminder"},
            {"id": 2, "value": "Touch point"},
            {"id": 3, "value": "1st Prospection meeting"},
            {"id": 4, "value": "DVP"},
            {"id": 5, "value": "Project review meeting"},
            {"id": 6, "value": "Client presentation / defense"},
            {"id": 7, "value": "Manifesto client"},
        ],
        # ⚠️ CLÉ INFÉRÉE, et il faut le savoir. `action` et `actionOnOpportunity`
        # sont attestées ; celle-ci ne l'est pas — c'est le nom que suggère la
        # convention des deux autres. Ce qui EST attesté, c'est qu'une
        # nomenclature d'actions sur candidat existe dans l'instance : la
        # feuille `Dashb` du fichier de mappings en compte les volumes sur 31
        # semaines (1 006 ITW1, 260 ITW2, 54 ITW3, 248 PREQUAL).
        #
        # Elle est déclarée parce que le bloc ④ fait émettre ces six types :
        # un dictionnaire muet sur ce que son propre jeu produit est le défaut
        # que cette docstring interdit. Si l'instance nomme la clé autrement,
        # c'est un renommage — pas une reprise du raisonnement.
        "actionOnCandidate": [
            {"id": 1, "value": "PREQUAL [1ST CONTACT]"},
            {"id": 2, "value": "ITW 1 [TA/BM]"},
            {"id": 3, "value": "ITW 2 [TECH/BUSINESS]"},
            {"id": 4, "value": "REFERENCE CHECK"},
            {"id": 5, "value": "ITW 3 [DIR/PARTNER]"},
            {"id": 6, "value": "PROPOSITION"},
        ],
        "actionOnOpportunity": [
            {"id": 1, "value": "NEED STUDY / QUALIFICATION"},
            {"id": 2, "value": "CLIENT PRESENTATION / DEFENSE"},
            {"id": 3, "value": "CLOSING"},
            {"id": 4, "value": "TODO"},
        ],
        "origin": [
            {"id": 1, "value": "Site carrière"},
            {"id": 2, "value": "LinkedIn"},
            {"id": 3, "value": "Cooptation"},
            {"id": 4, "value": "Chasse"},
            {"id": 5, "value": "Salon Big Data Paris"},
        ],
    }


def build_realiste_dataset(seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)

    agences = _agences()
    poles = _poles()
    roles = _roles()
    ressources = _ressources(rng)
    business_units = _business_units(ressources)
    contrats = _contrats(ressources, rng, seed)
    candidats = _candidats(rng)
    societes = _societes(rng)
    contacts = _contacts(societes, rng)
    opportunites = _opportunites(societes, contacts, rng)
    projets = _projets(opportunites, societes, rng)
    missions = _missions(projets, ressources, rng)
    matrice = _jours_travailles(missions, rng)
    commandes = _commandes(projets, missions, rng)
    factures = _factures(commandes, missions, matrice, rng)
    achats = _achats(missions, ressources, rng)
    paiements = _paiements(achats)
    comptes, connexions, transactions = _banque(factures, societes, commandes, projets, rng)
    cras, index_cra = _cras(ressources, rng)
    temps = _temps(missions, ressources, matrice, index_cra, rng)
    absences = _absences_et_rapports(ressources, agences, rng)
    frais = _frais(missions, ressources, projets, agences, rng)
    actions = _actions(
        candidats,
        contacts,
        opportunites,
        projets,
        ressources=ressources,
        factures=factures,
        rng=rng,
    )

    # Consolidation projets ← missions (CA simulé, marge, rentabilité).
    for projet in projets:
        missions_projet = [
            m for m in missions if m["relationships"]["project"]["data"]["id"] == projet["id"]
        ]
        ca = round(
            sum(m["attributes"]["turnoverSimulatedExcludingTax"] for m in missions_projet), 2
        )
        couts = round(
            sum(m["attributes"]["costsSimulatedExcludingTax"] for m in missions_projet), 2
        )
        projet["attributes"]["turnoverSimulatedExcludingTax"] = ca
        projet["attributes"]["marginSimulatedExcludingTax"] = round(ca - couts, 2)
        projet["attributes"]["profitabilitySimulated"] = (
            round((ca - couts) / ca * 100, 2) if ca else 0.0
        )

    # Le CV résumé des ressources pointe des références réelles du dossier technique.
    donnees_techniques = _donnees_techniques(ressources, projets, societes, rng)
    for res in ressources:
        res["attributes"]["references"] = [
            {"id": ref["id"], "title": ref["title"], "description": ref["description"]}
            for ref in donnees_techniques[res["id"]]["attributes"]["references"]
        ]
        del res["attributes"]["_bu"]  # clé interne au générateur

    return {
        "absences": absences,
        "actions": actions,
        # Les avantages VERSÉS : le variable, les primes, les avantages en
        # nature réellement payés. Indexés par RESSOURCE, comme la route.
        "advantages": _avantages_verses(ressources, contrats, seed),
        "agencies": agences,
        "banking_accounts": comptes,
        "banking_connections": connexions,
        "banking_transactions": transactions,
        "business_units": business_units,
        "candidates": candidats,
        "companies": societes,
        "contacts": contacts,
        "contracts": contrats,
        "deliveries": missions,
        "expenses": frais,
        "invoices": factures,
        "opportunities": opportunites,
        "orders": commandes,
        "payments": paiements,
        "poles": poles,
        "projects": projets,
        "purchases": achats,
        "resources": ressources,
        "roles": roles,
        "times": temps,
        "times_reports": cras,
        "technical_data": donnees_techniques,
        "remuneration": _remuneration(ressources, contrats, agences),
        "dictionary": _dictionnaire(),
    }
