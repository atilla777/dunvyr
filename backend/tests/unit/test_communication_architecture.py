"""Architecture tests: communication ownership and public-only campaigns use."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "dunvyr"
COMMUNICATION_SRC = SRC_DIR / "communication"
COMMUNICATION_DOMAIN_DIR = COMMUNICATION_SRC / "domain"
FORBIDDEN_DOMAIN_ROOTS = {
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "starlette",
    "dunvyr.communication.application",
    "dunvyr.communication.infrastructure",
    "dunvyr.communication.presentation",
    "dunvyr.communication.public",
    "dunvyr.campaigns",
    "dunvyr.identity",
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
def test_communication_domain_imports_no_frameworks_or_outer_layers() -> None:
    sources = sorted(COMMUNICATION_DOMAIN_DIR.glob("*.py"))
    assert sources

    violations: list[str] = []
    for path in sources:
        for module in _imported_modules(path):
            if any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_DOMAIN_ROOTS
            ):
                violations.append(f"{path.name}: {module}")

    assert violations == []


@pytest.mark.unit
def test_communication_consumes_campaigns_only_through_its_public_contract() -> None:
    imported_campaign_modules: set[str] = set()
    for path in sorted(COMMUNICATION_SRC.rglob("*.py")):
        imported_campaign_modules.update(
            module
            for module in _imported_modules(path)
            if module == "dunvyr.campaigns" or module.startswith("dunvyr.campaigns.")
        )

    assert imported_campaign_modules == {"dunvyr.campaigns.public"}


@pytest.mark.unit
def test_communication_consumes_identity_only_through_its_public_contract() -> None:
    imported_identity_modules: set[str] = set()
    for path in sorted(COMMUNICATION_SRC.rglob("*.py")):
        imported_identity_modules.update(
            module
            for module in _imported_modules(path)
            if module == "dunvyr.identity" or module.startswith("dunvyr.identity.")
        )

    assert imported_identity_modules == {"dunvyr.identity.public"}


@pytest.mark.unit
def test_communication_never_references_campaigns_tables() -> None:
    violations: list[str] = []
    for path in sorted(COMMUNICATION_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "campaigns_campaigns" in text or "campaigns_members" in text:
            violations.append(path.name)

    assert violations == []
