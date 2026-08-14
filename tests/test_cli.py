from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def synthetic_conversation() -> dict:
    return {
        "title": "Synthetic Chat",
        "id": "00000000-0000-0000-0000-000000000001",
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "create_time": 1,
        "update_time": 2,
        "current_node": "assistant",
        "mapping": {
            "user": {
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "create_time": 1,
                    "content": {
                        "parts": [
                            "Synthetic attachment",
                            {"asset_pointer": "file-service://file-demo123"},
                        ]
                    },
                },
            },
            "assistant": {
                "parent": "user",
                "message": {
                    "author": {"role": "assistant"},
                    "create_time": 2,
                    "content": {"parts": ["Synthetic response"]},
                },
            },
        },
    }


def run_cli(export: Path | None, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source = Path(__file__).parents[1] / "src"
    environment["PYTHONPATH"] = str(source)
    command = [sys.executable, "-m", "chatgpt_export_organizer"]
    if export is not None:
        command.append(str(export))
    command.extend(arguments)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_scan_and_group_synthetic_asset(tmp_path: Path) -> None:
    asset = tmp_path / "file-demo123.dat"
    asset.write_bytes(b"synthetic")
    (tmp_path / "conversations-000.json").write_text(
        json.dumps([synthetic_conversation()]), encoding="utf-8"
    )
    (tmp_path / "conversation_asset_file_names.json").write_text(
        json.dumps({"file-demo123.dat": "notes.txt"}), encoding="utf-8"
    )

    result = run_cli(tmp_path, "--quiet", "--group", "--restore-originals")
    assert result.returncode == 0, result.stderr

    report = tmp_path / "ChatGPT_DAT_Chat_Index.csv"
    with report.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["Status"] == "Matched"
    assert rows[0]["Chat Titles"] == "Synthetic Chat"

    group = tmp_path / "Grouped_DAT_Files" / "Synthetic Chat"
    assert (group / "Synthetic Chat__file-demo123.dat").exists()
    assert (group / "notes.txt").read_bytes() == b"synthetic"


def test_export_single_chat_to_json_and_pdf(tmp_path: Path) -> None:
    try:
        import arabic_reshaper  # noqa: F401
        import bidi  # noqa: F401
        import reportlab  # noqa: F401
    except ImportError:
        pytest.skip("optional PDF dependencies are not installed")

    (tmp_path / "file-demo123.dat").write_bytes(b"synthetic")
    (tmp_path / "conversations-000.json").write_text(
        json.dumps([synthetic_conversation()]), encoding="utf-8"
    )

    result = run_cli(
        tmp_path,
        "--quiet",
        "--export-chats",
        "--chat-id",
        "00000000-0000-0000-0000-000000000001",
    )
    assert result.returncode == 0, result.stderr
    report = tmp_path / "Extracted_Chats" / "Chat_Export_Report.csv"
    with report.open(encoding="utf-8-sig") as stream:
        row = next(csv.DictReader(stream))
    assert row["Status"].startswith("Complete")
    assert Path(row["Extracted JSON"]).exists()
    pdf = Path(row["PDF"])
    assert pdf.read_bytes().startswith(b"%PDF-")


def write_synthetic_export(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "file-demo123.dat").write_bytes(b"synthetic")
    (folder / "conversations-000.json").write_text(
        json.dumps([synthetic_conversation()]), encoding="utf-8"
    )
    (folder / "conversation_asset_file_names.json").write_text(
        json.dumps({"file-demo123.dat": "notes.txt"}), encoding="utf-8"
    )


def test_managed_folder_import_is_isolated_and_repeatable(tmp_path: Path) -> None:
    source = tmp_path / "incoming-export"
    workspace = tmp_path / "workspace"
    write_synthetic_export(source)

    arguments = (
        "--import-export",
        str(source),
        "--workspace",
        str(workspace),
        "--quiet",
        "--group",
        "--restore-originals",
    )
    first = run_cli(None, *arguments)
    second = run_cli(None, *arguments)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    imports = sorted((workspace / "imports").iterdir())
    assert len(imports) == 2
    assert imports[0] != imports[1]
    for imported in imports:
        assert (imported / "source" / "file-demo123.dat").read_bytes() == b"synthetic"
        assert (imported / "import_manifest.json").exists()
        assert (imported / "results" / "ChatGPT_DAT_Chat_Index.csv").exists()
        group = imported / "results" / "Grouped_DAT_Files" / "Synthetic Chat"
        assert (group / "Synthetic Chat__file-demo123.dat").exists()
        assert (group / "notes.txt").exists()

    assert (source / "file-demo123.dat").read_bytes() == b"synthetic"
    assert not (source / "ChatGPT_DAT_Chat_Index.csv").exists()


def test_managed_zip_import_and_source_protection(tmp_path: Path) -> None:
    export = tmp_path / "export-data"
    write_synthetic_export(export)
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        for path in export.iterdir():
            stream.write(path, arcname=f"wrapped-export/{path.name}")

    workspace = tmp_path / "workspace"
    result = run_cli(
        None,
        "--import-export",
        str(archive),
        "--workspace",
        str(workspace),
        "--quiet",
    )
    assert result.returncode == 0, result.stderr
    imported = next((workspace / "imports").iterdir())
    manifest = json.loads((imported / "import_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_type"] == "zip"
    assert len(manifest["source_sha256"]) == 64
    assert (imported / "results" / "ChatGPT_DAT_Chat_Index.csv").exists()

    rejected = run_cli(
        None,
        "--import-export",
        str(archive),
        "--workspace",
        str(workspace),
        "--move",
        "--group",
    )
    assert rejected.returncode == 2
    assert "disabled for managed imports" in rejected.stderr


def test_managed_import_supports_exports_without_assets(tmp_path: Path) -> None:
    source = tmp_path / "conversation-only"
    source.mkdir()
    (source / "conversations-000.json").write_text(
        json.dumps([synthetic_conversation()]), encoding="utf-8"
    )
    workspace = tmp_path / "workspace"

    result = run_cli(
        None,
        "--import-export",
        str(source),
        "--workspace",
        str(workspace),
        "--quiet",
    )
    assert result.returncode == 0, result.stderr
    imported = next((workspace / "imports").iterdir())
    report = imported / "results" / "ChatGPT_DAT_Chat_Index.csv"
    with report.open(encoding="utf-8-sig") as stream:
        assert list(csv.DictReader(stream)) == []


def test_managed_import_rejects_zip_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../outside.txt", "must not escape")
        stream.writestr("conversations-000.json", "[]")
    workspace = tmp_path / "workspace"

    result = run_cli(
        None,
        "--import-export",
        str(archive),
        "--workspace",
        str(workspace),
    )
    assert result.returncode == 2
    assert "unsafe ZIP path" in result.stderr
    assert not (tmp_path / "outside.txt").exists()
