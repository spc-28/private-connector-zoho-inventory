import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from zoho_connector.capabilities import Capabilities
from zoho_connector.client.zoho_client import ZohoClient
from zoho_connector.config import Settings
from zoho_connector.errors import Code, ConnectorError

ORDERS = "/salesorders"
SCAN_PAGE_SIZE = 200
DETAIL_TTL_SECONDS = 60

Check = Callable[[dict], bool]


@dataclass
class OrderFilters:
    query: str | None = None
    status: str | None = None
    customer_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None


@dataclass
class OrderPage:
    rows: list[dict]
    has_more: bool
    filtered_locally: list[str]


class OrderService:
    """Reads sales orders, using only server-side filters the spike verified."""

    def __init__(self, client: ZohoClient, capabilities: Capabilities, settings: Settings):
        self._client = client
        self._capabilities = capabilities
        self._settings = settings
        self._details: dict[str, tuple[float, dict]] = {}

    async def search(self, filters: OrderFilters, page: int, per_page: int) -> OrderPage:
        params, checks = self._plan(filters)
        rows, has_more = await self._page(params, page, per_page)
        rows = [row for row in rows if all(check(row) for _, check in checks)]
        return OrderPage(rows, has_more, [name for name, _ in checks])

    async def scan(self, params: dict, match: Check) -> tuple[list[dict], bool]:
        """Pages through orders up to the scan cap. Returns matches and whether the scan finished."""
        found = []
        for page in range(1, self._settings.scan_cap + 1):
            rows, has_more = await self._page(params, page, SCAN_PAGE_SIZE)
            found += [row for row in rows if match(row)]
            if not has_more:
                return found, True
        return found, False

    async def detail(self, order_id: str) -> dict:
        cached = self._details.get(order_id)
        if cached and time.monotonic() - cached[0] < DETAIL_TTL_SECONDS:
            return cached[1]
        so = (await self._client.get(f"{ORDERS}/{order_id}"))["salesorder"]
        self._details[order_id] = (time.monotonic(), so)
        return so

    async def by_number(self, number: str) -> dict | None:
        params = {"salesorder_number": number} if self._verified("salesorder_number") else {}
        rows, finished = await self.scan(params, lambda row: row.get("salesorder_number") == number)
        if rows:
            return rows[0]
        if not finished:
            raise search_incomplete(self._settings.scan_cap * SCAN_PAGE_SIZE)
        return None

    async def customer_ids(self, email: str) -> list[str]:
        body = await self._client.get("/contacts", {"email": email})
        return [contact["contact_id"] for contact in body.get("contacts", [])]

    async def customer_orders(self, customer_id: str) -> list[dict]:
        if self._verified("customer_id"):
            rows, _ = await self._page({"customer_id": customer_id}, 1, SCAN_PAGE_SIZE)
            return rows
        rows, _ = await self.scan({}, lambda row: row.get("customer_id") == customer_id)
        return rows

    async def _page(self, params: dict, page: int, per_page: int) -> tuple[list[dict], bool]:
        query = dict(params)
        if self._capabilities.sort_by_date():
            query |= {"sort_column": "date", "sort_order": "D"}
        return await self._client.get_page(ORDERS, "salesorders", page, per_page, query)

    def _plan(self, filters: OrderFilters) -> tuple[dict, list[tuple[str, Check]]]:
        params: dict = {}
        checks: list[tuple[str, Check]] = []

        def use(capability: str, server: dict, local: Check) -> None:
            if self._verified(capability):
                params.update(server)
            else:
                checks.append((capability, local))

        if filters.query:
            needle = filters.query.lower()
            use("search_text", {"search_text": filters.query}, lambda r: needle in _text(r))
        if filters.customer_id:
            cid = filters.customer_id
            use("customer_id", {"customer_id": cid}, lambda r: r.get("customer_id") == cid)
        if filters.date_from or filters.date_to:
            low, high = filters.date_from or "0000", filters.date_to or "9999"
            server = {"date_start": filters.date_from, "date_end": filters.date_to}
            server = {key: value for key, value in server.items() if value}
            use("date_range", server, lambda r: low <= r.get("date", "") <= high)
        if filters.status:
            wanted = filters.status
            checks.append(("status", lambda r: wanted in _statuses(r)))
        return params, checks

    def _verified(self, capability: str) -> bool:
        return self._capabilities.verified(capability)


def _text(row: dict) -> str:
    return json.dumps(row).lower()


def _statuses(row: dict) -> set[str]:
    return {row.get("status"), row.get("order_status"), row.get("shipped_status")}


def search_incomplete(covered: int) -> ConnectorError:
    return ConnectorError(
        Code.SEARCH_INCOMPLETE,
        f"Searched the {covered} most recent orders without finishing.",
        hint="Supply the Zoho order number or a narrower filter.",
    )
