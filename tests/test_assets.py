from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from chatgpt_export_organizer.assets import detect_type, extract_assets


def test_detects_binary_signatures_and_office_containers(tmp_path: Path) -> None:
    png = tmp_path / "image.dat"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"synthetic")
    assert detect_type(png).extension == ".png"

    document = tmp_path / "document.dat"
    with zipfile.ZipFile(document, "w") as stream:
        stream.writestr("[Content_Types].xml", "synthetic")
        stream.writestr("word/document.xml", "synthetic")
    detected = detect_type(document)
    assert detected.extension == ".docx"
    assert detected.category == "Documents"


def test_extracts_assets_without_claiming_unproven_origin(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "results" / "ChatGPT_Files"
    source.mkdir()
    (source / "file-user123.dat").write_bytes(b"%PDF-synthetic")
    (source / "file-assistant456.dat").write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
    (source / "file-orphan789.dat").write_text("plain text", encoding="utf-8")
    (source / "conversation_asset_file_names.json").write_text(
        json.dumps(
            {
                "file-user123.dat": "user-report.pdf",
                "file-assistant456.dat": "generated-image.png",
            }
        ),
        encoding="utf-8",
    )
    conversation = {
        "title": "Synthetic",
        "conversation_id": "conversation-1",
        "mapping": {
            "user": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": [{"asset_pointer": "file-service://file-user123"}]},
                }
            },
            "assistant": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "parts": [{"asset_pointer": "file-service://file-assistant456"}]
                    },
                }
            },
        },
    }
    (source / "conversations-000.json").write_text(
        json.dumps([conversation]), encoding="utf-8"
    )

    result = extract_assets(source, output)
    assert result["examined"] == 3
    assert result["copied"] == 3
    assert (output / "Origin_Uncertain" / "Documents" / "user-report.pdf").exists()
    assert (output / "Origin_Uncertain" / "Images" / "generated-image.png").exists()
    assert (output / "Unreferenced" / "Documents" / "file-orphan789.txt").exists()

    with (output / "Asset_Inventory.csv").open(encoding="utf-8-sig") as stream:
        rows = {row["asset_id"]: row for row in csv.DictReader(stream)}
    assert rows["file-user123"]["associated_roles"] == "user"
    assert rows["file-user123"]["origin_classification"] == "ORIGIN_UNCERTAIN"
    assert rows["file-assistant456"]["origin_classification"] == "ORIGIN_UNCERTAIN"
    assert rows["file-orphan789"]["origin_classification"] == "UNREFERENCED"


def test_repeated_extraction_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "results" / "ChatGPT_Files"
    source.mkdir()
    (source / "file-demo123.dat").write_bytes(b"%PDF-synthetic")
    (source / "conversations-000.json").write_text("[]", encoding="utf-8")

    first = extract_assets(source, output)
    second = extract_assets(source, output)
    assert first["copied"] == 1
    assert second["copied"] == 0
    assert second["existing"] == 1
