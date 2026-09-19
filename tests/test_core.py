from __future__ import annotations

from pathlib import Path

from chatgpt_export_organizer.cli import (
    asset_id_from_name,
    canonical_messages,
    conservative_pdf_text,
    conversation_output_stem,
    proposed_dat_name,
    safe_original_filename,
    safe_title_prefix,
    valid_pdf_file,
)
from chatgpt_export_organizer.gui import human_size
from chatgpt_export_organizer.inbox import (
    ensure_inbox_layout,
    incoming_archives,
    inspect_archive,
    select_inbox_archive,
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


def test_conversation_output_name_uses_title_without_identifier() -> None:
    conversation = {
        "title": "خارطة المؤسس التقني لتأسيس شركة برمجيات بالذكاء الاصطناعي",
        "conversation_id": "synthetic-conversation-core",
    }
    assert conversation_output_stem(conversation) == conversation["title"]
    assert conversation_output_stem(conversation, 2) == f"{conversation['title']} (2)"


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


def test_inbox_layout_and_unambiguous_selection(tmp_path: Path) -> None:
    paths = ensure_inbox_layout(tmp_path)
    assert paths["incoming"].is_dir()
    assert paths["processed"].is_dir()
    assert paths["rejected"].is_dir()
    assert paths["imports"].is_dir()

    first = paths["incoming"] / "first.zip"
    first.write_bytes(b"not yet inspected")
    assert incoming_archives(tmp_path) == [first]
    assert select_inbox_archive(tmp_path) == first

    second = paths["incoming"] / "second.zip"
    second.write_bytes(b"not yet inspected")
    try:
        select_inbox_archive(tmp_path)
    except ValueError as error:
        assert "multiple ZIP archives" in str(error)
    else:
        raise AssertionError("multiple inbox archives must require an explicit choice")
    assert select_inbox_archive(tmp_path, "second.zip") == second


def test_archive_inspection_checks_complete_zip(tmp_path: Path) -> None:
    import zipfile

    valid = tmp_path / "valid.zip"
    with zipfile.ZipFile(valid, "w") as stream:
        stream.writestr("synthetic.txt", "safe")
    inspection = inspect_archive(valid)
    assert inspection.valid
    assert len(inspection.sha256) == 64

    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"PK\x03\x04incomplete")
    rejected = inspect_archive(invalid)
    assert not rejected.valid
    assert "central directory" in rejected.error


def test_human_size_for_gui() -> None:
    assert human_size(1024) == "1.0 KB"
