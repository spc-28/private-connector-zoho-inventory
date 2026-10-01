import argparse
import asyncio
import secrets
import sys

from zoho_connector.auth import oauth, token_store
from zoho_connector.auth.loopback import receive_redirect
from zoho_connector.auth.token_store import Tokens
from zoho_connector.config import Settings
from zoho_connector.context import Context
from zoho_connector.errors import ConnectorError
from zoho_connector.redact import redact


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="zoho-connector-setup", description="Authorize the read-only Zoho Inventory connector."
    )
    parser.add_argument("--self-client-code", help="Grant code from a Zoho Self Client (headless).")
    parser.add_argument(
        "--force", action="store_true", help="Authorize again even if tokens exist."
    )
    parser.add_argument("--logout", action="store_true", help="Revoke and forget the tokens.")
    args = parser.parse_args()
    settings = Settings()
    if not (settings.client_id and settings.client_secret):
        sys.exit("Set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in .env first (see .env.example).")
    try:
        asyncio.run(_run(settings, args))
    except ConnectorError as exc:
        sys.exit(f"Setup failed: {exc.message} {exc.hint}".strip())


async def _run(settings: Settings, args: argparse.Namespace) -> None:
    if args.logout:
        await _logout(settings)
        return
    existing = token_store.load()
    if existing and not args.force and not args.self_client_code:
        print("Already authorized. Use --force to authorize again.")
    else:
        tokens = await _authorize(settings, args.self_client_code)
        token_store.save(tokens)
        print(
            f"Authorized. Data center API: {tokens.api_domain}. "
            f"Refresh token {redact(tokens.refresh_token)} saved to the OS keychain."
        )
    await _choose_organization(settings)


async def _authorize(settings: Settings, self_client_code: str | None) -> Tokens:
    if self_client_code:
        return await oauth.exchange_code(settings, settings.accounts_url, self_client_code, None)
    state = secrets.token_urlsafe(24)
    params = receive_redirect(settings.redirect_uri, oauth.authorize_url(settings, state))
    if not params:
        sys.exit("Timed out waiting for the Zoho redirect.")
    if not secrets.compare_digest(params.get("state", ""), state):
        sys.exit("The redirect's state did not match. Setup aborted.")
    if "code" not in params:
        sys.exit(f"Zoho did not grant access: {params.get('error', 'unknown error')}")
    accounts_server = params.get("accounts-server", settings.accounts_url)
    return await oauth.exchange_code(
        settings, accounts_server, params["code"], settings.redirect_uri
    )


async def _choose_organization(settings: Settings) -> None:
    context = Context.create(settings)
    try:
        body = await context.client.get("/organizations", with_org=False)
    finally:
        await context.client.aclose()
    organizations = body.get("organizations", [])
    if not organizations:
        sys.exit("No Zoho Inventory organization is available for this login.")
    chosen = organizations[0] if len(organizations) == 1 else _prompt(organizations)
    context.organization.write({"id": chosen["organization_id"], "name": chosen["name"]})
    print(f"Organization selected: {chosen['name']} ({chosen['organization_id']}).")


def _prompt(organizations: list[dict]) -> dict:
    for index, org in enumerate(organizations, start=1):
        print(f"  {index}. {org['name']} ({org['organization_id']})")
    while True:
        choice = input("Choose an organization number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(organizations):
            return organizations[int(choice) - 1]


async def _logout(settings: Settings) -> None:
    tokens = token_store.load()
    if tokens:
        await oauth.revoke(tokens)
    token_store.clear()
    Context.create(settings).organization.delete()
    print("Tokens revoked and removed from the keychain.")
