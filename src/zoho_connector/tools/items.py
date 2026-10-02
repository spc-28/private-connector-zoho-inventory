from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from zoho_connector.context import Context
from zoho_connector.result import ok
from zoho_connector.services.items import ItemFilters, is_low_stock
from zoho_connector.shaping import inputs
from zoho_connector.shaping.provenance import now_iso, source
from zoho_connector.tools.guard import READ_ONLY, guarded

MAX_LOCATION_DETAILS = 5


def register(server: MCPServer, context: Context) -> None:
    @server.tool(annotations=READ_ONLY)
    @guarded
    async def search_items(
        query: Annotated[str | None, Field(description="Part of the item name or SKU.")] = None,
        sku: Annotated[str | None, Field(description="Exact SKU.")] = None,
        location: Annotated[
            str | None, Field(description="Location name to show stock for, e.g. Jaipur.")
        ] = None,
        low_stock_only: Annotated[
            bool, Field(description="Only items at or below their reorder level.")
        ] = False,
        limit: Annotated[int, Field(ge=1, le=50, description="Results per page, 1 to 50.")] = 10,
        cursor: Annotated[
            str | None, Field(description="next_cursor from a previous call.")
        ] = None,
    ) -> dict:
        """Read-only. Find products and their stock: on hand, available, and reorder level.

        Use it for "how many units of SKU X do we have" or "which items need reordering"
        (set low_stock_only). Pass location to see stock at one location.
        """
        offset = inputs.decode_cursor(cursor).get("o", 0)
        rows = await context.items.find(ItemFilters(query, sku, low_stock_only))
        page = rows[offset : offset + limit]
        fetched_at = now_iso()
        items = [_item(row, fetched_at) for row in page]
        if location:
            await _add_location_stock(context, items, location)
        has_more = offset + limit < len(rows)
        return ok(
            {
                "items": items,
                "next_cursor": inputs.encode_cursor({"o": offset + limit}) if has_more else None,
            }
        )


def _item(row: dict, fetched_at: str) -> dict:
    level = row.get("reorder_level")
    return {
        "item_id": row["item_id"],
        "name": row.get("name"),
        "sku": row.get("sku") or None,
        "unit": row.get("unit") or None,
        "stock_on_hand": row.get("stock_on_hand"),
        "available_stock": row.get("available_stock"),
        "reorder_level": level if level not in ("", None) else None,
        "below_reorder_level": is_low_stock(row),
        "source": source("item", row["item_id"], fetched_at),
    }


async def _add_location_stock(context: Context, items: list[dict], location: str) -> None:
    wanted = location.lower()
    known = await context.items.locations()
    for item in items[:MAX_LOCATION_DETAILS]:
        detail = await context.items.detail(item["item_id"])
        per_location = [
            entry
            for entry in detail.get("locations") or []
            if str(entry.get("location_name", "")).lower() == wanted
        ]
        if per_location:
            entry = per_location[0]
            item["location_stock"] = {
                "location": entry.get("location_name"),
                "stock_on_hand": entry.get("location_stock_on_hand"),
                "available_stock": entry.get("location_available_stock"),
            }
        elif len(known) == 1 and str(known[0].get("location_name", "")).lower() == wanted:
            item["location_stock"] = {
                "location": known[0]["location_name"],
                "stock_on_hand": item["stock_on_hand"],
                "available_stock": item["available_stock"],
                "note": "This organization has one location, so all stock is held there.",
            }
        else:
            names = [entry.get("location_name") for entry in known]
            item["location_stock"] = {"location": None, "note": f"Known locations: {names}"}
