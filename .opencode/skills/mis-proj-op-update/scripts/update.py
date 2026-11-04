"""Preflight or apply MIS package installation/update from exact Git snapshots."""

import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess


SOURCE = "https://github.com/atilla777/mis"
RECORD = Path("mis-installation")


def git(source, *args):
    return subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def snapshot(source, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Revision must be a full lowercase commit SHA")
    if git(source, "rev-parse", revision + "^{commit}").decode().strip() != revision:
        raise ValueError("Revision is not a commit")
    files = {}
    tree = git(source, "ls-tree", "-rz", revision, "--", "skills", "commands/opencode")
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = PurePosixPath(raw_path.decode())
        parts = path.parts
        managed = (
            str(path) == "skills/LICENSE-RIS"
            or (
                len(parts) >= 3 and parts[0] == "skills" and parts[1].startswith("mis-")
            )
            or (
                len(parts) == 3
                and parts[:2] == ("commands", "opencode")
                and parts[2].startswith("mis-")
                and path.suffix == ".md"
            )
        )
        if not managed:
            continue
        if ".." in parts or path.is_absolute() or mode != "100644" or kind != "blob":
            raise ValueError(f"Unsafe upstream package path: {path}")
        relative = (
            Path("commands", path.name) if parts[0] == "commands" else Path(*parts)
        )
        files[relative] = git(source, "cat-file", "blob", oid)
    if (
        Path("skills/LICENSE-RIS") not in files
        or Path("commands/mis-plan.md") not in files
    ):
        raise ValueError("Revision does not contain a MIS package")
    return files


def safe_path(project, relative):
    destination = project / ".opencode" / relative
    for part in (destination, *destination.parents):
        if part == project:
            break
        if part.is_symlink():
            raise ValueError(f"Destination symlink: {part}")
        if part != destination and part.exists() and not part.is_dir():
            raise ValueError(f"Not a directory: {part}")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"Not a file: {destination}")
    if destination.exists() and destination.stat().st_nlink > 1:
        raise ValueError(f"Destination hard link: {destination}")
    return destination


def update(project, source, revision, from_revision=None, apply=False, install=False):
    project = Path(project).resolve(strict=True)
    source = Path(source).resolve(strict=True)
    if not project.is_dir() or project == source:
        raise ValueError("Choose a consumer directory, not the MIS source")
    record = safe_path(project, RECORD)
    if install and from_revision is not None:
        raise ValueError("Installation does not accept --from-revision")
    if record.exists():
        fields = {}
        for line in record.read_text().split("\n\n", 1)[0].splitlines():
            key, separator, value = line.partition("=")
            if not separator or key in fields:
                raise ValueError("Invalid installation record")
            fields[key] = value
        if (fields.get("format"), fields.get("source"), fields.get("harness")) != (
            "1",
            SOURCE,
            "opencode",
        ):
            raise ValueError("Unsupported installation record/source")
        baseline = fields.get("revision", "")
        if install and baseline != revision:
            raise ValueError("MIS already installed at another revision; use update")
        if from_revision is not None and from_revision != baseline:
            raise ValueError("Explicit baseline disagrees with installation record")
    else:
        if from_revision is None and not install:
            raise ValueError(
                "Missing installation record; establish --from-revision first"
            )
        baseline = from_revision
    old = snapshot(source, baseline) if baseline is not None else {}
    new = snapshot(source, revision)
    # Check unknown files only inside owned skill directories, never other skills.
    owned = {
        p.parts[1]
        for p in old.keys() | new.keys()
        if len(p.parts) >= 3 and p.parts[0] == "skills"
    }
    for name in sorted(owned):
        directory = project / ".opencode/skills" / name
        safe_path(project, Path("skills", name, "SKILL.md"))
        if directory.exists():
            for path in directory.rglob("*"):
                relative = path.relative_to(project / ".opencode")
                if path.is_symlink() or (
                    not path.is_dir() and relative not in old and relative not in new
                ):
                    raise ValueError(
                        f"Unknown file or symlink in managed skill: {path}"
                    )
    changes = []
    for relative in sorted(old.keys() | new.keys()):
        path = safe_path(project, relative)
        current = path.read_bytes() if path.exists() else None
        before, after = old.get(relative), new.get(relative)
        if current != before and current != after:
            raise ValueError(f"Local modification/conflicting addition: {path}")
        if current is None and before is not None and after is not None:
            raise ValueError(f"Missing baseline file: {path}")
        if current != after:
            changes.append((relative, after))
    receipt = (
        f"format=1\nsource={SOURCE}\nrevision={revision}\nharness=opencode\n\n"
        "Managed MIS package; verified against exact upstream Git objects.\n"
    ).encode()
    if not record.exists() or record.read_bytes() != receipt:
        changes.append((RECORD, receipt))
    if apply:
        for relative, content in changes:
            path = project / ".opencode" / relative
            if content is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        for relative, content in new.items():
            if (project / ".opencode" / relative).read_bytes() != content:
                raise ValueError(f"Post-update verification failed: {relative}")
    return baseline, [
        (str(path), "delete" if content is None else "write")
        for path, content in changes
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--from-revision")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--install", action="store_true", help="First package install, not Beads setup"
    )
    args = parser.parse_args()
    try:
        baseline, changes = update(
            args.project,
            args.source,
            args.revision,
            args.from_revision,
            args.apply,
            args.install,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"MIS update: {error}\n")
    print(
        f"MIS: {baseline} -> {args.revision} ({'applied' if args.apply else 'preflight only'})"
    )
    for path, action in changes:
        print(f"  {action}: .opencode/{path}")
    if not changes:
        print("  Verified; no changes")
