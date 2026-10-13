"""BoondManager API mock — container image and installable Python package.

The surface reproduces the documented vendor modules
(https://doc.boondmanager.com/api-externe/) over ONE realistic and coherent
dataset — « Boréal Conseil », a French IT consulting firm — that EVOLVES over
time to exercise incremental extraction (see evolution.py).

Two usage modes, deliberately both kept:

  • **In-process** — `TestClient(boondmanager_mock.app)`. The property that
    must not be lost: the application the stack queries IS the one the tests
    exercise.

  • **In a container** — `python -m boondmanager_mock`, in docker compose as
    in a CI sidecar. This mode is what makes the `/__admin` control plane
    indispensable: outside the process, the state can no longer be mutated
    from Python.

Re-exports so nothing needs to know the internal structure:

    app                  the FastAPI application
    state                the mutable state (dataset, fail_collections, reset)
    build_dataset        dataset construction
    build_client_jwt     the HS256 JWT for X-Jwt-Client-Boondmanager
    JWT_HEADER_NAME      that header's name
"""

from __future__ import annotations

from .app import app, contract_openapi
from .auth import JWT_HEADER_NAME, build_client_jwt
from .injection import engine
from .settings import settings
from .state import build_dataset, state

__all__ = [
    "JWT_HEADER_NAME",
    "app",
    "build_client_jwt",
    "build_dataset",
    "contract_openapi",
    "engine",
    "settings",
    "state",
]

__version__ = "0.11.0"
