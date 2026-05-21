"""Tests for the interactive launcher menu."""

from __future__ import annotations

import importlib.util
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCH_PATH = ROOT / "launch.py"

spec = importlib.util.spec_from_file_location("launch_module_for_tests", LAUNCH_PATH)
launch = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(launch)


def test_zh_new_game_menu_prompts_are_localized(monkeypatch, capsys):
    answers = iter(["0", "0"])
    prompts = []
    started = []

    def prompt_line(prompt=""):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(launch, "_prompt_line", prompt_line)
    monkeypatch.setattr(launch, "_run_play", lambda args, lang: started.append((args, lang)) or 0)

    launch._menu_new_game({}, "zh")

    text = capsys.readouterr().out
    assert "-- 选择角色 --" in text
    assert "开始:" in text
    assert prompts == ["\n输入编号 (0-4): ", "\n进阶等级 0-10。直接回车为标准模式 (0): "]
    assert started == [(["--character", "Ironclad", "--ascension", "0"], "zh")]
