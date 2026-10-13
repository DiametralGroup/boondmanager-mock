"""Container entry point: `python -m boondmanager_mock`.

Deliberately minimal — no CLI, no options. Everything is configured through
environment variables (see settings.py), because that is the only mechanism
that works identically in docker compose, a Kubernetes Deployment, and a
Tekton sidecar.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "boondmanager_mock:app",
        host=os.environ.get("BOOND_MOCK_HOST", "0.0.0.0"),
        port=int(os.environ.get("BOOND_MOCK_PORT", "8000")),
        log_config=None,
    )


if __name__ == "__main__":
    main()
