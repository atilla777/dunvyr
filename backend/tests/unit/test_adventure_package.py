"""Tests for the server-owned adventure package boundary."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.unit
def test_package_loader_is_available():
    spec = importlib.util.find_spec("dunvyr.adventures.infrastructure.package_loader")
    assert spec is not None, "the server must provide an adventure package loader"


def test_loader_rejects_missing_initial_location(tmp_path):
    import json

    from dunvyr.adventures.infrastructure.package_loader import PackageError, load_package

    (tmp_path / "adventure.json").write_text(
        json.dumps({"schema_version": 1, "initial_location_id": "missing"})
    )
    with pytest.raises(PackageError, match=r"initial|fields"):
        load_package(tmp_path)


@pytest.fixture
def package_dir(tmp_path):
    import shutil
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "adventures" / "last-shift"
    shutil.copytree(source, tmp_path / "package")
    return tmp_path / "package"


def mutate(root: Path, change: Callable[[Any], Any]) -> None:
    import json

    path = root / "adventure.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False))


@pytest.mark.unit
def test_domain_references_without_boundary_models(package_dir):
    import json

    from dunvyr.adventures.domain.package import validate_references

    data = json.loads((package_dir / "adventure.json").read_text())
    validate_references(data)
    data["skills"].append(data["skills"][0])
    with pytest.raises(ValueError, match="duplicate skill"):
        validate_references(data)
    data["skills"].pop()
    data["initial_location_id"] = "missing"
    with pytest.raises(ValueError, match="missing initial location"):
        validate_references(data)


@pytest.mark.unit
def test_real_package_loads_and_fingerprint_binds_normalized_content_and_bytes(package_dir):
    import json

    from dunvyr.adventures.infrastructure.package_loader import load_package

    original = load_package(package_dir)
    data = json.loads(original.content)
    assert data["title"] == "Последняя смена"
    assert {a["id"] for a in data["archetypes"]} == {"engineer", "scout", "negotiator"}
    assert len(original.resources["airlock-image"]) > 100
    (package_dir / "adventure.json").write_text(json.dumps(data, ensure_ascii=False, indent=4))
    assert load_package(package_dir).fingerprint == original.fingerprint
    mutate(package_dir, lambda d: d.update(title="Другая смена"))
    assert load_package(package_dir).fingerprint != original.fingerprint


@pytest.mark.unit
@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(initial_location_id="missing"),
        lambda d: d.update(unknown="SENTINEL"),
        lambda d: d["skills"].append(d["skills"][0]),
        lambda d: d["archetypes"].append(d["archetypes"][0]),
        lambda d: d["locations"].append(d["locations"][0]),
        lambda d: d["assets"].append(d["assets"][0]),
        lambda d: d["locations"][0]["objects"].append(d["locations"][0]["objects"][0]),
        lambda d: d["archetypes"][0]["skills"].update(missing=1),
        lambda d: d["archetypes"][0]["characteristics"].pop("presence"),
        lambda d: d["archetypes"][0]["characteristics"].update(strength=11),
        lambda d: d["skills"][0].update(characteristic="magic"),
        lambda d: d["locations"][0].update(illustration="missing"),
        lambda d: d["locations"][0]["objects"][0]["hotspot"].update(x=0.99),
        lambda d: d["locations"][0]["exits"].append(
            {"id": "exit", "object_id": "missing", "target_location_id": "airlock"}
        ),
        lambda d: d["locations"][0]["exits"].append(
            {"id": "exit", "object_id": "door", "target_location_id": "missing"}
        ),
    ],
)
def test_invalid_package_invariants(package_dir, change):
    from dunvyr.adventures.infrastructure.package_loader import PackageError, load_package

    mutate(package_dir, change)
    with pytest.raises(PackageError):
        load_package(package_dir)


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "../outside.png",
        "/etc/passwd",
        "https://example.com/a.png",
        "sub/../../a.png",
        "link.png",
        "pipe.png",
    ],
)
def test_unsafe_paths_rejected(package_dir, path):
    import os

    from dunvyr.adventures.infrastructure.package_loader import PackageError, load_package

    (package_dir / "link.png").symlink_to(package_dir / "airlock.png")
    os.mkfifo(package_dir / "pipe.png")
    mutate(package_dir, lambda d: d["assets"][0].update(path=path))
    with pytest.raises(PackageError):
        load_package(package_dir)


@pytest.mark.unit
def test_invalid_png_and_duplicate_json_keys_rejected(package_dir):
    from dunvyr.adventures.infrastructure.package_loader import PackageError, load_package

    (package_dir / "airlock.png").write_bytes(b"\x89PNG\r\n\x1a\nSENTINEL")
    with pytest.raises(PackageError, match="PNG"):
        load_package(package_dir)
    (package_dir / "adventure.json").write_text('{"id":"one","id":"two"}')
    with pytest.raises(PackageError, match="duplicate JSON"):
        load_package(package_dir)


@pytest.mark.unit
def test_fingerprint_changes_when_valid_resource_bytes_change(package_dir):
    import struct
    import zlib

    from dunvyr.adventures.infrastructure.package_loader import load_package

    before = load_package(package_dir)
    path = package_dir / "airlock.png"
    png = path.read_bytes()
    payload = b"author\x00Dunvyr"
    chunk = b"tEXt" + payload
    path.write_bytes(
        png[:-12]
        + struct.pack(">I", len(payload))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk))
        + png[-12:]
    )
    after = load_package(package_dir)
    assert before.content == after.content
    assert before.fingerprint != after.fingerprint


@pytest.mark.unit
def test_oversized_json_and_symlinked_directory_rejected(package_dir):
    from dunvyr.adventures.infrastructure.package_loader import PackageError, load_package

    (package_dir / "sub").symlink_to(package_dir, target_is_directory=True)
    mutate(package_dir, lambda d: d["assets"][0].update(path="sub/airlock.png"))
    with pytest.raises(PackageError):
        load_package(package_dir)
    (package_dir / "adventure.json").write_bytes(b" " * 1_000_001)
    with pytest.raises(PackageError):
        load_package(package_dir)
