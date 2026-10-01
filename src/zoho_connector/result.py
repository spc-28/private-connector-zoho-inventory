from typing import Any

from zoho_connector.errors import ConnectorError


def ok(data: Any, missing: list[str] | None = None) -> dict:
    result = {"ok": True, "data": data}
    if missing:
        result |= {"partial": True, "missing": missing}
    return result


def fail(error: ConnectorError) -> dict:
    return {"ok": False, "error": error.to_dict()}
