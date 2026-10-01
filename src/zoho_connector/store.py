import json
import os
from pathlib import Path


class JsonFile:
    """A small JSON document on disk, written atomically and readable only by the owner."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
