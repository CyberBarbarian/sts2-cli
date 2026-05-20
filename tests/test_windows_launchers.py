"""Regression tests for Windows batch launchers."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launchers_use_the_user_python_command_before_py_launcher():
    for name in ("sts2-cli.bat", "sts2-cli-zh.bat"):
        script = (ROOT / name).read_text(encoding="utf-8")

        assert "python --version" in script
        assert "py -3 --version" in script
        assert script.index("python --version") < script.index("py -3 --version")
