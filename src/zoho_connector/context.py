from dataclasses import dataclass

from zoho_connector.auth.token_manager import TokenManager
from zoho_connector.capabilities import Capabilities
from zoho_connector.client.quota import DailyQuota
from zoho_connector.client.rate_limiter import RateLimiter
from zoho_connector.client.zoho_client import ZohoClient
from zoho_connector.config import Settings
from zoho_connector.evidence.builder import EvidenceBuilder
from zoho_connector.services.documents import DocumentExporter
from zoho_connector.services.items import ItemService
from zoho_connector.services.lookup import OrderLookup
from zoho_connector.services.orders import OrderService
from zoho_connector.store import JsonFile


@dataclass
class Context:
    settings: Settings
    tokens: TokenManager
    quota: DailyQuota
    organization: JsonFile
    capabilities: Capabilities
    client: ZohoClient
    orders: OrderService
    lookup: OrderLookup
    evidence: EvidenceBuilder
    documents: DocumentExporter
    items: ItemService

    @classmethod
    def create(cls, settings: Settings | None = None) -> "Context":
        settings = settings or Settings()
        organization = JsonFile(settings.state_dir / "organization.json")
        tokens = TokenManager(settings)
        quota = DailyQuota(JsonFile(settings.state_dir / "quota.json"), settings.daily_limit)
        limiter = RateLimiter(
            settings.rate_per_minute, settings.max_concurrency, settings.max_queue_wait_seconds
        )
        org_id = settings.organization_id or organization.read().get("id")
        client = ZohoClient(settings, tokens, limiter, quota, org_id)
        capabilities = Capabilities(JsonFile(settings.state_dir / "capabilities.json"))
        orders = OrderService(client, capabilities, settings)
        lookup = OrderLookup(orders, capabilities, settings)
        return cls(
            settings=settings,
            tokens=tokens,
            quota=quota,
            organization=organization,
            capabilities=capabilities,
            client=client,
            orders=orders,
            lookup=lookup,
            evidence=EvidenceBuilder(client, orders, lookup, settings),
            documents=DocumentExporter(client, settings),
            items=ItemService(client, settings),
        )
