#!/usr/bin/env python3
"""Build, install, and ad-hoc sign the local macOS desktop application."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "ChatGPT Export Organizer"


def run(command: list[str], working_directory: Path) -> int:
    return subprocess.run(command, cwd=working_directory, check=False).returncode


def main() -> int:
    if sys.platform != "darwin":
        print("Error: build_macos_app.py must run on macOS.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    cache_root = Path.home() / "Library" / "Caches" / "chatgpt-export-organizer"
    spec_path = cache_root / "spec"
    work_path = cache_root / "build"
    dist_path = cache_root / "dist"
    for directory in (spec_path, work_path, dist_path):
        directory.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--specpath",
        str(spec_path),
        "--workpath",
        str(work_path),
        "--distpath",
        str(dist_path),
        "--windowed",
        "--name",
        APP_NAME,
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
    build_status = run(command, root)
    if build_status != 0:
        return build_status

    built_app = dist_path / f"{APP_NAME}.app"
    if not built_app.is_dir():
        print(f"Error: application bundle was not created: {built_app}", file=sys.stderr)
        return 2

    applications_directory = Path.home() / "Applications"
    applications_directory.mkdir(parents=True, exist_ok=True)
    installed_app = applications_directory / f"{APP_NAME}.app"

    if installed_app.exists():
        shutil.rmtree(installed_app)
    shutil.copytree(built_app, installed_app, symlinks=True)

    post_build_commands = [
        ["/usr/bin/xattr", "-cr", str(installed_app)],
        ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(installed_app)],
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--verbose=2",
            str(installed_app),
        ],
    ]
    for command in post_build_commands:
        status = run(command, root)
        if status != 0:
            return status

    print(f"Application installed at: {installed_app}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
