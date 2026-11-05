"""Architecture test: the identity domain stays free of outer layers/frameworks."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

IDENTITY_DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "dunvyr" / "identity" / "domain"
FORBIDDEN_ROOTS = {
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "starlette",
    "dunvyr.identity.application",
    "dunvyr.identity.infrastructure",
    "dunvyr.identity.presentation",
    "dunvyr.identity.public",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


@pytest.mark.unit
def test_identity_domain_imports_no_frameworks_or_outer_layers() -> None:
    sources = sorted(IDENTITY_DOMAIN_DIR.glob("*.py"))
    assert sources

    violations: list[str] = []
    for path in sources:
        for module in _imported_modules(path):
            if any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_ROOTS
            ):
                violations.append(f"{path.name}: {module}")

    assert violations == []
