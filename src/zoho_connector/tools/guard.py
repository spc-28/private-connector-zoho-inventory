import functools
import logging
import time

from mcp.types import ToolAnnotations

from zoho_connector.errors import Code, ConnectorError
from zoho_connector.result import fail

log = logging.getLogger("zoho_connector.tools")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)


def guarded(fn):
    """Turns every outcome into the result envelope and logs name, status and latency only."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        started = time.perf_counter()
        status = "ok"
        try:
            return await fn(*args, **kwargs)
        except ConnectorError as exc:
            status = exc.code.value
            return fail(exc)
        except Exception as exc:  # noqa: BLE001 - a tool must never crash the agent
            status = f"unexpected:{type(exc).__name__}"
            return fail(
                ConnectorError(
                    Code.UPSTREAM_ERROR, "The connector hit an unexpected error.", retryable=True
                )
            )
        finally:
            latency_ms = (time.perf_counter() - started) * 1000
            log.info("tool=%s status=%s latency_ms=%.0f", fn.__name__, status, latency_ms)

    return wrapper
