"""Builds the draft contest summary from typed fields only. No free text from Zoho."""

from zoho_connector.shaping.privacy import safe_label

MAX_CHARS = 1000


def draft_summary(order: dict, invoices: list[dict], delivery: dict, fetched_at: str) -> str:
    amount = f"{order['currency']} {float(order['total']):.2f}"
    parts = [f"Order {order['order_number']} dated {order['date']} for {amount}."]
    numbers = [i["invoice_number"] for i in invoices if safe_label(i.get("invoice_number"))]
    parts.append(f"Invoiced as {', '.join(numbers)}." if numbers else "No invoice is recorded.")
    parts.append(_shipping(delivery, fetched_at[:10]))
    return " ".join(parts)[:MAX_CHARS]


def _shipping(delivery: dict, as_of: str) -> str:
    if delivery["strength"] == "absent":
        return "No shipment is recorded."
    text = "Shipped"
    if delivery.get("shipped_on"):
        text += f" on {delivery['shipped_on']}"
    if carrier := safe_label(delivery.get("carrier")):
        text += f" via {carrier}"
    if tracking := safe_label(delivery.get("tracking_number")):
        text += f", tracking {tracking}"
    text += "."
    if delivery["status"] == "delivered":
        text += f" Zoho status is delivered as of {as_of}."
    return text
