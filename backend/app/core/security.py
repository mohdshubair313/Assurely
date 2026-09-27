"""Verify customer identity before any consent or profile-memory access.

Tokens must be issued by a trusted identity provider and signed with an RSA
key advertised at the configured JWKS URL. This API does not mint tokens or
accept a caller-supplied UUID as proof of identity.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False, scheme_name="SessionBearer")


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300)


def _auth_configuration() -> tuple[str, str, str]:
    settings = get_settings()
    issuer = settings.auth_issuer.strip()
    audience = settings.auth_audience.strip()
    jwks_url = settings.auth_jwks_url.strip()
    if not all((issuer, audience, jwks_url)) or not jwks_url.startswith("https://"):
        raise HTTPException(
            status_code=503,
            detail="Profile-memory authentication is not configured.",
        )
    return issuer, audience, jwks_url


def _verify_token(credentials: HTTPAuthorizationCredentials) -> uuid.UUID:
    issuer, audience, jwks_url = _auth_configuration()
    token = credentials.credentials
    if credentials.scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid bearer token.")
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def optional_authenticated_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
) -> uuid.UUID | None:
    """Allow anonymous messages, but validate every supplied bearer token."""
    if credentials is None:
        return None
    return _verify_token(credentials)


def require_authenticated_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
) -> uuid.UUID:
    """Fail closed when the identity provider or bearer token is absent."""
    _auth_configuration()
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="A verified bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _verify_token(credentials)


def require_matching_user_id(
    authenticated_user_id: uuid.UUID, requested_user_id: uuid.UUID
) -> None:
    if authenticated_user_id != requested_user_id:
        raise HTTPException(status_code=403, detail="The user_id does not match the token subject.")
