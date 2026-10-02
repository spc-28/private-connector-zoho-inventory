import asyncio

from zoho_connector.client.zoho_client import ZohoClient
from zoho_connector.config import Settings
from zoho_connector.errors import ConnectorError
from zoho_connector.evidence import buckets, delivery, rules, summary
from zoho_connector.evidence.rules import DisputeFacts
from zoho_connector.result import ok
from zoho_connector.services.lookup import Corroboration, Match, OrderLookup
from zoho_connector.services.orders import OrderService
from zoho_connector.shaping.money import same_amount
from zoho_connector.shaping.orders import customer, invoice_summary, order_summary
from zoho_connector.shaping.provenance import now_iso, source

MAX_PACKAGE_DETAILS = 3


class EvidenceBuilder:
    """Assembles one graded, source-tagged evidence pack from Zoho records."""

    def __init__(
        self, client: ZohoClient, orders: OrderService, lookup: OrderLookup, settings: Settings
    ):
        self._client = client
        self._orders = orders
        self._lookup = lookup
        self._field = settings.payment_link_field

    async def build(
        self,
        order_id: str | None,
        payment_ref: str | None,
        facts: DisputeFacts,
        corroboration: Corroboration,
    ) -> dict:
        match = await self._resolve(order_id, payment_ref, corroboration)
        so = await self._orders.detail(match.row["salesorder_id"])
        fetched_at = now_iso()
        details, missing = await self._package_details(so.get("packages", []))
        history = await self._history(so, facts.reason, missing)
        return ok(self._pack(so, match, details, history, facts, fetched_at), missing)

    async def _resolve(
        self, order_id: str | None, payment_ref: str | None, corroboration: Corroboration
    ) -> Match:
        if order_id:
            row = {"salesorder_id": order_id}
            return Match(row, "direct_id", "salesorder_id", "high", {})
        return await self._lookup.by_payment(payment_ref, None, corroboration)

    async def _package_details(self, packages: list[dict]) -> tuple[dict, list[str]]:
        shipped = [p for p in packages if p.get("shipment_id")][:MAX_PACKAGE_DETAILS]
        results = await asyncio.gather(
            *(self._client.get(f"/packages/{p['package_id']}") for p in shipped),
            return_exceptions=True,
        )
        details, missing = {}, []
        for package, result in zip(shipped, results, strict=True):
            if isinstance(result, ConnectorError):
                missing.append(f"package:{package['package_id']}")
            elif isinstance(result, BaseException):
                raise result
            else:
                details[package["package_id"]] = result.get("package", {})
        return details, missing

    async def _history(self, so: dict, reason: str, missing: list[str]) -> dict | None:
        if reason not in ("fraud", "duplicate"):
            return None
        try:
            rows = await self._orders.customer_orders(so["customer_id"])
        except ConnectorError:
            missing.append("customer_order_history")
            return None
        others = [row for row in rows if row["salesorder_id"] != so["salesorder_id"]]
        if reason == "fraud":
            prior = [row for row in others if row.get("date", "") < so["date"]]
            fulfilled = [row for row in prior if row.get("status") == "fulfilled"]
            return {"prior_orders": len(prior), "prior_fulfilled_orders": len(fulfilled)}
        same = [row for row in others if same_amount(row.get("total"), so.get("total"))]
        return {"other_orders_same_amount": [self._brief(row) for row in same]}

    def _pack(self, so, match, details, history, facts: DisputeFacts, fetched_at) -> dict:
        order = order_summary(so, self._field, fetched_at)
        invoices = [invoice_summary(invoice) for invoice in so.get("invoices", [])]
        packages = so.get("packages", [])
        shipped = delivery.assess(packages, details, fetched_at)
        found = rules.discrepancies(order, shipped, facts)
        return {
            "match": match.describe(),
            "order": {
                key: order[key]
                for key in (
                    "order_number",
                    "date",
                    "total",
                    "currency",
                    "status",
                    "payment_reference",
                    "source",
                )
            },
            "customer": customer(so),
            "invoices": [
                {**i, "source": source("invoice", i["invoice_id"], fetched_at)} for i in invoices
            ],
            "delivery": shipped,
            "contest_buckets": buckets.contest_buckets(
                facts.reason, invoices, shipped, packages, history
            ),
            "gaps": buckets.gaps(facts.reason, invoices, shipped),
            "discrepancies": found,
            "evidence_readiness": rules.readiness(bool(invoices), shipped, found),
            "summary": summary.draft_summary(order, invoices, shipped, fetched_at),
        }

    @staticmethod
    def _brief(row: dict) -> dict:
        return {
            "order_number": row.get("salesorder_number"),
            "date": row.get("date"),
            "total": row.get("total"),
            "status": row.get("status"),
        }
