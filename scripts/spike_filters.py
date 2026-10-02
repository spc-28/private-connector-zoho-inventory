"""Day-0 spike: probes which Zoho sales-order filters really work. Read-only, about 18 calls."""

import asyncio
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from zoho_connector.client.zoho_client import ZohoClient
from zoho_connector.context import Context
from zoho_connector.errors import Code, ConnectorError

SAMPLE_SIZE = 50
ORDERS = "/salesorders"
DELIVERY_HINTS = ("deliver", "track", "aftership", "carrier", "shipment")

Probe = tuple[str, dict, Callable[[dict], bool]]


async def main() -> None:
    context = Context.create()
    try:
        report = await run(context.client, context.settings.payment_link_field)
    finally:
        await context.client.aclose()
    context.capabilities.save(report)
    print_report(report, context.capabilities.path)


async def run(client: ZohoClient, link_field: str) -> dict:
    baseline, _ = await client.get_page(ORDERS, "salesorders", 1, SAMPLE_SIZE)
    if not baseline:
        sys.exit("No sales orders found. Seed the demo organization first.")
    sample = next((order for order in baseline if order.get(link_field)), baseline[0])
    filters = {}
    for name, params, matches in probes(sample, link_field):
        filters[name] = await verdict(client, baseline, sample["salesorder_id"], params, matches)
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "organization_id": client.organization_id,
        "payment_link_field": link_field,
        "salesorder_filters": filters,
        "sort_by_date_desc": await sort_check(client),
        "per_page_200_accepted": await per_page_check(client),
        "list_row_fields": sorted(sample),
        "package_fields": await package_fields(client, baseline),
        "item_stock_shape": await item_stock_shape(client),
    }


def probes(sample: dict, link_field: str) -> list[Probe]:
    ref = str(sample.get(link_field) or "")
    number = sample.get("salesorder_number")
    customer_id = sample.get("customer_id")
    status = str(sample.get("status") or "")
    date = sample.get("date")
    found: list[Probe] = [
        ("salesorder_number", {"salesorder_number": number}, _equals("salesorder_number", number)),
        ("customer_id", {"customer_id": customer_id}, _equals("customer_id", customer_id)),
        ("filter_by_status", {"filter_by": f"Status.{status.title()}"}, _equals("status", status)),
        ("date_range", {"date_start": date, "date_end": date}, _equals("date", date)),
    ]
    if ref:
        found += [
            (link_field, {link_field: ref}, _equals(link_field, ref)),
            (
                f"{link_field}_startswith",
                {f"{link_field}_startswith": ref[:6]},
                lambda order: str(order.get(link_field, "")).startswith(ref[:6]),
            ),
            (
                "search_text",
                {"search_text": ref},
                lambda order: any(ref in str(value) for value in order.values()),
            ),
        ]
    return found


def _equals(field: str, value) -> Callable[[dict], bool]:
    return lambda order: order.get(field) == value


async def verdict(
    client: ZohoClient, baseline: list[dict], sample_id: str, params: dict, matches
) -> str:
    try:
        rows, _ = await client.get_page(ORDERS, "salesorders", 1, SAMPLE_SIZE, params)
    except ConnectorError as exc:
        if exc.code == Code.INVALID_INPUT:
            return "rejected"
        raise
    if sample_id not in {row["salesorder_id"] for row in rows}:
        return "no_match"
    if all(matches(row) for row in rows):
        narrowed = len(rows) < len(baseline) or not all(matches(row) for row in baseline)
        return "verified" if narrowed else "inconclusive"
    return "ignored" if len(rows) >= len(baseline) else "loose"


async def sort_check(client: ZohoClient) -> str:
    params = {"sort_column": "date", "sort_order": "D"}
    try:
        rows, _ = await client.get_page(ORDERS, "salesorders", 1, SAMPLE_SIZE, params)
    except ConnectorError as exc:
        if exc.code == Code.INVALID_INPUT:
            return "rejected"
        raise
    dates = [row.get("date", "") for row in rows]
    return "verified" if dates == sorted(dates, reverse=True) else "ignored"


async def per_page_check(client: ZohoClient) -> bool:
    try:
        await client.get_page(ORDERS, "salesorders", 1, 200)
    except ConnectorError as exc:
        if exc.code == Code.INVALID_INPUT:
            return False
        raise
    return True


async def package_fields(client: ZohoClient, baseline: list[dict]) -> dict:
    for order in baseline[:4]:
        detail = (await client.get(f"{ORDERS}/{order['salesorder_id']}"))["salesorder"]
        packages = detail.get("packages") or []
        if packages:
            package_id = packages[0]["package_id"]
            package = (await client.get(f"/packages/{package_id}")).get("package", {})
            return {
                "on_salesorder": sorted(packages[0]),
                "package_detail": sorted(package),
                "delivery_related": sorted(
                    key for key in {*packages[0], *package} if any(h in key for h in DELIVERY_HINTS)
                ),
            }
    return {"note": "no packages found in the first four orders"}


async def item_stock_shape(client: ZohoClient) -> str:
    items, _ = await client.get_page("/items", "items", 1, 1)
    if not items:
        return "no items"
    item = (await client.get(f"/items/{items[0]['item_id']}")).get("item", {})
    if "locations" in item:
        return "locations"
    return "warehouses" if "warehouses" in item else "none"


def print_report(report: dict, path) -> None:
    print(f"\nSales-order filters (organization {report['organization_id']}):")
    for name, result in report["salesorder_filters"].items():
        print(f"  {name:32} {result}")
    print(f"  {'sort by date, newest first':32} {report['sort_by_date_desc']}")
    print(f"  {'per_page=200 accepted':32} {report['per_page_200_accepted']}")
    print(f"\nDelivery-related package fields: {report['package_fields'].get('delivery_related')}")
    print(f"Item stock shape: {report['item_stock_shape']}")
    print(f"\nCapability matrix written to {path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConnectorError as exc:
        sys.exit(f"Spike failed: {exc.message} {exc.hint}".strip())
