"""Regression tests for Windows console encoding-sensitive subprocess calls."""
import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAY_PY = ROOT / "python" / "play.py"


class _Completed:
    returncode = 0


def _load_play_module(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.syspath_prepend(str(ROOT / "python"))

    spec = importlib.util.spec_from_file_location("play_under_test_windows_encoding", PLAY_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, calls


def test_dotnet_probe_decodes_captured_output_as_utf8(monkeypatch):
    module, calls = _load_play_module(monkeypatch)

    assert module.LOCAL_DOTNET_DIR == str(ROOT / ".tools" / "dotnet")

    captured_calls = [call for call in calls if call["kwargs"].get("capture_output")]
    assert captured_calls
    for call in captured_calls:
        assert call["kwargs"].get("text") is True
        assert call["kwargs"].get("encoding") == "utf-8"
        assert call["kwargs"].get("errors") == "replace"


def test_build_decodes_captured_output_as_utf8(monkeypatch):
    module, calls = _load_play_module(monkeypatch)
    calls.clear()
    module.DOTNET = "dotnet"

    assert module._build() is True

    assert calls
    kwargs = calls[-1]["kwargs"]
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True
    assert kwargs.get("encoding") == "utf-8"
    assert kwargs.get("errors") == "replace"
