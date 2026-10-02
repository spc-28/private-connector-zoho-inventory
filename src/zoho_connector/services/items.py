from dataclasses import dataclass

from zoho_connector.client.zoho_client import ZohoClient
from zoho_connector.config import Settings
from zoho_connector.services.orders import SCAN_PAGE_SIZE, search_incomplete


@dataclass
class ItemFilters:
    query: str | None = None
    sku: str | None = None
    low_stock_only: bool = False


class ItemService:
    """Reads items and stock. Filters locally, because Zoho's item filters are unverified."""

    def __init__(self, client: ZohoClient, settings: Settings):
        self._client = client
        self._scan_cap = settings.scan_cap
        self._locations: list[dict] | None = None

    async def find(self, filters: ItemFilters) -> list[dict]:
        rows = await self._all()
        return [row for row in rows if _matches(row, filters)]

    async def detail(self, item_id: str) -> dict:
        return (await self._client.get(f"/items/{item_id}")).get("item", {})

    async def locations(self) -> list[dict]:
        if self._locations is None:
            body = await self._client.get("/locations")
            self._locations = body.get("locations", [])
        return self._locations

    async def _all(self) -> list[dict]:
        rows = []
        for page in range(1, self._scan_cap + 1):
            batch, has_more = await self._client.get_page("/items", "items", page, SCAN_PAGE_SIZE)
            rows += batch
            if not has_more:
                return rows
        raise search_incomplete(self._scan_cap * SCAN_PAGE_SIZE)


def is_low_stock(row: dict) -> bool:
    level = row.get("reorder_level")
    if level in (None, ""):
        return False
    return float(row.get("stock_on_hand") or 0) <= float(level)


def _matches(row: dict, filters: ItemFilters) -> bool:
    if filters.sku and str(row.get("sku", "")).lower() != filters.sku.lower():
        return False
    if filters.query:
        needle = filters.query.lower()
        if needle not in f"{row.get('name', '')} {row.get('sku', '')}".lower():
            return False
    return not filters.low_stock_only or is_low_stock(row)
