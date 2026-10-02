import base64
import json
from datetime import date

from zoho_connector.errors import Code, ConnectorError


def invalid(field: str, message: str) -> ConnectorError:
    return ConnectorError(Code.INVALID_INPUT, message, hint=f"Fix the '{field}' input.")


def parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise invalid(field, f"'{field}' must be a date like 2026-09-05.") from exc


def record_id(value: str, field: str) -> str:
    if not value.isdigit():
        raise invalid(field, f"'{field}' must be a Zoho record ID made of digits.")
    return value


def exactly_one(**values) -> str:
    given = [name for name, value in values.items() if value]
    if len(given) != 1:
        names = " or ".join(values)
        raise invalid(names, f"Provide exactly one of {names}.")
    return given[0]


def encode_cursor(state: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(state).encode()).decode()


def decode_cursor(cursor: str | None) -> dict:
    if not cursor:
        return {}
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except ValueError as exc:
        raise invalid("cursor", "The cursor is not valid. Start again without one.") from exc
