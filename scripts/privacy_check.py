#!/usr/bin/env python3
"""Fail when repository files resemble private ChatGPT export artifacts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES = {
    "chat.html",
    "conversation_asset_file_names.json",
    "library_files.json",
    "shared_conversations.json",
    "user_settings.json",
    "ChatGPT_DAT_Chat_Index.csv",
    "Chat_Export_Report.csv",
}
FORBIDDEN_SUFFIXES = {".dat", ".pdf"}
SENSITIVE_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/workspace/" + r"scratch/"),
    re.compile(r"\blibfile_[0-9a-f]{16,}\b"),
    re.compile(r"\bfile_00000000[0-9a-f]{16,}\b"),
]
ALLOWED_SYNTHETIC_ID = "00000000-0000-0000-0000-000000000001"


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def main() -> int:
    violations = []
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        if (path.name in FORBIDDEN_NAMES or path.name.startswith("conversations-")) and not str(
            relative
        ).startswith("examples/synthetic_export/"):
            violations.append(f"forbidden export filename: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"forbidden binary/export suffix: {relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                violations.append(f"sensitive pattern {pattern.pattern!r}: {relative}")
        for identifier in re.findall(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            text,
            flags=re.IGNORECASE,
        ):
            if identifier != ALLOWED_SYNTHETIC_ID:
                violations.append(f"non-synthetic conversation-like ID: {relative}")

    if violations:
        print("Privacy check failed:", file=sys.stderr)
        for violation in sorted(set(violations)):
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Privacy check passed: no private export artifacts detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
