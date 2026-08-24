"""Les modes de panne — pilotés par HTTP, donc utilisables depuis un conteneur.

« The point of the mock is to reproduce failure modes, not just happy paths. »
Un test par mode listé, plus les deux propriétés qui rendent ces modes
exploitables : la panne transitoire s'épuise, la panne persistante non.
"""

from __future__ import annotations

import boondmanager_mock as mock
from tests.conftest import ADMIN, JWT

TOTAL_RESSOURCES = 34


# ── Le plan de contrôle lui-même ─────────────────────────────────────────────


def test_admin_exige_un_jeton(client) -> None:
    """Sans jeton, /__admin est fermé — même quand il est monté."""
    assert client.get("/__admin/state").status_code == 401
    assert client.post("/__admin/inject", json={"kind": "status"}).status_code == 401


def test_admin_monte_conditionnellement(client) -> None:
    """Le routeur admin n'est pas « monté puis interdit » : il est absent.

    On vérifie la condition à la source plutôt que de ré-importer le paquet
    dans un autre état, ce qui polluerait la session. La preuve que le montage
    a eu lieu est comportementale : l'endpoint répond.
    """
    import inspect
    import sys

    app_module = sys.modules["boondmanager_mock.app"]
    source = inspect.getsource(app_module)
    assert "if settings.admin_enabled:" in source, (
        "le montage du routeur admin n'est plus conditionnel"
    )
    assert client.get("/__admin/state", headers=ADMIN).status_code == 200


# ── 429 + Retry-After ────────────────────────────────────────────────────────


def test_rate_limit_avec_retry_after(client) -> None:
    """Après N requêtes : 429 avec un en-tête Retry-After exploitable."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={
            "kind": "rate_limit",
            "scope": "/api/resources",
            "after_requests": 2,
            "retry_after_seconds": 3,
        },
    )
    assert client.get("/api/resources", headers=JWT).status_code == 200
    assert client.get("/api/resources", headers=JWT).status_code == 200
    trop = client.get("/api/resources", headers=JWT)
    assert trop.status_code == 429
    assert trop.headers["Retry-After"] == "3"


def test_rate_limit_ne_touche_pas_les_autres_collections(client) -> None:
    """Le `scope` est bien respecté : une autre collection reste servie."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={"kind": "rate_limit", "scope": "/api/resources", "after_requests": 0},
    )
    assert client.get("/api/resources", headers=JWT).status_code == 429
    assert client.get("/api/companies", headers=JWT).status_code == 200


# ── 500 / 503 transitoires ───────────────────────────────────────────────────


def test_status_transitoire_s_epuise(client) -> None:
    """`times: 2` → deux échecs, puis ça repasse.

    C'est ce qui permet de tester un RETRY. Sans compteur, on ne testerait
    qu'un échec — et le test « le run se termine malgré un 503 » serait
    impossible à écrire.
    """
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={"kind": "status", "scope": "/api/projects", "status": 503, "times": 2},
    )
    assert client.get("/api/projects", headers=JWT).status_code == 503
    assert client.get("/api/projects", headers=JWT).status_code == 503
    assert client.get("/api/projects", headers=JWT).status_code == 200


def test_status_persistant_ne_s_epuise_pas(client) -> None:
    """Sans `times`, la panne dure — le run DOIT échouer, pas se terminer à moitié."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={"kind": "status", "scope": "/api/projects", "status": 500},
    )
    for _ in range(5):
        assert client.get("/api/projects", headers=JWT).status_code == 500


# ── Ordre instable ───────────────────────────────────────────────────────────


def test_ordre_instable_par_injection(client) -> None:
    """L'instabilité d'ordre est un mode de CHAOS, en opt-in — le défaut est
    stable, comme la vraie API (relevé 2026-07-31)."""
    client.post("/__admin/inject", headers=ADMIN, json={"kind": "unstable_order", "scope": "*"})
    page1 = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    page2 = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    assert [d["id"] for d in page1] != [d["id"] for d in page2]


def test_ordre_stable_avec_sort(client) -> None:
    """Avec `sort`, l'ordre est reproductible — et effectivement trié."""
    params = {"maxResults": 10, "sort": "lastName"}
    a = client.get("/api/resources", headers=JWT, params=params).json()["data"]
    b = client.get("/api/resources", headers=JWT, params=params).json()["data"]
    assert [d["id"] for d in a] == [d["id"] for d in b]
    noms = [d["attributes"]["lastName"] for d in a]
    assert noms == sorted(noms)


def test_ordre_instable_par_environnement(client, monkeypatch) -> None:
    monkeypatch.setattr(mock.settings, "stable_order", False)
    a = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    b = client.get("/api/resources", headers=JWT, params={"maxResults": 10}).json()["data"]
    assert [d["id"] for d in a] != [d["id"] for d in b]


# ── Dérive de pagination ─────────────────────────────────────────────────────


def test_page_drift_duplique_un_enregistrement(client) -> None:
    """Un enregistrement rendu sur deux pages consécutives — la cause classique
    d'une duplication silencieuse quand la donnée bouge en cours de pagination."""
    client.post(
        "/__admin/inject",
        headers=ADMIN,
        json={
            "kind": "page_drift",
            "scope": "/api/times-reports",
            "after_page": 1,
            "mode": "insert",
        },
    )
    params = {"maxResults": 10, "sort": "term", "startMonth": "2026-05", "endMonth": "2026-07"}
    page1 = client.get("/api/times-reports", headers=JWT, params={**params, "page": 1}).json()
    page2 = client.get("/api/times-reports", headers=JWT, params={**params, "page": 2}).json()
    ids1 = [d["id"] for d in page1["data"]]
    ids2 = [d["id"] for d in page2["data"]]
    assert set(ids1) & set(ids2), "un enregistrement doit apparaître sur les deux pages"


# ── Filtre incrémental + mutations ───────────────────────────────────────────


def test_mutate_avance_l_horodatage_et_rend_l_enregistrement_visible(client) -> None:
    """Le chemin exact d'un test d'incrémentalité côté consommateur.

    Sans l'avancée de `updateDate`, le curseur incrémental ne reverrait jamais
    l'enregistrement modifié — et le test « une modification met à jour
    exactement une ligne » passerait en ne testant rien.
    """
    curseur = {
        "period": "updated",
        "startDate": "2026-07-14",
        "endDate": "2026-12-31",
        "maxResults": 500,
    }
    avant = client.get("/api/resources", headers=JWT, params=curseur).json()
    assert avant["meta"]["totals"]["rows"] == 0, "le jeu de base est antérieur au curseur"

    reponse = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={"collection": "resources", "id": "3", "attributes": {"title": "Modifié"}},
    )
    assert reponse.status_code == 200

    modifie = client.get("/api/resources/3", headers=JWT).json()["data"]
    assert modifie["attributes"]["title"] == "Modifié"
    # `_bump` avance d'une seconde en préservant le fuseau : l'enregistrement
    # reste dans la fenêtre du jeu de base, mais SON updateDate a bougé.
    apres = client.get("/api/resources?maxResults=500", headers=JWT).json()
    lui = next(d for d in apres["data"] if d["id"] == "3")
    tous = client.get(
        "/api/resources?maxResults=500&sort=updateDate&order=desc", headers=JWT
    ).json()
    assert lui["attributes"]["updateDate"] >= tous["data"][-1]["attributes"]["updateDate"]


# ── Mutations de RELATIONS ───────────────────────────────────────────────────
#
# Chez BoondManager, le manager d'une ressource et son agence sont des
# RELATIONS JSON:API, pas des attributs. Un consommateur qui dérive des droits
# d'accès d'un organigramme (insights360/iris) doit pouvoir simuler les deux
# mutations correspondantes : changement de hiérarchie et réaffectation
# d'entité.


def test_mutate_change_une_relation_sans_toucher_aux_autres(client) -> None:
    """Le patch est clef par clef, comme celui des attributs.

    Sans cela, éprouver un changement de manager emporterait l'agence avec
    lui, et le test aval observerait DEUX mutations en croyant en mesurer une.
    """
    avant = client.get("/api/resources/3", headers=JWT).json()["data"]
    agence_avant = avant["relationships"]["agency"]["data"]["id"]

    reponse = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={
            "collection": "resources",
            "id": "3",
            "relationships": {"mainManager": {"data": {"id": "5", "type": "resource"}}},
        },
    )
    assert reponse.status_code == 200

    apres = client.get("/api/resources/3", headers=JWT).json()["data"]
    assert apres["relationships"]["mainManager"]["data"]["id"] == "5"
    assert apres["relationships"]["agency"]["data"]["id"] == agence_avant


def test_mutate_accepte_l_identifiant_nu_et_conserve_le_type(client) -> None:
    """`{"agency": "2"}` vaut la forme canonique — et le `type` ne vient pas
    de la main du testeur, donc il ne peut pas se désaccorder."""
    reponse = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={"collection": "resources", "id": "3", "relationships": {"agency": "2"}},
    )
    assert reponse.status_code == 200

    relations = client.get("/api/resources/3", headers=JWT).json()["data"]["relationships"]
    assert relations["agency"]["data"] == {"id": "2", "type": "agency"}


def test_mutate_refuse_une_clef_inconnue_au_lieu_de_mentir(client) -> None:
    """LA régression qui motive ce lot.

    Patcher `attributes: {"main_manager_id": …}` — le nom de la colonne vue à
    l'arrivée du pipeline, pas celui de la relation — renvoyait 200 et ne
    changeait rien. Le scénario aval passait au vert sans rien avoir éprouvé.
    Le refus doit en plus NOMMER les relations disponibles, pour que l'erreur
    se corrige sans aller lire le code du mock.
    """
    reponse = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={
            "collection": "resources",
            "id": "3",
            "attributes": {"main_manager_id": "5"},
        },
    )
    assert reponse.status_code == 400
    corps = reponse.text
    assert "main_manager_id" in corps
    assert "mainManager" in corps, "le message doit montrer la clef correcte"


def test_mutate_refuse_un_patch_vide(client) -> None:
    """« Muté » sans rien à muter est le même mensonge, sous une autre forme."""
    reponse = client.post(
        "/__admin/mutate",
        headers=ADMIN,
        json={"collection": "resources", "id": "3"},
    )
    assert reponse.status_code == 400


def test_soft_delete_pose_un_drapeau_sans_supprimer(client) -> None:
    """Suppression LOGIQUE, jamais physique.

    Un pipeline incrémental en stratégie `merge` ne peut pas observer une
    suppression physique sans rafraîchissement complet.
    """
    total_avant = client.get("/api/resources", headers=JWT).json()["meta"]["totals"]["rows"]
    client.post("/__admin/delete", headers=ADMIN, json={"collection": "resources", "id": "8"})
    # Le drapeau vit sur l'item de RECHERCHE (le profil réel ne le porte pas).
    liste = client.get("/api/resources?maxResults=500", headers=JWT).json()["data"]
    marque = next(d for d in liste if d["id"] == "8")
    assert marque["attributes"]["isDeleted"] is True
    total_apres = client.get("/api/resources", headers=JWT).json()["meta"]["totals"]["rows"]
    assert total_apres == total_avant, "l'enregistrement reste servi, avec son drapeau"


# ── Observabilité du plan de contrôle ────────────────────────────────────────


def test_state_expose_les_parametres_recus(client) -> None:
    """La propriété qui permet de PROUVER qu'un consommateur envoie son curseur.

    Un pipeline qui aurait oublié son paramètre incrémental passerait sinon tous
    ses tests : le mock rendrait simplement tout, et le résultat serait correct.
    """
    client.get(
        "/api/resources",
        headers=JWT,
        params={
            "period": "updated",
            "startDate": "2026-03-01",
            "endDate": "2026-03-31",
            "sort": "updateDate",
            "maxResults": 100,
        },
    )
    etat = client.get("/__admin/state", headers=ADMIN).json()
    recus = etat["last_query_params_by_path"]["/api/resources"]
    assert recus["period"] == "updated"
    assert recus["startDate"] == "2026-03-01"
    assert recus["sort"] == "updateDate"
    assert etat["request_counts_by_path"]["/api/resources"] >= 1


def test_l_historique_des_parametres_garde_tous_les_appels(client) -> None:
    """Deux consommateurs du meme chemin ne s'ecrasent plus dans l'etat.

    Constate le 13/08 cote consommateur : les ressources s'extraient en
    incremental (updatedSince), puis la collecte des contrats reliste le meme
    chemin sans curseur — et `last_query_params_by_path` ne montrait que le
    second appel. L'historique garde les deux, dans l'ordre.
    """
    client.get(
        "/api/resources",
        headers=JWT,
        params={"updatedSince": "2026-01-01T00:00:00Z", "sort": "id"},
    )
    client.get("/api/resources", headers=JWT, params={"sort": "id"})
    etat = client.get("/__admin/state", headers=ADMIN).json()
    appels = etat["query_params_by_path"]["/api/resources"]
    assert len(appels) >= 2
    assert appels[-2].get("updatedSince") == "2026-01-01T00:00:00Z"
    assert "updatedSince" not in appels[-1]
    assert etat["last_query_params_by_path"]["/api/resources"] == appels[-1]


def test_reset_change_de_graine(client) -> None:
    """La graine est réglable par HTTP — et le reset la confirme."""
    reponse = client.post("/__admin/reset", headers=ADMIN, json={"seed": 7})
    assert reponse.json() == {"status": "reset", "seed": 7}
    assert (
        client.get("/api/resources", headers=JWT).json()["meta"]["totals"]["rows"]
        == TOTAL_RESSOURCES
    )
    mock.state.reset()  # revient à la graine de l'environnement pour la suite
