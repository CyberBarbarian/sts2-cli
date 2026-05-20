"""Regression tests for user-facing setup documentation."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launch_docs_use_powershell_current_directory_prefix():
    for rel in ("README.md", "docs/cross-platform-usage.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")

        assert ".\\sts2-cli.bat" in text
        assert ".\\sts2-cli-zh.bat" in text
        assert not re.search(r"(?m)^sts2-cli(?:-zh)?\.bat$", text)
