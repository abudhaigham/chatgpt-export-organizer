"""Evidence-based extraction and inventory for ChatGPT export assets."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ASSET_ID_PATTERN = re.compile(r"file[-_][A-Za-z0-9]+")


@dataclass(frozen=True)
class DetectedType:
    mime_type: str
    extension: str
    category: str
    confidence: str
    evidence: str


SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png", "Images"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg", "Images"),
    (b"%PDF-", "application/pdf", ".pdf", "Documents"),
    (b"RIFF", "application/octet-stream", "", "Other"),
    (b"ID3", "audio/mpeg", ".mp3", "Audio"),
    (b"GIF87a", "image/gif", ".gif", "Images"),
    (b"GIF89a", "image/gif", ".gif", "Images"),
    (b"BM", "image/bmp", ".bmp", "Images"),
)


EXTENSION_TYPES = {
    ".csv": ("text/csv", "Spreadsheets"),
    ".doc": ("application/msword", "Documents"),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Documents",
    ),
    ".html": ("text/html", "Documents"),
    ".jpeg": ("image/jpeg", "Images"),
    ".jpg": ("image/jpeg", "Images"),
    ".json": ("application/json", "Other"),
    ".md": ("text/markdown", "Documents"),
    ".mp3": ("audio/mpeg", "Audio"),
    ".mp4": ("video/mp4", "Video"),
    ".pdf": ("application/pdf", "Documents"),
    ".png": ("image/png", "Images"),
    ".ppt": ("application/vnd.ms-powerpoint", "Presentations"),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "Presentations",
    ),
    ".txt": ("text/plain", "Documents"),
    ".wav": ("audio/wav", "Audio"),
    ".xls": ("application/vnd.ms-excel", "Spreadsheets"),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Spreadsheets",
    ),
    ".zip": ("application/zip", "Archives"),
}


INVENTORY_FIELDS = (
    "asset_id",
    "dat_filename",
    "restored_filename",
    "original_filename",
    "detected_mime_type",
    "detected_extension",
    "category",
    "type_confidence",
    "type_evidence",
    "size_bytes",
    "sha256",
    "conversation_ids",
    "conversation_titles",
    "associated_roles",
    "origin_classification",
    "classification_confidence",
    "classification_evidence",
    "extraction_status",
    "extracted_path",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_filename(value: str) -> str:
    basename = value.replace("\\", "/").rsplit("/", 1)[-1]
    basename = re.sub(r"[/:\\\x00-\x1f]", "-", basename)
    basename = re.sub(r"\s+", " ", basename).strip(" .")
    return basename[:220] or "asset"


def asset_id_from_name(filename: str) -> str | None:
    matches = ASSET_ID_PATTERN.findall(Path(filename).stem)
    return matches[-1] if matches else None


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def _zip_type(path: Path) -> DetectedType:
    try:
        with zipfile.ZipFile(path) as stream:
            names = set(stream.namelist())
    except (OSError, zipfile.BadZipFile):
        return DetectedType("application/octet-stream", "", "Other", "LOW", "invalid ZIP")
    if any(name.startswith("word/") for name in names):
        return DetectedType(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
            "Documents",
            "HIGH",
            "ZIP container contains word/",
        )
    if any(name.startswith("xl/") for name in names):
        return DetectedType(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
            "Spreadsheets",
            "HIGH",
            "ZIP container contains xl/",
        )
    if any(name.startswith("ppt/") for name in names):
        return DetectedType(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pptx",
            "Presentations",
            "HIGH",
            "ZIP container contains ppt/",
        )
    return DetectedType("application/zip", ".zip", "Archives", "HIGH", "ZIP signature")


def detect_type(path: Path, original_name: str = "") -> DetectedType:
    with path.open("rb") as stream:
        head = stream.read(8192)

    if head.startswith(b"PK\x03\x04"):
        return _zip_type(path)
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return DetectedType("audio/wav", ".wav", "Audio", "HIGH", "RIFF/WAVE signature")
    if len(head) >= 12 and head[4:12] in (b"ftypisom", b"ftypmp42", b"ftypM4V "):
        return DetectedType("video/mp4", ".mp4", "Video", "HIGH", "ISO BMFF signature")
    if head.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n"):
        return DetectedType("image/jp2", ".jp2", "Images", "HIGH", "JPEG 2000 signature")
    for signature, mime_type, extension, category in SIGNATURES:
        if head.startswith(signature) and signature != b"RIFF":
            return DetectedType(mime_type, extension, category, "HIGH", "binary signature")

    suffix = Path(original_name).suffix.lower()
    if suffix in EXTENSION_TYPES:
        mime_type, category = EXTENSION_TYPES[suffix]
        return DetectedType(mime_type, suffix, category, "MEDIUM", "original filename extension")

    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return DetectedType(
            "application/octet-stream", "", "Other", "LOW", "unrecognized binary content"
        )
    stripped = text.lstrip("\ufeff\r\n\t ")
    if stripped.startswith(("{", "[")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        else:
            return DetectedType("application/json", ".json", "Other", "HIGH", "valid JSON")
    if stripped.lower().startswith(("<!doctype html", "<html")):
        return DetectedType("text/html", ".html", "Documents", "HIGH", "HTML markup")
    return DetectedType("text/plain", ".txt", "Documents", "MEDIUM", "UTF-8 text")


def load_asset_map(source_root: Path) -> dict[str, str]:
    path = source_root / "conversation_asset_file_names.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(original).strip()
        for key, original in value.items()
        if isinstance(original, str) and original.strip()
    }


def conversation_associations(
    source_root: Path, known_ids: set[str]
) -> dict[str, dict[str, set[str]]]:
    associations: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "conversation_ids": set(), "titles": set()}
    )
    for path in sorted(source_root.glob("conversations-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        conversations = payload if isinstance(payload, list) else [payload]
        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue
            conversation_id = str(
                conversation.get("conversation_id") or conversation.get("id") or ""
            ).strip()
            title = str(conversation.get("title") or "Untitled conversation").strip()
            mapping = conversation.get("mapping")
            if not isinstance(mapping, dict):
                continue
            for node in mapping.values():
                if not isinstance(node, dict) or not isinstance(node.get("message"), dict):
                    continue
                message = node["message"]
                author = message.get("author")
                role = (
                    str(author.get("role") or "unknown").lower()
                    if isinstance(author, dict)
                    else "unknown"
                )
                referenced = {
                    asset_id
                    for text in iter_strings(message)
                    for asset_id in ASSET_ID_PATTERN.findall(text)
                    if asset_id in known_ids
                }
                for asset_id in referenced:
                    associations[asset_id]["roles"].add(role)
                    if conversation_id:
                        associations[asset_id]["conversation_ids"].add(conversation_id)
                    associations[asset_id]["titles"].add(title)
    return associations


def classify_origin(roles: set[str]) -> tuple[str, str, str]:
    if not roles:
        return "UNREFERENCED", "HIGH", "no conversation message reference found"
    if roles == {"user"}:
        return (
            "ORIGIN_UNCERTAIN",
            "LOW",
            "referenced only by user messages; role association does not prove upload origin",
        )
    if roles == {"assistant"}:
        return (
            "ORIGIN_UNCERTAIN",
            "LOW",
            "referenced only by assistant messages; role association does not prove generation",
        )
    return (
        "SHARED_OR_REUSED",
        "MEDIUM",
        f"referenced by multiple roles: {', '.join(sorted(roles))}",
    )


def collision_safe_target(directory: Path, filename: str, asset_id: str, source: Path) -> Path:
    target = directory / filename
    if not target.exists() or sha256_file(target) == sha256_file(source):
        return target
    suffix = "".join(Path(filename).suffixes)
    stem = filename[: -len(suffix)] if suffix else filename
    counter = 1
    while True:
        extra = f"__{asset_id}" if counter == 1 else f"__{asset_id}_{counter}"
        candidate = directory / f"{stem[:160]}{extra}{suffix}"
        if not candidate.exists() or sha256_file(candidate) == sha256_file(source):
            return candidate
        counter += 1


def extract_assets(source_root: Path, output_root: Path) -> dict[str, Any]:
    dat_paths = sorted(source_root.rglob("*.dat"), key=lambda path: str(path).lower())
    by_id = {
        asset_id: path
        for path in dat_paths
        if (asset_id := asset_id_from_name(path.name)) is not None
    }
    original_names = load_asset_map(source_root)
    associations = conversation_associations(source_root, set(by_id))
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    copied = 0
    existing = 0

    for asset_id, source in sorted(by_id.items()):
        original_name = original_names.get(f"{asset_id}.dat", "")
        detected = detect_type(source, original_name)
        association = associations.get(
            asset_id, {"roles": set(), "conversation_ids": set(), "titles": set()}
        )
        roles = set(association["roles"])
        classification, classification_confidence, classification_evidence = classify_origin(roles)
        classification_folder = (
            "Shared_or_Reused"
            if classification == "SHARED_OR_REUSED"
            else "Unreferenced"
            if classification == "UNREFERENCED"
            else "Origin_Uncertain"
        )
        destination_directory = output_root / classification_folder / detected.category
        destination_directory.mkdir(parents=True, exist_ok=True)

        original_safe = safe_filename(original_name) if original_name else ""
        if original_safe:
            candidate = original_safe
            if not Path(candidate).suffix and detected.extension:
                candidate += detected.extension
        else:
            candidate = f"{asset_id}{detected.extension}"
        destination = collision_safe_target(destination_directory, candidate, asset_id, source)
        source_hash = sha256_file(source)
        if destination.exists() and sha256_file(destination) == source_hash:
            status = "EXISTS_IDENTICAL"
            existing += 1
        else:
            shutil.copy2(source, destination)
            status = "COPIED"
            copied += 1

        rows.append(
            {
                "asset_id": asset_id,
                "dat_filename": source.name,
                "restored_filename": destination.name,
                "original_filename": original_name,
                "detected_mime_type": detected.mime_type,
                "detected_extension": detected.extension,
                "category": detected.category,
                "type_confidence": detected.confidence,
                "type_evidence": detected.evidence,
                "size_bytes": source.stat().st_size,
                "sha256": source_hash,
                "conversation_ids": " | ".join(sorted(association["conversation_ids"])),
                "conversation_titles": " | ".join(sorted(association["titles"])),
                "associated_roles": " | ".join(sorted(roles)),
                "origin_classification": classification,
                "classification_confidence": classification_confidence,
                "classification_evidence": classification_evidence,
                "extraction_status": status,
                "extracted_path": str(destination),
            }
        )

    inventory = output_root / "Asset_Inventory.csv"
    with inventory.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "examined": len(rows),
        "copied": copied,
        "existing": existing,
        "inventory": inventory,
    }
