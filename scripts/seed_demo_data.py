"""Fictional food-store demo data. No real people, emails or payments."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    name: str
    sku: str
    rate: float
    purchase_rate: float
    stock: int
    reorder_level: int


@dataclass(frozen=True)
class Customer:
    first_name: str
    last_name: str
    email: str
    phone: str
    city: str
    state: str

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class Order:
    reference: str
    date: str
    customer_email: str
    lines: tuple[tuple[str, int], ...]
    outcome: str
    carrier: str | None = None
    tracking: str | None = None


ITEMS = (
    Item("Masala Chai 250g", "FOOD-CHAI-250", 240, 150, 50, 10),
    Item("Raw Forest Honey 500g", "FOOD-HONEY-500", 450, 300, 30, 5),
    Item("California Almonds 500g", "FOOD-ALMD-500", 520, 380, 8, 15),
    Item("Aged Basmati Rice 5kg", "FOOD-RICE-5KG", 899, 650, 20, 5),
)

CUSTOMERS = (
    Customer("Aarav", "Mehta", "aarav.mehta@example.com", "9800000001", "Jaipur", "Rajasthan"),
    Customer("Meera", "Iyer", "meera.iyer@example.com", "9800000002", "Bengaluru", "Karnataka"),
    Customer("Kabir", "Sethi", "kabir.sethi@example.com", "9800000003", "Pune", "Maharashtra"),
)

CHAI, HONEY, ALMONDS, RICE = (item.sku for item in ITEMS)
AARAV, MEERA, KABIR = (customer.email for customer in CUSTOMERS)

ORDERS = (
    Order(
        "pay_DEMO0001",
        "2026-09-05",
        AARAV,
        ((CHAI, 2), (HONEY, 1)),
        "delivered",
        "Delhivery",
        "DLVDEMO000001",
    ),
    Order(
        "pay_DEMO0002", "2026-09-08", MEERA, ((ALMONDS, 3),), "shipped", "Blue Dart", "BDDEMO000002"
    ),
    Order("pay_DEMO0003", "2026-09-12", KABIR, ((RICE, 1),), "confirmed"),
    Order("pay_DEMO0004", "2026-09-15", AARAV, ((ALMONDS, 2),), "packed"),
    Order("pay_DEMO0005", "2026-09-18", MEERA, ((CHAI, 1),), "void"),
    Order("pay_DEMO0006", "2026-09-21", KABIR, ((HONEY, 2),), "confirmed"),
    Order("pay_DEMO0007", "2026-09-24", AARAV, ((RICE, 1), (ALMONDS, 1)), "confirmed"),
    Order("pay_DEMO0008", "2026-09-27", MEERA, ((CHAI, 4),), "confirmed"),
)
