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


def test_card_type_rarity_suffix_does_not_repeat_matching_labels():
    play.LANG = "en"

    rendered = plain(play.card_type_rarity_suffix({
        "type": "Status",
        "rarity": "Status",
    }))

    assert rendered == " Status"
    assert "Status Status" not in rendered


def test_card_type_rarity_suffix_keeps_distinct_labels():
    play.LANG = "en"

    rendered = plain(play.card_type_rarity_suffix({
        "type": "Attack",
        "rarity": "Basic",
    }))

    assert rendered == " Attack Basic"


def test_show_rest_site_uses_titles_and_descriptions(capsys):
    play.LANG = "en"

    play.show_rest_site({
        "context": {"act_name": "Overgrowth", "floor": 16},
        "player": {"name": "The Silent", "hp": 70, "max_hp": 70, "gold": 99, "deck_size": 10},
        "options": [
            {
                "index": 0,
                "option_id": "HEAL",
                "name": "HealRestSiteOption",
                "title": "Rest",
                "description": "Heal for 30% of your Max HP (21).",
                "is_enabled": True,
            },
            {
                "index": 2,
                "option_id": "LIFT",
                "name": "LiftRestSiteOption",
                "title": "Train",
                "description": "Start battles with +1 Strength. (3 Left)",
                "is_enabled": True,
            },
        ],
    })

    rendered = plain(capsys.readouterr().out)
    assert "[0] Rest" in rendered
    assert "Heal for 30% of your Max HP (21)." in rendered
    assert "[2] Train" in rendered
    assert "Start battles with +1 Strength. (3 Left)" in rendered
    assert "HealRestSiteOption" not in rendered
    assert "LiftRestSiteOption" not in rendered


def test_context_display_floor_prefers_player_facing_floor():
    assert play.context_display_floor({"floor": 8, "display_floor": 7}) == 7
    assert play.context_display_floor({"floor": 8}) == 8


def test_show_event_uses_player_facing_floor(capsys):
    play.LANG = "en"

    play.show_event({
        "context": {
            "act_name": "Overgrowth",
            "floor": 8,
            "display_floor": 7,
            "engine_floor": 8,
            "map_floor": 7,
        },
        "event_name": "Unrest Site",
        "player": {"name": "The Defect", "hp": 29, "max_hp": 75, "gold": 3, "deck_size": 16},
        "options": [
            {
                "index": 0,
                "title": "Rest Anyways",
                "description": "Heal to full HP.",
                "is_locked": False,
            },
        ],
    })

    rendered = plain(capsys.readouterr().out)
    assert "Overgrowth Floor 7" in rendered
    assert "Overgrowth Floor 8" not in rendered


def test_render_map_lists_boss_choice(capsys):
    play.LANG = "en"

    play._render_map(
        {
            "context": {"act_name": "Overgrowth", "floor": 16},
            "current_coord": {"col": 2, "row": 15},
            "rows": [
                [
                    {
                        "col": 2,
                        "row": 15,
                        "type": "RestSite",
                        "children": [{"col": 2, "row": 16}],
                        "visited": True,
                        "current": True,
                    }
                ]
            ],
            "boss": {"col": 2, "row": 16, "type": "Boss"},
        },
        choice_set={(2, 16)},
        choice_indices={(2, 16): 0},
    )

    rendered = plain(capsys.readouterr().out)

    assert "[0]" in rendered
    assert "0=Boss" in rendered


def test_show_map_renumbers_visible_choices_when_start_choice_is_hidden(capsys):
    play.LANG = "en"

    state = {
        "choices": [
            {"col": 3, "row": 0, "type": "Start"},
            {"col": 1, "row": 1, "type": "Monster"},
            {"col": 5, "row": 1, "type": "Monster"},
        ]
    }
    map_data = {
        "type": "map",
        "context": {"act_name": "Hive", "floor": 0},
        "current_coord": {"col": 3, "row": 0},
        "rows": [
            [
                {"col": 1, "row": 1, "type": "Monster", "children": [{"col": 1, "row": 2}], "visited": False},
                {"col": 5, "row": 1, "type": "Monster", "children": [{"col": 5, "row": 2}], "visited": False},
            ],
            [
                {"col": 1, "row": 2, "type": "Event", "children": [], "visited": False},
                {"col": 5, "row": 2, "type": "Event", "children": [], "visited": False},
            ]
        ],
        "boss": {"col": 3, "row": 15, "type": "Boss"},
    }

    def send_fn(cmd):
        assert cmd == {"cmd": "get_map"}
        return map_data

    visible_choices = play.show_map(state, send_fn=send_fn)
    rendered = plain(capsys.readouterr().out)

    assert visible_choices == state["choices"][1:]
    assert "[0]" in rendered
    assert "[1]" in rendered
    assert "[2]" not in rendered
    assert "0=Monster" in rendered
    assert "1=Monster" in rendered
    assert "2=Monster" not in rendered


def test_card_select_prompt_only_advertises_skip_when_optional():
    play.LANG = "en"

    required = plain(play.card_select_input_prompt(1, 1))
    optional = plain(play.card_select_input_prompt(0, 1))
    skippable_required_count = plain(play.card_select_input_prompt(1, 1, can_skip=True))

    assert "skip" not in required.lower()
    assert "(s)" not in required
    assert "pick 1 card" in required
    assert "skip" in optional.lower()
    assert "(s)" in optional
    assert "pick 1 card" in skippable_required_count
    assert "skip" in skippable_required_count.lower()
    assert "(s)" in skippable_required_count


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


def test_card_description_keeps_exported_keyword_lines_without_prefix_duplication():
    play.LANG = "en"

    lines = [plain(line) for line in play.card_description_display_lines({
        "name": "Ascender's Bane",
        "description": "Unplayable.\nEthereal.\nEternal.",
        "keywords": ["Eternal", "Unplayable", "Ethereal"],
    })]

    assert lines == ["Unplayable.", "Ethereal.", "Eternal."]


def test_combat_view_does_not_duplicate_keyword_lines_in_title(capsys):
    play.LANG = "en"

    play.show_combat({
        "round": 1,
        "energy": 0,
        "max_energy": 3,
        "draw_pile_count": 0,
        "discard_pile_count": 0,
        "player": {"name": "The Silent", "hp": 56, "max_hp": 70, "gold": 99, "deck_size": 13},
        "enemies": [],
        "hand": [{
            "index": 0,
            "name": "Ascender's Bane",
            "cost": 0,
            "type": "Curse",
            "can_play": False,
            "target_type": "None",
            "description": "Unplayable.\nEthereal.\nEternal.",
            "keywords": ["Eternal", "Unplayable", "Ethereal"],
        }],
    })

    text = plain(capsys.readouterr().out)
    assert "[Unplayable Eternal]" not in text
    assert "Unplayable.\n" in text
    assert "Ethereal.\n" in text
    assert "Eternal.\n" in text


def test_player_positive_debuff_powers_are_labeled_as_debuffs(capsys):
    play.LANG = "en"

    play.show_combat({
        "round": 1,
        "energy": 3,
        "max_energy": 3,
        "draw_pile_count": 0,
        "discard_pile_count": 0,
        "player": {"name": "The Silent", "hp": 56, "max_hp": 70, "gold": 99, "deck_size": 13},
        "player_powers": [
            {
                "name": "Vulnerable",
                "description": "Vulnerable creatures take 50% more damage from Attacks.",
                "amount": 3,
                "type": "Debuff",
            },
            {
                "name": "Double Damage",
                "description": "This turn, Attacks deal double damage.",
                "amount": 1,
                "type": "Buff",
            },
        ],
        "enemies": [],
        "hand": [],
    })

    text = plain(capsys.readouterr().out)
    assert "Debuff Vulnerable 3" in text
    assert "Buff Double Damage 1" in text


def test_enemy_power_descriptions_are_visible_in_combat(capsys):
    play.LANG = "en"

    play.show_combat({
        "round": 1,
        "energy": 3,
        "max_energy": 3,
        "draw_pile_count": 0,
        "discard_pile_count": 0,
        "player": {"name": "The Silent", "hp": 56, "max_hp": 70, "gold": 99, "deck_size": 13},
        "enemies": [
            {
                "index": 0,
                "name": "Phrog Parasite",
                "hp": 61,
                "max_hp": 61,
                "intents": [{"type": "StatusCard"}],
                "powers": [
                    {
                        "name": "Infested",
                        "amount": 4,
                        "description": "Upon dying, summons... something.",
                    }
                ],
            }
        ],
        "hand": [],
    })

    text = plain(capsys.readouterr().out)
    assert "Infested 4" in text
    assert "Upon dying, summons... something." in text


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


def test_card_detail_extension_can_print_full_upgrade_description(capsys):
    play.LANG = "en"

    play.print_card_detail_extension(
        {
            "name": "Strike",
            "cost": 1,
            "description": "Deal 6 damage.",
            "stats": {"damage": 6},
            "after_upgrade": {
                "cost": 1,
                "description": "Deal 9 damage.",
                "stats": {"damage": 9},
            },
        },
        include_upgrade_description=True,
    )

    text = plain(capsys.readouterr().out)
    assert "Upgrade preview: Deal 9 damage." in text


def test_card_detail_extension_omits_target_rows_from_upgrade_summary(capsys):
    play.LANG = "en"

    play.print_card_detail_extension({
        "name": "Strike",
        "cost": 1,
        "description": "Deal 6 damage.",
        "stats": {
            "damage": 6,
            "damage_by_target": [
                {"target_index": 0, "target_name": "Mawler", "damage": 6, "unblocked_damage": 6}
            ],
        },
        "after_upgrade": {
            "cost": 1,
            "description": "Deal 9 damage.",
            "stats": {
                "damage": 9,
                "damage_by_target": [
                    {"target_index": 0, "target_name": "Mawler", "damage": 9, "unblocked_damage": 9}
                ],
            },
        },
    })

    text = plain(capsys.readouterr().out)
    assert "dmg 6" in text
    assert "target_index" not in text
    assert "Mawler" not in text


def test_card_detail_extension_omits_internal_dynamic_upgrade_stats(capsys):
    play.LANG = "en"

    play.print_card_detail_extension({
        "name": "Precise Cut",
        "cost": 0,
        "description": "Deal 9 damage.\nDeals 2 less damage for each other card in your Hand.",
        "stats": {
            "calculationbase": 13,
            "extradamage": 2,
            "calculateddamage": 9,
        },
        "after_upgrade": {
            "cost": 0,
            "description": "Deal 16 damage.\nDeals 2 less damage for each other card in your Hand.",
            "stats": {
                "calculationbase": 16,
                "extradamage": 2,
                "calculateddamage": 16,
            },
        },
    })

    text = plain(capsys.readouterr().out)
    assert "dmg 9" in text
    assert "13" not in text


def test_card_detail_extension_can_hide_upgrade_summary(capsys):
    play.LANG = "en"

    play.print_card_detail_extension(
        {
            "name": "Strike",
            "cost": 1,
            "description": "Deal 10 damage.",
            "stats": {"damage": 10},
            "after_upgrade": {
                "cost": 1,
                "description": "Deal 9 damage.",
                "stats": {"damage": 9},
            },
        },
        include_upgrade_summary=False,
    )

    text = plain(capsys.readouterr().out)
    assert "Deal 10 damage." in text
    assert "upgrade:" not in text
    assert "10\u21929" not in text


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


def test_card_select_upgrade_description_is_enabled_for_smith():
    assert play.card_select_should_show_upgrade_description({
        "decision": "card_select",
        "source_room_option": {"option_id": "SMITH"},
    })


def test_card_select_upgrade_summary_is_hidden_for_combat_effect_select():
    assert not play.card_select_should_show_upgrade_summary({
        "decision": "card_select",
        "combat": {"round": 1},
        "source_card": {"name": "Nightmare"},
        "prompt": "Choose a Card.",
    })
    assert play.card_select_should_show_upgrade_summary({
        "decision": "card_select",
        "source_room_option": {"option_id": "SMITH"},
    })
    assert play.card_select_should_show_upgrade_summary({
        "decision": "card_select",
        "prompt": "Choose a Card.",
    })


def test_card_select_context_lines_include_source_power_description():
    play.LANG = "en"

    lines = [plain(line) for line in play.card_select_context_lines({
        "prompt": "Choose a card to add into your Hand.",
        "source_power": {
            "name": "Stratagem",
            "description": "Whenever you shuffle your Draw Pile, choose 1 card from it to put into your Hand.",
        },
    })]

    assert lines == [
        "Choose a card to add into your Hand.",
        "Stratagem: Whenever you shuffle your Draw Pile, choose 1 card from it to put into your Hand.",
    ]


def test_card_select_context_lines_include_source_card_description():
    play.LANG = "en"

    lines = [plain(line) for line in play.card_select_context_lines({
        "prompt": "Choose a card to put back in your Hand.",
        "source_card": {
            "name": "Hologram",
            "description": "Gain 3 Block.\nPut a card from your Discard Pile into your Hand.\nExhaust.",
        },
    })]

    assert lines == [
        "Choose a card to put back in your Hand.",
        "Hologram: Gain 3 Block. Put a card from your Discard Pile into your Hand. Exhaust.",
    ]


def test_print_card_select_context_shows_source_prompt(capsys):
    play.LANG = "en"

    play.print_card_select_context({
        "prompt": "Lead Paperweight: Choose 1 of 2 Colorless cards to add to your Deck.",
    })

    text = plain(capsys.readouterr().out)
    assert "Lead Paperweight: Choose 1 of 2 Colorless cards to add to your Deck." in text


def test_print_card_select_combat_context_shows_live_fight(capsys):
    play.LANG = "en"

    play.print_card_select_combat_context({
        "combat": {
            "round": 4,
            "energy": 2,
            "max_energy": 3,
            "draw_pile_count": 3,
            "discard_pile_count": 9,
            "exhaust_pile_count": 2,
            "enemies": [
                {
                    "index": 0,
                    "name": "Bygone Effigy",
                    "hp": 67,
                    "max_hp": 127,
                    "block": 0,
                    "intents": [{"type": "Attack", "damage": 23}],
                    "powers": [
                        {
                            "name": "Strength",
                            "amount": 10,
                            "description": "Strength adds additional damage to Attacks.",
                        }
                    ],
                }
            ],
            "orbs": [
                {"name": "Lightning", "passive": 3, "evoke": 8, "is_next_to_evoke": True},
            ],
            "hand": [
                {"index": 0, "name": "Defend", "cost": 1, "stats": {"block": 6}},
            ],
        }
    })

    text = plain(capsys.readouterr().out)
    assert "Combat context" in text
    assert "Round 4" in text
    assert "Bygone Effigy" in text
    assert "Attack 23" in text
    assert "Strength adds additional damage to Attacks." in text
    assert "Lightning" in text
    assert "Hand" in text


def test_card_select_combat_context_omits_non_combat_select():
    play.LANG = "en"

    lines = play.card_select_combat_context_lines({
        "prompt": "Let Go: Transform a card in your Deck.",
        "cards": [{"index": 0, "name": "Strike"}],
    })

    assert lines == []


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


def test_player_state_change_lines_include_reward_relic_upgrade_details():
    play.LANG = "en"

    old_state = {
        "player": {
            "hp": 70,
            "max_hp": 70,
            "gold": 99,
            "deck_size": 1,
            "relics": [],
            "deck": [
                {
                    "id": "CARD.STRIKE",
                    "name": "Strike",
                    "cost": 1,
                    "type": "Attack",
                    "upgraded": False,
                    "description": "Deal 6 damage.",
                }
            ],
        }
    }
    new_state = {
        "player": {
            "hp": 70,
            "max_hp": 70,
            "gold": 99,
            "deck_size": 1,
            "relics": [{"name": "Whetstone", "description": "Upon pickup, Upgrade 2 random Attacks."}],
            "deck": [
                {
                    "id": "CARD.STRIKE",
                    "name": "Strike",
                    "cost": 1,
                    "type": "Attack",
                    "upgraded": True,
                    "description": "Deal 9 damage.",
                }
            ],
        }
    }

    lines = [plain(line) for line in play.player_state_change_lines(old_state, new_state)]

    assert any("Card details:" in line for line in lines)
    assert any("+Strike+" in line and "Attack" in line for line in lines)
    assert any("Deal 9 damage." in line for line in lines)
    assert any("Relic details:" in line for line in lines)
    assert any("+Whetstone" in line for line in lines)
    assert any("Upon pickup, Upgrade 2 random Attacks." in line for line in lines)
    assert any("Relic: Whetstone" in line for line in lines)


def test_player_state_change_lines_include_added_potion_details():
    play.LANG = "en"

    old_state = {
        "player": {
            "hp": 29,
            "max_hp": 70,
            "gold": 46,
            "deck_size": 18,
            "relics": [],
            "deck": [],
            "potions": [
                {"id": "FRUIT_JUICE", "name": "Fruit Juice", "description": "Gain 5 Max HP."},
            ],
        }
    }
    new_state = {
        "player": {
            "hp": 29,
            "max_hp": 70,
            "gold": 14,
            "deck_size": 18,
            "relics": [],
            "deck": [],
            "potions": [
                {"id": "FRUIT_JUICE", "name": "Fruit Juice", "description": "Gain 5 Max HP."},
                {
                    "id": "POWER_POTION",
                    "name": "Power Potion",
                    "description": "Choose 1 of 3 random Power cards to add into your Hand.",
                },
                {"id": "REGEN_POTION", "name": "Regen Potion", "description": "Gain 5 Regen."},
            ],
        }
    }

    lines = [plain(line) for line in play.player_state_change_lines(old_state, new_state)]

    assert any("Potion details:" in line for line in lines)
    assert any("+Power Potion" in line for line in lines)
    assert any("Choose 1 of 3 random Power cards" in line for line in lines)
    assert any("+Regen Potion" in line for line in lines)
    assert any("Gain 5 Regen." in line for line in lines)
    assert any("Potions: +Power Potion +Regen Potion" in line for line in lines)
    assert any("Gold: -32" in line for line in lines)


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


def test_combat_reward_shows_optional_skip_affordance(capsys):
    play.LANG = "en"

    play.show_combat_reward({
        "player": {
            "name": "The Defect",
            "hp": 70,
            "max_hp": 70,
            "gold": 99,
            "deck_size": 10,
            "relics": [],
            "potions": [],
        },
        "rewards": [
            {
                "index": 1,
                "kind": "potion",
                "name": "Block Potion",
                "description": "Gain 12 Block.",
                "can_claim": False,
                "can_skip": True,
                "blocked_reason": "potion_slots_full",
            },
        ],
    })

    text = plain(capsys.readouterr().out)
    assert "Cannot claim: potion_slots_full." in text
    assert "Type s1 to skip this reward." in text


def test_card_reward_marks_upgraded_cards(capsys):
    play.LANG = "en"

    play.show_card_reward({
        "gold_earned": 14,
        "player": {
            "name": "The Defect",
            "hp": 68,
            "max_hp": 75,
            "gold": 113,
            "deck_size": 10,
            "relics": [{"name": "Silver Crucible", "description": "The first 3 card rewards you see are Upgraded."}],
            "potions": [],
        },
        "cards": [
            {
                "index": 0,
                "name": "Compile Driver",
                "cost": 1,
                "type": "Attack",
                "rarity": "Common",
                "upgraded": True,
                "description": "Deal 10 damage.\nDraw 1 card for each unique Orb you have.",
            },
            {
                "index": 1,
                "name": "Cold Snap",
                "cost": 1,
                "type": "Attack",
                "rarity": "Common",
                "upgraded": False,
                "description": "Deal 6 damage.\nChannel 1 Frost.",
            },
        ],
    })

    text = plain(capsys.readouterr().out)
    assert "[0] Compile Driver+ (1)" in text
    assert "Deal 10 damage." in text
    assert "[1] Cold Snap (1)" in text
    assert "Cold Snap+ (1)" not in text


def test_show_player_includes_potion_slot_capacity(capsys):
    play.LANG = "en"

    play.show_player({
        "name": "The Defect",
        "hp": 70,
        "max_hp": 70,
        "gold": 99,
        "deck_size": 10,
        "relics": [],
        "potion_slots": 4,
        "potion_empty_slots": 2,
        "potions": [
            {"index": 0, "name": "Lucky Tonic", "description": "Gain 1 Buffer."},
            {"index": 1, "name": "Vulnerable Potion", "description": "Apply 3 Vulnerable."},
        ],
    })

    text = plain(capsys.readouterr().out)
    assert "Potions 2/4" in text
    assert "2 empty" in text


def test_show_player_marks_targeted_potions(capsys):
    play.LANG = "en"

    play.show_player({
        "name": "The Silent",
        "hp": 70,
        "max_hp": 70,
        "gold": 99,
        "deck_size": 10,
        "relics": [],
        "potions": [
            {
                "index": 0,
                "name": "Beetle Juice",
                "description": "Enemy's attacks deal 30% less damage for the next 4 turns.",
                "target_type": "AnyEnemy",
            },
        ],
    })

    text = plain(capsys.readouterr().out)
    assert "[0] Beetle Juice -> target enemy:" in text


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


def test_combat_inline_stat_uses_total_damage_for_repeated_hits():
    play.LANG = "en"
    rendered = plain(play.combat_hand_inline_stat_str(
        {
            "damage": 5,
            "damage_by_target": [
                {"target_index": 0, "target_name": "Wriggler", "damage": 5, "repeat": 3, "total_damage": 15},
                {"target_index": 1, "target_name": "Wriggler", "damage": 5, "repeat": 3, "total_damage": 15},
            ],
        },
        card={"id": "CARD.GUNK_UP", "type": "Attack", "target_type": "AnyEnemy"},
        enemies=[
            {"index": 0, "name": "Wriggler", "hp": 10},
            {"index": 1, "name": "Wriggler", "hp": 13},
        ],
    ))

    assert rendered == "15dmg"


def test_combat_inline_stat_hides_unplayable_status_damage():
    play.LANG = "en"
    rendered = plain(play.combat_hand_inline_stat_str(
        {"damage": 3},
        card={
            "id": "CARD.INFECTION",
            "name": "Infection",
            "type": "Status",
            "rarity": "Status",
            "can_play": False,
            "target_type": "None",
        },
        enemies=[],
    ))

    assert rendered == ""


def test_combat_inline_stat_hides_playable_status_self_damage():
    play.LANG = "en"
    rendered = plain(play.combat_hand_inline_stat_str(
        {"damage": 5},
        card={
            "id": "CARD.TOXIC",
            "name": "Toxic",
            "type": "Status",
            "rarity": "Status",
            "can_play": True,
            "target_type": "None",
            "description": "At the end of your turn, if this is in your Hand, take 5 damage.",
        },
        enemies=[
            {"index": 0, "name": "Myte", "hp": 13},
            {"index": 1, "name": "Myte", "hp": 13},
        ],
    ))

    assert rendered == ""


def test_target_damage_detail_lines_hide_random_enemy_rows():
    play.LANG = "en"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "id": "CARD.RICOCHET",
            "type": "Attack",
            "target_type": "None",
            "description": "Deal 3 damage to a random enemy 4 times.",
            "stats": {
                "damage": 3,
                "damage_by_target": [
                    {"target_index": 0, "target_name": "Myte", "damage": 3, "repeat": 4, "total_damage": 12},
                    {"target_index": 1, "target_name": "Myte", "damage": 3, "repeat": 4, "total_damage": 12},
                ],
            },
        },
        enemies=[
            {"index": 0, "name": "Myte", "hp": 13},
            {"index": 1, "name": "Myte", "hp": 13},
        ],
    )]

    assert lines == []


def test_target_damage_detail_lines_label_all_enemy_rows_as_damage_by_enemy():
    play.LANG = "en"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "id": "CARD.SHIV",
            "type": "Attack",
            "target_type": "AllEnemies",
            "description": "Deal 4 damage to ALL enemies.",
            "stats": {
                "damage": 4,
                "damage_by_target": [
                    {"target_index": 0, "target_name": "Myte", "damage": 4},
                    {"target_index": 1, "target_name": "Myte", "damage": 4},
                ],
            },
        },
        enemies=[
            {"index": 0, "name": "Myte", "hp": 13},
            {"index": 1, "name": "Myte", "hp": 13},
        ],
    )]
    rendered = "\n".join(lines)

    assert "Damage by enemy:" in rendered
    assert "Target damage:" not in rendered
    assert "[0] Myte: 4dmg" in rendered
    assert "[1] Myte: 4dmg" in rendered


def test_target_damage_detail_lines_show_multiple_targets():
    play.LANG = "en"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "target_type": "AnyEnemy",
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


def test_target_damage_detail_lines_include_indices_for_duplicate_names():
    play.LANG = "en"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "target_type": "AnyEnemy",
            "stats": {
                "damage": 4,
                "damage_by_target": [
                    {"target_index": 0, "target_name": "Wriggler", "damage": 4},
                    {"target_index": 1, "target_name": "Wriggler", "damage": 4},
                ],
            }
        },
        enemies=[
            {"index": 0, "name": "Wriggler", "hp": 21},
            {"index": 1, "name": "Wriggler", "hp": 19},
        ],
    )]

    assert any("[0] Wriggler: 4dmg" in line for line in lines)
    assert any("[1] Wriggler: 4dmg" in line for line in lines)


def test_target_damage_detail_lines_show_single_target_block_context():
    play.LANG = "en"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "target_type": "AnyEnemy",
            "stats": {
                "damage": 10,
                "damage_by_target": [
                    {
                        "target_index": 0,
                        "target_name": "Nibbit",
                        "damage": 10,
                        "unblocked_damage": 5,
                        "block": 5,
                    },
                ],
            }
        },
        enemies=[{"index": 0, "name": "Nibbit", "hp": 15, "block": 5}],
    )]

    assert any("[0] Nibbit: 10dmg (Block 5)" in line for line in lines)


def test_zh_target_damage_detail_lines_are_localized():
    play.LANG = "zh"
    lines = [plain(line) for line in play.card_target_damage_display_lines(
        {
            "target_type": "AnyEnemy",
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


def test_pile_display_lines_support_exhaust_pile():
    play.LANG = "en"
    lines = [plain(line) for line in play.pile_display_lines(
        "exhaust",
        [
            {
                "index": 0,
                "name": "Neow's Fury",
                "cost": 1,
                "type": "Attack",
                "description": "Deal 10 damage.\nExhaust.",
            }
        ],
    )]

    assert any("Exhaust Pile" in line for line in lines)
    assert any("Neow's Fury" in line for line in lines)
    assert any("Exhaust." in line for line in lines)


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


def test_execute_card_sequence_binds_indices_to_initial_hand_instances():
    state = {
        "decision": "combat_play",
        "energy": 5,
        "hand": [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "b", "name": "B", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 2, "instance_id": "c", "name": "C", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 3, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 4, "instance_id": "e", "name": "E", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
        ],
        "enemies": [],
    }
    hands_after = [
        [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "c", "name": "C", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 2, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 3, "instance_id": "e", "name": "E", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
        ],
        [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 2, "instance_id": "e", "name": "E", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
        ],
        [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
        ],
    ]
    sent = []

    def send(cmd):
        sent.append(cmd)
        return {
            "decision": "combat_play",
            "energy": 5,
            "hand": hands_after[len(sent) - 1],
            "enemies": [],
        }

    result = play.execute_card_sequence(state, [1, 2, 4], send)

    assert [cmd["args"]["card_index"] for cmd in sent] == [1, 1, 2]
    assert result["decision"] == "combat_play"


def test_execute_card_sequence_binds_targets_to_initial_enemy_instances():
    state = {
        "decision": "combat_play",
        "energy": 5,
        "hand": [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "b", "name": "B", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "AnyEnemy"},
            {"index": 2, "instance_id": "c", "name": "C", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 3, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 4, "instance_id": "e", "name": "E", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "AnyEnemy"},
            {"index": 5, "instance_id": "f", "name": "F", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "AnyEnemy"},
        ],
        "enemies": [
            {"index": 0, "instance_id": "enemy-a", "name": "A", "hp": 7},
            {"index": 1, "instance_id": "enemy-b", "name": "B", "hp": 28},
            {"index": 2, "instance_id": "enemy-c", "name": "C", "hp": 12},
        ],
    }
    hands_after = [
        [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "c", "name": "C", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 2, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 3, "instance_id": "e", "name": "E", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "AnyEnemy"},
            {"index": 4, "instance_id": "f", "name": "F", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "AnyEnemy"},
        ],
        [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "c", "name": "C", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 2, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 3, "instance_id": "f", "name": "F", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "AnyEnemy"},
        ],
        [
            {"index": 0, "instance_id": "a", "name": "A", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 1, "instance_id": "c", "name": "C", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
            {"index": 2, "instance_id": "d", "name": "D", "cost": 0, "energy_cost": 0, "can_play": True, "target_type": "None"},
        ],
    ]
    enemies_after = [
        state["enemies"],
        [
            {"index": 0, "instance_id": "enemy-b", "name": "B", "hp": 28},
            {"index": 1, "instance_id": "enemy-c", "name": "C", "hp": 12},
        ],
        [
            {"index": 0, "instance_id": "enemy-b", "name": "B", "hp": 28},
        ],
    ]
    sent = []

    def send(cmd):
        sent.append(cmd)
        return {
            "decision": "combat_play",
            "energy": 5,
            "hand": hands_after[len(sent) - 1],
            "enemies": enemies_after[len(sent) - 1],
        }

    result = play.execute_card_sequence(
        state,
        [
            {"card_index": 1, "target_index": 0},
            {"card_index": 4, "target_index": 0},
            {"card_index": 5, "target_index": 2},
        ],
        send,
    )

    assert [cmd["args"] for cmd in sent] == [
        {"card_index": 1, "target_index": 0},
        {"card_index": 3, "target_index": 0},
        {"card_index": 3, "target_index": 1},
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
