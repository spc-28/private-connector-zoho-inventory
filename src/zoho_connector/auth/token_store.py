import json
from dataclasses import asdict, dataclass

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "zoho-inventory-connector"
ACCOUNT = "oauth"


@dataclass
class Tokens:
    refresh_token: str
    accounts_server: str
    api_domain: str
    access_token: str = ""
    expires_at: float = 0.0


def load() -> Tokens | None:
    raw = keyring.get_password(SERVICE, ACCOUNT)
    return Tokens(**json.loads(raw)) if raw else None


def save(tokens: Tokens) -> None:
    keyring.set_password(SERVICE, ACCOUNT, json.dumps(asdict(tokens)))


def clear() -> None:
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except PasswordDeleteError:
        pass
