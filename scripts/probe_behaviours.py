#!/usr/bin/env python3
"""Probe BEHAVIOURS — pagination, sorting, filters — on the mock or the real API.

`compare_real.py` compares SHAPES. This script asks the questions shapes cannot
answer, the same way to both sides, so that each can be compared to the
contract (RAML):

  1. pagination : is `maxResults` honoured? what happens above the maximum?
                  are the modules without pagination in the contract paginated?
  2. sorting    : is `sort=id` (outside every `sortList`) honoured? official
                  keys and `order`? what is the default order?
  3. incremental: does `updatedSince` (outside the contract) filter?
                  does the official `period=updated`?
  4. /times     : does the contract's `period=inProgress` filter?

Read-only (GET only). The output only contains counts, technical identifiers
and dates — never a business value — so it can be committed.

    real : export BOOND_REAL_USER_TOKEN=… BOOND_REAL_CLIENT_TOKEN=… BOOND_REAL_CLIENT_KEY=…
           python scripts/probe_behaviours.py --target real --output probe.json
    mock : uv run python scripts/probe_behaviours.py --target mock

Run on 2026-09-29: 108 calls on the real API — docs/comparisons/2026-09-29.md.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Les 11 modules où le contrat documente `period=updated`.
PERIOD_UPDATED = [
    "resources", "companies", "contacts", "projects", "actions", "opportunities",
    "candidates", "purchases", "invoices", "payments", "orders",
]  # fmt: skip
# Modules sans le trait `sortablePaginable` au contrat.
NOT_PAGINATED = ["agencies", "poles", "business-units"]
FUTURE_ISO = "2099-01-01T00:00:00Z"
PAUSE_S = 0.25


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def client_jwt(user_token: str, client_token: str, client_key: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"userToken": user_token, "clientToken": client_token}).encode())
    signature = hmac.new(client_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256)
    return f"{header}.{payload}.{_b64url(signature.digest())}"


def _env(name: str) -> str:
    """`BOOND_REAL_*` comme compare_real.py, à défaut les noms du consommateur."""
    return os.environ.get(f"BOOND_REAL_{name}") or os.environ.get(f"BOOND_{name}") or ""


class Target:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        if name == "real":
            tokens = {n: _env(n) for n in ("USER_TOKEN", "CLIENT_TOKEN", "CLIENT_KEY")}
            if missing := [n for n, v in tokens.items() if not v]:
                sys.exit(f"missing variables: {missing}")
            self.base = (_env("API_URL") or "https://ui.boondmanager.com/api").rstrip("/")
            self.headers = {
                "X-Jwt-Client-Boondmanager": client_jwt(
                    tokens["USER_TOKEN"], tokens["CLIENT_TOKEN"], tokens["CLIENT_KEY"]
                ),
                "Accept": "application/json",
            }
        else:
            os.environ.setdefault("BOOND_MOCK_EVOLUTION_INTERVAL", "3600")
            from fastapi.testclient import TestClient

            import boondmanager_mock as mock

            mock.state.reset()
            self.test_client = TestClient(mock.app)
            self.headers = {
                mock.JWT_HEADER_NAME: mock.build_client_jwt(
                    "mock-user-token", "mock-client-token", "mock-client-key"
                )
            }

    def get(self, path: str, **params: Any) -> tuple[int, dict[str, Any]]:
        self.calls += 1
        if self.name == "mock":
            r = self.test_client.get(f"/api/{path}", params=params, headers=self.headers)
            return r.status_code, r.json()
        url = f"{self.base}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        for attempt in range(4):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers=self.headers), timeout=60
                ) as response:
                    body = response.read()
                    time.sleep(PAUSE_S)
                    return response.status, json.loads(body or b"{}")
            except urllib.error.HTTPError as e:
                if e.code in (429, 502, 503, 504) and attempt < 3:
                    time.sleep(min(float(e.headers.get("Retry-After") or 2 ** (attempt + 1)), 30))
                    continue
                try:
                    return e.code, json.loads(e.read() or b"{}")
                except ValueError:
                    return e.code, {}
        return 0, {}


def total(body: dict[str, Any]) -> int | None:
    rows = ((body.get("meta") or {}).get("totals") or {}).get("rows")
    return rows if isinstance(rows, int) else None


def ids(body: dict[str, Any]) -> list[str]:
    return [str(i.get("id")) for i in body.get("data") or []]


def values(body: dict[str, Any], field: str) -> list[Any]:
    return [(i.get("attributes") or {}).get(field) for i in body.get("data") or []]


def monotonic(items: list[Any], order: str) -> bool | None:
    present = [x for x in items if x not in (None, "")]
    if len(present) < 2:
        return None
    return present == sorted(present, reverse=(order == "desc"))


def probe(t: Target) -> dict[str, Any]:
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    status, body = t.get("resources", maxResults=1)
    out: dict[str, Any] = {
        "target": t.name,
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "version": (body.get("meta") or {}).get("version"),
        "first_status": status,
    }

    pagination: dict[str, Any] = {}
    for path, sizes in (("actions", [2, 100, 101, 500]), ("companies", [2, 500, 501])):
        for size in sizes:
            status, body = t.get(path, maxResults=size)
            pagination[f"{path}?maxResults={size}"] = {
                "status": status, "rows": len(body.get("data") or []), "total": total(body),
            }  # fmt: skip
    for path in NOT_PAGINATED:
        status, body = t.get(path, page=2, maxResults=1)
        pagination[f"{path}?page=2&maxResults=1"] = {
            "status": status, "rows": len(body.get("data") or []), "total": total(body),
        }  # fmt: skip
    out["pagination"] = pagination

    sorting: dict[str, Any] = {}
    for path in ("resources", "companies", "actions"):
        _, default = t.get(path, maxResults=5)
        _, asc = t.get(path, maxResults=5, sort="id", order="asc")
        _, desc = t.get(path, maxResults=5, sort="id", order="desc")
        sorting[f"{path}: sort=id"] = {
            "default": ids(default), "asc": ids(asc), "desc": ids(desc),
            "honoured": ids(asc) != ids(desc),
        }  # fmt: skip
    for path, key in (
        ("resources", "updateDate"),
        ("resources", "creationDate"),
        ("companies", "updateDate"),
        ("actions", "startDate"),
    ):
        for order in ("asc", "desc"):
            _, body = t.get(path, maxResults=5, sort=key, order=order)
            sorting[f"{path}: sort={key}&order={order}"] = {
                "ids": ids(body), "monotonic": monotonic(values(body, key), order),
            }  # fmt: skip
    for path, key in (
        ("resources", "updateDate"),
        ("companies", "updateDate"),
        ("actions", "startDate"),
    ):
        _, body = t.get(path, maxResults=10)
        sorting[f"{path}: default order"] = {
            "ids": ids(body), f"{key} descending": monotonic(values(body, key), "desc"),
        }  # fmt: skip
    out["sorting"] = sorting

    incremental: dict[str, Any] = {}
    for path in PERIOD_UPDATED:
        _, all_rows = t.get(path, maxResults=1)
        _, since = t.get(path, maxResults=1, updatedSince=FUTURE_ISO)
        _, future = t.get(
            path, maxResults=1, period="updated", startDate="2099-01-01", endDate="2099-12-31"
        )
        _, recent = t.get(
            path, maxResults=1, period="updated",
            startDate=yesterday.isoformat(), endDate=today.isoformat(),
        )  # fmt: skip
        incremental[path] = {
            "total": total(all_rows),
            "updatedSince=2099": total(since),
            "period=updated 2099": total(future),
            "period=updated since yesterday": total(recent),
        }
    out["incremental"] = incremental

    month_start = today.replace(day=1)
    previous_end = month_start - dt.timedelta(days=1)
    _, all_times = t.get("times", maxResults=1)
    _, current = t.get(
        "times", maxResults=1, period="inProgress",
        startDate=month_start.isoformat(), endDate=today.isoformat(),
    )  # fmt: skip
    _, previous = t.get(
        "times", maxResults=1, period="inProgress",
        startDate=previous_end.replace(day=1).isoformat(), endDate=previous_end.isoformat(),
    )  # fmt: skip
    out["times"] = {
        "total": total(all_times),
        "inProgress current month": total(current),
        "inProgress previous month": total(previous),
    }
    out["calls"] = t.calls
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--target", choices=["mock", "real"], required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = probe(Target(args.target))
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
