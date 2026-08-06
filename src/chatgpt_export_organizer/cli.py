#!/usr/bin/env python3
"""Organize and extract data from a local ChatGPT export.

No third-party packages are required.
"""

from __future__ import annotations

import argparse
import csv
import filecmp
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

ASSET_ID_PATTERN = re.compile(r"file[-_][A-Za-z0-9]+")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Map and organize ChatGPT export assets, restore original filenames, "
            "and extract conversations to JSON and PDF."
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Extracted ChatGPT export folder (default: current directory).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output CSV path (default: <folder>/ChatGPT_DAT_Chat_Index.csv).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Find .dat and conversations-*.json files in subfolders too.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Print only the final summary instead of every asset.",
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help=(
            "Rename matched .dat files by prefixing their chat title. Without "
            "this option, proposed names are reported but files are unchanged."
        ),
    )
    parser.add_argument(
        "--group",
        nargs="?",
        const="Grouped_DAT_Files",
        metavar="DIRECTORY",
        help=(
            "Copy assets into chat-name folders. The default destination is "
            "<folder>/Grouped_DAT_Files; optionally provide another directory."
        ),
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="With --group, move original assets instead of copying them.",
    )
    parser.add_argument(
        "--restore-originals",
        action="store_true",
        help=(
            "With --group, create an additional copy using the original filename "
            "and extension recorded in conversation_asset_file_names.json."
        ),
    )
    parser.add_argument(
        "--export-chats",
        nargs="?",
        const="Extracted_Chats",
        metavar="DIRECTORY",
        help=(
            "Extract every conversation to its own JSON file and readable PDF. "
            "Default destination: <folder>/Extracted_Chats."
        ),
    )
    parser.add_argument(
        "--chat-id",
        action="append",
        help="With --export-chats, export only this conversation ID; repeat as needed.",
    )
    parser.add_argument(
        "--overwrite-chat-exports",
        action="store_true",
        help="Recreate existing extracted JSON and PDF chat files.",
    )
    parser.add_argument(
        "--font",
        help="Optional Unicode TrueType font path for chat PDFs.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def discover_dat_names(folder: Path, recursive: bool) -> list[str]:
    files = folder.rglob("*.dat") if recursive else folder.glob("*.dat")
    names = sorted({item.name for item in files if item.is_file()})
    if names:
        return names

    # Useful when only export metadata has been copied beside the script.
    manifest = folder / "export_manifest.json"
    if manifest.exists():
        try:
            data = load_json(manifest)
            names = sorted(
                {
                    Path(item["path"]).name
                    for item in data.get("export_files", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("path"), str)
                    and item["path"].lower().endswith(".dat")
                }
            )
        except (OSError, json.JSONDecodeError, TypeError) as error:
            print(f"Warning: could not read {manifest.name}: {error}", file=sys.stderr)
    return names


def discover_dat_paths(folder: Path, recursive: bool) -> list[Path]:
    files = folder.rglob("*.dat") if recursive else folder.glob("*.dat")
    return sorted((item for item in files if item.is_file()), key=lambda item: str(item).lower())


def asset_id_from_name(filename: str) -> str | None:
    """Recover the stable asset ID from original or already-prefixed names."""
    candidates = ASSET_ID_PATTERN.findall(Path(filename).stem)
    return candidates[-1] if candidates else None


def safe_title_prefix(titles: list[str]) -> str:
    if not titles:
        return ""
    prefix = " + ".join(dict.fromkeys(titles))
    prefix = re.sub(r"[/:\\\x00-\x1f]", "-", prefix)
    prefix = re.sub(r"\s+", " ", prefix).strip(" .-")
    return prefix or "Untitled conversation"


def truncate_utf8(text: str, maximum_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return text
    encoded = encoded[:maximum_bytes]
    while encoded:
        try:
            return encoded.decode("utf-8").rstrip(" .-")
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return "Chat"


def proposed_dat_name(asset_id: str, titles: list[str]) -> str:
    canonical = f"{asset_id}.dat"
    prefix = safe_title_prefix(titles)
    if not prefix:
        return canonical
    # Stay comfortably below the common 255-byte filesystem filename limit.
    separator = "__"
    available = 240 - len((separator + canonical).encode("utf-8"))
    prefix = truncate_utf8(prefix, max(20, available))
    return f"{prefix}{separator}{canonical}"


def safe_original_filename(original_name: str) -> str:
    """Return a safe basename while retaining the original extension."""
    basename = original_name.replace("\\", "/").rsplit("/", 1)[-1]
    basename = re.sub(r"[/:\\\x00-\x1f]", "-", basename)
    basename = re.sub(r"\s+", " ", basename).strip(" .")
    if not basename:
        return "Original file"
    suffix = "".join(Path(basename).suffixes)
    stem = basename[: -len(suffix)] if suffix else basename
    available = 240 - len(suffix.encode("utf-8"))
    return f"{truncate_utf8(stem, max(20, available))}{suffix}"


def original_copy_destination(
    folder: Path, original_name: str, asset_id: str, source: Path
) -> tuple[Path, bool]:
    """Choose a collision-safe target; bool is true when identical content exists."""
    filename = safe_original_filename(original_name)
    target = folder / filename
    if not target.exists():
        return target, False
    if filecmp.cmp(source, target, shallow=False):
        return target, True

    suffix = "".join(Path(filename).suffixes)
    stem = filename[: -len(suffix)] if suffix else filename
    alternate_name = f"{truncate_utf8(stem, 150)}__{asset_id}{suffix}"
    alternate = folder / alternate_name
    if not alternate.exists():
        return alternate, False
    if filecmp.cmp(source, alternate, shallow=False):
        return alternate, True

    counter = 2
    while True:
        numbered = folder / f"{truncate_utf8(stem, 140)}__{asset_id}_{counter}{suffix}"
        if not numbered.exists():
            return numbered, False
        if filecmp.cmp(source, numbered, shallow=False):
            return numbered, True
        counter += 1


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


def asset_reference_counts(conversation: dict[str, Any], known_ids: set[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in iter_strings(conversation):
        for asset_id in ASSET_ID_PATTERN.findall(text):
            if asset_id in known_ids:
                counts[asset_id] += 1
    return counts


def conversation_files(folder: Path, recursive: bool) -> list[Path]:
    files = (
        folder.rglob("conversations-*.json") if recursive else folder.glob("conversations-*.json")
    )
    return sorted(path for path in files if path.is_file())


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


class PdfDependencyError(RuntimeError):
    pass


def prepare_pdf_runtime(font_override: str | None) -> dict[str, Any]:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as error:
        raise PdfDependencyError(
            "PDF export requires reportlab, arabic-reshaper, and python-bidi. "
            "Install them with: python3 -m pip install reportlab arabic-reshaper python-bidi"
        ) from error

    if font_override:
        candidates = [(Path(font_override).expanduser(), Path(font_override).expanduser())]
    else:
        candidates = [
            (
                Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            ),
            (
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            ),
            (
                Path("/Library/Fonts/Arial Unicode.ttf"),
                Path("/Library/Fonts/Arial Unicode.ttf"),
            ),
            (
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ),
            (
                Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
                Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
            ),
        ]

    font_error = None
    for regular, bold in candidates:
        if not regular.exists():
            continue
        if not bold.exists():
            bold = regular
        try:
            pdfmetrics.registerFont(TTFont("ChatSans", str(regular)))
            pdfmetrics.registerFont(TTFont("ChatSans-Bold", str(bold)))
            break
        except Exception as error:  # ReportLab raises different font parse errors.
            font_error = error
    else:
        detail = f" Last font error: {font_error}" if font_error else ""
        raise PdfDependencyError(
            "No suitable Unicode TrueType font was found. Supply one with "
            "--font /path/to/font.ttf." + detail
        )

    return {
        "arabic_reshaper": arabic_reshaper,
        "get_display": get_display,
        "colors": colors,
        "TA_CENTER": TA_CENTER,
        "TA_LEFT": TA_LEFT,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "mm": mm,
        "PageBreak": PageBreak,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
    }


def canonical_messages(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conversation.get("mapping") or {}
    node_id = conversation.get("current_node")
    messages: list[dict[str, Any]] = []
    seen: set[str] = set()
    while node_id and node_id not in seen:
        seen.add(node_id)
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            break
        message = node.get("message")
        if isinstance(message, dict) and message.get("author", {}).get("role") in {
            "user",
            "assistant",
        }:
            messages.append(message)
        node_id = node.get("parent")
    if messages:
        return list(reversed(messages))

    fallback = []
    for node in mapping.values():
        message = node.get("message") if isinstance(node, dict) else None
        if isinstance(message, dict) and message.get("author", {}).get("role") in {
            "user",
            "assistant",
        }:
            fallback.append(message)
    return sorted(fallback, key=lambda item: item.get("create_time") or 0)


def exported_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict):
            if isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif part.get("asset_pointer"):
                texts.append(f"[Attached asset: {part['asset_pointer']}]")
    return "\n\n".join(texts).strip()


def text_chunks(text: str, limit: int = 7000) -> list[str]:
    if not text:
        return ["[No textual content]"]
    result = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        result.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        result.append(text)
    return result


def conservative_pdf_text(text: str) -> str:
    """Remove export markers and replace font-risky astral symbols."""
    # Remove complete internal citation/file-citation tokens before stripping
    # their private-use delimiters, so identifiers such as turn0search4 do not leak.
    text = re.sub(r"\ue200.*?\ue201", "", text, flags=re.DOTALL)
    result = []
    symbol_pending = False
    for character in text:
        codepoint = ord(character)
        category = unicodedata.category(character)
        if category in {"Co", "Cs"} or codepoint in {0xFE0E, 0xFE0F}:
            continue
        if category == "Cf":
            continue
        if codepoint > 0xFFFF:
            if not symbol_pending:
                result.append("[symbol]")
                symbol_pending = True
            continue
        symbol_pending = False
        result.append(character)
    return "".join(result)


def pdf_display_text(text: str, runtime: dict[str, Any], conservative: bool = False) -> str:
    if conservative:
        text = conservative_pdf_text(text)
    arabic = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
    visual_lines = []
    for line in text.split("\n"):
        if arabic.search(line):
            line = runtime["get_display"](runtime["arabic_reshaper"].reshape(line))
        visual_lines.append(line)
    return "\n".join(visual_lines)


def pdf_markup(text: str, runtime: dict[str, Any], conservative: bool = False) -> str:
    text = pdf_display_text(text, runtime, conservative)
    text = escape(text).replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.replace("\n", "<br/>")


def utc_time(value: Any) -> str:
    if not value:
        return "Timestamp unavailable"
    return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def conversation_output_stem(conversation: dict[str, Any]) -> str:
    title = clean(conversation.get("title")) or "Untitled conversation"
    conversation_id = clean(conversation.get("conversation_id") or conversation.get("id"))
    safe_title = truncate_utf8(safe_title_prefix([title]), 140)
    return f"{safe_title}__{conversation_id or 'unknown-id'}"


def create_conversation_pdf(
    conversation: dict[str, Any],
    output: Path,
    runtime: dict[str, Any],
    conservative: bool = False,
) -> int:
    colors = runtime["colors"]
    A4 = runtime["A4"]
    mm = runtime["mm"]
    ParagraphStyle = runtime["ParagraphStyle"]
    styles = runtime["getSampleStyleSheet"]()
    Paragraph = runtime["Paragraph"]
    Spacer = runtime["Spacer"]
    PageBreak = runtime["PageBreak"]
    SimpleDocTemplate = runtime["SimpleDocTemplate"]

    messages = canonical_messages(conversation)
    title = clean(conversation.get("title")) or "Untitled conversation"
    conversation_id = clean(conversation.get("conversation_id") or conversation.get("id"))
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="ChatSans-Bold",
        fontSize=21,
        leading=26,
        textColor=colors.HexColor("#17365D"),
        alignment=runtime["TA_CENTER"],
        spaceAfter=10,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="ChatSans",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#4B5563"),
        alignment=runtime["TA_CENTER"],
    )
    user_head = ParagraphStyle(
        "UserHead",
        parent=styles["Heading3"],
        fontName="ChatSans-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.white,
        backColor=colors.HexColor("#0B6E99"),
        borderPadding=(5, 7, 5, 7),
        spaceBefore=9,
        spaceAfter=5,
    )
    assistant_head = ParagraphStyle(
        "AssistantHead", parent=user_head, backColor=colors.HexColor("#10A37F")
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="ChatSans",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1F2937"),
        alignment=runtime["TA_LEFT"],
        spaceAfter=4,
        splitLongWords=True,
        wordWrap="LTR",
    )

    metadata_title = conservative_pdf_text(title) if conservative else title
    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title=metadata_title,
        author="ChatGPT export conversion",
    )

    footer_title = truncate_utf8(pdf_display_text(title, runtime, conservative), 90)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("ChatSans", 7.5)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(17 * mm, 9 * mm, f"{footer_title} - ChatGPT export")
        canvas.drawRightString(A4[0] - 17 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    story = [
        Spacer(1, 25 * mm),
        Paragraph(pdf_markup(title, runtime, conservative), title_style),
        Paragraph(
            f"Conversation ID: {pdf_markup(conversation_id, runtime, conservative)}",
            meta_style,
        ),
        Paragraph(f"Created: {utc_time(conversation.get('create_time'))}", meta_style),
        Paragraph(f"Last updated: {utc_time(conversation.get('update_time'))}", meta_style),
        Paragraph(f"Messages in active branch: {len(messages):,}", meta_style),
        Spacer(1, 9 * mm),
        Paragraph(
            "This PDF reproduces the chronological user-assistant message path selected "
            "as the active branch in the ChatGPT data export.",
            meta_style,
        ),
        PageBreak(),
    ]
    for number, message in enumerate(messages, start=1):
        role = message.get("author", {}).get("role", "unknown")
        label = "User" if role == "user" else "ChatGPT"
        head_style = user_head if role == "user" else assistant_head
        story.append(
            Paragraph(f"{number}. {label} - {utc_time(message.get('create_time'))}", head_style)
        )
        for chunk in text_chunks(exported_message_text(message)):
            story.append(Paragraph(pdf_markup(chunk, runtime, conservative), body_style))
        story.append(Spacer(1, 2 * mm))

    output.parent.mkdir(parents=True, exist_ok=True)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return len(messages)


def valid_pdf_file(path: Path) -> bool:
    try:
        if path.stat().st_size < 100:
            return False
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return False
            stream.seek(max(0, path.stat().st_size - 4096))
            return b"%%EOF" in stream.read()
    except OSError:
        return False


def export_conversations(
    sources: list[Path], destination: Path, args: argparse.Namespace
) -> dict[str, int]:
    runtime = prepare_pdf_runtime(args.font)
    requested_ids = set(args.chat_id or [])
    destination.mkdir(parents=True, exist_ok=True)
    report_rows = []
    processed = 0

    for source in sources:
        try:
            data = load_json(source)
        except (OSError, json.JSONDecodeError) as error:
            report_rows.append(
                {
                    "Chat Title": "",
                    "Conversation ID": "",
                    "Source JSON": source.name,
                    "Message Count": "",
                    "Extracted JSON": "",
                    "PDF": "",
                    "Status": "Source failed",
                    "Error": clean(error),
                }
            )
            continue

        conversations = data if isinstance(data, list) else [data]
        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue
            conversation_id = clean(conversation.get("conversation_id") or conversation.get("id"))
            if requested_ids and conversation_id not in requested_ids:
                continue
            processed += 1
            title = clean(conversation.get("title")) or "Untitled conversation"
            stem = conversation_output_stem(conversation)
            chat_folder = destination / stem
            json_path = chat_folder / f"{stem}.json"
            pdf_path = chat_folder / f"{stem}.pdf"
            status = "Complete"
            error_text = ""
            message_count = len(canonical_messages(conversation))
            try:
                chat_folder.mkdir(parents=True, exist_ok=True)
                if args.overwrite_chat_exports or not json_path.exists():
                    with json_path.open("w", encoding="utf-8") as stream:
                        json.dump(conversation, stream, ensure_ascii=False, indent=2)
                if args.overwrite_chat_exports or not valid_pdf_file(pdf_path):
                    try:
                        message_count = create_conversation_pdf(
                            conversation, pdf_path, runtime, conservative=False
                        )
                    except AssertionError:
                        pdf_path.unlink(missing_ok=True)
                        message_count = create_conversation_pdf(
                            conversation, pdf_path, runtime, conservative=True
                        )
                        status = "Complete - compatibility fallback"
                    if not valid_pdf_file(pdf_path):
                        raise OSError("Generated PDF failed structural validation")
                else:
                    status = "Skipped - existing JSON and PDF preserved"
            except Exception as error:
                status = "Failed"
                error_text = f"{type(error).__name__}: {clean(error)}"
            report_rows.append(
                {
                    "Chat Title": title,
                    "Conversation ID": conversation_id,
                    "Source JSON": source.name,
                    "Message Count": message_count,
                    "Extracted JSON": str(json_path),
                    "PDF": str(pdf_path),
                    "Status": status,
                    "Error": error_text,
                }
            )
            if not args.quiet or processed % 25 == 0:
                print(f"Chat export {processed:,}: {title} [{status}]")

    report_path = destination / "Chat_Export_Report.csv"
    fieldnames = [
        "Chat Title",
        "Conversation ID",
        "Source JSON",
        "Message Count",
        "Extracted JSON",
        "PDF",
        "Status",
        "Error",
    ]
    with report_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)
    selected_rows = [row for row in report_rows if row["Conversation ID"]]
    return {
        "processed": len(selected_rows),
        "succeeded": sum(row["Status"].startswith("Complete") for row in selected_rows),
        "failed": sum(row["Status"] == "Failed" for row in selected_rows),
        "skipped": sum(row["Status"].startswith("Skipped") for row in selected_rows),
        "source_failed": sum(row["Status"] == "Source failed" for row in report_rows),
        "report": str(report_path),
    }


def main() -> int:
    args = arguments()
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"Error: folder not found: {folder}", file=sys.stderr)
        return 2

    if args.move and not args.group:
        print("Error: --move can only be used together with --group.", file=sys.stderr)
        return 2
    if args.restore_originals and not args.group:
        print("Error: --restore-originals requires --group.", file=sys.stderr)
        return 2
    if (args.chat_id or args.overwrite_chat_exports or args.font) and not args.export_chats:
        print(
            "Error: --chat-id, --overwrite-chat-exports, and --font require --export-chats.",
            file=sys.stderr,
        )
        return 2

    group_root: Path | None = None
    if args.group:
        requested_group = Path(args.group).expanduser()
        group_root = requested_group if requested_group.is_absolute() else folder / requested_group
        group_root = group_root.resolve()

    dat_paths = discover_dat_paths(folder, args.recursive)
    if group_root:
        dat_paths = [
            path
            for path in dat_paths
            if group_root != path.resolve() and group_root not in path.resolve().parents
        ]
    dat_names = [path.name for path in dat_paths] or discover_dat_names(folder, args.recursive)
    if not dat_names:
        print(f"Error: no .dat files found in {folder}", file=sys.stderr)
        return 2

    dat_by_id: dict[str, str] = {}
    for name in dat_names:
        asset_id = asset_id_from_name(name)
        if asset_id:
            dat_by_id[asset_id] = name
    if not dat_by_id:
        print("Error: no recognizable ChatGPT asset IDs found in .dat filenames.", file=sys.stderr)
        return 2
    known_ids = set(dat_by_id)
    paths_by_name: dict[str, list[Path]] = defaultdict(list)
    for path in dat_paths:
        paths_by_name[path.name].append(path)

    name_map_path = folder / "conversation_asset_file_names.json"
    original_names: dict[str, str] = {}
    if name_map_path.exists():
        try:
            loaded = load_json(name_map_path)
            if isinstance(loaded, dict):
                original_names = {str(key): clean(value) for key, value in loaded.items()}
        except (OSError, json.JSONDecodeError, TypeError) as error:
            print(f"Warning: could not read {name_map_path.name}: {error}", file=sys.stderr)

    sources = conversation_files(folder, args.recursive)
    if not sources:
        print("Error: no conversations-*.json files found.", file=sys.stderr)
        return 2

    matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    conversation_count = 0
    for source in sources:
        try:
            data = load_json(source)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Warning: skipped {source.name}: {error}", file=sys.stderr)
            continue
        conversations = data if isinstance(data, list) else [data]
        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue
            conversation_count += 1
            counts = asset_reference_counts(conversation, known_ids)
            for asset_id, count in counts.items():
                matches[asset_id].append(
                    {
                        "title": clean(conversation.get("title")) or "Untitled conversation",
                        "id": clean(conversation.get("conversation_id") or conversation.get("id")),
                        "source": source.name,
                        "references": count,
                    }
                )

    output = (
        Path(args.output).expanduser() if args.output else folder / "ChatGPT_DAT_Chat_Index.csv"
    )
    if not output.is_absolute():
        output = (Path.cwd() / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    matched_assets = 0
    multiple_chat_assets = 0
    renamed_assets = 0
    rename_skipped = 0
    grouped_assets = 0
    group_skipped = 0
    originals_restored = 0
    originals_skipped = 0
    originals_unavailable = 0
    rows: list[dict[str, Any]] = []
    for asset_id, dat_name in sorted(dat_by_id.items(), key=lambda item: item[1].lower()):
        asset_matches = matches.get(asset_id, [])
        if asset_matches:
            matched_assets += 1
        if len(asset_matches) > 1:
            multiple_chat_assets += 1
        titles = [match["title"] for match in asset_matches]
        proposed_name = proposed_dat_name(asset_id, titles) if asset_matches else dat_name
        source_paths = paths_by_name.get(dat_name, [])
        current_path = source_paths[0] if len(source_paths) == 1 else None
        rename_status = "Not requested"
        if asset_matches and dat_name == proposed_name:
            rename_status = "Already named"
        elif asset_matches and not args.rename:
            rename_status = "Preview only"
        elif asset_matches and args.rename:
            if current_path is None:
                rename_status = "Skipped - source path missing or ambiguous"
                rename_skipped += 1
            else:
                target_path = current_path.with_name(proposed_name)
                if target_path.exists():
                    rename_status = "Skipped - target already exists"
                    rename_skipped += 1
                else:
                    current_path.rename(target_path)
                    current_path = target_path
                    rename_status = "Renamed"
                    renamed_assets += 1
        elif not asset_matches:
            rename_status = "Unmatched - unchanged"

        group_folder_name = (
            truncate_utf8(safe_title_prefix(titles), 180) if titles else "_Unmatched"
        )
        group_status = "Not requested"
        grouped_path = ""
        grouped_dat_source: Path | None = None
        if group_root:
            if current_path is None:
                group_status = "Skipped - source path missing or ambiguous"
                group_skipped += 1
            else:
                destination_folder = group_root / group_folder_name
                destination_folder.mkdir(parents=True, exist_ok=True)
                grouped_filename = proposed_name if asset_matches else dat_name
                destination = destination_folder / grouped_filename
                grouped_path = str(destination)
                if destination.exists():
                    group_status = "Skipped - destination already exists"
                    group_skipped += 1
                    grouped_dat_source = destination
                elif args.move:
                    shutil.move(str(current_path), str(destination))
                    current_path = destination
                    group_status = "Moved"
                    grouped_assets += 1
                    grouped_dat_source = destination
                else:
                    shutil.copy2(current_path, destination)
                    group_status = "Copied"
                    grouped_assets += 1
                    grouped_dat_source = destination

        original_name = original_names.get(f"{asset_id}.dat", "")
        restored_name = ""
        restored_path = ""
        restore_status = "Not requested"
        if args.restore_originals:
            if not original_name:
                restore_status = "Unavailable - original filename not recorded"
                originals_unavailable += 1
            elif grouped_dat_source is None or not grouped_dat_source.exists():
                restore_status = "Skipped - grouped DAT source unavailable"
                originals_skipped += 1
            else:
                original_target, identical_exists = original_copy_destination(
                    grouped_dat_source.parent, original_name, asset_id, grouped_dat_source
                )
                restored_name = original_target.name
                restored_path = str(original_target)
                if identical_exists:
                    restore_status = "Skipped - identical original copy exists"
                    originals_skipped += 1
                else:
                    shutil.copy2(grouped_dat_source, original_target)
                    restore_status = "Restored"
                    originals_restored += 1

        row = {
            "DAT Filename": dat_name,
            "Asset ID": asset_id,
            "Original Filename": original_name,
            "Status": "Matched" if asset_matches else "Not found in conversation JSON",
            "Chat Count": len(asset_matches),
            "Chat Titles": " | ".join(titles),
            "Conversation IDs": " | ".join(match["id"] for match in asset_matches),
            "Conversation JSON Files": " | ".join(match["source"] for match in asset_matches),
            "Reference Counts": " | ".join(str(match["references"]) for match in asset_matches),
            "Proposed DAT Filename": proposed_name,
            "Rename Status": rename_status,
            "Proposed Group Folder": group_folder_name,
            "Grouped File Path": grouped_path,
            "Group Status": group_status,
            "Restored Original Filename": restored_name,
            "Restored Original Path": restored_path,
            "Original Restore Status": restore_status,
        }
        rows.append(row)
        if not args.quiet:
            destination = row["Chat Titles"] or "NOT FOUND IN CONVERSATIONS"
            original = row["Original Filename"] or "original name unavailable"
            action = f" -> {proposed_name}" if asset_matches else ""
            grouping = f" [{group_status}]" if group_root else ""
            restoration = f" [{restore_status}]" if args.restore_originals else ""
            print(
                f"{dat_name} -> {original} -> {destination}{action} "
                f"[{rename_status}]{grouping}{restoration}"
            )

    fieldnames = list(rows[0])
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    chat_export_result: dict[str, Any] | None = None
    chat_export_root: Path | None = None
    if args.export_chats:
        requested_export = Path(args.export_chats).expanduser()
        chat_export_root = (
            requested_export if requested_export.is_absolute() else folder / requested_export
        ).resolve()
        try:
            chat_export_result = export_conversations(sources, chat_export_root, args)
        except PdfDependencyError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 2

    print()
    print(f"DAT files examined:       {len(dat_names):,}")
    print(f"Conversation files read:  {len(sources):,}")
    print(f"Conversations examined:   {conversation_count:,}")
    print(f"Assets matched to chats:  {matched_assets:,}")
    print(f"Assets in multiple chats: {multiple_chat_assets:,}")
    print(f"Assets not matched:       {len(dat_names) - matched_assets:,}")
    if args.rename:
        print(f"Files renamed:            {renamed_assets:,}")
        print(f"Renames skipped:          {rename_skipped:,}")
    else:
        print("Files renamed:            0 (preview mode)")
    if group_root:
        operation = "moved" if args.move else "copied"
        print(f"Files {operation} to groups:  {grouped_assets:,}")
        print(f"Grouping operations skipped: {group_skipped:,}")
        print(f"Grouped files directory:      {group_root}")
    else:
        print("Files grouped:            0 (not requested)")
    if args.restore_originals:
        print(f"Original-name copies made:    {originals_restored:,}")
        print(f"Original restores skipped:    {originals_skipped:,}")
        print(f"Original names unavailable:   {originals_unavailable:,}")
    else:
        print("Original-name copies made: 0 (not requested)")
    if chat_export_result and chat_export_root:
        print(f"Chats selected for export:    {chat_export_result['processed']:,}")
        print(f"Chat PDFs created:            {chat_export_result['succeeded']:,}")
        print(f"Existing chat exports skipped:{chat_export_result['skipped']:,}")
        print(f"Chat export failures:         {chat_export_result['failed']:,}")
        print(f"Conversation source failures: {chat_export_result['source_failed']:,}")
        print(f"Extracted chats directory:    {chat_export_root}")
        print(f"Chat export report:           {chat_export_result['report']}")
    else:
        print("Chats extracted to PDF:    0 (not requested)")
    print(f"CSV report:               {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
