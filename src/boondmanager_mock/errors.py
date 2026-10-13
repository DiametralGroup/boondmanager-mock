"""Error envelope — the exact shape observed on the real API (9.1.78.1).

A real error ALWAYS carries `meta` (version, isLogged, language, timestamp…),
then `{status, code, detail, title | source}` entries:

    401/403/404/405 : {"status": "404", "code": "404",
                       "detail": "HTTP 404 (GET /api/resources/999999999)",
                       "title": "404"}
    422 JWT         : {"status": "422", "code": "422",
                       "detail": "422 - Signature verification failed",
                       "source": {"parameter": "xJwtClient"}}
    422 business    : {"status": "422", "code": "1017",
                       "detail": "1017 - Missing required attribute",
                       "source": {"parameter": "endMonth"}}

Key dialect detail: when the request is unauthenticated (401, invalid JWT) or
the ROUTE does not exist (404/405 — routing precedes auth), `meta` renders
`isLogged: false` and `language: "en"`, with no `login` nor `customer`.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def error_entry(
    status_code: int,
    detail: str,
    *,
    code: str | None = None,
    source: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One entry of the `errors` array — `title` OR `source`, never both."""
    entry: dict[str, Any] = {
        "status": str(status_code),
        "code": code or str(status_code),
        "detail": detail,
    }
    if source is not None:
        entry["source"] = source
    else:
        entry["title"] = str(status_code)
    return entry


def error_response(
    status_code: int,
    entries: list[dict[str, Any]],
    *,
    logged_in: bool = True,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """The full envelope: meta (per authentication state) + errors."""
    from .envelope import error_meta

    return JSONResponse(
        status_code=status_code,
        content={"meta": error_meta(logged_in), "errors": entries},
        headers=headers or {},
    )


def generic_detail(status_code: int, request: Request) -> str:
    """`"HTTP 404 (GET /api/resources/12?maxResults=2)"` — the real format."""
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return f"HTTP {status_code} ({request.method} {target})"


def error(
    status_code: int,
    detail: str | None = None,
    *,
    request: Request | None = None,
    code: str | None = None,
    source: dict[str, str] | None = None,
    logged_in: bool = True,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """A single-entry error. Without `detail`, the real generic message is
    built from the request (`HTTP {code} ({method} {path})`)."""
    if detail is None:
        detail = f"HTTP {status_code}" if request is None else generic_detail(status_code, request)
    return error_response(
        status_code,
        [error_entry(status_code, detail, code=code, source=source)],
        logged_in=logged_in,
        headers=headers,
    )
