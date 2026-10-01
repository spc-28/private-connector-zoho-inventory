from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

STATE_DIR = Path.home() / ".zoho_connector"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZOHO_", env_file=".env", extra="ignore")

    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://127.0.0.1:8765/callback"
    accounts_url: str = "https://accounts.zoho.com"
    organization_id: str = ""
    payment_link_field: str = "reference_number"

    rate_per_minute: int = 100
    max_concurrency: int = 5
    daily_limit: int = 1000
    max_queue_wait_seconds: float = 10.0
    max_retries: int = 3
    block_cooldown_seconds: int = 60
    scan_cap: int = 10

    state_dir: Path = STATE_DIR
    export_dir: Path = STATE_DIR / "exports"
    export_retention_days: int = 7

    @property
    def redirect_host_port(self) -> tuple[str, int]:
        parsed = urlparse(self.redirect_uri)
        return parsed.hostname or "127.0.0.1", parsed.port or 80
