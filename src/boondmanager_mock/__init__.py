"""Mock de l'API BoondManager — image container et paquet Python installable.

La surface reproduit les modules documentés du fournisseur
(https://doc.boondmanager.com/api-externe/) sur UN jeu de données réaliste et
cohérent — « Boréal Conseil », ESN française — qui ÉVOLUE dans le temps pour
éprouver l'extraction incrémentale (cf. evolution.py).

Deux modes d'utilisation, délibérément maintenus tous les deux :

  • **En process** — `TestClient(boondmanager_mock.app)`. La propriété qu'il ne
    faut pas perdre : l'application que la stack interroge EST celle que les
    tests exercent.

  • **En conteneur** — `python -m boondmanager_mock`, en docker compose comme
    en sidecar CI. C'est ce mode qui rend indispensable le plan de contrôle
    `/__admin` : hors du processus, on ne peut plus muter l'état en Python.

Ré-exports pour que rien n'ait besoin de connaître la structure interne :

    app                  l'application FastAPI
    state                l'état mutable (dataset, fail_collections, reset)
    build_dataset        construction du jeu de données
    build_client_jwt     le JWT HS256 de X-Jwt-Client-Boondmanager
    JWT_HEADER_NAME      le nom de cet en-tête
"""

from __future__ import annotations

from .app import app, contrat_openapi
from .auth import JWT_HEADER_NAME, build_client_jwt
from .injection import engine
from .settings import settings
from .state import build_dataset, state

__all__ = [
    "JWT_HEADER_NAME",
    "app",
    "build_client_jwt",
    "build_dataset",
    "contrat_openapi",
    "engine",
    "settings",
    "state",
]

__version__ = "0.11.0"
