import hashlib
import os
import time
from datetime import UTC, datetime, timedelta

from zoho_connector.client.zoho_client import ZohoClient
from zoho_connector.config import Settings
from zoho_connector.errors import Code, ConnectorError

DAY_SECONDS = 86400
SOURCES = {
    "invoice": lambda record_id: (f"/invoices/{record_id}", {"accept": "pdf"}),
    "package_slip": lambda record_id: ("/packages/print", {"package_ids": record_id}),
}


class DocumentExporter:
    """Saves evidence PDFs locally for upload to Razorpay. The model only ever sees the path."""

    def __init__(self, client: ZohoClient, settings: Settings):
        self._client = client
        self._dir = settings.export_dir
        self._retention_days = settings.export_retention_days

    async def export(self, document_type: str, record_id: str) -> dict:
        self._purge_expired()
        path, params = SOURCES[document_type](record_id)
        content = await self._client.get_bytes(path, params)
        if not content.startswith(b"%PDF"):
            raise ConnectorError(
                Code.UPSTREAM_ERROR, "Zoho did not return a PDF for this record.", retryable=True
            )
        target = self._dir / f"{document_type}-{record_id}-{int(time.time())}.pdf"
        self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(content)
        os.chmod(target, 0o600)
        expires = datetime.now(UTC) + timedelta(days=self._retention_days)
        return {
            "document_type": document_type,
            "record_id": record_id,
            "path": str(target),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "content_type": "application/pdf",
            "delete_after": expires.date().isoformat(),
            "note": "Contains unmasked customer details. Upload to Razorpay; do not paste it.",
        }

    def _purge_expired(self) -> None:
        if not self._dir.exists():
            return
        cutoff = time.time() - self._retention_days * DAY_SECONDS
        for file in self._dir.glob("*.pdf"):
            if file.stat().st_mtime < cutoff:
                file.unlink(missing_ok=True)
