from dataclasses import dataclass
from datetime import date

from zoho_connector.shaping.money import same_amount

CONTRADICTING = {"D2_ORDER_CANCELLED", "D3_SHIPPED_AFTER_DISPUTE", "D4_NO_SHIPMENT"}
CANCELLED = {"void", "cancelled"}


@dataclass
class DisputeFacts:
    reason: str
    disputed_amount: float | None = None
    dispute_date: date | None = None


def discrepancies(order: dict, delivery: dict, facts: DisputeFacts) -> list[dict]:
    found = []
    if facts.disputed_amount is not None and not same_amount(order["total"], facts.disputed_amount):
        found.append(
            _rule(
                "D1_AMOUNT_MISMATCH",
                f"Disputed amount {facts.disputed_amount:.2f} differs from order total "
                f"{float(order['total']):.2f}.",
            )
        )
    if order.get("status") in CANCELLED:
        found.append(_rule("D2_ORDER_CANCELLED", f"The order status is {order['status']}."))
    shipped_on = delivery.get("shipped_on")
    if facts.dispute_date and shipped_on and date.fromisoformat(shipped_on) > facts.dispute_date:
        found.append(
            _rule("D3_SHIPPED_AFTER_DISPUTE", f"Shipped on {shipped_on}, after the dispute date.")
        )
    if facts.reason == "not_received" and delivery["strength"] == "absent":
        found.append(_rule("D4_NO_SHIPMENT", "No shipment is recorded for this order."))
    return found


def readiness(has_invoice: bool, delivery: dict, found: list[dict]) -> dict:
    fired = [item["rule"] for item in found]
    supporting = []
    if has_invoice:
        supporting.append("R1_INVOICE_PRESENT")
    if delivery["strength"] == "tracked_shipment":
        supporting.append("R2_TRACKED_SHIPMENT")
    return {"level": _level(has_invoice, delivery, fired), "rules_fired": supporting + fired}


def _level(has_invoice: bool, delivery: dict, fired: list[str]) -> str:
    if CONTRADICTING.intersection(fired):
        return "contradicting"
    shipment_exists = delivery["strength"] != "absent"
    if has_invoice and delivery["strength"] == "tracked_shipment":
        return "partial" if fired else "strong"
    if has_invoice and shipment_exists:
        return "partial"
    return "weak"


def _rule(rule: str, detail: str) -> dict:
    return {"rule": rule, "detail": detail}
