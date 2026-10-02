from datetime import UTC, datetime


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def source(record: str, record_id: str, fetched_at: str) -> dict:
    return {"record": record, "id": record_id, "fetched_at": fetched_at}
