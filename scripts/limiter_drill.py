"""Limiter drill: squeezes the local limiter and fires a burst. Zoho itself is never burst.

Every call must come back as a structured result (ok or RATE_LIMITED); none may hang or crash.
"""

import sys

import anyio
from mcp_session import call, open_session

BURST = 10
DRILL_LIMITS = {
    "ZOHO_RATE_PER_MINUTE": "3",
    "ZOHO_MAX_CONCURRENCY": "2",
    "ZOHO_MAX_QUEUE_WAIT_SECONDS": "1",
}
TIMEOUT_SECONDS = 60


async def main() -> int:
    outcomes: list[tuple[str, int | None]] = []
    async with open_session(DRILL_LIMITS) as session:

        async def one() -> None:
            result, _ = await call(session, "search_items", {"sku": "FOOD-CHAI-250"})
            error = result.get("error", {})
            outcomes.append(
                (
                    "ok" if result.get("ok") else error.get("code", "?"),
                    error.get("retry_after_seconds"),
                )
            )

        with anyio.fail_after(TIMEOUT_SECONDS):
            async with anyio.create_task_group() as group:
                for _ in range(BURST):
                    group.start_soon(one)
    return _report(outcomes)


def _report(outcomes: list[tuple[str, int | None]]) -> int:
    counts: dict[str, int] = {}
    for code, _ in outcomes:
        counts[code] = counts.get(code, 0) + 1
    retry_after = sorted({seconds for code, seconds in outcomes if code == "RATE_LIMITED"})
    print(f"Burst of {BURST} calls with the limiter set to {DRILL_LIMITS}")
    print(f"Outcomes: {counts}")
    print(f"retry_after_seconds offered: {retry_after}")
    structured = set(counts) <= {"ok", "RATE_LIMITED"}
    throttled = counts.get("RATE_LIMITED", 0) > 0
    passed = structured and throttled and len(outcomes) == BURST
    print("PASS: every call returned a structured result" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(anyio.run(main))
