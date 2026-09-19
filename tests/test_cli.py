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
    expected_folder = (
        tmp_path
        / "Extracted_Chats"
        / "جميع المحادثات — تصنيف المشروع غير متاح في تصدير OpenAI"
        / "Synthetic Chat"
    )
    assert Path(row["Extracted JSON"]) == expected_folder / "Synthetic Chat.json"
    assert pdf == expected_folder / "Synthetic Chat.pdf"
    assert row["Project Classification"] == "Unavailable in OpenAI export"
    notice = tmp_path / "Extracted_Chats" / "PROJECT_CLASSIFICATION_NOTICE.txt"
    assert "لا يتضمن تصدير OpenAI علاقة موثوقة" in notice.read_text(encoding="utf-8")
    assert "00000000-0000-0000-0000-000000000001" not in str(pdf)


def test_duplicate_chat_titles_receive_readable_numbers(tmp_path: Path) -> None:
    try:
        import arabic_reshaper  # noqa: F401
        import bidi  # noqa: F401
        import reportlab  # noqa: F401
    except ImportError:
        pytest.skip("optional PDF dependencies are not installed")

    first = synthetic_conversation()
    second = synthetic_conversation()
    second["id"] = "synthetic-conversation-duplicate"
    second["conversation_id"] = second["id"]
    (tmp_path / "conversations-000.json").write_text(json.dumps([first, second]), encoding="utf-8")

    result = run_cli(tmp_path, "--quiet", "--export-chats")
    assert result.returncode == 0, result.stderr
    root = tmp_path / "Extracted_Chats" / "جميع المحادثات — تصنيف المشروع غير متاح في تصدير OpenAI"
    assert (root / "Synthetic Chat" / "Synthetic Chat.json").exists()
    assert (root / "Synthetic Chat (2)" / "Synthetic Chat (2).json").exists()


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


def make_inbox_archive(workspace: Path, filename: str = "chatgpt-export.zip") -> Path:
    export = workspace / "synthetic-source"
    write_synthetic_export(export)
    incoming = workspace / "01_Incoming_Exports"
    incoming.mkdir(parents=True, exist_ok=True)
    archive = incoming / filename
    with zipfile.ZipFile(archive, "w") as stream:
        for path in export.iterdir():
            stream.write(path, arcname=path.name)
    return archive


def test_inbox_import_moves_archive_only_after_success(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    archive = make_inbox_archive(workspace)

    result = run_cli(
        None,
        "--process-inbox",
        archive.name,
        "--workspace",
        str(workspace),
        "--quiet",
    )
    assert result.returncode == 0, result.stderr
    assert not archive.exists()
    processed = workspace / "02_Processed_Exports" / archive.name
    assert processed.exists()
    assert processed.with_suffix(".zip.processed.json").exists()
    imported = next((workspace / "imports").iterdir())
    assert (imported / "IMPORT_COMPLETE.json").exists()
    assert (imported / "results" / "ChatGPT_DAT_Chat_Index.csv").exists()


def test_inbox_rejects_invalid_and_duplicate_archives(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    incoming = workspace / "01_Incoming_Exports"
    incoming.mkdir(parents=True)
    invalid = incoming / "broken.zip"
    invalid.write_bytes(b"PK\x03\x04incomplete")

    rejected = run_cli(
        None,
        "--process-inbox",
        invalid.name,
        "--workspace",
        str(workspace),
    )
    assert rejected.returncode == 2
    assert not invalid.exists()
    assert (workspace / "03_Rejected_Exports" / invalid.name).exists()

    archive = make_inbox_archive(workspace)
    first = run_cli(
        None,
        "--process-inbox",
        archive.name,
        "--workspace",
        str(workspace),
        "--quiet",
    )
    assert first.returncode == 0, first.stderr
    processed = workspace / "02_Processed_Exports" / archive.name
    duplicate = incoming / archive.name
    duplicate.write_bytes(processed.read_bytes())
    second = run_cli(
        None,
        "--process-inbox",
        duplicate.name,
        "--workspace",
        str(workspace),
    )
    assert second.returncode == 2
    assert "duplicate" in second.stderr
    assert not duplicate.exists()
