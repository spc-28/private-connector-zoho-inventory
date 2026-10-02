from zoho_connector.shaping.privacy import mask_email, mask_phone, untrusted
from zoho_connector.shaping.provenance import source


def order_summary(row: dict, link_field: str, fetched_at: str) -> dict:
    return {
        "order_id": row["salesorder_id"],
        "order_number": row.get("salesorder_number"),
        "date": row.get("date"),
        "status": row.get("status"),
        "shipped_status": row.get("shipped_status") or None,
        "invoiced_status": row.get("invoiced_status") or None,
        "total": row.get("total"),
        "currency": row.get("currency_code"),
        "payment_reference": row.get(link_field) or None,
        "customer": {
            "name": untrusted(row.get("customer_name")),
            "email": mask_email(row.get("email")),
        },
        "source": source("salesorder", row["salesorder_id"], fetched_at),
    }


def order_detail(so: dict, link_field: str, fetched_at: str) -> dict:
    return {
        **order_summary(so, link_field, fetched_at),
        "customer": customer(so),
        "line_items": [
            {
                "name": line.get("name"),
                "sku": line.get("sku") or None,
                "quantity": line.get("quantity"),
                "rate": line.get("rate"),
                "total": line.get("item_total"),
            }
            for line in so.get("line_items", [])
        ],
        "invoices": [invoice_summary(invoice) for invoice in so.get("invoices", [])],
        "packages": [package_summary(package) for package in so.get("packages", [])],
    }


def customer(so: dict) -> dict:
    person = (so.get("contact_person_details") or [{}])[0]
    address = so.get("shipping_address") or so.get("billing_address") or {}
    return {
        "name": untrusted(so.get("customer_name")),
        "email": mask_email(person.get("email") or so.get("email")),
        "phone": mask_phone(person.get("mobile") or person.get("phone")),
        "city": address.get("city") or None,
        "state": address.get("state") or None,
        "pin": address.get("zip") or None,
    }


def invoice_summary(invoice: dict) -> dict:
    return {
        "invoice_id": invoice.get("invoice_id"),
        "invoice_number": invoice.get("invoice_number"),
        "status": invoice.get("status"),
        "date": invoice.get("date"),
        "total": invoice.get("total"),
    }


def package_summary(package: dict) -> dict:
    return {
        "package_id": package.get("package_id"),
        "package_number": package.get("package_number"),
        "status": package.get("status"),
        "shipment_id": package.get("shipment_id") or None,
        "carrier": package.get("carrier") or None,
        "tracking_number": package.get("tracking_number") or None,
        "shipment_date": package.get("shipment_date") or None,
    }
