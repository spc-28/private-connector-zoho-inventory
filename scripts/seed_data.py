"""Creates the fictional food demo data in a Zoho Inventory demo organization.

It uses its own write-scoped Self Client and never imports the connector, which stays read-only.
Safe to re-run: items, customers and orders are matched by SKU, email and Reference# first.
"""

import argparse
import asyncio
import sys
from datetime import datetime

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from seed_demo_data import CUSTOMERS, ITEMS, ORDERS, Order

SCOPES = (
    "ZohoInventory.items.ALL,ZohoInventory.contacts.ALL,ZohoInventory.salesorders.ALL,"
    "ZohoInventory.packages.ALL,ZohoInventory.shipmentorders.ALL,ZohoInventory.settings.READ"
)
STAGES = ("confirmed", "packed", "shipped", "delivered")


class SeedError(Exception):
    pass


class SeedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZOHO_SEED_", env_file=".env", extra="ignore")

    client_id: str = ""
    client_secret: str = ""
    accounts_url: str = "https://accounts.zoho.com"
    org_name: str = ""


class Zoho:
    def __init__(self, http: httpx.AsyncClient, api_domain: str):
        self._http = http
        self._base = f"{api_domain}/inventory/v1"
        self.org_id: str | None = None

    async def call(self, method: str, path: str, *, params=None, json=None) -> dict:
        query = dict(params or {})
        if self.org_id:
            query["organization_id"] = self.org_id
        response = await self._http.request(method, f"{self._base}{path}", params=query, json=json)
        body = response.json() if response.content else {}
        if response.status_code >= 300 or body.get("code", 0) != 0:
            message = body.get("message", "no message")
            raise SeedError(f"{method} {path} failed (HTTP {response.status_code}): {message}")
        return body

    async def list_all(self, path: str, key: str) -> list[dict]:
        rows, page = [], 1
        while True:
            body = await self.call("GET", path, params={"page": page, "per_page": 200})
            rows += body.get(key, [])
            if not body.get("page_context", {}).get("has_more_page"):
                return rows
            page += 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed fictional demo data into a Zoho Inventory demo organization.",
        epilog=f"Generate the Self Client grant code with these scopes:\n{SCOPES}",
    )
    parser.add_argument("--code", required=True, help="Self Client grant code (expires quickly).")
    args = parser.parse_args()
    settings = SeedSettings()
    if not (settings.client_id and settings.client_secret and settings.org_name):
        sys.exit("Set ZOHO_SEED_CLIENT_ID, ZOHO_SEED_CLIENT_SECRET and ZOHO_SEED_ORG_NAME in .env.")
    try:
        asyncio.run(seed(settings, args.code))
    except SeedError as exc:
        sys.exit(f"Seeding stopped: {exc}\nFix the cause and re-run; finished steps are skipped.")


async def seed(settings: SeedSettings, code: str) -> None:
    tokens = await exchange(settings, code)
    try:
        headers = {"Authorization": f"Zoho-oauthtoken {tokens['access_token']}"}
        async with httpx.AsyncClient(headers=headers, timeout=30) as http:
            zoho = Zoho(http, tokens["api_domain"])
            org = await pick_organization(zoho, settings.org_name)
            zoho.org_id = org["organization_id"]
            item_ids = await ensure_items(zoho)
            customer_ids = await ensure_customers(zoho)
            existing = {
                row.get("reference_number"): row["salesorder_id"]
                for row in await zoho.list_all("/salesorders", "salesorders")
            }
            for order in ORDERS:
                await ensure_order(zoho, order, item_ids, customer_ids, existing)
    finally:
        await revoke(settings, tokens.get("refresh_token"))
    print("\nDone. The seed token was revoked.")


async def exchange(settings: SeedSettings, code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=20) as http:
        body = (await http.post(f"{settings.accounts_url}/oauth/v2/token", data=data)).json()
    if "access_token" not in body:
        raise SeedError(f"Zoho rejected the grant code ({body.get('error', 'unknown')}).")
    return body


async def revoke(settings: SeedSettings, refresh_token: str | None) -> None:
    if refresh_token:
        async with httpx.AsyncClient(timeout=20) as http:
            await http.post(
                f"{settings.accounts_url}/oauth/v2/token/revoke", params={"token": refresh_token}
            )


async def pick_organization(zoho: Zoho, name: str) -> dict:
    organizations = (await zoho.call("GET", "/organizations")).get("organizations", [])
    for org in organizations:
        if org["name"] == name:
            return org
    names = ", ".join(org["name"] for org in organizations) or "none"
    raise SeedError(f"No organization is named '{name}'. Available: {names}.")


async def ensure_items(zoho: Zoho) -> dict[str, dict]:
    existing = {row.get("sku"): row for row in await zoho.list_all("/items", "items")}
    items = {}
    for item in ITEMS:
        if item.sku not in existing:
            body = {
                "name": item.name,
                "sku": item.sku,
                "unit": "pcs",
                "item_type": "inventory",
                "product_type": "goods",
                "rate": item.rate,
                "purchase_rate": item.purchase_rate,
                "reorder_level": item.reorder_level,
                "initial_stock": item.stock,
                "initial_stock_rate": item.purchase_rate,
            }
            existing[item.sku] = (await zoho.call("POST", "/items", json=body))["item"]
            _report("created", f"item {item.sku}")
        else:
            _report("exists", f"item {item.sku}")
        items[item.sku] = {"id": existing[item.sku]["item_id"], "rate": item.rate}
    return items


async def ensure_customers(zoho: Zoho) -> dict[str, str]:
    existing = {
        row.get("email"): row["contact_id"] for row in await zoho.list_all("/contacts", "contacts")
    }
    for customer in CUSTOMERS:
        if customer.email in existing:
            _report("exists", f"customer {customer.email}")
            continue
        body = {
            "contact_name": customer.name,
            "contact_type": "customer",
            "billing_address": {"city": customer.city, "state": customer.state, "country": "India"},
            "shipping_address": {
                "city": customer.city,
                "state": customer.state,
                "country": "India",
            },
            "contact_persons": [
                {
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": customer.email,
                    "phone": customer.phone,
                    "is_primary_contact": True,
                }
            ],
        }
        contact = (await zoho.call("POST", "/contacts", json=body))["contact"]
        existing[customer.email] = contact["contact_id"]
        _report("created", f"customer {customer.email}")
    return existing


async def ensure_order(zoho: Zoho, order: Order, items: dict, customers: dict, existing: dict):
    so_id = existing.get(order.reference) or await create_order(zoho, order, items, customers)
    so = (await zoho.call("GET", f"/salesorders/{so_id}"))["salesorder"]
    if so.get("status") == "draft":
        await zoho.call("POST", f"/salesorders/{so_id}/status/confirmed")
    if order.outcome == "void":
        if so.get("status") != "void":
            await zoho.call("POST", f"/salesorders/{so_id}/status/void")
        _report("void", order.reference)
        return
    target = STAGES.index(order.outcome)
    package = (so.get("packages") or [None])[0]
    if target >= 1 and package is None:
        package = await create_package(zoho, so, order)
    shipment_id = package.get("shipment_id") if package else None
    if target >= 2 and not shipment_id:
        shipment_id = await create_shipment(zoho, so_id, package["package_id"], order)
    if target >= 3 and package.get("status") != "delivered":
        await zoho.call("POST", f"/shipmentorders/{shipment_id}/status/delivered")
    _report(order.outcome, f"{order.reference} ({so.get('salesorder_number')})")


async def create_order(zoho: Zoho, order: Order, items: dict, customers: dict) -> str:
    body = {
        "customer_id": customers[order.customer_email],
        "date": order.date,
        "reference_number": order.reference,
        "line_items": [
            {"item_id": items[sku]["id"], "quantity": quantity, "rate": items[sku]["rate"]}
            for sku, quantity in order.lines
        ],
    }
    return (await zoho.call("POST", "/salesorders", json=body))["salesorder"]["salesorder_id"]


async def create_package(zoho: Zoho, so: dict, order: Order) -> dict:
    body = {
        "package_number": f"PKG-{_suffix(order)}",
        "date": _today(),
        "line_items": [
            {"so_line_item_id": line["line_item_id"], "quantity": line["quantity"]}
            for line in so["line_items"]
        ],
    }
    params = {"salesorder_id": so["salesorder_id"]}
    return (await zoho.call("POST", "/packages", params=params, json=body))["package"]


async def create_shipment(zoho: Zoho, so_id: str, package_id: str, order: Order) -> str:
    body = {
        "shipment_number": f"SHP-{_suffix(order)}",
        "date": _today(),
        "delivery_method": order.carrier,
        "tracking_number": order.tracking,
    }
    params = {"package_ids": package_id, "salesorder_id": so_id}
    shipment = await zoho.call("POST", "/shipmentorders", params=params, json=body)
    return shipment["shipmentorder"]["shipment_id"]


def _suffix(order: Order) -> str:
    return order.reference.removeprefix("pay_")


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _report(status: str, what: str) -> None:
    print(f"  {status:10} {what}")


if __name__ == "__main__":
    main()
