"""Compatibility checks for supported Python versions."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fstring_expressions_do_not_embed_unicode_escape_literals():
    """Keep supported launch paths away from fragile f-string backslash syntax."""
    source = (ROOT / "python" / "play.py").read_text(encoding="utf-8")
    pattern = re.compile(r"\bf[\"'].*(?:\\[uU][0-9a-fA-F]{4}|\\N\{)")
    offenders = [
        f"{line_no}: {line.strip()}"
        for line_no, line in enumerate(source.splitlines(), start=1)
        if pattern.search(line)
    ]

    assert offenders == []
