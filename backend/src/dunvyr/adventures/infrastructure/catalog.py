"""Server-configured local catalog, with invalid entries isolated and logged."""

import json
import logging
import re
from pathlib import Path

from dunvyr.adventures.infrastructure.package_loader import (
    LoadedPackage,
    PackageError,
    load_package,
)

logger = logging.getLogger(__name__)
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class LocalCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, adventure_id: str) -> LoadedPackage | None:
        if not ID.fullmatch(adventure_id):
            return None
        try:
            package = load_package(self.root / adventure_id)
            if json.loads(package.content)["id"] != adventure_id:
                raise PackageError("package ID does not match directory")
            return package
        except PackageError as exc:
            logger.warning("Invalid adventure package %s: %s", adventure_id, exc)
            return None

    def list(self) -> list[dict[str, str]]:
        try:
            entries = sorted(self.root.iterdir())
        except OSError as exc:
            logger.warning("Cannot read adventure catalog: %s", exc)
            return []
        result = []
        for entry in entries:
            package = self.load(entry.name)
            if package is not None:
                data = json.loads(package.content)
                result.append(
                    {
                        "adventure_id": data["id"],
                        "fingerprint": package.fingerprint,
                        "title": data["title"],
                        "description": data["summary"],
                        "edition": data["edition"],
                    }
                )
        return result
