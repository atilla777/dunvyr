"""Enforce adventure ownership, layering and public-only consumption."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "dunvyr" / "adventures"
FOREIGN_TABLES = ("identity_", "campaigns_campaigns", "campaigns_members", "communication_")
DOMAIN_FORBIDDEN = (
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "starlette",
    "dunvyr.campaigns",
    "dunvyr.identity",
    "dunvyr.adventures.application",
    "dunvyr.adventures.infrastructure",
    "dunvyr.adventures.presentation",
    "dunvyr.adventures.public",
)


def modules(source: str) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def forbidden_imports(source: str, roots: tuple[str, ...]) -> set[str]:
    return {
        module
        for module in modules(source)
        if any(module == root or module.startswith(root + ".") for root in roots)
    }


def foreign_tables(source: str) -> set[str]:
    return {table for table in FOREIGN_TABLES if table in source}


def foreign_internal_imports(source: str) -> set[str]:
    result = set()
    for module in modules(source):
        for context in (
            "campaigns",
            "identity",
            "characters",
            "gameplay",
            "communication",
            "narration",
        ):
            prefix = f"dunvyr.{context}"
            if (
                module == prefix or module.startswith(prefix + ".")
            ) and module != prefix + ".public":
                result.add(module)
    return result


@pytest.mark.unit
def test_adventure_domain_is_pure() -> None:
    paths = list((ROOT / "domain").glob("*.py"))
    assert paths
    assert not {
        path.name: forbidden_imports(path.read_text(), DOMAIN_FORBIDDEN)
        for path in paths
        if forbidden_imports(path.read_text(), DOMAIN_FORBIDDEN)
    }


@pytest.mark.unit
def test_adventure_foreign_contexts_are_public_only() -> None:
    for path in ROOT.rglob("*.py"):
        assert not foreign_internal_imports(path.read_text()), path


@pytest.mark.unit
def test_adventure_adapters_do_not_access_foreign_tables() -> None:
    paths = list((ROOT / "infrastructure").rglob("*.py"))
    assert paths
    assert not {
        path.name: foreign_tables(path.read_text())
        for path in paths
        if foreign_tables(path.read_text())
    }


@pytest.mark.unit
def test_guards_detect_violations() -> None:
    assert forbidden_imports("import pydantic\n", DOMAIN_FORBIDDEN) == {"pydantic"}
    assert foreign_internal_imports("import dunvyr.identity.infrastructure\n") == {
        "dunvyr.identity.infrastructure"
    }
    assert foreign_tables('query = "SELECT * FROM campaigns_members"') == {"campaigns_members"}
    assert foreign_tables('query = "UPDATE identity_guests SET id=1"') == {"identity_"}
