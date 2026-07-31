from __future__ import annotations

import sys
from pathlib import Path

import pytest


PYTHON_DIR = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON_DIR))
import headless_session


class Pipe:
    def __init__(self, lines=()):
        self.lines = list(lines)
        self.writes = []
        self.closed = False

    def readline(self):
        return self.lines.pop(0) if self.lines else ""

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        return None

    def close(self):
        self.closed = True


class Process:
    def __init__(self, lines=()):
        self.stdin = Pipe()
        self.stdout = Pipe(lines)
        self.stderr = Pipe()
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        return 0

    def kill(self):
        self.killed = True


def test_runtime_env_preserves_or_forces_existing_library_paths(monkeypatch, tmp_path):
    dotnet_dir = tmp_path / "dotnet"
    dotnet_dir.mkdir()
    dotnet = dotnet_dir / "dotnet.exe"
    dotnet.write_bytes(b"")
    base = {
        "PATH": "system-bin",
        "STS2_LIB": "external-lib",
        "STS2_GAME_DIR": "external-game",
    }

    preserved = headless_session.build_runtime_env(
        local_dotnet=str(dotnet),
        local_dotnet_dir=str(dotnet_dir),
        lib_dir="repo-lib",
        force_local_lib=False,
        base=base,
    )
    forced = headless_session.build_runtime_env(
        local_dotnet=str(dotnet),
        local_dotnet_dir=str(dotnet_dir),
        lib_dir="repo-lib",
        force_local_lib=True,
        base=base,
    )

    assert preserved["STS2_LIB"] == "external-lib"
    assert preserved["STS2_GAME_DIR"] == "external-game"
    assert forced["STS2_LIB"] == "repo-lib"
    assert forced["STS2_GAME_DIR"] == "repo-lib"
    assert forced["DOTNET_ROOT"] == str(dotnet_dir)
    assert forced["PATH"].split(headless_session.os.pathsep, 1) == [
        str(dotnet_dir),
        "system-bin",
    ]


def test_session_owns_json_transport_and_callbacks(monkeypatch):
    process = Process([
        "diagnostic\n",
        '{"type":"ready"}\n',
        '{"type":"decision"}\n',
    ])
    captured = {}
    actions = []
    states = []
    skipped = []

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(headless_session.subprocess, "Popen", fake_popen)
    session = headless_session.HeadlessSession(
        ["dotnet", "headless.dll"],
        env={"BOUND": "1"},
        stderr=headless_session.subprocess.DEVNULL,
        eof_error="EOF",
        on_action=actions.append,
        on_state=states.append,
        on_skip=skipped.append,
    )

    response = session.send({"cmd": "start"}, record=False)
    recorded_response = session.send({"cmd": "action"})

    assert response == {"type": "ready"}
    assert recorded_response == {"type": "decision"}
    assert actions == [{"cmd": "action"}]
    assert states == [{"type": "ready"}, {"type": "decision"}]
    assert skipped == ["diagnostic"]
    assert process.stdin.writes == [
        '{"cmd": "start"}\n',
        '{"cmd": "action"}\n',
    ]
    assert captured["command"] == ["dotnet", "headless.dll"]
    assert captured["kwargs"]["env"] == {"BOUND": "1"}
    assert captured["kwargs"]["stderr"] is headless_session.subprocess.DEVNULL


def test_session_eof_policy_is_explicit(monkeypatch):
    processes = [Process(), Process()]
    monkeypatch.setattr(
        headless_session.subprocess,
        "Popen",
        lambda *_args, **_kwargs: processes.pop(0),
    )

    optional = headless_session.HeadlessSession(
        ["headless"],
        env={},
        stderr=None,
        eof_error=None,
    )
    required = headless_session.HeadlessSession(
        ["headless"],
        env={},
        stderr=None,
        eof_error="simulator EOF",
    )

    assert optional.read() is None
    with pytest.raises(RuntimeError, match="simulator EOF"):
        required.read()


def test_session_close_terminates_and_closes_streams(monkeypatch):
    process = Process()
    monkeypatch.setattr(
        headless_session.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )
    session = headless_session.HeadlessSession(
        ["headless"],
        env={},
        stderr=headless_session.subprocess.DEVNULL,
        eof_error=None,
    )

    session.close()

    assert process.terminated is True
    assert process.killed is False
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True
