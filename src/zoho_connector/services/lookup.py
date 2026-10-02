from dataclasses import dataclass
from datetime import date

from zoho_connector.capabilities import Capabilities
from zoho_connector.config import Settings
from zoho_connector.errors import Code, ConnectorError
from zoho_connector.services.orders import SCAN_PAGE_SIZE, OrderService, search_incomplete
from zoho_connector.shaping.money import same_amount
from zoho_connector.shaping.orders import order_summary
from zoho_connector.shaping.provenance import now_iso

DATE_TOLERANCE_DAYS = 2


@dataclass
class Corroboration:
    amount: float | None = None
    payment_date: date | None = None

    def check(self, row: dict) -> dict:
        result = {}
        if self.amount is not None:
            result["amount"] = "match" if same_amount(row.get("total"), self.amount) else "mismatch"
        if self.payment_date is not None:
            gap = abs((date.fromisoformat(row["date"]) - self.payment_date).days)
            result["date"] = "match" if gap <= DATE_TOLERANCE_DAYS else "mismatch"
        return result


@dataclass
class Match:
    row: dict
    strategy: str
    matched_on: str
    confidence: str
    corroboration: dict

    def describe(self) -> dict:
        return {
            "strategy": self.strategy,
            "matched_on": self.matched_on,
            "confidence": self.confidence,
            "corroboration": self.corroboration,
        }


class OrderLookup:
    """Finds the Zoho order behind a Razorpay payment, trying the cheapest reliable route first."""

    def __init__(self, orders: OrderService, capabilities: Capabilities, settings: Settings):
        self._orders = orders
        self._capabilities = capabilities
        self._field = settings.payment_link_field
        self._scan_limit = settings.scan_cap * SCAN_PAGE_SIZE

    async def by_payment(
        self, payment_ref: str, receipt: str | None, corroboration: Corroboration
    ) -> Match:
        if receipt and (row := await self._orders.by_number(receipt)):
            return self._decide([row], "receipt_order_number", "salesorder_number", corroboration)
        rows, strategy, finished = await self._candidates(payment_ref)
        if not rows:
            if not finished:
                raise search_incomplete(self._scan_limit)
            raise ConnectorError(
                Code.NOT_FOUND,
                "No Zoho order carries this payment reference.",
                hint="Try search_orders with the customer's email or the order date.",
            )
        return self._decide(rows, strategy, self._field, corroboration)

    async def _candidates(self, payment_ref: str) -> tuple[list[dict], str, bool]:
        exact = lambda row: row.get(self._field) == payment_ref
        if self._capabilities.verified(self._field):
            rows, finished = await self._orders.scan({self._field: payment_ref}, exact)
            return rows, "exact_filter", finished
        if self._capabilities.verified("search_text"):
            rows, finished = await self._orders.scan({"search_text": payment_ref}, exact)
            return rows, "text_search", finished
        rows, finished = await self._orders.scan({}, exact)
        return rows, "bounded_scan", finished

    def _decide(
        self, rows: list[dict], strategy: str, matched_on: str, corroboration: Corroboration
    ) -> Match:
        if len(rows) == 1:
            return Match(rows[0], strategy, matched_on, "high", corroboration.check(rows[0]))
        agreeing = [row for row in rows if "mismatch" not in corroboration.check(row).values()]
        if len(agreeing) == 1 and (corroboration.amount or corroboration.payment_date):
            row = agreeing[0]
            return Match(row, strategy, matched_on, "medium", corroboration.check(row))
        fetched_at = now_iso()
        raise ConnectorError(
            Code.AMBIGUOUS_MATCH,
            f"{len(rows)} orders carry this payment reference.",
            hint="Ask a person to choose, or pass amount and payment_date to narrow it down.",
            details={"candidates": [order_summary(r, self._field, fetched_at) for r in rows]},
        )
