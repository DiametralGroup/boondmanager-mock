"""Les endroits où l'API RÉELLE diverge de sa propre documentation.

Un mock a deux fidélités possibles, et elles s'opposent : être fidèle à la
DOCUMENTATION, ou fidèle au COMPORTEMENT OBSERVÉ. Ce dépôt choisit le second,
sans exception.

La raison est concrète. Un mock qui « fait bien » là où le fournisseur ne le
fait pas rend son consommateur vert sur un comportement qui n'existe pas : le
dimensionnement, la cadence d'extraction et la charge imposée à l'API se
calculent alors sur une fiction. C'est exactement ce qui s'est produit pour
insights360 — sa cadence horaire supposait un filtre incrémental sur /times,
et représentait en réalité ~25 000 appels par jour chez le fournisseur.

Chaque écart consigné ici a été MESURÉ contre ui.boondmanager.com, avec une
date et des chiffres. Aucun n'est déduit de la documentation.
"""

from __future__ import annotations

from typing import Any

from boondmanager_mock.app import COLLECTIONS
from tests.conftest import JWT


def _total(reponse: Any) -> int:
    return int(reponse.json()["meta"]["totals"]["rows"])


def test_times_ignore_les_formes_hors_contrat_comme_l_api_reelle(client: Any) -> None:
    """`/times` accepte les formes de filtre HORS contrat et les IGNORE.

    Mesuré le 2026-08-04 contre ui.boondmanager.com, sur un tenant de
    production à 106 976 lignes de temps :

        sans filtre                    → 106 976
        startDate + endDate            → 106 976
        startMonth + endMonth          → 106 976
        period=updated + startDate     → 106 976

    Aucune de ces formes n'est rejetée — un 422 aurait au moins signalé
    quelque chose. Mais aucune n'est non plus celle du contrat, qui ne
    documente sur `/times` que `period=inProgress` : c'est le test suivant.
    """
    h = JWT

    reference = _total(client.get("/api/times", params={"maxResults": 1}, headers=h))
    assert reference > 0, "le jeu de référence doit contenir des lignes de temps"

    for filtre in (
        {"startDate": "2026-07-01", "endDate": "2026-07-31"},
        {"startMonth": "2026-07", "endMonth": "2026-07"},
        {"period": "updated", "startDate": "2026-07-01"},
        {"period": "created", "startDate": "2026-07-01", "endDate": "2026-07-31"},
    ):
        p = dict(filtre)
        p["maxResults"] = "1"
        reponse = client.get("/api/times", params=p, headers=h)
        assert reponse.status_code == 200, (
            f"{filtre} doit être ACCEPTÉ, pas rejeté — l'API réelle ne renvoie "
            f"aucune erreur sur ces paramètres (reçu {reponse.status_code})"
        )
        assert _total(reponse) == reference, (
            f"{filtre} a filtré {reference - _total(reponse)} ligne(s). L'API "
            "réelle n'en filtre aucune : le mock doit reproduire le "
            "comportement observé, pas la documentation."
        )


def test_times_honore_period_in_progress_comme_l_api_reelle(client: Any) -> None:
    """La forme du CONTRAT filtre, sur la date de la ligne.

    Sondé le 2026-09-29 : 111 745 lignes sans filtre, 2 716 avec
    `period=inProgress&startDate=2026-09-01&endDate=2026-09-29`, 2 575 pour
    août. La conclusion du 2026-08-04 (« aucun fenêtrage possible ») venait de
    formes hors contrat.
    """
    h = JWT
    tout = client.get("/api/times", params={"maxResults": 500}, headers=h).json()["data"]
    jours = sorted({t["attributes"]["startDate"][:10] for t in tout})
    assert len(jours) > 2, "le jeu doit couvrir plusieurs jours pour éprouver le filtre"
    debut, fin = jours[1], jours[-2]

    reponse = client.get(
        "/api/times",
        params={"maxResults": 500, "period": "inProgress", "startDate": debut, "endDate": fin},
        headers=h,
    )
    assert reponse.status_code == 200
    fenetre = reponse.json()["data"]
    attendus = [t["id"] for t in tout if debut <= t["attributes"]["startDate"][:10] <= fin]
    assert 0 < len(fenetre) < len(tout)
    assert sorted(t["id"] for t in fenetre) == sorted(attendus)


def test_seule_times_restreint_ses_periodes(client: Any) -> None:
    """L'écart est LOCAL à `/times` — pas une propriété du mock entier.

    Sans cette contre-épreuve, une collection privée de `period=updated` par
    erreur passerait inaperçue, et un consommateur perdrait silencieusement
    son incrémentalité.
    """
    restreintes = {s.chemin: s.periodes for s in COLLECTIONS if "updated" not in s.periodes}
    assert restreintes == {"times": ("inProgress",)}, (
        f"seule /times restreint ses valeurs de `period` ; trouvé : {restreintes}. "
        "Changer cela exige une MESURE contre l'API réelle, documentée dans "
        "docs/comparisons/."
    )

    h = JWT
    # `/actions` porte `creationDate` et honore le filtre — contre-épreuve sur
    # une collection au comportement conforme à la documentation.
    total = _total(client.get("/api/actions", params={"maxResults": 1}, headers=h))
    filtre = _total(
        client.get(
            "/api/actions",
            params={"maxResults": 1, "period": "created", "endDate": "1900-01-01"},
            headers=h,
        )
    )
    assert filtre < total, (
        "une fenêtre fermée en 1900 doit vider /actions ; si elle ne le fait "
        "pas, le filtre de période est cassé pour TOUTES les collections"
    )


def test_updated_since_est_ignore_partout(client: Any) -> None:
    """`updatedSince` n'est pas au contrat, et le fournisseur l'ignore sur les
    11 modules qui ont `period=updated` (sondé le 2026-09-29). Le mock l'ignore
    donc par défaut : l'appliquer rendait vert un client qui relisait tout."""
    h = JWT
    for chemin in ("resources", "companies", "contacts", "actions", "candidates", "invoices"):
        total = _total(client.get(f"/api/{chemin}", params={"maxResults": 1}, headers=h))
        futur = _total(
            client.get(
                f"/api/{chemin}",
                params={"maxResults": 1, "updatedSince": "2099-01-01T00:00:00Z"},
                headers=h,
            )
        )
        officiel = _total(
            client.get(
                f"/api/{chemin}",
                params={
                    "maxResults": 1,
                    "period": "updated",
                    "startDate": "2099-01-01",
                    "endDate": "2099-12-31",
                },
                headers=h,
            )
        )
        assert futur == total, f"{chemin} : updatedSince ne doit rien filtrer"
        assert officiel == 0, f"{chemin} : period=updated doit filtrer"
