"""Test harness.

Two environment settings, set BEFORE the package import (configuration is
read at import time):

  • the `/__admin` control plane is mounted — mounting is conditional;
  • the evolution interval is set to 3600s: no event fires on the wall clock
    during the suite, even on a slow CI. Evolution tests fast-forward time
    EXPLICITLY via /__admin/clock — that is what makes them deterministic.
"""

from __future__ import annotations

import os

os.environ.setdefault("BOOND_MOCK_ADMIN_ENABLED", "true")
os.environ.setdefault("BOOND_MOCK_EVOLUTION_INTERVAL", "3600")

import pytest
from fastapi.testclient import TestClient

import boondmanager_mock as mock

JWT = {
    mock.JWT_HEADER_NAME: mock.build_client_jwt(
        "mock-user-token", "mock-client-token", "mock-client-key"
    )
}
ADMIN = {"X-Mock-Admin-Token": "mock-admin-token"}


@pytest.fixture()
def client():
    """A client on a FRESHLY RESET state — before AND after, so a test leaves
    neither an injection rule nor an evolution event to the next one."""
    c = TestClient(mock.app)
    mock.state.reset()
    yield c
    mock.state.reset()


@pytest.fixture()
def boond_state(client):  # noqa: ARG001 — the fixture chains the reset
    """The mock's mutable state, for tests that inspect the dataset."""
    return mock.state
