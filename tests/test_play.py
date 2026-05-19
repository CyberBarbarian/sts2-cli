"""Tests for CLI play helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import types


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


def test_orb_labels_include_next_evoke_and_position():
    play.LANG = "en"

    parts = play.orb_display_parts([
        {
            "name": "Frost",
            "type": "Frost",
            "passive": 2,
            "evoke": 5,
            "position_label": "rightmost",
            "is_next_to_evoke": True,
        },
        {
            "name": "Glass",
            "type": "Glass",
            "passive": 4,
            "evoke": 8,
            "position_label": "leftmost",
            "is_next_to_evoke": False,
        },
    ])

    rendered = plain(" ".join(parts))
    assert "Frost(2/5; rightmost,next)" in rendered
    assert "Glass(4/8; leftmost)" in rendered
    assert all(ord(ch) < 128 for ch in rendered)


def test_zh_enemy_intent_labels_are_localized_text():
    play.LANG = "zh"

    parts = play.enemy_intent_display_parts([
        {"type": "Attack", "damage": 7, "hits": 2},
        {"type": "Defend"},
        {"type": "Debuff"},
    ])

    rendered = plain(" ".join(parts))
    assert "Attack" not in rendered
    assert "Defend" not in rendered
    assert "Debuff" not in rendered
    assert "\u653b\u51fb 7x2" in rendered
    assert "\u9632\u5fa1" in rendered
    assert "\u8d1f\u9762\u6548\u679c" in rendered


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


def test_card_detail_extension_prints_affliction_effect(capsys):
    play.LANG = "en"

    play.print_card_detail_extension({
        "name": "Strike",
        "description": "Deal 7 damage.\nBound",
        "affliction": "Bound",
        "affliction_description": "Only 1 Bound card can be played each turn. Cards are un-Bound at end of turn.",
    })

    text = plain(capsys.readouterr().out)
    assert "Bound: Only 1 Bound card can be played each turn." in text


def test_card_detail_extension_prints_enchantment_effect(capsys):
    play.LANG = "en"

    play.print_card_detail_extension({
        "name": "Strike",
        "description": "Deal 7 damage.",
        "enchantment": "Sown",
        "enchantment_description": "The first time you play this card each combat, gain [E].",
    })

    text = plain(capsys.readouterr().out)
    assert "Sown: The first time you play this card each combat, gain [E]." in text


def test_card_select_context_lines_include_source_event_hover_tip():
    play.LANG = "en"

    lines = [plain(line) for line in play.card_select_context_lines({
        "prompt": "Read the Back: Choose an Attack to Enchant with Sharp 2.",
        "source_event_option": {
            "hover_tips": [
                {
                    "kind": "EnchantmentHoverTip",
                    "title": "Sharp",
                    "description": "Increases damage on this card by 2.",
                }
            ],
        },
    })]

    assert lines[0] == "Read the Back: Choose an Attack to Enchant with Sharp 2."
    assert any("Sharp:" in line and "damage" in line for line in lines)


def test_card_select_context_lines_include_source_potion_description():
    play.LANG = "en"

    lines = [plain(line) for line in play.card_select_context_lines({
        "source_potion": {
            "name": "Attack Potion",
            "description": "Choose 1 of 3 random Attack cards to add into your Hand.",
        },
    })]

    assert lines == [
        "Attack Potion: Choose 1 of 3 random Attack cards to add into your Hand."
    ]


def test_card_select_context_lines_include_source_room_option_description():
    play.LANG = "en"

    lines = [plain(line) for line in play.card_select_context_lines({
        "source_room_option": {
            "title": "Smith",
            "description": "Upgrade a card in your Deck.",
        },
    })]

    assert lines == ["Smith: Upgrade a card in your Deck."]


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
    answers = iter(["2", "3", "7"])

    lang, character, ascension = play.prompt_start_options(
        lang=None,
        character=None,
        ascension=None,
        input_fn=lambda prompt="": next(answers),
        output_fn=lambda text="": None,
    )

    assert lang == "zh"
    assert character == "Defect"
    assert ascension == 7


def test_resolve_start_options_defaults_when_menu_is_disabled():
    lang, character, ascension = play.resolve_start_options(
        lang=None,
        character=None,
        ascension=None,
        show_menu=False,
    )

    assert lang == "en"
    assert character == "Ironclad"
    assert ascension == 0


def test_resolve_start_options_preserves_explicit_language_without_menu():
    lang, character, ascension = play.resolve_start_options(
        lang="zh",
        character=None,
        ascension=None,
        show_menu=False,
    )

    assert lang == "zh"
    assert character == "Ironclad"
    assert ascension == 0


def test_should_show_start_menu_false_when_lang_arg_is_explicit():
    args = types.SimpleNamespace(
        auto=False,
        seed=None,
        character=None,
        ascension=None,
        load=None,
        continue_save=None,
    )
    stdin = types.SimpleNamespace(isatty=lambda: True)

    assert play.should_show_start_menu(args, stdin=stdin, argv=["--lang", "zh"]) is False
    assert play.should_show_start_menu(args, stdin=stdin, argv=["--lang=zh"]) is False


def test_should_show_start_menu_true_for_double_click_tty():
    args = types.SimpleNamespace(
        auto=False,
        seed=None,
        character=None,
        ascension=None,
        load=None,
        continue_save=None,
    )
    stdin = types.SimpleNamespace(isatty=lambda: True)

    assert play.should_show_start_menu(args, stdin=stdin, argv=[]) is True


def test_zh_start_summary_prefers_engine_player_name():
    play.LANG = "zh"

    line = plain(play.start_run_summary_line(
        "Ironclad",
        "loc-seed",
        0,
        {"player": {"name": {"en": "Ironclad", "zh": "\u94c1\u7532\u6218\u58eb"}}},
    ))

    assert "Ironclad" not in line
    assert any("\u4e00" <= ch <= "\u9fff" for ch in line)


def test_zh_pile_display_lines_are_localized():
    play.LANG = "zh"

    text = plain("\n".join(play.pile_display_lines("draw", [], count=0)))

    assert "Draw Pile" not in text
    assert "Empty" not in text
    assert any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_zh_combat_rewards_are_localized(capsys):
    play.LANG = "zh"

    play.show_combat_reward({
        "player": {
            "name": "\u94c1\u7532\u6218\u58eb",
            "hp": 80,
            "max_hp": 80,
            "gold": 99,
            "deck_size": 10,
            "relics": [],
            "potions": [],
        },
        "rewards": [
            {"index": 0, "kind": "gold", "amount": 12},
            {"index": 1, "kind": "card_reward", "count": 3},
        ],
    })

    text = plain(capsys.readouterr().out)
    assert "Combat Rewards" not in text
    assert "Card Reward" not in text
    assert "gold" not in text
    assert any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_zh_crystal_sphere_labels_are_localized(capsys):
    play.LANG = "zh"

    play.show_crystal_sphere({
        "player": {
            "name": "\u94c1\u7532\u6218\u58eb",
            "hp": 80,
            "max_hp": 80,
            "gold": 99,
            "deck_size": 10,
            "relics": [],
            "potions": [],
        },
        "grid_width": 1,
        "grid_height": 1,
        "cells": [{"x": 0, "y": 0, "is_hidden": True}],
        "tool": "big",
        "divinations_remaining": 2,
        "visible_items": [
            {
                "index": 0,
                "item_kind": "card",
                "card_rarity": "Rare",
                "is_fully_revealed": False,
                "revealed_cells": 1,
                "total_cells": 2,
            }
        ],
        "revealed_items": [
            {
                "index": 1,
                "item_kind": "gold",
                "is_good": True,
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
            }
        ],
    })

    text = plain(capsys.readouterr().out)
    for english in ("Crystal Sphere", "Tool", "Visible items", "complete", "partial", "cells", "good item"):
        assert english not in text
    assert any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_combat_inline_stat_prefers_single_target_damage():
    play.LANG = "en"
    rendered = plain(play.combat_hand_inline_stat_str(
        {
            "damage": 6,
            "damage_by_target": [
                {"target_index": 0, "target_name": "Nibbit", "damage": 9, "vulnerable": 1}
            ],
        },
        card={"id": "CARD.STRIKE", "target_type": "AnyEnemy"},
        enemies=[{"index": 0, "name": "Nibbit", "hp": 22}],
    ))

    assert "9dmg" in rendered
    assert "6dmg" not in rendered


def test_target_damage_detail_lines_show_multiple_targets():
    play.LANG = "en"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "stats": {
                "damage": 6,
                "damage_by_target": [
                    {"target_index": 0, "target_name": "Nibbit", "damage": 9, "vulnerable": 1},
                    {"target_index": 1, "target_name": "Other Nibbit", "damage": 6, "vulnerable": 0},
                ],
            }
        },
        enemies=[
            {"index": 0, "name": "Nibbit", "hp": 22},
            {"index": 1, "name": "Other Nibbit", "hp": 31},
        ],
    )]

    assert any("Nibbit: 9dmg" in line for line in lines)
    assert any("Other Nibbit: 6dmg" in line for line in lines)


def test_zh_target_damage_detail_lines_are_localized():
    play.LANG = "zh"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "stats": {
                "damage": 6,
                "damage_by_target": [
                    {"target_index": 0, "target_name": "\u5c0f\u5543\u517d", "damage": 9, "vulnerable": 1},
                ],
            }
        },
        enemies=[{"index": 0, "name": "\u5c0f\u5543\u517d", "hp": 22}],
    )]
    rendered = "\n".join(lines)

    assert "Target damage" not in rendered
    assert "Vulnerable" not in rendered
    assert "dmg" not in rendered
    assert "\u76ee\u6807\u4f24\u5bb3" in rendered
    assert "\u5c0f\u5543\u517d: 9\u4f24" in rendered
    assert "\u6613\u4f24 1" in rendered


def test_pile_display_lines_include_card_descriptions():
    play.LANG = "en"
    lines = [plain(line) for line in play.pile_display_lines(
        "draw",
        [
            {
                "index": 0,
                "name": "Strike",
                "cost": 1,
                "type": "Attack",
                "description": "Deal 6 damage.",
            }
        ],
    )]

    assert any("Draw Pile" in line for line in lines)
    assert any("Strike" in line for line in lines)
    assert any("Deal 6 damage." in line for line in lines)


def test_parse_card_sequence_accepts_ordered_indices():
    assert play.parse_card_sequence("seq 3,1,0") == [3, 1, 0]
    assert play.parse_card_sequence("play 2 0") == [2, 0]
    assert play.parse_card_sequence("3,2") == [3, 2]
    assert play.parse_card_sequence("3") is None


def test_parse_card_sequence_accepts_per_card_targets():
    assert play.parse_card_sequence("seq 3@1,2@0") == [
        {"card_index": 3, "target_index": 1},
        {"card_index": 2, "target_index": 0},
    ]
    assert play.parse_card_sequence("play 4>2 1") == [
        {"card_index": 4, "target_index": 2},
        {"card_index": 1},
    ]


def test_execute_card_sequence_uses_explicit_targets_with_multiple_enemies():
    state = {
        "decision": "combat_play",
        "energy": 3,
        "hand": [
            {"index": 0, "name": "Strike", "cost": 1, "energy_cost": 1, "can_play": True, "target_type": "AnyEnemy"},
            {"index": 1, "name": "Strike", "cost": 1, "energy_cost": 1, "can_play": True, "target_type": "AnyEnemy"},
        ],
        "enemies": [
            {"index": 0, "name": "Louse", "hp": 12},
            {"index": 1, "name": "Cultist", "hp": 20},
        ],
    }
    sent = []

    def send(cmd):
        sent.append(cmd)
        return {
            "decision": "combat_play",
            "energy": 2,
            "hand": [
                {"index": 1, "name": "Strike", "cost": 1, "energy_cost": 1, "can_play": True, "target_type": "AnyEnemy"},
            ],
            "enemies": state["enemies"],
        }

    result = play.execute_card_sequence(
        state,
        [{"card_index": 0, "target_index": 1}, {"card_index": 1, "target_index": 0}],
        send,
    )

    assert [cmd["args"] for cmd in sent] == [
        {"card_index": 0, "target_index": 1},
        {"card_index": 1, "target_index": 0},
    ]
    assert result["decision"] == "combat_play"


def test_execute_card_sequence_stops_when_state_requires_manual_choice():
    state = {
        "decision": "combat_play",
        "energy": 3,
        "hand": [
            {"index": 0, "name": "Strike", "cost": 1, "energy_cost": 1, "can_play": True, "target_type": "None"},
            {"index": 1, "name": "Strike", "cost": 1, "energy_cost": 1, "can_play": True, "target_type": "None"},
        ],
        "enemies": [],
    }
    sent = []
    messages = []

    def send(cmd):
        sent.append(cmd)
        return {"decision": "card_select", "cards": []}

    result = play.execute_card_sequence(
        state,
        [0, 1],
        send,
        output_fn=messages.append,
    )

    assert len(sent) == 1
    assert sent[0]["action"] == "play_card"
    assert result["decision"] == "card_select"
    assert any("stopped" in message.lower() for message in messages)
