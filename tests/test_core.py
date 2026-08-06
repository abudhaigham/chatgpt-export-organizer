from __future__ import annotations

from pathlib import Path

from chatgpt_export_organizer.cli import (
    asset_id_from_name,
    canonical_messages,
    conservative_pdf_text,
    proposed_dat_name,
    safe_original_filename,
    safe_title_prefix,
    valid_pdf_file,
)


def test_asset_id_survives_chat_prefix() -> None:
    assert asset_id_from_name("file-demo123.dat") == "file-demo123"
    assert (
        asset_id_from_name("Project Notes__file_demoasset0000000000000001.dat")
        == "file_demoasset0000000000000001"
    )


def test_safe_names_remove_path_characters() -> None:
    assert safe_title_prefix(["Project / Notes: 2026"]) == "Project - Notes- 2026"
    assert safe_original_filename("../../private/report.pdf") == "report.pdf"
    assert proposed_dat_name("file-demo123", ["Project Notes"]).endswith("__file-demo123.dat")


def test_canonical_messages_follow_active_branch() -> None:
    conversation = {
        "current_node": "assistant",
        "mapping": {
            "root": {"parent": None, "message": None},
            "user": {
                "parent": "root",
                "message": {"author": {"role": "user"}, "create_time": 1},
            },
            "assistant": {
                "parent": "user",
                "message": {"author": {"role": "assistant"}, "create_time": 2},
            },
            "alternate": {
                "parent": "user",
                "message": {"author": {"role": "assistant"}, "create_time": 3},
            },
        },
    }
    messages = canonical_messages(conversation)
    assert [message["author"]["role"] for message in messages] == ["user", "assistant"]
    assert [message["create_time"] for message in messages] == [1, 2]


def test_compatibility_cleanup_removes_internal_citations() -> None:
    text = "Answer\ue200cite\ue202turn0search4\ue201 👍 complete"
    cleaned = conservative_pdf_text(text)
    assert "turn0search4" not in cleaned
    assert "[symbol]" in cleaned


def test_pdf_validator_rejects_non_pdf(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_text("not a pdf", encoding="utf-8")
    assert not valid_pdf_file(invalid)
