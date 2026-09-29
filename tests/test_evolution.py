"""L'évolution temporelle — ce qui rend l'extraction INCRÉMENTALE testable.

Un extracteur incrémental ne prouve rien contre un jeu figé : son curseur
passerait tous les tests sans avoir jamais filtré. Ici, la vie de l'entreprise
avance quand l'horloge avance — et l'horloge se pilote par `/__admin/clock`,
donc les tests font défiler des heures en quelques millisecondes.

L'intervalle est fixé à 3600 s par le harnais : UNE heure virtuelle = UN
événement. Aucun événement ne se déclenche à l'horloge murale pendant la suite.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import boondmanager_mock as mock
from tests.conftest import ADMIN, JWT

UNE_HEURE = 3600
#: Curseur posé APRÈS le plafond du jeu de base (2026-07-12) et AVANT l'époque
#: des événements (2026-07-15) : il isole exactement ce qui a évolué.
CURSEUR = {
    "period": "updated",
    "startDate": "2026-07-14",
    "endDate": "2026-12-31",
    "maxResults": "500",
}


def _avancer(client: TestClient, heures: int) -> None:
    client.post("/__admin/clock", headers=ADMIN, json={"advance_seconds": heures * UNE_HEURE})


def _rows(client: TestClient, chemin: str, **params: str) -> int:
    reponse = client.get(f"/api/{chemin}", headers=JWT, params={"maxResults": 500, **params})
    return reponse.json()["meta"]["totals"]["rows"]


def test_le_jeu_est_stable_sans_avance_d_horloge(client):
    avant = _rows(client, "actions")
    assert _rows(client, "actions") == avant
    assert _rows(client, "resources", **CURSEUR) == 0


def test_de_nouvelles_actions_apparaissent(client):
    avant = _rows(client, "actions")
    _avancer(client, 1)  # événement 0 : une action CRM
    assert _rows(client, "actions") == avant + 1


def test_un_profil_est_mis_a_jour_avec_le_curseur_qui_le_voit(client):
    _avancer(client, 2)  # événements 0-1 : action + profil enrichi
    corps = client.get("/api/resources", headers=JWT, params=CURSEUR).json()
    assert corps["meta"]["totals"]["rows"] == 1
    assert corps["data"][0]["attributes"]["updateDate"].startswith("2026-07-15")


def test_staffing_puis_destaffing_visibles_sur_le_profil(client, boond_state):
    """Le banc bouge : mission créée, `availability` basculée, `updateDate` frais.

    Le banc se repère par `availability: "immediate"` — le champ OBSERVÉ en
    réel. Les événements `staffing` tombent aux index 2, 10, 18, 26… Tant
    qu'il reste des consultants au banc ils sont staffés ; ensuite l'événement
    DÉSTAFFE quelqu'un — les deux sens finissent par se produire.
    """
    missions_avant = len(boond_state.dataset["deliveries"])
    banc_avant = [
        r["id"]
        for r in boond_state.dataset["resources"]
        if r["attributes"]["availability"] == "immediate"
    ]
    assert banc_avant, "le jeu de base doit avoir un banc d'intercontrat"

    _avancer(client, 3)  # inclut l'événement staffing k=2
    assert len(boond_state.dataset["deliveries"]) == missions_avant + 1
    staffe = next(r for r in boond_state.dataset["resources"] if r["id"] == banc_avant[0])
    assert staffe["attributes"]["availability"] != "immediate"
    assert staffe["attributes"]["updateDate"].startswith("2026-07-15")

    # 4 cycles de plus : le banc (4 personnes) est épuisé → déstaffing.
    # (35 heures virtuelles après l'époque, le jour a tourné : on borne par ≥.)
    _avancer(client, 8 * 4)
    en_intercontrat = [
        r
        for r in boond_state.dataset["resources"]
        if r["attributes"]["availability"] == "immediate"
        and r["attributes"]["realAvailability"] >= "2026-07-15"
    ]
    assert en_intercontrat, "au moins un consultant doit avoir été déstaffé"
    destaffe = en_intercontrat[0]
    missions_closes = [
        m
        for m in boond_state.dataset["deliveries"]
        if m["attributes"]["state"] == 2
        and m["attributes"]["endDate"] == destaffe["attributes"]["realAvailability"]
        and m["relationships"]["dependsOn"]["data"]["id"] == destaffe["id"]
    ]
    assert missions_closes, "la mission du déstaffé doit être close à la date de l'événement"


def test_facture_reglee_et_transaction_bancaire(client):
    transactions_avant = _rows(client, "banking-transactions")
    reglees_avant = _rows(client, "invoices", period="performedPayment")  # ignoré → total
    _avancer(client, 4)  # inclut l'événement facture k=3
    assert _rows(client, "banking-transactions") == transactions_avant + 1
    corps = client.get("/api/invoices", headers=JWT, params=CURSEUR).json()
    assert corps["meta"]["totals"]["rows"] == 1
    facture = corps["data"][0]["attributes"]
    assert facture["state"] == 2
    assert facture["performedPaymentDate"] == "2026-07-15"
    assert reglees_avant  # garde-fou : la collection n'était pas vide


def test_extraction_incrementale_de_bout_en_bout(client, monkeypatch):
    """Le scénario cible : snapshot complet, curseur, delta — rien d'autre.

    C'est LE flux que les consommateurs (ophelie, insights360) rejoueront
    contre ce mock : la passe incrémentale ne doit revoir QUE ce qui a bougé.
    """
    collections = ("resources", "contacts", "actions", "invoices", "opportunities")
    snapshot = {c: _rows(client, c) for c in collections}
    assert all(_rows(client, c, **CURSEUR) == 0 for c in collections)

    _avancer(client, 8)  # un cycle complet d'événements

    delta = {c: _rows(client, c, **CURSEUR) for c in collections}
    assert delta["actions"] >= 3, "les nouvelles actions portent le gros du delta"
    assert delta["contacts"] >= 1, "un contact a été créé chez un client"
    assert delta["resources"] >= 2, "profil enrichi + staffing"
    assert delta["invoices"] == 1, "une facture a été réglée"
    assert delta["opportunities"] == 1, "une opportunité a avancé"

    # Le total a bougé là où des entités sont NÉES, pas ailleurs.
    assert _rows(client, "actions") > snapshot["actions"]
    assert _rows(client, "resources") == snapshot["resources"]

    # L'affordance fine (updatedSince, ISO-8601), rallumée à la demande, voit
    # le même delta — le fournisseur, lui, l'ignore.
    monkeypatch.setattr(mock.settings, "updated_since_enabled", True)
    fin = client.get(
        "/api/actions",
        headers=JWT,
        params={"updatedSince": "2026-07-14T00:00:00+0200", "maxResults": 500},
    ).json()
    assert fin["meta"]["totals"]["rows"] == delta["actions"]


def test_la_chronologie_est_deterministe(client):
    """Même graine, même horloge → même vie d'entreprise, au détail près.

    C'est ce qui permet de rejouer un incident d'extraction : la séquence ne
    dépend que de la graine, jamais de l'heure de lancement des tests.
    """
    _avancer(client, 8)
    premier = client.get("/__admin/state", headers=ADMIN).json()["evolution"]["journal"]

    mock.state.reset()
    _avancer(client, 8)
    second = client.get("/__admin/state", headers=ADMIN).json()["evolution"]["journal"]

    assert premier == second


def test_le_journal_expose_le_delta(client):
    _avancer(client, 3)
    evolution = client.get("/__admin/state", headers=ADMIN).json()["evolution"]
    assert evolution["applied"] == 3
    assert [e["kind"] for e in evolution["journal"]] == ["action", "profil", "staffing"]
    assert all(e["at"].startswith("2026-07-15") for e in evolution["journal"])


def test_evolution_desactivable(client, monkeypatch):
    monkeypatch.setattr(mock.settings, "evolution_enabled", False)
    avant = _rows(client, "actions")
    _avancer(client, 5)
    assert _rows(client, "actions") == avant


def test_le_reset_rearme_la_chronologie(client):
    _avancer(client, 2)
    assert client.get("/__admin/state", headers=ADMIN).json()["evolution"]["applied"] == 2
    client.post("/__admin/reset", headers=ADMIN)
    assert client.get("/__admin/state", headers=ADMIN).json()["evolution"]["applied"] == 0
    assert _rows(client, "resources", **CURSEUR) == 0
