"""Strict v1 local package reader; never pass a client-provided filesystem path.

load_package(package_directory) returns canonical JSON and immutable resource bytes
for the snapshot writer. The caller selects directories from its configured server root.
"""

import hashlib
import json
import os
import re
import stat
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dunvyr.adventures.domain.package import validate_references


class PackageError(ValueError):
    """An invalid or unsafe local adventure package."""


Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
Rating = Annotated[int, Field(ge=0, le=10)]
Characteristic = Literal["strength", "agility", "intellect", "presence"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Skill(StrictModel):
    id: Id
    name: Text
    characteristic: Characteristic


class Characteristics(StrictModel):
    strength: Rating
    agility: Rating
    intellect: Rating
    presence: Rating


class Archetype(StrictModel):
    id: Id
    name: Text
    characteristics: Characteristics
    skills: dict[Id, Rating] = Field(min_length=1, max_length=100)


class Asset(StrictModel):
    id: Id
    path: Annotated[str, Field(min_length=1, max_length=240)]


class Hotspot(StrictModel):
    x: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    width: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]

    @model_validator(mode="after")
    def within_image(self) -> Hotspot:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("hotspot exceeds image bounds")
        return self


class SceneObject(StrictModel):
    id: Id
    name: Text
    public_description: Text
    hotspot: Hotspot
    visibility: Literal["visible", "hidden"]


class Exit(StrictModel):
    id: Id
    target_location_id: Id
    object_id: Id


class Location(StrictModel):
    id: Id
    name: Text
    illustration: Id
    public_description: Text
    objects: list[SceneObject] = Field(max_length=100)
    exits: list[Exit] = Field(max_length=100)


class Package(StrictModel):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    id: Id
    title: Text
    summary: Text
    edition: Annotated[str, Field(min_length=1, max_length=100)]
    skills: list[Skill] = Field(min_length=1, max_length=100)
    archetypes: list[Archetype] = Field(min_length=1, max_length=100)
    initial_location_id: Id
    locations: list[Location] = Field(min_length=1, max_length=100)
    assets: list[Asset] = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class LoadedPackage:
    content: str
    resources: dict[str, bytes]
    fingerprint: str


def _read(root: Path, relative: str, limit: int) -> bytes:
    if not re.fullmatch(
        r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?(?:/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?)*", relative
    ):
        raise PackageError("unsafe resource path")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fds: list[int] = []
    try:
        fd = os.open(root, flags | os.O_DIRECTORY)
        fds.append(fd)
        parts = relative.split("/")
        for part in parts[:-1]:
            fd = os.open(part, flags | os.O_DIRECTORY, dir_fd=fd)
            fds.append(fd)
        fd = os.open(parts[-1], flags, dir_fd=fd)
        fds.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise PackageError("resource is not a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise PackageError("resource exceeds size limit")
        return data
    except OSError as exc:
        raise PackageError(f"cannot safely read {relative}") from exc
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _png(data: bytes) -> None:
    """Validate a bounded non-interlaced 8-bit RGB/RGBA PNG, including pixels and CRCs."""
    try:
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("signature")
        pos = 8
        chunks: list[bytes] = []
        compressed = bytearray()
        width = height = channels = 0
        while pos < len(data):
            if pos + 12 > len(data):
                raise ValueError("truncated chunk")
            length = struct.unpack_from(">I", data, pos)[0]
            end = pos + 12 + length
            if end > len(data):
                raise ValueError("truncated data")
            kind = data[pos + 4 : pos + 8]
            payload = data[pos + 8 : pos + 8 + length]
            crc = struct.unpack_from(">I", data, pos + 8 + length)[0]
            if zlib.crc32(kind + payload) != crc:
                raise ValueError("CRC")
            chunks.append(kind)
            if kind == b"IHDR":
                if len(chunks) != 1 or length != 13:
                    raise ValueError("IHDR")
                width, height, depth, color, compression, filtering, interlace = struct.unpack(
                    ">IIBBBBB", payload
                )
                if not (
                    1 <= width <= 4096
                    and 1 <= height <= 4096
                    and width * height <= 4_000_000
                    and depth == 8
                    and color in (2, 6)
                    and compression == filtering == interlace == 0
                ):
                    raise ValueError("unsupported dimensions or PNG format")
                channels = 3 if color == 2 else 4
            elif kind == b"IDAT":
                if not chunks or chunks[0] != b"IHDR" or b"IEND" in chunks:
                    raise ValueError("IDAT ordering")
                compressed.extend(payload)
            elif kind == b"IEND":
                if length or end != len(data):
                    raise ValueError("IEND")
                break
            elif kind[0] & 32 == 0:
                raise ValueError("unsupported critical chunk")
            pos = end
        if not chunks or chunks[-1] != b"IEND" or not compressed or chunks.count(b"IHDR") != 1:
            raise ValueError("missing chunks")
        first = chunks.index(b"IDAT")
        last = len(chunks) - 1 - chunks[::-1].index(b"IDAT")
        if any(kind != b"IDAT" for kind in chunks[first : last + 1]):
            raise ValueError("nonconsecutive IDAT")
        size = (width * channels + 1) * height
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(compressed), size + 1)
        if len(pixels) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("invalid image data")
        if any(pixels[row * (width * channels + 1)] > 4 for row in range(height)):
            raise ValueError("invalid PNG filter")
    except (ValueError, struct.error, zlib.error, IndexError) as exc:
        raise PackageError(f"invalid PNG: {exc}") from exc


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_package(root: Path) -> LoadedPackage:
    """Load one trusted configured directory; never use user input as root."""
    data = _read(root, "adventure.json", 1_000_000)
    try:
        raw = json.loads(data, object_pairs_hook=_pairs)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PackageError(f"invalid package fields: {exc}") from exc
    try:
        package = Package.model_validate(raw)
        validate_references(package.model_dump())
    except (ValidationError, ValueError) as exc:
        raise PackageError(f"invalid package fields: {exc}") from exc
    resources = {}
    for asset in package.assets:
        data = _read(root, asset.path, 8_000_000)
        _png(data)
        resources[asset.id] = data
    content = json.dumps(
        package.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    manifest = {key: hashlib.sha256(value).hexdigest() for key, value in resources.items()}
    fingerprint_data = json.dumps(
        {"content": json.loads(content), "resources": manifest},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return LoadedPackage(
        content, resources, hashlib.sha256(fingerprint_data.encode("utf-8")).hexdigest()
    )
