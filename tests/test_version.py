"""Une seule version : pyproject, le paquet et le contrat OpenAPI disent la même.

Jusqu'à 0.10.0, les trois divergeaient (0.10.0, 0.3.0, 0.5.4) : le contrat
publié annonçait une version vieille de sept releases.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import boondmanager_mock as mock

RACINE = Path(__file__).resolve().parents[1]


def test_une_seule_version() -> None:
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    version = projet["project"]["version"]
    assert mock.__version__ == version
    assert mock.app.version == version
