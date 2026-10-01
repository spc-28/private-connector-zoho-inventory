from mcp.server.mcpserver import MCPServer

from zoho_connector.context import Context
from zoho_connector.errors import Code, ConnectorError
from zoho_connector.result import ok
from zoho_connector.tools.guard import READ_ONLY, guarded


def register(server: MCPServer, context: Context) -> None:
    @server.tool(annotations=READ_ONLY)
    @guarded
    async def connector_status() -> dict:
        """Read-only. Check the connector's health before other work.

        Returns whether Zoho access is authorized, the selected organization, the data center,
        Zoho calls used today against the daily limit, and which order-lookup strategies the
        day-0 spike verified. Costs at most one Zoho call. Call it first in a session or after
        an AUTH_REQUIRED, CONFIG_REQUIRED or QUOTA_EXHAUSTED error.
        """
        return ok(
            {
                "read_only": True,
                "authorized": await _authorized(context),
                "organization": context.organization.read() or None,
                "data_center": context.tokens.api_domain if context.tokens.authorized else None,
                "zoho_calls_today": context.quota.used(),
                "daily_limit": context.quota.limit,
                "verified_lookups": _verified_lookups(context),
            }
        )


async def _authorized(context: Context) -> bool:
    if not context.client.organization_id:
        return context.tokens.authorized
    try:
        await context.client.get(f"/organizations/{context.client.organization_id}")
    except ConnectorError as exc:
        if exc.code in (Code.AUTH_REQUIRED, Code.FORBIDDEN_SCOPE):
            return False
        raise
    return True


def _verified_lookups(context: Context) -> list[str] | str:
    filters = context.capabilities.read().get("salesorder_filters")
    if filters is None:
        return "spike not run"
    return sorted(name for name, verdict in filters.items() if verdict == "verified")
