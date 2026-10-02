from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from zoho_connector.context import Context
from zoho_connector.evidence.rules import DisputeFacts
from zoho_connector.result import ok
from zoho_connector.services.lookup import Corroboration
from zoho_connector.shaping import inputs
from zoho_connector.shaping.money import to_major
from zoho_connector.tools.guard import READ_ONLY, guarded

Reason = Literal["not_received", "fraud", "duplicate", "unknown"]


def register(server: MCPServer, context: Context) -> None:
    @server.tool(annotations=READ_ONLY)
    @guarded
    async def get_dispute_evidence(
        reason_category: Annotated[
            Reason,
            Field(description="Map the Razorpay dispute reason to one of these categories."),
        ],
        order_id: Annotated[str | None, Field(description="Zoho sales order ID.")] = None,
        payment_ref: Annotated[str | None, Field(description="Razorpay payment ID.")] = None,
        disputed_amount: Annotated[
            int | None, Field(description="Disputed amount in paise, as Razorpay gives it.")
        ] = None,
        currency: Annotated[str, Field(description="Razorpay currency code.")] = "INR",
        payment_date: Annotated[str | None, Field(description="Payment date, YYYY-MM-DD.")] = None,
        dispute_date: Annotated[
            str | None, Field(description="Date the dispute was raised, YYYY-MM-DD.")
        ] = None,
    ) -> dict:
        """Read-only. Build a graded, source-tagged evidence pack for a Razorpay dispute in one call.

        Pass exactly one of order_id or payment_ref. Returns facts and document IDs sorted into
        Razorpay contest buckets, gaps to fill from other systems, discrepancies that undercut
        the case, an evidence_readiness level, and a draft summary under 1000 characters.
        Readiness is not a decision to contest: a person or the Dispute Responder decides.
        Delivery is a Zoho status, never a carrier-confirmed delivery date. This tool never
        contacts Razorpay.
        """
        inputs.exactly_one(order_id=order_id, payment_ref=payment_ref)
        if order_id:
            inputs.record_id(order_id, "order_id")
        disputed = to_major(disputed_amount, currency) if disputed_amount is not None else None
        facts = DisputeFacts(
            reason_category, disputed, inputs.parse_date(dispute_date, "dispute_date")
        )
        corroboration = Corroboration(disputed, inputs.parse_date(payment_date, "payment_date"))
        return await context.evidence.build(order_id, payment_ref, facts, corroboration)

    @server.tool(annotations=READ_ONLY)
    @guarded
    async def get_evidence_document(
        document_type: Literal["invoice", "package_slip"],
        record_id: Annotated[
            str,
            Field(description="invoice_id or package_id from get_dispute_evidence's buckets."),
        ],
    ) -> dict:
        """Read-only. Save an invoice or package slip as a PDF for upload to Razorpay.

        Returns the local file path, SHA-256 hash and size, never the contents. The file holds
        unmasked customer details: hand the path to the uploader, do not read it into the chat.
        Files are deleted after the retention period.
        """
        exported = await context.documents.export(
            document_type, inputs.record_id(record_id, "record_id")
        )
        return ok(exported)
