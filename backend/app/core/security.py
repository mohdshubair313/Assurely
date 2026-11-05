"""Verify customer identity before any consent or profile-memory access.

Tokens must be issued by a trusted identity provider and signed with an RSA
key advertised at the configured JWKS URL. This API does not mint tokens or
accept a caller-supplied UUID as proof of identity.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

import httpx
import jwt
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False, scheme_name="SessionBearer")


@lru_cache(maxsize=8)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


def _auth_configuration(settings: Settings | None = None) -> tuple[str, str, str]:
    settings = settings or get_settings()
    issuer = settings.auth_issuer.strip()
    audience = settings.auth_audience.strip()
    jwks_url = settings.auth_jwks_url.strip()
    provider = getattr(settings, "auth_provider", "legacy_oidc")
    if provider not in {"clerk", "legacy_oidc"}:
        raise HTTPException(503, "Authentication is not configured.")
    if provider == "clerk":
        try:
            parsed = urlsplit(issuer)
            _ = parsed.port
        except ValueError as exc:
            raise HTTPException(503, "Clerk authentication is not configured.") from exc
        parties = getattr(settings, "auth_authorized_parties", [])
        valid_parties = bool(parties) and all(
            _origin(value, settings.environment) for value in parties
        )
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or jwks_url != issuer.rstrip("/") + "/.well-known/jwks.json"
            or not valid_parties
            or (
                settings.environment == "production"
                and parsed.hostname.endswith(".clerk.accounts.dev")
            )
        ):
            raise HTTPException(503, "Clerk authentication is not configured.")
    elif not all((issuer, audience, jwks_url)) or not jwks_url.startswith("https://"):
        raise HTTPException(
            status_code=503,
            detail="Profile-memory authentication is not configured.",
        )
    return issuer, audience, jwks_url


def _origin(value: str, environment: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.hostname
        and "*" not in parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and (
            parsed.scheme == "https"
            or (
                environment == "development"
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1"}
            )
        )
    )


def _verify_token(credentials: HTTPAuthorizationCredentials) -> uuid.UUID:
    issuer, audience, jwks_url = _auth_configuration()
    clerk = getattr(get_settings(), "auth_provider", "legacy_oidc") == "clerk"
    token = credentials.credentials
    if credentials.scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="Invalid bearer token.")
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or (clerk and not isinstance(header.get("kid"), str)):
            raise ValueError("Invalid signing header")
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        if clerk:
            # Keep our bounded, issuer-pinned JWKS cache. The official SDK verifies
            # the token with that fetched public key without a second API call.
            pem = signing_key.key.public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode("ascii")
            verified = authenticate_request(
                httpx.Request("GET", issuer, headers={"Authorization": f"Bearer {token}"}),
                AuthenticateRequestOptions(
                    jwt_key=pem, audience=audience or None,
                    authorized_parties=get_settings().auth_authorized_parties,
                    accepts_token=["session_token"], clock_skew_in_ms=0,
                ),
            )
            if not verified.is_signed_in or not isinstance(verified.payload, dict):
                raise ValueError("Invalid Clerk session")
            claims = verified.payload
            # SDK 7.1 deliberately does not enforce an expected issuer or require
            # all time claims. Preserve Assurely's stricter application contract.
            if (
                claims["iss"] != issuer
                or claims["v"] != 2
                or isinstance(claims["v"], bool)
                or not isinstance(claims["sub"], str)
                or not re.fullmatch(r"user_[A-Za-z0-9]{1,240}", claims["sub"])
                or not isinstance(claims["sid"], str)
                or not re.fullmatch(r"sess_[A-Za-z0-9]{1,240}", claims["sid"])
                or claims["azp"] not in get_settings().auth_authorized_parties
                or claims.get("sts", "active") != "active"
                or any(type(claims[field]) is not int for field in ("exp", "iat", "nbf"))
                or claims["exp"] <= claims["iat"]
                or claims["exp"] <= claims["nbf"]
            ):
                raise ValueError("Invalid session claims")
            from app.db.auth_identity import resolve_identity

            return resolve_identity(issuer, claims["sub"])
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], issuer=issuer, audience=audience,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        return uuid.UUID(claims["sub"])
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, "Identity verification is unavailable.") from exc
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as exc:
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
        if getattr(get_settings(), "auth_provider", "legacy_oidc") == "clerk":
            return require_authenticated_user_id(None)
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


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: uuid.UUID
    issuer: str
    provider: str
    roles: frozenset[str]


def server_roles(user_id: uuid.UUID) -> frozenset[str]:
    settings = get_settings()
    roles = {"customer"}
    for role, field in (
        ("admin", "admin_subjects"),
        ("qualified_policy_reviewer", "policy_reviewer_subjects"),
        ("policy_publisher", "policy_publisher_subjects"),
        ("human_advisor", "advisor_subjects"),
    ):
        try:
            allowed = {uuid.UUID(item) for item in getattr(settings, field, [])}
            tests = {uuid.UUID(item) for item in getattr(settings, "auth_test_subjects", [])}
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(503, "Role authorization is not configured.") from exc
        if user_id in allowed and user_id not in tests:
            roles.add(role)
    return frozenset(roles)


def is_test_account(user_id: uuid.UUID) -> bool:
    try:
        return user_id in {
            uuid.UUID(value) for value in getattr(get_settings(), "auth_test_subjects", [])
        }
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Test-account authorization is not configured.") from exc


def require_principal(
    user_id: Annotated[uuid.UUID, Depends(require_authenticated_user_id)],
) -> AuthenticatedPrincipal:
    settings = get_settings()
    return AuthenticatedPrincipal(
        user_id,
        settings.auth_issuer,
        getattr(settings, "auth_provider", "legacy_oidc"),
        server_roles(user_id),
    )


def require_admin(
    principal: Annotated[AuthenticatedPrincipal, Depends(require_principal)],
) -> AuthenticatedPrincipal:
    if "admin" not in principal.roles:
        raise HTTPException(403, "Administrator authorization is required.")
    return principal
