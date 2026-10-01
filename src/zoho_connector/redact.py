def redact(secret: str | None) -> str:
    if not secret:
        return "<none>"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-2:]}"
