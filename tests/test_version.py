"""A single version: pyproject, the package and the OpenAPI contract all agree.

Up to 0.10.0, the three diverged (0.10.0, 0.3.0, 0.5.4): the published
contract announced a version seven releases old.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import boondmanager_mock as mock

ROOT = Path(__file__).resolve().parents[1]


def test_single_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    assert mock.__version__ == version
    assert mock.app.version == version
