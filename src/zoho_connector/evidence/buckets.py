"""Maps a dispute reason to Razorpay's contest buckets and to evidence Zoho cannot supply."""

ELSEWHERE = "source elsewhere"

EXTERNAL_EVIDENCE = {
    "not_received": ("customer_communication", "refund_cancellation_policy"),
    "fraud": ("access_activity_log", "customer_communication"),
    "duplicate": ("customer_communication",),
    "unknown": ("customer_communication", "term_and_conditions"),
}

BUCKETS = {
    "not_received": ("billing_proof", "shipping_proof"),
    "fraud": ("shipping_proof", "others"),
    "duplicate": ("billing_proof",),
    "unknown": ("billing_proof", "shipping_proof"),
}


def contest_buckets(
    reason: str, invoices: list[dict], delivery: dict, packages: list[dict], history: dict | None
) -> dict:
    available = {
        "billing_proof": {
            "documents": [{"document_type": "invoice", "id": i["invoice_id"]} for i in invoices],
        },
        "shipping_proof": {
            "documents": [
                {"document_type": "package_slip", "id": p["package_id"]}
                for p in packages
                if p.get("shipment_id")
            ],
            "facts": {
                key: delivery.get(key)
                for key in ("status", "strength", "shipped_on", "carrier", "tracking_number")
            },
        },
        "others": [{"type": "customer_order_history", "facts": history}] if history else [],
    }
    return {bucket: available[bucket] for bucket in BUCKETS[reason]}


def gaps(reason: str, invoices: list[dict], delivery: dict) -> list[dict]:
    found = []
    if not invoices:
        found.append({"item": "invoice", "how": "no invoice is linked to this order in Zoho"})
    if delivery["strength"] == "absent":
        found.append({"item": "shipment", "how": "no shipment is recorded in Zoho"})
    else:
        if not delivery.get("tracking_number"):
            found.append({"item": "tracking_number", "how": "add it to the shipment in Zoho"})
        found.append(
            {
                "item": "carrier_proof_of_delivery",
                "how": "not available from Zoho; obtain it with the tracking number",
            }
        )
    found += [{"item": item, "how": ELSEWHERE} for item in EXTERNAL_EVIDENCE[reason]]
    return found
