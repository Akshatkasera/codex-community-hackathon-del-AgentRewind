from __future__ import annotations

import secrets

from fastapi import Request

from .config import get_settings


def extract_api_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    header_token = request.headers.get("X-API-Key")
    if header_token:
        return header_token.strip()
    return None


def request_is_authorized(request: Request) -> bool:
    settings = get_settings()
    if not settings.auth_required:
        return True
    token = extract_api_token(request)
    if not token:
        return False
    return any(secrets.compare_digest(token, allowed) for allowed in settings.auth_tokens)


def requires_auth(path: str) -> bool:
    return path.startswith("/api/")
