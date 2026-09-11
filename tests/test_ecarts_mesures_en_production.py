"""Les endroits où le mock racontait autre chose que le fournisseur.

┌─ CE QUE CES TESTS DÉFENDENT ────────────────────────────────────────────────┐
│ Ce dépôt existe pour qu'un consommateur puisse développer sans toucher      │
│ l'API réelle. Cette promesse ne tient QUE si ce qu'il émet est ce que le    │
│ fournisseur émet — un mock plus généreux que la vraie API ne rend pas       │
│ service : il déplace la découverte du défaut vers la production, là où      │
│ elle coûte le plus cher.                                                    │
│                                                                             │
│ Deux sondes, toutes deux en LECTURE SEULE contre un tenant de production :  │
│                                                                             │
│   2026-08-12 — les dix-huit collections, une page chacune. Quatre écarts.   │
│                Chacun avait déjà cassé la chaîne insights360 en production  │
│                pendant que la CI restait verte — au pire moment, et pour la │
│                pire raison : parce qu'on avait cru le mock.                 │
│                                                                             │
│   2026-09-10 — le PACKAGE SALARIAL : profils de contrat et avantages. Trois │
│                champs que le mock remplissait et que le fournisseur laisse  │
│                vides, une forme jamais observée (`advantageTypes`), et une  │
│                route entière qui manquait (`/resources/{id}/advantages`,    │
│                là où vit le variable).                                       │
│                                                                             │
│ Ces tests ne vérifient donc pas un choix de conception, mais un RELEVÉ. Ils │
│ ne doivent bouger que si une nouvelle sonde montre autre chose.             │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from tests.conftest import ADMIN, JWT

# Les dix-huit collections sondées, par leur chemin d'API.
COLLECTIONS = [
    "resources",
    "agencies",
    "companies",
    "contacts",
    "projects",
    "times",
    "actions",
    "opportunities",
    "poles",
    "candidates",
    "orders",
    "purchases",
    "business-units",
    "absences",
    "invoices",
    "expenses",
    "payments",
]


def _premiers(client, collection: str, **params) -> list[dict]:
    requete = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/{collection}" + (f"?{requete}" if requete else "")
    reponse = client.get(url, headers=JWT)
    assert reponse.status_code == 200, f"{collection}: {reponse.status_code}"
    return reponse.json()["data"]


# ── 1. `isDeleted` n'est pas un champ du fournisseur ─────────────────────────


def test_aucune_collection_ne_sert_isdeleted_par_defaut(client):
    """Absent des DIX-HUIT collections réelles — il doit l'être ici aussi.

    C'est l'écart qui a coûté le plus cher : dix-sept modèles de staging bâtis
    sur `where not is_deleted`, tous verts contre ce mock, tous cassés au
    premier run de production.
    """
    fautives = []
    for collection in COLLECTIONS:
        lignes = _premiers(client, collection, maxResults=5)
        if any("isDeleted" in (ligne.get("attributes") or {}) for ligne in lignes):
            fautives.append(collection)

    assert not fautives, (
        "isDeleted servi par défaut sur : "
        + ", ".join(fautives)
        + " — le fournisseur ne l'expose sur AUCUNE collection."
    )


def test_le_drapeau_reste_disponible_apres_une_suppression_explicite(client):
    """L'affordance n'est pas supprimée : elle cesse d'être un DÉFAUT.

    `/__admin/delete` doit continuer à poser le drapeau, sinon on perd le seul
    moyen d'exercer la gestion des suppressions chez le consommateur. Ce qui
    change, c'est qu'il faut le DEMANDER — et une charge par défaut ressemble
    alors à celle du fournisseur.
    """
    client.post("/__admin/delete", headers=ADMIN, json={"collection": "resources", "id": "8"})
    lignes = _premiers(client, "resources", maxResults=500)
    marquee = next(ligne for ligne in lignes if ligne["id"] == "8")
    assert marquee["attributes"]["isDeleted"] is True

    autres = [ligne for ligne in lignes if ligne["id"] != "8"]
    assert all("isDeleted" not in ligne["attributes"] for ligne in autres), (
        "seul l'enregistrement explicitement supprimé porte le drapeau"
    )


# ── 2. `/orders` ne porte pas d'horodatage de mise à jour ────────────────────


def test_les_commandes_n_ont_ni_updatedate_ni_creationdate(client):
    """`/orders` ne porte AUCUN des deux horodatages.

    `updateDate` d'abord : il porte la stratégie d'extraction, et le servir fait
    déclarer la collection incrémentale — le curseur casse alors en réel.

    `creationDate` ensuite, et c'est une erreur qu'il vaut la peine de garder
    sous test : 0.6.0 l'avait maintenu au motif qu'« il ne pilote aucune
    stratégie, donc le servir ne coûte rien ». C'était faux — un modèle qui LIT
    une colonne a besoin qu'elle EXISTE, et `stg_commande` est tombé sur
    « column o.creation_date does not exist » au run suivant.

    D'où la forme de ce test : la règle n'admet pas d'exception « inoffensive ».
    """
    for ligne in _premiers(client, "orders", maxResults=10):
        attributs = ligne["attributes"]
        for champ in ("updateDate", "creationDate"):
            assert champ not in attributs, f"le fournisseur ne rend pas `{champ}` sur les commandes"
        assert "date" in attributs, (
            "`date` (la date de commande) est bien rendue en réel — ne pas la retirer"
        )


def test_les_autres_collections_gardent_leur_updatedate(client):
    """Le garde inverse : ne pas « corriger » au-delà de ce qui a été mesuré."""
    for collection in ("resources", "companies", "projects", "invoices"):
        lignes = _premiers(client, collection, maxResults=5)
        assert all("updateDate" in ligne["attributes"] for ligne in lignes), (
            f"{collection} doit garder son updateDate — il est bien rendu en réel"
        )


# ── 3. `/actions` ignore `maxResults` ────────────────────────────────────────


def test_les_actions_ignorent_maxresults(client):
    """`GET /actions?maxResults=500` rend 30 lignes, pas 500.

    Le paramètre est ACCEPTÉ — pas de 422 — et silencieusement ignoré. Un
    consommateur qui croit tenir 500 lignes par page sous-estime son nombre de
    pages d'un facteur 16.
    """
    reponse = client.get("/api/actions?maxResults=500", headers=JWT)
    assert reponse.status_code == 200, "le paramètre est accepté, jamais rejeté"

    corps = reponse.json()
    total = corps["meta"]["totals"]["rows"]
    assert len(corps["data"]) == min(30, total)


def test_les_autres_collections_honorent_maxresults(client):
    """Sans ce garde, on aurait « corrigé » tout le monde au lieu d'/actions."""
    for collection in ("contacts", "candidates", "times"):
        lignes = _premiers(client, collection, maxResults=100)
        total = client.get(f"/api/{collection}", headers=JWT).json()["meta"]["totals"]["rows"]
        attendu = min(100, total)
        assert len(lignes) == attendu, (
            f"{collection} doit honorer maxResults ({len(lignes)} au lieu de {attendu})"
        )


# ── 4. `startDate` d'un BESOIN peut valoir « immediate » ─────────────────────


def test_le_debut_d_un_besoin_peut_etre_la_chaine_immediate(client):
    """1 523 des 1 850 besoins de production portent « immediate », soit 82 %.

    Ce n'est donc pas un cas limite mais le cas DOMINANT. Le mock ne servait que
    des dates, si bien que `stg_opportunite` castait sans filet et tombait sur
    « invalid input syntax for type date: "immediate" ».

    La proportion compte autant que la présence : un jeu où le cas majoritaire
    est minoritaire laisse passer les modèles qui ne le gèrent pas.
    """
    lignes = _premiers(client, "opportunities", maxResults=500)
    debuts = [ligne["attributes"].get("startDate") for ligne in lignes]
    renseignes = [d for d in debuts if d]

    assert "immediate" in renseignes, "le littéral doit être présent"
    immediats = sum(1 for d in renseignes if d == "immediate")
    assert immediats > len(renseignes) / 2, (
        f"« immediate » doit être MAJORITAIRE ({immediats}/{len(renseignes)}) — "
        "c'est ce que rend la production"
    )
    assert any(d != "immediate" for d in renseignes), (
        "des dates réelles doivent subsister : les deux formes coexistent"
    )


# ── 5. `availability` d'un CANDIDAT est un code, pas une date ────────────────


def test_la_disponibilite_d_un_candidat_est_un_code_entier(client):
    """Relevé sur 26 814 candidats réels : des entiers, `-1` sur 24 289.

    Le mock servait une date ISO, et le consommateur la castait en date.
    """
    for ligne in _premiers(client, "candidates", maxResults=20):
        valeur = ligne["attributes"]["availability"]
        assert isinstance(valeur, int), (
            f"availability = {valeur!r} ({type(valeur).__name__}) — attendu un code entier"
        )


def test_la_disponibilite_d_une_ressource_reste_une_date(client):
    """Même nom, autre entité, autre type — et c'est le fournisseur qui le dit.

    Sur une RESSOURCE, `availability` est bien une date (ou « immediate »).
    Aligner les deux serait lisser un écart que le mock doit justement porter.
    """
    for ligne in _premiers(client, "resources", maxResults=20):
        valeur = ligne["attributes"]["availability"]
        assert isinstance(valeur, str), (
            f"availability = {valeur!r} — sur une ressource, c'est une date ou « immediate »"
        )


# ── 6. Le contrat dans `included` porte la rémunération ─────────────────────


def test_le_contrat_inclus_porte_le_salaire(client):
    """`GET /contracts` répond 405 : `included` est le SEUL chemin vers le salaire.

    Le mock n'y servait que trois attributs, sur l'idée d'une « forme réduite ».
    Sondé en production le 2026-08-13 : les seize attributs y sont, dont
    `monthlySalary`, renseigné.

    Ce que la forme réduite a coûté : ne trouvant la rémunération nulle part, le
    consommateur a conclu — et écrit dans SPEC-DEVIATIONS #5 — qu'aucun endpoint
    de rémunération n'était attesté chez BoondManager, puis a bâti tout un
    détour par un CSV de fixtures. Le fournisseur la servait depuis le début.
    """
    ressources = _premiers(client, "resources", maxResults=20)
    contrats = []
    for ressource in ressources:
        reponse = client.get(f"/api/resources/{ressource['id']}/administrative", headers=JWT)
        assert reponse.status_code == 200
        contrats += [
            inclus
            for inclus in (reponse.json().get("included") or [])
            if inclus.get("type") == "contract"
        ]

    assert contrats, "aucun contrat dans `included` — le chemin vers le salaire est coupé"
    for contrat in contrats:
        attributs = contrat["attributes"]
        assert "monthlySalary" in attributs, (
            "`monthlySalary` absent d'`included` : le consommateur ne peut PAS "
            "l'atteindre autrement, `GET /contracts` répondant 405."
        )
        assert isinstance(attributs["monthlySalary"], (int, float))
        # Le taux d'activité change la lecture du montant : un 80 % au même
        # salaire contractuel ne pèse pas la même chose sur la masse salariale.
        assert "activityRate" in attributs


def test_la_liste_des_contrats_reste_un_405(client):
    """Le garde inverse : c'est le 405 qui rend `included` indispensable.

    Si la liste devenait accessible, le détour par la fiche ressource — 364
    appels en production — n'aurait plus lieu d'être. Ce test dit que ce n'est
    pas le cas, et il le dira le jour où ça changera.
    """
    assert client.get("/api/contracts", headers=JWT).status_code == 405


# ═════════════════════════════════════════════════════════════════════════════
#  Sonde du 2026-09-10 — le package salarial
# ═════════════════════════════════════════════════════════════════════════════
#
# Quatre écarts mesurés contre un tenant de production ce jour-là. Trois
# concernent des champs que le mock REMPLISSAIT alors que le fournisseur ne les
# alimente pas — la fiction crédible, celle qui rend un consommateur vert en CI
# et faux en production. Le quatrième est une route entière qui manquait.


def test_expenses_details_est_servi_mais_toujours_vide(client):
    """0 contrat sur 18 en production. Le mock en remplissait 38 sur 38.

    C'est la famille exacte d'`isDeleted` : la clé existe, le tableau est vide,
    et un consommateur qui bâtit un modèle dessus ne s'en aperçoit qu'en prod.
    La clé reste ÉMISE — le fournisseur l'émet — avec la valeur qu'il lui donne.
    """
    for cid in ("1", "7", "12"):
        attrs = client.get(f"/api/contracts/{cid}", headers=JWT).json()["data"]["attributes"]
        assert "expensesDetails" in attrs, "la clé doit être émise"
        assert attrs["expensesDetails"] == []
        assert attrs["dailyExpenses"] == 0
        assert attrs["monthlyExpenses"] == 0
        assert attrs["calendar"] == ""


def test_activity_rate_est_nul_partout(client):
    """0 contrat sur 18 en production, et sur les 800 du tenant du consommateur.

    Le mock servait 100. Un consommateur a pondéré un brut annuel par ce taux
    et livré 800 lignes de rémunération à zéro — sans une erreur, parce qu'un
    salaire nul se lit comme « cette personne ne gagne rien ».
    """
    attrs = client.get("/api/contracts/1", headers=JWT).json()["data"]["attributes"]
    assert attrs["activityRate"] == 0


def test_les_types_d_avantage_portent_la_forme_relevee(client):
    """`advantageTypes` était servi VIDE : sa forme n'avait jamais été observée.

    Relevé le 2026-09-10 — 16 contrats sur 18, 55 lignes. Elle n'a rien à voir
    avec `DetailFraisContrat`, contrairement à ce qu'on pouvait supposer.
    """
    vus = []
    for cid in [str(i) for i in range(1, 39)]:
        reponse = client.get(f"/api/contracts/{cid}", headers=JWT)
        if reponse.status_code == 200:
            vus += reponse.json()["data"]["attributes"]["advantageTypes"]
    assert vus, "le tableau ne doit plus être vide partout"
    for ligne in vus:
        assert set(ligne) == {
            "reference",
            "name",
            "frequency",
            "category",
            "participationQuota",
            "employeeQuota",
            "agencyQuota",
        }
        assert ligne["frequency"] in {"daily", "monthly", "semiAnnual", "annual"}
        assert ligne["category"] in {"variableSalaryBasis", "package", "fixedAmount"}


def test_category_ne_dit_pas_ce_qui_est_acquis(client):
    """Le piège que le jeu de données DOIT porter, parce que le réel le porte.

    En production, la ligne nommée « Variable » est `fixedAmount` tandis que
    « Prime de vacances » est `variableSalaryBasis`. `category` décrit comment
    le montant est exprimé, pas s'il est dû. Un consommateur qui branche un
    « acquis / conditionnel » sur cette colonne doit tomber ICI.
    """
    par_nom = {}
    for cid in [str(i) for i in range(1, 39)]:
        reponse = client.get(f"/api/contracts/{cid}", headers=JWT)
        if reponse.status_code == 200:
            for ligne in reponse.json()["data"]["attributes"]["advantageTypes"]:
                par_nom[ligne["name"]] = ligne["category"]
    assert par_nom.get("Variable") == "fixedAmount"
    assert par_nom.get("Prime de vacances") == "variableSalaryBasis"


def test_la_reference_n_est_pas_un_code_global(client):
    """En production, le même 21 désigne « Health Insurance » et « Variable ».

    C'est une clé de CONFIGURATION d'agence. Un référentiel joint dessus
    rapprocherait des lignes sans rapport — le jeu de données reproduit la
    collision pour que ça se voie.
    """
    noms_par_reference: dict[int, set[str]] = {}
    for cid in [str(i) for i in range(1, 39)]:
        reponse = client.get(f"/api/contracts/{cid}", headers=JWT)
        if reponse.status_code == 200:
            for ligne in reponse.json()["data"]["attributes"]["advantageTypes"]:
                noms_par_reference.setdefault(ligne["reference"], set()).add(ligne["name"])
    assert any(len(noms) > 1 for noms in noms_par_reference.values()), (
        "aucune collision de `reference` : le piège du réel n'est pas reproduit"
    )


def test_les_avantages_verses_sont_servis_et_epars(client):
    """La route qui manquait — et c'est là que vit le variable.

    `GET /resources/{id}/advantages`, relevé le 2026-09-10 : 200 OK,
    `meta.totals.rows` = 54 sur une ressource, historique 2020 → 2026.
    ÉPARSE : six ressources sur huit n'en ont aucune.
    """
    totaux = {}
    for rid in [str(i) for i in range(1, 35)]:
        corps = client.get(f"/api/resources/{rid}/advantages", headers=JWT).json()
        totaux[rid] = corps["meta"]["totals"]["rows"]
    assert any(n == 0 for n in totaux.values()), "l'éparpillement n'est pas reproduit"
    assert max(totaux.values()) > 20, "aucun historique long : la pagination n'est pas éprouvée"

    riche = max(totaux, key=lambda r: totaux[r])
    corps = client.get(f"/api/resources/{riche}/advantages", headers=JWT).json()
    ligne = corps["data"][0]
    assert ligne["type"] == "advantage"
    assert set(ligne["attributes"]) == {
        "date",
        "quantity",
        "costPaid",
        "returnDate",
        "currency",
        "currencyAgency",
        "exchangeRate",
        "exchangeRateAgency",
        "canReadAdvantage",
        "canWriteAdvantage",
        "advantageType",
    }
    assert set(ligne["attributes"]["advantageType"]) == {"reference", "name"}
    # Le rattachement au CONTRAT, pas à la ressource : une personne peut en
    # avoir huit successifs, et un versement de 2020 n'appartient pas à celui
    # de 2026.
    assert ligne["relationships"]["contract"]["data"]["type"] == "contract"


def test_les_avantages_verses_n_ont_pas_de_curseur(client):
    """Pas d'`updateDate` : aucune extraction incrémentale n'est possible.

    En servir un inviterait un consommateur à poser un curseur qui ne
    rapatrierait rien en production — la panne silencieuse et coûteuse.
    """
    for rid in [str(i) for i in range(1, 35)]:
        for ligne in client.get(f"/api/resources/{rid}/advantages", headers=JWT).json()["data"]:
            assert "updateDate" not in ligne["attributes"]


def test_aucune_collection_d_avantages_en_masse(client):
    """`/advantages` n'existe pas — le coût d'un appel par ressource est structurel.

    Mesuré : 403 (WAF) sur `/advantages`, 404 sur `/resources-advantages` et
    `/contracts-advantages`. Un consommateur qui espère une recherche en masse
    doit se heurter au même mur ici qu'en production.
    """
    for chemin in ("/api/advantages", "/api/resources-advantages", "/api/contracts-advantages"):
        assert client.get(chemin, headers=JWT).status_code in (403, 404)


def test_le_cout_journalier_ne_se_derive_pas_du_brut(client):
    """La formule plausible que la production dément.

    Le jeu de données servait `contractAverageDailyCost = monthlySalary * 12 *
    chargeFactor / numberOfWorkingDays`. Éprouvée le 2026-09-10 sur 25 contrats
    réels : UN seul vérifie à moins de 1 %, les 24 autres non — écart relatif
    médian 11,7 %, maximum 44,2 %.

    Un mock où la relation tient exactement invite le consommateur à recalculer
    le coût au lieu de lire le champ, et son chiffre est alors faux de 12 % en
    production sans qu'aucun test ne rougisse.
    """
    exacts = testables = 0
    for cid in [str(i) for i in range(1, 39)]:
        reponse = client.get(f"/api/contracts/{cid}", headers=JWT)
        if reponse.status_code != 200:
            continue
        a = reponse.json()["data"]["attributes"]
        m, f, j, d = (
            a["monthlySalary"],
            a["chargeFactor"],
            a["numberOfWorkingDays"],
            a["contractAverageDailyCost"],
        )
        if not (m and f and j and d):
            continue
        testables += 1
        if abs(m * 12 * f / j - d) / d < 0.01:
            exacts += 1

    assert testables > 10, "pas assez de contrats pour conclure"
    # En production : 1 sur 25. On exige simplement que la relation ne soit pas
    # la règle — un mock qui la respecterait partout serait le piège d'origine.
    assert exacts / testables < 0.2, (
        f"{exacts}/{testables} contrats vérifient la formule : le jeu de données "
        "laisse croire à une relation que le fournisseur ne respecte pas"
    )


def test_chaque_agence_porte_du_package(client):
    """Un axe métier vide rend le test du consommateur VERT PAR VACUITÉ.

    Le tirage des avantages a d'abord été fait par modulo sur l'identifiant —
    `% 7` pour les droits, `% 3` pour les versements. Les deux ont écarté
    exactement la même cohorte, 7 · 14 · 28, c'est-à-dire toute l'agence de
    Nantes. Or c'est la seule entité qui distingue deux rôles BI chez
    insights360 : son gate de cloisonnement a vu les deux rôles compter le même
    nombre de lignes, et n'a rien pu prouver.

    Un identifiant n'est pas une variable aléatoire : ici il est attribué par
    agence, donc TOUT modulo se corrèle à l'agence. Ce test garantit la
    couverture au lieu de l'espérer.
    """
    par_agence: dict[str, dict[str, int]] = {}
    for rid in [str(i) for i in range(1, 35)]:
        adm = client.get(f"/api/resources/{rid}/administrative", headers=JWT)
        if adm.status_code != 200:
            continue
        corps = adm.json()["data"]
        agence = ((corps["relationships"].get("agency") or {}).get("data") or {}).get("id")
        refs = corps["relationships"]["contracts"]["data"]
        if agence is None or not refs:
            continue
        compte = par_agence.setdefault(agence, {"contrats": 0, "droits": 0, "versements": 0})
        compte["contrats"] += len(refs)
        for ref in refs:
            attrs = client.get(f"/api/contracts/{ref['id']}", headers=JWT).json()["data"][
                "attributes"
            ]
            compte["droits"] += len(attrs["advantageTypes"])
        compte["versements"] += client.get(f"/api/resources/{rid}/advantages", headers=JWT).json()[
            "meta"
        ]["totals"]["rows"]

    assert len(par_agence) >= 3, f"trop peu d'agences pour conclure : {sorted(par_agence)}"
    vides = {a: c for a, c in par_agence.items() if not c["droits"] or not c["versements"]}
    assert not vides, (
        f"agences sans package salarial : {vides}. "
        "Un axe métier vide rend vert par vacuité le gate de cloisonnement du consommateur."
    )
