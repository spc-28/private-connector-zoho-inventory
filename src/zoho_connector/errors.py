from enum import StrEnum


class Code(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONFIG_REQUIRED = "CONFIG_REQUIRED"
    FORBIDDEN_SCOPE = "FORBIDDEN_SCOPE"
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    SEARCH_INCOMPLETE = "SEARCH_INCOMPLETE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"


class ConnectorError(Exception):
    def __init__(
        self,
        code: Code,
        message: str,
        *,
        retryable: bool = False,
        hint: str = "",
        retry_after_seconds: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.hint = hint
        self.retry_after_seconds = retry_after_seconds
        self.details = details

    def to_dict(self) -> dict:
        error = {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "hint": self.hint,
        }
        if self.retry_after_seconds is not None:
            error["retry_after_seconds"] = self.retry_after_seconds
        if self.details:
            error["details"] = self.details
        return error


def auth_required(message: str = "The connector is not authorized with Zoho.") -> ConnectorError:
    return ConnectorError(
        Code.AUTH_REQUIRED, message, hint="Ask the merchant to run zoho-connector-setup."
    )


def rate_limited(seconds: float, message: str) -> ConnectorError:
    return ConnectorError(
        Code.RATE_LIMITED,
        message,
        retryable=True,
        hint="Wait, then retry the same call.",
        retry_after_seconds=max(1, round(seconds)),
    )
