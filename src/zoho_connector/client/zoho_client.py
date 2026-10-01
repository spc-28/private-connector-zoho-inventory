import asyncio
import random

import httpx

from zoho_connector.auth.token_manager import TokenManager
from zoho_connector.client.quota import DailyQuota
from zoho_connector.client.rate_limiter import RateLimiter
from zoho_connector.config import Settings
from zoho_connector.errors import Code, ConnectorError, auth_required, rate_limited

BLOCKED_PER_MINUTE = 44
DAILY_LIMIT_HIT = 45
TOO_MANY_IN_FLIGHT = 1070
NOT_AUTHORIZED = 57


class _Retry(Exception):
    pass


class ZohoClient:
    """The only code that talks to Zoho Inventory. It issues GET requests only."""

    def __init__(
        self,
        settings: Settings,
        tokens: TokenManager,
        limiter: RateLimiter,
        quota: DailyQuota,
        organization_id: str | None,
    ):
        self._settings = settings
        self._tokens = tokens
        self._limiter = limiter
        self._quota = quota
        self._organization_id = organization_id
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    @property
    def organization_id(self) -> str | None:
        return self._organization_id

    async def get(self, path: str, params: dict | None = None, *, with_org: bool = True) -> dict:
        return (await self._request(path, params, with_org)).json()

    async def get_bytes(self, path: str, params: dict | None = None) -> bytes:
        return (await self._request(path, params, True)).content

    async def get_page(
        self, path: str, key: str, page: int, per_page: int, params: dict | None = None
    ) -> tuple[list[dict], bool]:
        body = await self.get(path, {**(params or {}), "page": page, "per_page": per_page})
        has_more = bool(body.get("page_context", {}).get("has_more_page"))
        return body.get(key, []), has_more

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, path: str, params: dict | None, with_org: bool) -> httpx.Response:
        query = dict(params or {})
        if with_org:
            query["organization_id"] = self._require_org()
        rejected: str | None = None
        for attempt in range(self._settings.max_retries + 1):
            token = await self._tokens.access_token(rejected)
            response = await self._send(path, query, token)
            try:
                return self._accept(response, token, rejected)
            except _Retry:
                if response is not None and response.status_code == 401:
                    rejected = token
                elif attempt < self._settings.max_retries:
                    await asyncio.sleep(_backoff(attempt))
        raise self._exhausted(response)

    async def _send(self, path: str, query: dict, token: str) -> httpx.Response | None:
        self._quota.check()
        url = f"{self._tokens.api_domain}/inventory/v1{path}"
        async with self._limiter.slot():
            try:
                response = await self._http.get(
                    url, params=query, headers={"Authorization": f"Zoho-oauthtoken {token}"}
                )
            except httpx.TransportError:
                return None
        self._quota.record()
        return response

    def _accept(
        self, response: httpx.Response | None, token: str, rejected: str | None
    ) -> httpx.Response:
        if response is None or response.status_code >= 500:
            raise _Retry
        status, code = response.status_code, _zoho_code(response)
        if status < 300:
            return response
        if status == 401:
            if rejected is None:
                raise _Retry
            if code == NOT_AUTHORIZED:
                raise ConnectorError(
                    Code.FORBIDDEN_SCOPE,
                    "Zoho refused this request for the granted scopes.",
                    hint="Re-run zoho-connector-setup and grant all requested read scopes.",
                )
            raise auth_required("Zoho rejected the access token after a refresh.")
        if status == 429:
            return self._throttled(code)
        if status == 404:
            raise ConnectorError(Code.NOT_FOUND, "Zoho has no matching record.")
        if status == 400:
            raise ConnectorError(
                Code.INVALID_INPUT, f"Zoho rejected the request: {_zoho_message(response)}"
            )
        raise ConnectorError(Code.UPSTREAM_ERROR, f"Zoho returned HTTP {status}.")

    def _throttled(self, code: int | None) -> httpx.Response:
        if code == BLOCKED_PER_MINUTE:
            seconds = self._settings.block_cooldown_seconds
            self._limiter.block(seconds)
            raise rate_limited(seconds, "Zoho blocked this organization for exceeding its rate.")
        if code == DAILY_LIMIT_HIT:
            self._quota.mark_exhausted()
            self._quota.check()
        raise _Retry

    def _exhausted(self, response: httpx.Response | None) -> ConnectorError:
        if response is not None and response.status_code == 429:
            return rate_limited(5, "Too many Zoho requests are in flight.")
        return ConnectorError(
            Code.UPSTREAM_ERROR,
            "Zoho did not respond successfully after retries.",
            retryable=True,
            hint="Retry later.",
        )

    def _require_org(self) -> str:
        if not self._organization_id:
            raise ConnectorError(
                Code.CONFIG_REQUIRED,
                "No Zoho organization is selected.",
                hint="Run zoho-connector-setup or set ZOHO_ORGANIZATION_ID.",
            )
        return self._organization_id


def _backoff(attempt: int) -> float:
    return min(20.0, 2**attempt) + random.uniform(0, 1)


def _zoho_code(response: httpx.Response) -> int | None:
    try:
        return int(response.json().get("code"))
    except (ValueError, TypeError, AttributeError):
        return None


def _zoho_message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("message", "unknown error"))[:200]
    except (ValueError, AttributeError):
        return "unknown error"
