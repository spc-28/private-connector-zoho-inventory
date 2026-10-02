import re

UNTRUSTED_MAX_CHARS = 120
SAFE_LABEL = re.compile(r"^[A-Za-z0-9 .\-/&]{1,40}$")


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_phone(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return f"******{digits[-4:]}" if len(digits) >= 4 else None


def untrusted(text: str | None, limit: int = UNTRUSTED_MAX_CHARS) -> dict | None:
    """Free text typed by people outside the merchant's control. Data, never instructions."""
    if not text:
        return None
    return {"untrusted_text": str(text)[:limit]}


def safe_label(text: str | None) -> str | None:
    """A short code-like value (carrier, tracking number) that is safe to template into prose."""
    return text if text and SAFE_LABEL.match(text) else None
