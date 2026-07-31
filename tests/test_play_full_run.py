import importlib.util
import sys
from pathlib import Path

import pytest


def _load_play_full_run():
    root = Path(__file__).resolve().parents[1]
    python_dir = root / "python"
    sys.path.insert(0, str(python_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "play_full_run",
            python_dir / "play_full_run.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(python_dir))


def test_full_run_skips_unclaimable_potion_rewards():
    play_full_run = _load_play_full_run()

    command = play_full_run.combat_reward_command({
        "rewards": [
            {
                "index": 0,
                "kind": "potion",
                "can_claim": False,
                "can_skip": True,
                "blocked_reason": "potion_slots_full",
            },
            {"index": 1, "kind": "card_reward", "can_claim": True, "can_skip": True},
        ],
    })

    assert command == {
        "cmd": "action",
        "action": "skip_reward",
        "args": {"reward_index": 0},
    }


def test_minimum_card_selection_uses_exported_indices_and_required_count():
    play_full_run = _load_play_full_run()
    state = {
        "min_select": 2,
        "cards": [{"index": 4}, {"index": 9}, {"index": 12}],
    }

    assert play_full_run.minimum_card_selection_indices(state) == "4,9"


def test_minimum_card_selection_rejects_insufficient_or_duplicate_options():
    play_full_run = _load_play_full_run()
    with pytest.raises(RuntimeError, match="only 1 option"):
        play_full_run.minimum_card_selection_indices(
            {"min_select": 2, "cards": [{"index": 4}]}
        )

    with pytest.raises(RuntimeError, match="duplicate"):
        play_full_run.minimum_card_selection_indices(
            {"min_select": 2, "cards": [{"index": 4}, {"index": 4}]}
        )


def test_full_run_binds_repo_local_prebuilt_runtime(tmp_path, monkeypatch):
    play_full_run = _load_play_full_run()
    dotnet_dir = tmp_path / ".tools" / "dotnet"
    dotnet_dir.mkdir(parents=True)
    dotnet = dotnet_dir / ("dotnet.exe" if play_full_run.os.name == "nt" else "dotnet")
    dotnet.write_bytes(b"host")
    headless = tmp_path / "src" / "Sts2Headless" / "bin" / "Debug" / "net9.0" / "Sts2Headless.dll"
    headless.parent.mkdir(parents=True)
    headless.write_bytes(b"headless")
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "sts2.dll").write_bytes(b"game")
    monkeypatch.setattr(play_full_run, "LOCAL_DOTNET_DIR", str(dotnet_dir))
    monkeypatch.setattr(play_full_run, "LOCAL_DOTNET", str(dotnet))
    monkeypatch.setattr(play_full_run, "HEADLESS_DLL", str(headless))
    monkeypatch.setattr(play_full_run, "LIB_DIR", str(lib_dir))
    monkeypatch.setenv("STS2_LIB", "C:/external/lib")
    monkeypatch.setenv("STS2_GAME_DIR", "C:/external/game")

    command, env = play_full_run._runtime_binding()

    assert command == [str(dotnet), str(headless)]
    assert env["DOTNET_ROOT"] == str(dotnet_dir)
    assert env["STS2_LIB"] == str(lib_dir)
    assert env["STS2_GAME_DIR"] == str(lib_dir)


def test_full_run_refuses_missing_repo_local_prebuilt_runtime(tmp_path, monkeypatch):
    play_full_run = _load_play_full_run()
    monkeypatch.setattr(play_full_run, "LOCAL_DOTNET", str(tmp_path / "missing-dotnet"))
    monkeypatch.setattr(play_full_run, "HEADLESS_DLL", str(tmp_path / "missing-headless"))
    monkeypatch.setattr(play_full_run, "LIB_DIR", str(tmp_path / "missing-lib"))

    with pytest.raises(RuntimeError, match="repository-local prebuilt runtime"):
        play_full_run._runtime_binding()


def test_play_run_launches_the_bound_prebuilt_dll_directly(monkeypatch):
    play_full_run = _load_play_full_run()
    captured = {}

    class Pipe:
        def __init__(self, lines=()):
            self.lines = list(lines)
            self.writes = []

        def readline(self):
            return self.lines.pop(0) if self.lines else ""

        def write(self, value):
            self.writes.append(value)

        def flush(self):
            return None

        def close(self):
            return None

    class Proc:
        def __init__(self):
            self.stdin = Pipe()
            self.stdout = Pipe(
                [
                    '{"type":"ready"}\n',
                    '{"type":"decision","decision":"game_over","victory":true,"player":{}}\n',
                ]
            )
            self.stderr = Pipe()

        def terminate(self):
            return None

        def wait(self, timeout):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(
        play_full_run,
        "_runtime_binding",
        lambda: (["repo-dotnet", "repo-headless.dll"], {"BOUND": "1"}),
    )

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Proc()

    monkeypatch.setattr(play_full_run.subprocess, "Popen", fake_popen)

    result = play_full_run.play_run("fixed", verbose=False, log=False)

    assert result["victory"] is True
    assert captured["command"] == ["repo-dotnet", "repo-headless.dll"]
    assert captured["kwargs"]["env"] == {"BOUND": "1"}
