"""Tests for CLI play helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAY_PATH = ROOT / "python" / "play.py"

sys.path.insert(0, str(ROOT / "python"))
spec = importlib.util.spec_from_file_location("play_module_for_tests", PLAY_PATH)
play = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(play)


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    return ANSI_RE.sub("", text)


def test_quit_save_defaults_to_save_dir(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    path = play._quit_with_save(None, "Ironclad", "seed123")

    assert path is not None
    assert path.startswith(play.SAVE_DIR)
    assert path.endswith(".save")


def test_enemy_intent_labels_are_text_not_symbols():
    play.LANG = "en"

    parts = play.enemy_intent_display_parts([
        {"type": "Attack", "damage": 7, "hits": 2},
        {"type": "Defend"},
        {"type": "Debuff"},
        {"type": "DeathBlow", "damage": 99},
        {"type": "Escape"},
    ])

    rendered = plain(" ".join(parts))
    assert "Attack 7x2" in rendered
    assert "Defend" in rendered
    assert "Debuff" in rendered
    assert "Deathblow 99" in rendered
    assert "Escape" in rendered
    assert all(ord(ch) < 128 for ch in rendered)


def test_event_option_detail_lines_include_hover_tip_effects():
    play.LANG = "en"

    lines = [plain(line) for line in play.event_option_detail_lines({
        "description": "Give a card Sown.",
        "hover_tips": [
            {
                "kind": "EnchantmentHoverTip",
                "title": "Sown",
                "description": "The first time you play this card each combat, gain [E].",
            }
        ],
    })]

    assert "Give a card Sown." in lines[0]
    assert any("Sown:" in line and "gain [E]" in line for line in lines)


def test_deck_change_detail_lines_include_added_card_descriptions():
    play.LANG = "en"

    old_cards = [{"id": "CARD.STRIKE", "name": "Strike"}]
    new_cards = [
        {"id": "CARD.BASH", "name": "Bash", "cost": 2, "type": "Attack", "description": "Deal 8 damage.\nApply 2 Vulnerable."}
    ]

    lines = [plain(line) for line in play.deck_change_detail_lines(old_cards, new_cards)]

    assert any("+Bash" in line and "Attack" in line for line in lines)
    assert any("Deal 8 damage." in line for line in lines)
    assert any("Apply 2 Vulnerable." in line for line in lines)


def test_prompt_start_options_lets_player_choose_character_and_ascension():
    play.LANG = "en"
    answers = iter(["3", "7"])

    character, ascension = play.prompt_start_options(
        character=None,
        ascension=None,
        input_fn=lambda prompt="": next(answers),
        output_fn=lambda text="": None,
    )

    assert character == "Defect"
    assert ascension == 7


def test_resolve_start_options_defaults_when_menu_is_disabled():
    character, ascension = play.resolve_start_options(
        character=None,
        ascension=None,
        show_menu=False,
    )

    assert character == "Ironclad"
    assert ascension == 0
