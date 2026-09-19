from __future__ import annotations

import re
from pathlib import Path

from chatgpt_export_organizer import __version__


def test_package_and_project_versions_match_release() -> None:
    project = Path(__file__).parents[1] / "pyproject.toml"
    content = project.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', content, flags=re.MULTILINE)
    assert match is not None
    assert match.group(1) == __version__ == "1.4.0"
