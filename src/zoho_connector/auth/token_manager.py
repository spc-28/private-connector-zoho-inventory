import asyncio
import time

from zoho_connector.auth import oauth, token_store
from zoho_connector.auth.token_store import Tokens
from zoho_connector.config import Settings
from zoho_connector.errors import auth_required

REFRESH_MARGIN_SECONDS = 300


class TokenManager:
    """Hands out a valid access token, refreshing once at a time and sharing it via the keychain."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._lock = asyncio.Lock()
        self._tokens = token_store.load()

    @property
    def authorized(self) -> bool:
        return self._tokens is not None

    @property
    def api_domain(self) -> str:
        return self._require().api_domain

    @property
    def accounts_server(self) -> str:
        return self._require().accounts_server

    async def access_token(self, rejected: str | None = None) -> str:
        if self._usable(self._tokens, rejected):
            return self._tokens.access_token
        async with self._lock:
            self._tokens = token_store.load() or self._tokens
            tokens = self._require()
            if not self._usable(tokens, rejected):
                self._tokens = await oauth.refresh(self._settings, tokens)
                token_store.save(self._tokens)
            return self._tokens.access_token

    def _require(self) -> Tokens:
        if self._tokens is None:
            raise auth_required()
        return self._tokens

    @staticmethod
    def _usable(tokens: Tokens | None, rejected: str | None) -> bool:
        return bool(
            tokens
            and tokens.access_token
            and tokens.access_token != rejected
            and tokens.expires_at - time.time() > REFRESH_MARGIN_SECONDS
        )
