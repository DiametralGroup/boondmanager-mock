"""Authentication — BoondManager's exact dialect.

This module ALSO carries `build_client_jwt` and `JWT_HEADER_NAME`, which used
to live in ophelie's production client (`app/boond/client.py`). This is
deliberate: the mock's test file at ophelie imported these two symbols from
the production client, which coupled the mock to application code. Publishing
them here makes the mock testable on its own, and consumers (insights360's dlt
pipeline, ophelie's test suite) get a single source for building the token.

Ophelie's PRODUCTION client is not moved: it stays at ophelie.

Three details of the real dialect that must not be "simplified":

  1. base64url WITHOUT padding. Padding makes verification fail on the API
     side.
  2. The payload is EXACTLY {"userToken", "clientToken"} — no iat, no exp, no
     iss. It is a static credential, not a session token.
  3. A JWT that is present but invalid returns **422, not 401**. That is what
     the real API does, and the status code is what a retry strategy keys on:
     a 401 invites retrying with different credentials, a 422 says the
     request is malformed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from .settings import settings

JWT_HEADER_NAME = "X-Jwt-Client-Boondmanager"


def _b64url(raw: bytes) -> str:
    """base64url WITHOUT padding — a trailing `=` would make verification fail."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def build_client_jwt(user_token: str, client_token: str, client_key: str) -> str:
    """The HS256 JWT expected in ``X-Jwt-Client-Boondmanager``."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"userToken": user_token, "clientToken": client_token}).encode())
    signature = _b64url(
        hmac.new(client_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}"


def jwt_is_valid(token: str) -> bool:
    """Signature AND claims.

    Checking the signature alone would not be enough: a correctly signed
    token carrying other tokens would be accepted. The real API checks both.
    """
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        expected = hmac.new(
            settings.client_key.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return False
        payload = json.loads(_b64url_decode(payload_b64))
        return bool(
            payload.get("userToken") == settings.user_token
            and payload.get("clientToken") == settings.client_token
        )
    except Exception:
        return False


def basic_is_valid(value: str) -> bool:
    try:
        user, _, password = base64.b64decode(value).decode().partition(":")
    except Exception:
        return False
    return user == settings.basic_user and password == settings.basic_password
