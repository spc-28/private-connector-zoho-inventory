from zoho_connector.shaping.provenance import source

DELIVERY_NOTE = (
    "Zoho holds a delivery status, not a carrier-confirmed delivery date. "
    "status_recorded_on is when the status was recorded in Zoho."
)


def assess(packages: list[dict], details: dict[str, dict], fetched_at: str) -> dict:
    """Grades how strongly Zoho's records show the order reached the customer."""
    shipped = [package for package in packages if package.get("shipment_id")]
    if not shipped:
        return {
            "status": "packed_not_shipped" if packages else "no_package",
            "strength": "absent",
            "delivered_on": None,
            "note": DELIVERY_NOTE,
        }
    package = max(shipped, key=_rank)
    shipment = (details.get(package["package_id"]) or package).get("shipment_order") or {}
    delivered = _delivered(package)
    tracking = package.get("tracking_number") or None
    return {
        "status": "delivered" if delivered else "shipped",
        "strength": _strength(delivered, tracking),
        "delivered_on": None,
        "status_basis": "tracking_integration" if _integrated(shipment) else "manual_status_update",
        "status_recorded_on": _recorded_on(shipment) if delivered else None,
        "shipped_on": package.get("shipment_date") or None,
        "carrier": package.get("carrier") or None,
        "tracking_number": tracking,
        "package_id": package["package_id"],
        "shipment_id": package["shipment_id"],
        "note": DELIVERY_NOTE,
        "source": source("package", package["package_id"], fetched_at),
    }


def _delivered(package: dict) -> bool:
    return "delivered" in (package.get("status"), package.get("shipment_status"))


def _rank(package: dict) -> tuple[bool, bool]:
    return _delivered(package), bool(package.get("tracking_number"))


def _strength(delivered: bool, tracking: str | None) -> str:
    if delivered:
        return "tracked_shipment" if tracking else "status_only"
    return "shipped_not_delivered"


def _integrated(shipment: dict) -> bool:
    return bool(shipment.get("is_tracking_enabled") or shipment.get("is_carrier_shipment"))


def _recorded_on(shipment: dict) -> str | None:
    for status in shipment.get("tracking_statuses") or []:
        if str(status.get("current_tracking_status", "")).lower() == "delivered":
            return status.get("date") or None
    return None
