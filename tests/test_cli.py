from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
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


def run_cli(export: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source = Path(__file__).parents[1] / "src"
    environment["PYTHONPATH"] = str(source)
    return subprocess.run(
        [sys.executable, "-m", "chatgpt_export_organizer", str(export), *arguments],
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
