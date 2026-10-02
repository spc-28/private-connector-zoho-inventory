"""Starts the connector over stdio and calls its tools, as an agent runtime would."""

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "zoho-connector"


@asynccontextmanager
async def open_session(env: dict | None = None):
    params = StdioServerParameters(command=str(SERVER), env={**os.environ, **(env or {})})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


async def call(session: ClientSession, tool: str, args: dict) -> tuple[dict, float]:
    started = time.perf_counter()
    result = await session.call_tool(tool, args)
    elapsed_ms = (time.perf_counter() - started) * 1000
    text = result.content[0].text if result.content else ""
    try:
        return json.loads(text), elapsed_ms
    except ValueError:
        return {"ok": False, "error": {"code": "NOT_JSON", "message": text[:200]}}, elapsed_ms
