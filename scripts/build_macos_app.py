#!/usr/bin/env python3
"""Build the local macOS desktop application with PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if sys.platform != "darwin":
        print("Error: build_macos_app.py must run on macOS.", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "ChatGPT Export Organizer",
        "--paths",
        str(root / "src"),
        "--hidden-import",
        "chatgpt_export_organizer.cli",
        "--collect-all",
        "reportlab",
        "--collect-all",
        "arabic_reshaper",
        "--collect-all",
        "bidi",
        str(root / "scripts" / "gui_launcher.py"),
    ]
    return subprocess.run(command, cwd=root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
