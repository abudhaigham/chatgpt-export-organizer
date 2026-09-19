"""Controlled inbox lifecycle for ChatGPT export archives."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

INCOMING_DIRECTORY = "01_Incoming_Exports"
PROCESSED_DIRECTORY = "02_Processed_Exports"
REJECTED_DIRECTORY = "03_Rejected_Exports"


@dataclass(frozen=True)
class ArchiveInspection:
    path: str
    size: int
    sha256: str
    valid: bool
    error: str


def default_workspace() -> Path:
    """Return the recommended user-facing workspace on macOS."""
    return Path.home() / "Documents" / "My Training" / "ChatGPT Export Organizer"


def ensure_inbox_layout(workspace: Path) -> dict[str, Path]:
    """Create and return the managed inbox directories."""
    workspace = workspace.expanduser().resolve()
    paths = {
        "workspace": workspace,
        "incoming": workspace / INCOMING_DIRECTORY,
        "processed": workspace / PROCESSED_DIRECTORY,
        "rejected": workspace / REJECTED_DIRECTORY,
        "imports": workspace / "imports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def incoming_archives(workspace: Path) -> list[Path]:
    """Return visible ZIP archives in the controlled inbox."""
    incoming = ensure_inbox_layout(workspace)["incoming"]
    return sorted(
        (
            path
            for path in incoming.iterdir()
            if path.is_file() and not path.name.startswith(".") and path.suffix.lower() == ".zip"
        ),
        key=lambda path: (path.stat().st_mtime, path.name.casefold()),
        reverse=True,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_archive(path: Path) -> ArchiveInspection:
    """Read every member and report whether an archive is complete and valid."""
    path = path.expanduser().resolve()
    size = 0
    digest = ""
    try:
        size = path.stat().st_size
        digest = sha256_file(path)
        if not zipfile.is_zipfile(path):
            raise zipfile.BadZipFile("missing or invalid ZIP central directory")
        with zipfile.ZipFile(path) as stream:
            failed_member = stream.testzip()
        if failed_member:
            raise zipfile.BadZipFile(f"CRC check failed for member: {failed_member}")
    except (OSError, zipfile.BadZipFile) as error:
        return ArchiveInspection(
            path=str(path),
            size=path.stat().st_size if path.exists() else 0,
            sha256=digest,
            valid=False,
            error=f"{type(error).__name__}: {error}",
        )
    return ArchiveInspection(path=str(path), size=size, sha256=digest, valid=True, error="")


def imported_digests(workspace: Path) -> set[str]:
    """Load source digests recorded by completed inbox imports."""
    imports = ensure_inbox_layout(workspace)["imports"]
    digests: set[str] = set()
    for completion in imports.glob("*/IMPORT_COMPLETE.json"):
        try:
            data = json.loads(completion.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        digest = data.get("source_sha256")
        if isinstance(digest, str) and digest:
            digests.add(digest)
    return digests


def record_import_completion(import_root: Path, inspection: ArchiveInspection) -> Path:
    """Record that all requested processing finished before the inbox file moves."""
    record = {
        "format_version": 1,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": inspection.sha256,
        "source_size": inspection.size,
        "status": "complete",
    }
    path = import_root / "IMPORT_COMPLETE.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def collision_safe_destination(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = directory / f"{stem}__{stamp}{suffix}"
    number = 2
    while candidate.exists():
        candidate = directory / f"{stem}__{stamp}__{number}{suffix}"
        number += 1
    return candidate


def move_with_record(
    source: Path,
    destination_directory: Path,
    inspection: ArchiveInspection,
    disposition: str,
    detail: str,
) -> Path:
    """Move an inbox archive and write an adjacent non-sensitive lifecycle record."""
    destination_directory.mkdir(parents=True, exist_ok=True)
    target = collision_safe_destination(destination_directory, source.name)
    shutil.move(str(source), str(target))
    record = {
        "format_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "disposition": disposition,
        "detail": detail,
        "archive_name": target.name,
        "inspection": asdict(inspection) | {"path": target.name},
    }
    record_path = target.with_suffix(f"{target.suffix}.{disposition.lower()}.json")
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def select_inbox_archive(workspace: Path, requested_name: str | None = None) -> Path:
    """Select one archive without silently guessing among multiple candidates."""
    paths = ensure_inbox_layout(workspace)
    archives = incoming_archives(workspace)
    if requested_name:
        requested = Path(requested_name)
        if requested.name != requested_name or requested.suffix.lower() != ".zip":
            raise ValueError("the inbox selection must be one ZIP filename, not a path")
        selected = paths["incoming"] / requested_name
        if selected not in archives:
            raise ValueError(f"selected inbox archive was not found: {requested_name}")
        return selected
    if not archives:
        raise ValueError(f"no ZIP archives found in {paths['incoming']}")
    if len(archives) > 1:
        names = ", ".join(path.name for path in archives)
        raise ValueError(f"multiple ZIP archives found; choose one explicitly: {names}")
    return archives[0]
