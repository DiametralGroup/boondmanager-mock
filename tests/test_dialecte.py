"""Le dialecte transverse : authentification, enveloppes, pagination, filtres.

Ces propriétés valent pour TOUTES les collections — on les vérifie sur une ou
deux, la fabrique de routes fait le reste.
"""

from __future__ import annotations

import base64

import boondmanager_mock as mock
from tests.conftest import JWT


def _basic(user: str, password: str) -> dict[str, str]:
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


# ── Authentification — le dialecte exact ─────────────────────────────────────


def test_health_est_public(client):
    assert client.get("/health").status_code == 200


def test_sans_identifiants_401_avec_enveloppe_errors(client):
    """Forme réelle : meta HORS SESSION + entrée status/code/detail/title."""
    reponse = client.get("/api/resources")
    assert reponse.status_code == 401
    corps = reponse.json()
    erreur = corps["errors"][0]
    assert erreur == {
        "status": "401",
        "code": "401",
        "detail": "HTTP 401 (GET /api/resources)",
        "title": "401",
    }
    assert corps["meta"]["isLogged"] is False
    assert corps["meta"]["language"] == "en"
    assert "login" not in corps["meta"]


def test_jwt_invalide_422_comme_la_vraie_api(client):
    """Forme réelle relevée : détail préfixé et `source.parameter: xJwtClient`."""
    faux = mock.build_client_jwt("mock-user-token", "mock-client-token", "MAUVAISE-CLE")
    reponse = client.get("/api/resources", headers={mock.JWT_HEADER_NAME: faux})
    assert reponse.status_code == 422
    erreur = reponse.json()["errors"][0]
    assert erreur["detail"] == "422 - Signature verification failed"
    assert erreur["source"] == {"parameter": "xJwtClient"}
    assert "title" not in erreur


def test_jetons_forges_rejetes(client):
    forge = mock.build_client_jwt("autre-user", "mock-client-token", "mock-client-key")
    assert client.get("/api/resources", headers={mock.JWT_HEADER_NAME: forge}).status_code == 422


def test_basic_auth_acceptee_et_rejetee(client):
    ok = client.get(
        "/api/companies", headers=_basic("demo@boreal-conseil.example", "mock-password")
    )
    assert ok.status_code == 200
    refuse = client.get("/api/companies", headers=_basic("demo@boreal-conseil.example", "non"))
    assert refuse.status_code == 401


def test_current_user(client):
    """Type réel `currentuser` (relevé), avec le login du compte."""
    corps = client.get("/api/application/current-user", headers=JWT).json()
    assert corps["data"]["type"] == "currentuser"
    assert corps["data"]["attributes"]["login"] == "demo@boreal-conseil.example"


# ── Enveloppes ───────────────────────────────────────────────────────────────


def test_enveloppe_de_liste_complete(client):
    """Le meta complet relevé en réel : totals + version + session + tenant."""
    corps = client.get("/api/resources", headers=JWT).json()
    assert set(corps) == {"data", "included", "meta"}
    meta = corps["meta"]
    assert meta["totals"]["rows"] == 34
    assert meta["isLogged"] is True
    assert meta["language"] == "fr"
    assert meta["customer"] == "boreal-conseil"
    assert meta["login"] == "demo@boreal-conseil.example"
    assert isinstance(meta["timestamp"], int)
    assert meta["version"] == "9.1.78.1"


def test_enveloppe_de_detail_sans_totals(client):
    corps = client.get("/api/resources/7", headers=JWT).json()
    assert corps["data"]["id"] == "7"
    assert "totals" not in corps["meta"]
    # Le profil réel n'inclut QUE l'agence et les contrats (liste blanche relevée).
    types_inclus = {e["type"] for e in corps["included"]}
    assert types_inclus == {"agency", "contract"}


def test_included_forme_reduite(client):
    """Une agence incluse ne porte que `name` — la forme du schéma officiel."""
    corps = client.get("/api/resources", headers=JWT).json()
    agences = [e for e in corps["included"] if e["type"] == "agency"]
    assert agences
    assert set(agences[0]["attributes"]) == {"name"}
    ressources = [e for e in corps["included"] if e["type"] == "resource"]
    assert set(ressources[0]["attributes"]) == {"firstName", "lastName"}


# ── Pagination ───────────────────────────────────────────────────────────────


def test_pagination_tranches_et_totaux(client):
    page1 = client.get("/api/times?page=1&maxResults=30", headers=JWT).json()
    page3 = client.get("/api/times?page=3&maxResults=30", headers=JWT).json()
    total = page1["meta"]["totals"]["rows"]
    assert total > 60, "il faut plus de deux pages pour tester la pagination"
    assert len(page1["data"]) == 30
    assert len(page3["data"]) == total - 60
    assert page1["meta"]["totals"]["rows"] == page3["meta"]["totals"]["rows"]


def test_times_reports_exige_sa_fenetre(client):
    """`startMonth`/`endMonth` obligatoires — 422 code métier 1017, une entrée
    par paramètre manquant avec `source.parameter` (forme réelle relevée)."""
    reponse = client.get("/api/times-reports", headers=JWT)
    assert reponse.status_code == 422
    entrees = reponse.json()["errors"]
    assert [e["code"] for e in entrees] == ["1017", "1017"]
    assert [e["source"]["parameter"] for e in entrees] == ["endMonth", "startMonth"]

    fenetre = client.get(
        "/api/times-reports?startMonth=2026-06&endMonth=2026-06&maxResults=500", headers=JWT
    ).json()
    assert fenetre["meta"]["totals"]["rows"] > 0
    assert all(t["attributes"]["term"] == "2026-06" for t in fenetre["data"])


def test_listes_contracts_et_deliveries_en_405(client):
    """La recherche n'existe pas en réel (relevé : 405) — les données passent
    par les détails et les relations."""
    for chemin in ("contracts", "deliveries"):
        reponse = client.get(f"/api/{chemin}", headers=JWT)
        assert reponse.status_code == 405
        erreur = reponse.json()["errors"][0]
        assert erreur["detail"] == f"HTTP 405 (GET /api/{chemin})"
        assert erreur["title"] == "405"


def test_pagination_defauts_et_plafond(client):
    defaut = client.get("/api/invoices", headers=JWT).json()
    assert len(defaut["data"]) == 30  # défaut maxResults=30
    plafonne = client.get("/api/invoices?maxResults=5000", headers=JWT).json()
    assert len(plafonne["data"]) == defaut["meta"]["totals"]["rows"]  # plafond 500 >> jeu


def test_pagination_invalide_422(client):
    assert client.get("/api/resources?page=abc", headers=JWT).status_code == 422


# ── Filtres ──────────────────────────────────────────────────────────────────


def test_keywords_filtre(client):
    corps = client.get("/api/companies?keywords=Lumina", headers=JWT).json()
    assert corps["meta"]["totals"]["rows"] >= 1
    assert all("Lumina" in str(item) for item in corps["data"])


def test_tri_officiel_sur_updateDate(client):
    """`sort=updateDate` est une clé de tri OFFICIELLE (resources, candidates,
    companies, contacts, opportunities) — l'outil du différentiel incrémental."""
    corps = client.get(
        "/api/resources?sort=updateDate&order=desc&maxResults=500", headers=JWT
    ).json()
    dates = [item["attributes"]["updateDate"] for item in corps["data"]]
    assert dates == sorted(dates, reverse=True)


def test_tri_chemin_pointe(client):
    corps = client.get("/api/times?sort=workUnitType.reference&maxResults=500", headers=JWT).json()
    references = [t["attributes"]["workUnitType"]["reference"] for t in corps["data"]]
    assert references == sorted(references, key=str)


def test_ordre_stable_par_defaut(client):
    """Relevé réel : deux appels identiques rendent la même séquence."""
    a = client.get("/api/resources?maxResults=10", headers=JWT).json()["data"]
    b = client.get("/api/resources?maxResults=10", headers=JWT).json()["data"]
    assert [d["id"] for d in a] == [d["id"] for d in b]


def test_period_updated_officiel(client):
    """`period=updated&startDate&endDate` — le filtre incrémental OFFICIEL."""
    tout = client.get("/api/companies?maxResults=500", headers=JWT).json()
    fenetre = client.get(
        "/api/companies?period=updated&startDate=2026-01-01&endDate=2026-12-31&maxResults=500",
        headers=JWT,
    ).json()
    rien = client.get(
        "/api/companies?period=updated&startDate=2099-01-01&endDate=2099-12-31&maxResults=500",
        headers=JWT,
    ).json()
    assert fenetre["meta"]["totals"]["rows"] == tout["meta"]["totals"]["rows"]
    assert rien["meta"]["totals"]["rows"] == 0


def test_period_created_officiel(client):
    recentes = client.get(
        "/api/candidates?period=created&startDate=2026-01-01&endDate=2026-12-31&maxResults=500",
        headers=JWT,
    ).json()
    assert recentes["meta"]["totals"]["rows"] >= 1
    for item in recentes["data"]:
        assert item["attributes"]["creationDate"][:4] == "2026"


def test_updated_since_affordance_du_mock(client):
    """Les deux formes non attestées restent servies (cf. UNVERIFIED-FIELDS)."""
    for param in ("updatedSince", "filter[updateDate][gte]"):
        futur = client.get(
            "/api/resources", headers=JWT, params={param: "2099-01-01T00:00:00Z", "maxResults": 500}
        ).json()
        assert futur["meta"]["totals"]["rows"] == 0


def test_filtres_metier_inconnus_ignores(client):
    """`period=hired`, `flags`, `keywordsType`… : acceptés, sans effet — un
    stub ne casse pas un client réel qui envoie ses filtres habituels."""
    corps = client.get(
        "/api/resources?period=hired&startDate=2020-01-01&endDate=2020-12-31&keywordsType=fullName",
        headers=JWT,
    ).json()
    assert corps["meta"]["totals"]["rows"] == 34


# ── Récupération des contrats — le chemin officiel ──────────────────────────


def test_le_profil_ressource_expose_ses_contrats(client):
    """`GET /resources/{id}` porte la relation `contracts` (schéma profile
    officiel) — ABSENTE de la recherche. C'est la divergence liste/détail que
    la vraie API a, et le point de départ documenté pour récupérer les contrats.
    """
    liste = client.get("/api/resources?maxResults=1", headers=JWT).json()
    assert "contracts" not in liste["data"][0]["relationships"]

    detail = client.get("/api/resources/7", headers=JWT).json()
    refs = detail["data"]["relationships"]["contracts"]["data"]
    assert refs, "un salarié porte au moins un contrat"
    inclus = {(e["type"], e["id"]) for e in detail["included"]}
    assert all(("contract", r["id"]) in inclus for r in refs)


def test_administrative_liste_les_contrats_et_contracts_id_les_detaille(client):
    """Le flux complet : administrative → refs de contrats → détail salarié.

    `GET /resources/{id}/administrative` → `relationships.contracts` +
    `included`, puis `GET /contracts/{id}` pour le détail — le parcours qu'un
    extracteur rejouera sur la vraie API.

    ⚠️ `included` n'est PAS réduit, contrairement à ce que ce test affirmait
    jusqu'au 2026-08-13. Sondé en production : les seize attributs du contrat y
    sont, `monthlySalary` compris et renseigné. La forme réduite était une
    invention du mock, et elle a coûté cher — ne trouvant la rémunération nulle
    part, le consommateur a conclu qu'aucun endpoint ne l'exposait
    (SPEC-DEVIATIONS #5) et a bâti un détour par un CSV de fixtures.
    """
    adm = client.get("/api/resources/7/administrative", headers=JWT).json()
    corps = adm["data"]
    assert corps["type"] == "resource"
    assert corps["attributes"]["reference"] == "BC-0007"
    assert corps["attributes"]["seniorityDate"], "l'ancienneté vient du premier contrat"

    refs = corps["relationships"]["contracts"]["data"]
    assert refs
    contrat_inclus = next(e for e in adm["included"] if e["type"] == "contract")
    # `included` porte la forme COMPLÈTE — c'est le seul chemin praticable vers
    # le salaire, `GET /contracts` répondant 405 chez le fournisseur.
    assert {"typeOf", "startDate", "endDate", "monthlySalary", "activityRate"} <= set(
        contrat_inclus["attributes"]
    )
    assert contrat_inclus["attributes"]["monthlySalary"] > 1500
    assert contrat_inclus["relationships"]["agency"]["data"]["type"] == "agency"

    for ref in refs:
        complet = client.get(f"/api/contracts/{ref['id']}", headers=JWT).json()["data"]
        assert complet["attributes"]["monthlySalary"] > 1500
        assert complet["relationships"]["dependsOn"]["data"]["id"] == "7"

    assert client.get("/api/resources/999/administrative", headers=JWT).status_code == 404


def test_administrative_d_un_sous_traitant(client):
    """Pas de contrat de travail, mais une société fournisseuse."""
    adm = client.get("/api/resources/23/administrative", headers=JWT).json()
    assert adm["data"]["relationships"]["contracts"]["data"] == []
    fournisseur = adm["data"]["relationships"]["providerCompany"]["data"]
    assert fournisseur is not None and fournisseur["type"] == "company"


# ── Le rattachement au groupe — onglet information d'une société ────────────

#: Relevé de production du 2026-09-13 (sonde lecture seule, noms seulement).
RELATIONS_INFORMATION_SOCIETE = {
    "agency",
    "createdBy",
    "files",
    "influencers",
    "mainManager",
    "parentCompany",
    "pole",
    "subsidiaries",
}


def test_la_liste_des_societes_ne_porte_pas_le_groupe(client):
    """Relevé réel : la recherche ne sert que `agency`, `mainManager`, `pole`.

    Y ajouter `parentCompany` rendrait un consommateur vert sur une relation
    que la liste du fournisseur ne sert pas — il ne découvrirait qu'en
    production qu'il faut un appel par fiche.
    """
    liste = client.get("/api/companies?maxResults=500", headers=JWT).json()
    for societe in liste["data"]:
        assert set(societe["relationships"]) == {"agency", "mainManager", "pole"}


def test_information_une_filiale_pointe_vers_sa_mere(client):
    corps = client.get("/api/companies/3/information", headers=JWT).json()
    assert corps["data"]["type"] == "company"
    assert corps["data"]["relationships"]["parentCompany"]["data"] == {
        "id": "9",
        "type": "company",
    }
    assert corps["data"]["relationships"]["subsidiaries"]["data"] == []
    # La mère référencée est résolue dans `included`.
    assert ("company", "9") in {(e["type"], e["id"]) for e in corps["included"]}


def test_information_la_mere_liste_ses_filiales_et_les_deux_sens_concordent(client):
    """Mesuré en réel : un groupe listait 16 filiales, chacune pointant vers lui."""
    mere = client.get("/api/companies/9/information", headers=JWT).json()["data"]
    assert mere["relationships"]["parentCompany"]["data"] is None
    filiales = mere["relationships"]["subsidiaries"]["data"]
    assert {f["id"] for f in filiales} == {"3", "5"}
    assert all(f["type"] == "company" for f in filiales)

    for filiale in filiales:
        fiche = client.get(f"/api/companies/{filiale['id']}/information", headers=JWT).json()
        assert fiche["data"]["relationships"]["parentCompany"]["data"]["id"] == "9"

    # Sens inverse, sur TOUTES les sociétés : toute mère déclarée liste sa fille.
    ids = [s["id"] for s in client.get("/api/companies?maxResults=500", headers=JWT).json()["data"]]
    fiches = {
        i: client.get(f"/api/companies/{i}/information", headers=JWT).json()["data"] for i in ids
    }
    for i, fiche in fiches.items():
        ref = fiche["relationships"]["parentCompany"]["data"]
        if ref is not None:
            soeurs = fiches[ref["id"]]["relationships"]["subsidiaries"]["data"]
            assert {"id": i, "type": "company"} in soeurs
        for fille in fiche["relationships"]["subsidiaries"]["data"]:
            assert fiches[fille["id"]]["relationships"]["parentCompany"]["data"]["id"] == i


def test_information_d_une_societe_sans_groupe(client):
    rels = client.get("/api/companies/1/information", headers=JWT).json()["data"]["relationships"]
    assert rels["parentCompany"] == {"data": None}
    assert rels["subsidiaries"] == {"data": []}


def test_information_forme_relevee_et_404(client):
    """Les huit relations et les vingt-sept attributs observés — ni plus, ni moins."""
    corps = client.get("/api/companies/9/information", headers=JWT).json()
    assert set(corps["data"]["relationships"]) == RELATIONS_INFORMATION_SOCIETE
    assert len(corps["data"]["attributes"]) == 27
    assert {e["type"] for e in corps["included"]} <= {"agency", "company", "resource"}

    absent = client.get("/api/companies/999/information", headers=JWT)
    assert absent.status_code == 404
    assert absent.json()["errors"][0]["detail"] == "HTTP 404 (GET /api/companies/999/information)"


# ── Affordances conservées ───────────────────────────────────────────────────


def test_technical_data(client):
    """Forme réelle relevée : type `resource`, quinze attributs, sans included."""
    corps = client.get("/api/resources/7/technical-data", headers=JWT).json()
    donnees = corps["data"]
    assert donnees["type"] == "resource"
    attrs = donnees["attributes"]
    assert set(attrs) == {
        "activityAreas",
        "description",
        "diplomas",
        "experience",
        "expertiseAreas",
        "languages",
        "references",
        "resourceCanModifyTechnicalData",
        "skills",
        "summary",
        "tdId",
        "tdLink",
        "title",
        "tools",
        "training",
    }
    references = attrs["references"]
    assert references and {"title", "company", "startYear", "description", "skills"} <= set(
        references[0]
    )
    assert isinstance(references[0]["skills"], list)
    absent = client.get("/api/resources/999/technical-data", headers=JWT)
    assert absent.status_code == 404
    assert (
        absent.json()["errors"][0]["detail"] == "HTTP 404 (GET /api/resources/999/technical-data)"
    )


def test_remuneration_csv_derivee_des_contrats(client, boond_state):
    reponse = client.get("/__fixtures/remuneration.csv", headers=JWT)
    assert reponse.status_code == 200
    lignes = reponse.text.strip().splitlines()
    assert lignes[0] == "collaborateur_id,upn,entite,periode,montant_brut_annuel"
    cdi = [c for c in boond_state.dataset["contracts"] if c["attributes"]["typeOf"] == 0]
    assert len(lignes) - 1 == len(cdi)


def test_route_inconnue_enveloppee(client):
    """Le réel enveloppe aussi ses 404 de routage (meta hors session)."""
    reponse = client.get("/api/times/regular_1", headers=JWT)
    assert reponse.status_code == 404
    corps = reponse.json()
    assert corps["errors"][0]["detail"] == "HTTP 404 (GET /api/times/regular_1)"
    assert corps["meta"]["isLogged"] is False


def test_panne_historique_en_process(client, boond_state):
    boond_state.fail_collections.add("projects")
    assert client.get("/api/projects", headers=JWT).status_code == 500
    assert client.get("/api/companies", headers=JWT).status_code == 200
