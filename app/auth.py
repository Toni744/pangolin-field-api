import logging
import os
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _auth_settings() -> tuple[str, str, str, str]:
    issuer = os.getenv("ENTRA_EXTERNAL_ID_ISSUER", "")
    jwks_url = os.getenv("ENTRA_EXTERNAL_ID_JWKS_URL", "")
    audience = os.getenv("ENTRA_API_AUDIENCE", "")
    required_scope = os.getenv("ENTRA_API_SCOPE", "samples.write")
    if not all((issuer, jwks_url, audience, required_scope)):
        logger.error("Microsoft Entra External ID token validation is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )
    if not issuer.startswith("https://") or not jwks_url.startswith("https://"):
        logger.error("External ID issuer and JWKS URL must use HTTPS.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is misconfigured.",
        )
    return issuer, jwks_url, audience, required_scope


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, timeout=5)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A bearer access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    issuer, jwks_url, audience, required_scope = _auth_settings()
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except PyJWKClientConnectionError as error:
        logger.warning("Could not retrieve External ID signing keys: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication service is temporarily unavailable.",
        ) from error
    except (InvalidTokenError, PyJWKClientError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    subject = claims.get("sub")
    scopes = claims.get("scp")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token has no valid user subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not isinstance(scopes, str) or required_scope not in scopes.split():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The access token does not grant the required API scope.",
        )
    return claims
