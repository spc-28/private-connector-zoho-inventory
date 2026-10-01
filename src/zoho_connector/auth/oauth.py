import time
from urllib.parse import urlencode

import httpx

from zoho_connector.auth.token_store import Tokens
from zoho_connector.config import Settings
from zoho_connector.errors import Code, ConnectorError, auth_required, rate_limited

READ_SCOPES = ",".join(
    f"ZohoInventory.{resource}.READ"
    for resource in (
        "salesorders",
        "invoices",
        "packages",
        "shipmentorders",
        "items",
        "contacts",
        "settings",
    )
)
TIMEOUT = httpx.Timeout(20.0)


def authorize_url(settings: Settings, state: str) -> str:
    query = urlencode(
        {
            "scope": READ_SCOPES,
            "client_id": settings.client_id,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "redirect_uri": settings.redirect_uri,
            "state": state,
        }
    )
    return f"{settings.accounts_url}/oauth/v2/auth?{query}"


async def exchange_code(
    settings: Settings, accounts_server: str, code: str, redirect_uri: str | None
) -> Tokens:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "code": code,
    }
    if redirect_uri:
        data["redirect_uri"] = redirect_uri
    body = await _post(f"{accounts_server}/oauth/v2/token", data)
    if "refresh_token" not in body:
        raise auth_required("Zoho issued no refresh token. Re-run setup with consent.")
    return Tokens(
        refresh_token=body["refresh_token"],
        accounts_server=accounts_server,
        api_domain=body["api_domain"],
        access_token=body["access_token"],
        expires_at=time.time() + int(body.get("expires_in", 3600)),
    )


async def refresh(settings: Settings, tokens: Tokens) -> Tokens:
    body = await _post(
        f"{tokens.accounts_server}/oauth/v2/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
        },
    )
    tokens.access_token = body["access_token"]
    tokens.expires_at = time.time() + int(body.get("expires_in", 3600))
    tokens.api_domain = body.get("api_domain", tokens.api_domain)
    return tokens


async def revoke(tokens: Tokens) -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        await http.post(
            f"{tokens.accounts_server}/oauth/v2/token/revoke",
            params={"token": tokens.refresh_token},
        )


async def _post(url: str, data: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.post(url, data=data)
    except httpx.TransportError as exc:
        raise ConnectorError(
            Code.UPSTREAM_ERROR, "Could not reach the Zoho accounts server.", retryable=True
        ) from exc
    if response.status_code >= 500:
        raise ConnectorError(
            Code.UPSTREAM_ERROR, "The Zoho accounts server failed.", retryable=True
        )
    body = _json(response)
    if "access_token" in body:
        return body
    description = str(body.get("error_description", "")).lower()
    if "too many requests" in description:
        raise rate_limited(60, "Zoho is limiting token requests for this client.")
    raise auth_required(f"Zoho rejected the token request ({body.get('error', 'unknown')}).")


def _json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {}
