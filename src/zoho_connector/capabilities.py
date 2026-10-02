from zoho_connector.store import JsonFile


class Capabilities:
    """What the day-0 spike proved about this organization's Zoho filters."""

    def __init__(self, store: JsonFile):
        self._store = store

    def verified(self, name: str) -> bool:
        return self._filters().get(name) == "verified"

    def sort_by_date(self) -> bool:
        return self._store.read().get("sort_by_date_desc") == "verified"

    def verified_names(self) -> list[str] | None:
        filters = self._store.read().get("salesorder_filters")
        if filters is None:
            return None
        return sorted(name for name, verdict in filters.items() if verdict == "verified")

    def _filters(self) -> dict:
        return self._store.read().get("salesorder_filters", {})
