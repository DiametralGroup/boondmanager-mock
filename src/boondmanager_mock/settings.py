"""Configuration — everything through environment variables, no file.

The original mock read its five variables at import time, which made it
impossible to change them in a test without reloading the module. They are
centralized here, in an object re-read by `reload()`, keeping the same
variable names as the existing deployments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Defaults identical to the original mock's: the existing composes and charts
# only set the first three.
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
    """Configuration state, re-read live by `reload()`."""

    user_token: str = ""
    client_token: str = ""
    client_key: str = ""
    basic_user: str = ""
    basic_password: str = ""

    # The original mock froze the seed at 42 with no way to change it other
    # than in Python. In a container, that was no longer possible at all.
    seed: int = 42

    # `/__admin` control plane. Closed by default: it only makes sense in
    # tests.
    admin_enabled: bool = False
    admin_token: str = "mock-admin-token"

    # STABLE order by default, aligned with the real API's observed behavior
    # (2026-07-31). Set to false (or inject `unstable_order`) to exercise a
    # pipeline that paginates without sorting.
    stable_order: bool = True

    # `updatedSince` / `filter[updateDate][gte]`: mock AFFORDANCE that the
    # real API IGNORES (probed 2026-09-29 on 11 modules: identical totals with
    # and without). Disabled by default since 0.11.0: applied unconditionally,
    # it made a client that re-read everything in production look green.
    updated_since_enabled: bool = False

    # The tenant name announced in `meta.customer`.
    customer: str = "boreal-conseil"

    # Collections served as 403 — reproduces a user token with a restricted
    # perimeter (`narrowPerimeter`), as observed on the real tenant.
    forbidden_collections: frozenset[str] = frozenset()

    # absent | csv — the compensation fixture outside /api (see README).
    compensation_mode: str = "csv"

    # ── Time evolution (incremental extraction) ──────────────────────────────
    # The dataset LIVES: a scripted event every `evolution_interval` seconds
    # (new actions, staffing/destaffing, invoices settled…). Setting this to
    # false — or the interval to 0 — freezes the dataset for uses that require
    # byte-for-byte stable content.
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
