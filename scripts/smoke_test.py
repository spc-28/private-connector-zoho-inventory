"""Live smoke test: runs every tool once against the seeded demo org and prints pass/fail."""

import sys
from collections.abc import Callable
from pathlib import Path

import anyio
from mcp_session import call, open_session

Check = Callable[[dict], bool]


def _ok(result: dict) -> bool:
    return result.get("ok") is True


CASES: list[tuple[str, dict, str, Check]] = [
    ("connector_status", {}, "authorized", lambda r: _ok(r) and r["data"]["authorized"]),
    (
        "search_orders",
        {"customer_email": "meera.iyer@example.com"},
        "customer history, masked",
        lambda r: (
            _ok(r)
            and r["data"]["orders"]
            and all(o["customer"]["email"].startswith("m***@") for o in r["data"]["orders"])
        ),
    ),
    (
        "get_order",
        {"order_number": "SO-00001"},
        "detail by number",
        lambda r: _ok(r) and r["data"]["order_number"] == "SO-00001",
    ),
    (
        "find_order_by_payment",
        {"payment_ref": "pay_DEMO0001", "amount": 93000, "payment_date": "2026-09-05"},
        "high-confidence link",
        lambda r: _ok(r) and r["data"]["match"]["confidence"] == "high",
    ),
    (
        "get_dispute_evidence",
        {"payment_ref": "pay_DEMO0001", "reason_category": "not_received"},
        "strong pack, no date",
        lambda r: (
            _ok(r)
            and r["data"]["evidence_readiness"]["level"] == "strong"
            and r["data"]["delivery"]["delivered_on"] is None
        ),
    ),
    (
        "get_dispute_evidence",
        {"payment_ref": "pay_DEMO0004", "reason_category": "not_received"},
        "contradicting pack",
        lambda r: _ok(r) and r["data"]["evidence_readiness"]["level"] == "contradicting",
    ),
    (
        "search_items",
        {"low_stock_only": True},
        "low stock found",
        lambda r: _ok(r) and any(i["sku"] == "FOOD-ALMD-500" for i in r["data"]["items"]),
    ),
]


async def main() -> int:
    rows, failures = [], 0
    async with open_session() as session:
        for tool, args, label, check in CASES:
            result, ms = await call(session, tool, args)
            passed = bool(check(result))
            rows.append((tool, label, passed, ms, _error(result)))
            if tool == "get_dispute_evidence" and passed and label.startswith("strong"):
                rows.append(await _document_case(session, result))
        failures = sum(1 for row in rows if not row[2])
    _print(rows)
    return 1 if failures else 0


async def _document_case(session, evidence: dict) -> tuple:
    invoice_id = evidence["data"]["contest_buckets"]["billing_proof"]["documents"][0]["id"]
    args = {"document_type": "invoice", "record_id": invoice_id}
    result, ms = await call(session, "get_evidence_document", args)
    passed = _ok(result) and Path(result["data"]["path"]).read_bytes()[:4] == b"%PDF"
    return ("get_evidence_document", "invoice PDF saved", passed, ms, _error(result))


def _error(result: dict) -> str:
    return "" if _ok(result) else result.get("error", {}).get("code", "?")


def _print(rows: list[tuple]) -> None:
    print(f"\n{'tool':24} {'case':28} {'result':6} {'ms':>6}")
    print("-" * 70)
    for tool, label, passed, ms, error in rows:
        status = "PASS" if passed else "FAIL"
        print(f"{tool:24} {label:28} {status:6} {ms:6.0f} {error}")
    passed = sum(1 for row in rows if row[2])
    print(f"\n{passed}/{len(rows)} passed")


if __name__ == "__main__":
    sys.exit(anyio.run(main))
