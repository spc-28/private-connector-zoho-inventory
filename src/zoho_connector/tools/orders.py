from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from zoho_connector.context import Context
from zoho_connector.errors import Code, ConnectorError
from zoho_connector.result import ok
from zoho_connector.services.lookup import Corroboration
from zoho_connector.services.orders import OrderFilters
from zoho_connector.shaping import inputs
from zoho_connector.shaping.money import to_major
from zoho_connector.shaping.orders import order_detail, order_summary
from zoho_connector.shaping.provenance import now_iso
from zoho_connector.tools.guard import READ_ONLY, guarded

Status = Literal["draft", "confirmed", "shipped", "fulfilled", "void", "closed"]
Limit = Annotated[int, Field(ge=1, le=50, description="Results per page, 1 to 50.")]
INCOMPLETE_NOTE = (
    "Some filters run inside the connector, and the scan stopped at its cap before reaching "
    "the oldest orders. Narrow the search with dates or a customer email to see older orders."
)


def register(server: MCPServer, context: Context) -> None:
    field = context.settings.payment_link_field

    @server.tool(annotations=READ_ONLY)
    @guarded
    async def search_orders(
        query: Annotated[str | None, Field(description="Text to search for.")] = None,
        status: Status | None = None,
        customer_email: Annotated[
            str | None, Field(description="Exact customer email, e.g. from Razorpay.")
        ] = None,
        date_from: Annotated[
            str | None, Field(description="Earliest order date, YYYY-MM-DD.")
        ] = None,
        date_to: Annotated[str | None, Field(description="Latest order date, YYYY-MM-DD.")] = None,
        limit: Limit = 10,
        cursor: Annotated[
            str | None, Field(description="next_cursor from a previous call.")
        ] = None,
    ) -> dict:
        """Read-only. Find Zoho sales orders, newest first, including one customer's history.

        Use it to answer "where is my order", "show this customer's orders" or to browse by
        status or date. Do not use it to link a Razorpay payment to an order; use
        find_order_by_payment for that. Customer details in results are masked.
        """
        inputs.parse_date(date_from, "date_from")
        inputs.parse_date(date_to, "date_to")
        customer_id = await _customer_id(context, customer_email) if customer_email else None
        filters = OrderFilters(query, status, customer_id, date_from, date_to)
        result = await context.orders.search(filters, inputs.decode_cursor(cursor), limit)
        fetched_at = now_iso()
        next_state = result.next_state
        data = {
            "orders": [order_summary(row, field, fetched_at) for row in result.rows],
            "next_cursor": inputs.encode_cursor(next_state) if next_state else None,
        }
        if result.filtered_locally:
            data["filtered_locally"] = result.filtered_locally
        if not result.scan_finished:
            data["note"] = INCOMPLETE_NOTE
        return ok(data)

    @server.tool(annotations=READ_ONLY)
    @guarded
    async def get_order(
        order_id: Annotated[str | None, Field(description="Zoho sales order ID.")] = None,
        order_number: Annotated[
            str | None, Field(description="Order number, e.g. SO-00042.")
        ] = None,
    ) -> dict:
        """Read-only. Full detail of one sales order: line items, totals, status, invoices,
        packages and shipments. Pass exactly one of order_id or order_number.

        For dispute evidence use get_dispute_evidence instead; it grades the evidence.
        """
        inputs.exactly_one(order_id=order_id, order_number=order_number)
        if order_number:
            row = await context.orders.by_number(order_number)
            if row is None:
                raise ConnectorError(
                    Code.NOT_FOUND,
                    f"No order is numbered {order_number}.",
                    hint="Check the number, or use search_orders.",
                )
            order_id = row["salesorder_id"]
        so = await context.orders.detail(inputs.record_id(order_id, "order_id"))
        return ok(order_detail(so, field, now_iso()))

    @server.tool(annotations=READ_ONLY)
    @guarded
    async def find_order_by_payment(
        payment_ref: Annotated[str, Field(description="Razorpay payment ID, e.g. pay_XXXX.")],
        receipt: Annotated[
            str | None, Field(description="Razorpay Order receipt, if it holds the order number.")
        ] = None,
        amount: Annotated[
            int | None, Field(description="Payment amount in paise, exactly as Razorpay gives it.")
        ] = None,
        currency: Annotated[str, Field(description="Razorpay currency code.")] = "INR",
        payment_date: Annotated[str | None, Field(description="Payment date, YYYY-MM-DD.")] = None,
    ) -> dict:
        """Read-only. Link a Razorpay payment to the Zoho sales order it paid for.

        Returns the order plus a match object saying how it was found and how confident the
        link is. Pass amount and payment_date when you have them; they settle ambiguous cases.
        If several orders match, it returns AMBIGUOUS_MATCH with candidates: ask a person to
        choose, never guess.
        """
        corroboration = Corroboration(
            to_major(amount, currency) if amount is not None else None,
            inputs.parse_date(payment_date, "payment_date"),
        )
        match = await context.lookup.by_payment(payment_ref, receipt, corroboration)
        order = order_summary(match.row, field, now_iso())
        return ok({"match": match.describe(), "order": order})


async def _customer_id(context: Context, email: str) -> str:
    ids = await context.orders.customer_ids(email)
    if not ids:
        raise ConnectorError(
            Code.NOT_FOUND,
            "No Zoho customer has this email.",
            hint="Check the email, or search by name with the query input.",
        )
    if len(ids) > 1:
        raise ConnectorError(
            Code.AMBIGUOUS_MATCH,
            f"{len(ids)} Zoho customers share this email.",
            hint="Ask a person which customer is meant.",
        )
    return ids[0]
