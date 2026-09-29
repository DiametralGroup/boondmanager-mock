"""Configuration — tout par variables d'environnement, aucun fichier.

Le mock d'origine lisait ses cinq variables au moment de l'import, ce qui
rendait impossible d'en changer dans un test sans recharger le module. On les
centralise ici, dans un objet relu par `reload()`, en gardant les mêmes noms de
variables que les déploiements existants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Valeurs par défaut identiques à celles du mock d'origine : les compose et
# charts existants ne fixent que les trois premières.
DEFAULTS: dict[str, str] = {
    "BOOND_MOCK_USER_TOKEN": "mock-user-token",
    "BOOND_MOCK_CLIENT_TOKEN": "mock-client-token",
    "BOOND_MOCK_CLIENT_KEY": "mock-client-key",
    "BOOND_MOCK_BASIC_USER": "demo@boreal-conseil.example",
    "BOOND_MOCK_BASIC_PASSWORD": "mock-password",
}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """État de configuration, relu à chaud par `reload()`."""

    user_token: str = ""
    client_token: str = ""
    client_key: str = ""
    basic_user: str = ""
    basic_password: str = ""

    # Le mock d'origine figeait la graine à 42 sans moyen d'en changer autrement
    # qu'en Python. En conteneur, ce n'était plus possible du tout.
    seed: int = 42

    # Plan de contrôle /__admin. Fermé par défaut : il n'a de sens qu'en test.
    admin_enabled: bool = False
    admin_token: str = "mock-admin-token"

    # Ordre STABLE par défaut — aligné sur le comportement observé de la vraie
    # API (2026-07-31). Passer à false (ou injecter `unstable_order`) pour
    # éprouver un pipeline qui pagine sans tri.
    stable_order: bool = True

    # `updatedSince` / `filter[updateDate][gte]` : AFFORDANCE du mock, que
    # l'API réelle IGNORE (sondé le 2026-09-29 sur 11 modules : totaux
    # identiques avec et sans). Désactivée par défaut depuis 0.11.0 : appliquée
    # d'office, elle a rendu vert un client qui relisait tout en production.
    updated_since_enabled: bool = False

    # Le nom du tenant annoncé dans `meta.customer`.
    customer: str = "boreal-conseil"

    # Collections servies en 403 — reproduit un user token à périmètre
    # restreint (`narrowPerimeter`), tel qu'observé sur le tenant réel.
    forbidden_collections: frozenset[str] = frozenset()

    # absent | csv — la fixture de rémunération hors /api (cf. README).
    compensation_mode: str = "csv"

    # ── Évolution temporelle (extraction incrémentale) ───────────────────────
    # Le jeu de données VIT : un événement scripté toutes les
    # `evolution_interval` secondes (nouvelles actions, staffing/déstaffing,
    # factures réglées…). Mettre à false — ou l'intervalle à 0 — fige le jeu de
    # données pour les usages qui exigent un contenu stable à l'octet près.
    evolution_enabled: bool = True
    evolution_interval: float = 60.0

    max_results_cap: int = 500
    default_max_results: int = 30

    extra: dict[str, str] = field(default_factory=dict)

    def reload(self) -> None:
        self.user_token = os.environ.get("BOOND_MOCK_USER_TOKEN", DEFAULTS["BOOND_MOCK_USER_TOKEN"])
        self.client_token = os.environ.get(
            "BOOND_MOCK_CLIENT_TOKEN", DEFAULTS["BOOND_MOCK_CLIENT_TOKEN"]
        )
        self.client_key = os.environ.get("BOOND_MOCK_CLIENT_KEY", DEFAULTS["BOOND_MOCK_CLIENT_KEY"])
        self.basic_user = os.environ.get("BOOND_MOCK_BASIC_USER", DEFAULTS["BOOND_MOCK_BASIC_USER"])
        self.basic_password = os.environ.get(
            "BOOND_MOCK_BASIC_PASSWORD", DEFAULTS["BOOND_MOCK_BASIC_PASSWORD"]
        )
        self.seed = int(os.environ.get("BOOND_MOCK_SEED", "42"))
        self.admin_enabled = _flag("BOOND_MOCK_ADMIN_ENABLED", False)
        self.admin_token = os.environ.get("BOOND_MOCK_ADMIN_TOKEN", "mock-admin-token")
        self.stable_order = _flag("BOOND_MOCK_STABLE_ORDER", True)
        self.updated_since_enabled = _flag("BOOND_MOCK_UPDATED_SINCE", False)
        self.customer = os.environ.get("BOOND_MOCK_CUSTOMER", "boreal-conseil")
        self.forbidden_collections = frozenset(
            c.strip()
            for c in os.environ.get("BOOND_MOCK_FORBIDDEN_COLLECTIONS", "").split(",")
            if c.strip()
        )
        self.compensation_mode = os.environ.get("BOOND_MOCK_COMPENSATION_MODE", "csv")
        self.evolution_enabled = _flag("BOOND_MOCK_EVOLUTION", True)
        self.evolution_interval = float(os.environ.get("BOOND_MOCK_EVOLUTION_INTERVAL", "60"))


settings = Settings()
settings.reload()
