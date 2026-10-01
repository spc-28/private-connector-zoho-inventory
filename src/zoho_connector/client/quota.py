import logging
from datetime import UTC, datetime

from zoho_connector.errors import Code, ConnectorError
from zoho_connector.store import JsonFile

log = logging.getLogger(__name__)
WARN_RATIO = 0.8


class DailyQuota:
    """Counts this connector's Zoho calls per UTC day. A lower bound: other apps share the quota."""

    def __init__(self, store: JsonFile, limit: int):
        self._store = store
        self._limit = limit

    @property
    def limit(self) -> int:
        return self._limit

    def used(self) -> int:
        data = self._store.read()
        return data.get("count", 0) if data.get("date") == _today() else 0

    def check(self) -> None:
        if self.used() >= self._limit:
            raise ConnectorError(
                Code.QUOTA_EXHAUSTED,
                "The daily Zoho API quota is used up.",
                hint="Not retryable today. The quota resets daily.",
            )

    def record(self) -> None:
        count = self.used() + 1
        self._store.write({"date": _today(), "count": count})
        if count == int(self._limit * WARN_RATIO):
            log.warning("zoho_quota_warning used=%d limit=%d", count, self._limit)

    def mark_exhausted(self) -> None:
        self._store.write({"date": _today(), "count": self._limit})


def _today() -> str:
    return datetime.now(UTC).date().isoformat()
