"""Runs each eval question through a Claude agent connected to the connector over MCP stdio.

Stands in for an Agent Studio agent: Claude sees only the connector's tools and its instructions.
Spends Anthropic API credits. Usage: .venv/bin/python evals/run_evals.py [--only Q01,Q12]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import anyio
from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from grading import grade
from mcp_session import open_session

MODEL = "claude-opus-5-5"
SYSTEM = (
    "You help a merchant's operations and finance team with orders, shipments, disputes and "
    "stock. Use the available tools to look things up, and answer from what they return. "
    "Today is 2026-10-02. Be concise and name order numbers, amounts and tracking numbers."
)


async def run_case(client: AsyncAnthropic, session, tools, case: dict) -> dict:
    instructions = session.initialize_result.instructions or ""
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=f"{SYSTEM}\n\nConnector instructions: {instructions}",
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        tools=tools,
        messages=[{"role": "user", "content": case["question"]}],
    )
    calls, last, started = [], None, time.perf_counter()
    async for message in runner:
        last = message
        calls += [block.name for block in message.content if block.type == "tool_use"]
    answer = _answer(last)
    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "tool_calls": calls,
        "answer": answer,
        "stop_reason": last.stop_reason if last else None,
        "seconds": round(time.perf_counter() - started, 1),
        **grade(case, answer, calls),
    }


def _answer(message) -> str:
    if message is None or message.stop_reason == "refusal":
        return ""
    return "\n".join(block.text for block in message.content if block.type == "text")


async def main(only: set[str] | None) -> int:
    cases = json.loads((HERE / "questions.json").read_text())
    cases = [case for case in cases if not only or case["id"] in only]
    client = AsyncAnthropic()
    results = []
    async with open_session() as session:
        tools = [async_mcp_tool(tool, session) for tool in (await session.list_tools()).tools]
        for case in cases:
            result = await run_case(client, session, tools, case)
            results.append(result)
            print(f"{result['id']} {'PASS' if result['passed'] else 'FAIL'} {result['checks']}")
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    passed = sum(result["passed"] for result in results)
    print(f"\n{passed}/{len(results)} passed. Details in evals/results.json")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Comma-separated question IDs, e.g. Q01,Q12")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    sys.exit(anyio.run(main, only))
