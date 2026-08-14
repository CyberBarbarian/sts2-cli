import copy

import pytest


def _scenario_command(seed):
    return {
        "cmd": "start_combat",
        "character": "Ironclad",
        "ascension": 3,
        "seed": seed,
        "lang": "en",
        "encounter": "ENCOUNTER.SHRINKER_BEETLE_WEAK",
        "player": {
            "hp": 61,
            "max_hp": 80,
            "gold": 123,
            "relics": ["RELIC.BURNING_BLOOD"],
            "relic_setup_mode": "direct",
            "potions": ["POTION.FIRE_POTION"],
            "deck": [
                {
                    "id": "CARD.STAMPEDE",
                    "current_upgrade_level": 1,
                    "enchantment": {
                        "id": "ENCHANTMENT.SWIFT",
                        "amount": 2,
                    },
                },
                {
                    "id": "CARD.SPOILS_MAP",
                    "props": {
                        "ints": [{"name": "SpoilsActIndex", "value": 1}],
                    },
                },
                {"id": "CARD.STRIKE_IRONCLAD"},
                {"id": "CARD.DEFEND_IRONCLAD"},
                {"id": "CARD.BASH"},
            ],
        },
    }


def test_start_combat_loads_semantic_card_state_atomically(game):
    state = game.send(_scenario_command("semantic-combat-1"))

    assert state["decision"] == "combat_play"
    assert state["player"]["hp"] == 61
    assert state["player"]["max_hp"] == 80
    assert state["player"]["gold"] == 123
    assert state["player"]["deck_size"] == 5
    stampede = next(card for card in state["player"]["deck"] if card["id"] == "CARD.STAMPEDE")
    assert stampede["upgraded"] is True
    assert stampede["enchantment_id"] == "SWIFT"
    assert stampede["enchantment_amount"] == 2


def test_start_combat_replaces_previous_combat_in_same_process(game):
    first = game.send(_scenario_command("semantic-combat-first"))
    second = game.send(_scenario_command("semantic-combat-second"))

    assert first["decision"] == "combat_play"
    assert second["decision"] == "combat_play"
    assert second["player"]["deck_size"] == 5


def test_start_combat_training_mode_stays_compact_across_actions(game):
    command = _scenario_command("compact-combat")
    command["observation_mode"] = "training_compact"

    state = game.send(command)
    next_state = game.act("end_turn")

    for row in (state, next_state):
        assert row["decision"] == "combat_play"
        assert row["observation_mode"] == "training_compact"
        assert "deck" not in row["player"]
        assert all("description" not in card for card in row["hand"])
        assert all(card["id"].startswith("CARD.") for card in row["hand"])
        assert all(enemy["id"].startswith("MONSTER.") for enemy in row["enemies"])


def test_terminal_combat_hp_is_captured_before_burning_blood(game):
    command = _scenario_command("pre-reward-terminal-hp")
    command["observation_mode"] = "training_compact"
    command["player"]["hp"] = 70
    command["player"]["potions"] = []
    command["player"]["deck"] = ["CARD.BLUDGEON"] * 5

    state = game.send(command)
    game.send({"cmd": "debug_set_enemy_hp", "enemy_index": 0, "hp": 1})
    bludgeon = next(card for card in state["hand"] if card["id"] == "CARD.BLUDGEON")
    terminal = game.act("play_card", card_index=bludgeon["index"], target_index=0)

    assert terminal["decision"] in {"combat_reward", "game_over"}
    assert terminal["combat_terminal_hp"] == 70
    if terminal["decision"] == "combat_reward":
        assert terminal["player"]["hp"] == 76
    else:
        assert terminal["player"]["hp"] == 70
    assert terminal.get("engine_error") is not True


def test_action_tape_matches_sequential_actions(game):
    command = _scenario_command("action-tape-equivalence")
    command["observation_mode"] = "training_compact"
    game.send(command)
    game.act("end_turn")
    sequential = game.act("end_turn")

    game.send(command)
    taped = game.send(
        {
            "cmd": "action_tape",
            "actions": [
                {"cmd": "action", "action": "end_turn"},
                {"cmd": "action", "action": "end_turn"},
            ],
        }
    )

    assert taped == sequential


@pytest.mark.parametrize("warm_template", [False, True])
@pytest.mark.parametrize("observation_mode", [None, "training_compact"])
def test_start_combat_action_tape_matches_two_command_replay(
    game,
    warm_template,
    observation_mode,
):
    command = _scenario_command(
        f"combined-action-tape-{warm_template}-{observation_mode}"
    )
    if observation_mode is not None:
        command["observation_mode"] = observation_mode
    actions = [
        {"cmd": "action", "action": "end_turn"},
        {"cmd": "action", "action": "end_turn"},
    ]

    combined_command = copy.deepcopy(command)
    combined_command["action_tape"] = actions
    if warm_template:
        game.send(command)
        expected = game.send({"cmd": "action_tape", "actions": actions})
        actual = game.send(combined_command)
    else:
        actual = game.send(combined_command)
        game.send(command)
        expected = game.send({"cmd": "action_tape", "actions": actions})

    assert actual == expected


def test_start_combat_action_tape_illegal_action_fails_and_does_not_leak_policy(game):
    command = _scenario_command("combined-action-tape-invalid")
    command["action_tape"] = [
        {
            "cmd": "action",
            "action": "play_card",
            "args": {"card_index": 999},
        }
    ]

    result = game.send(command)
    outside_tape = game.act("end_turn")

    assert result["type"] == "error"
    assert "Invalid card index 999" in result["message"]
    assert outside_tape["type"] == "error"
    assert "before an authoritative decision has been exported" in outside_tape["message"]


def test_start_combat_action_tape_rejects_intermediate_pending_choice(game):
    command = _scenario_command("combined-action-tape-pending")
    command["player"]["deck"] = [
        {"id": "CARD.ARMAMENTS"},
        {"id": "CARD.ARMAMENTS"},
        {"id": "CARD.ARMAMENTS"},
        {"id": "CARD.ARMAMENTS"},
        {"id": "CARD.ARMAMENTS"},
    ]
    root = game.send(command)
    armaments = next(card for card in root["hand"] if card["id"] == "CARD.ARMAMENTS")
    command["action_tape"] = [
        {
            "cmd": "action",
            "action": "play_card",
            "args": {"card_index": armaments["index"]},
        },
        {"cmd": "action", "action": "end_turn"},
    ]

    result = game.send(command)

    assert result["type"] == "error"
    assert "crossed a pending choice" in result["message"]


def test_start_combat_action_tape_rejects_intermediate_terminal(game):
    command = _scenario_command("combined-action-tape-terminal")
    command["player"]["hp"] = 1
    command["player"]["relics"] = []
    command["player"]["potions"] = []
    command["action_tape"] = [
        {"cmd": "action", "action": "end_turn"},
        {"cmd": "action", "action": "end_turn"},
        {"cmd": "action", "action": "end_turn"},
    ]

    result = game.send(command)

    assert result["type"] == "error"
    assert "terminal state before its final action" in result["message"]


def test_identical_start_combat_template_restore_preserves_proof_state(game):
    command = _scenario_command("template-proof-equivalence")
    command["player"]["deck"] = [
        {"id": "CARD.STRIKE_IRONCLAD"},
        {"id": "CARD.DEFEND_IRONCLAD"},
        {"id": "CARD.BASH"},
    ]

    first_state = game.send(command)
    first_token = game.send({"cmd": "proof_state_token"})
    restored_state = game.send(command)
    restored_token = game.send({"cmd": "proof_state_token"})

    assert first_state == restored_state
    assert first_token["supported"] is True
    assert restored_token["supported"] is True
    assert first_token["canonical_json"] == restored_token["canonical_json"]
    assert first_token["token_sha256"] == restored_token["token_sha256"]


def test_start_combat_strict_player_setup_rejects_unknown_models(game):
    command = _scenario_command("strict-combat")
    command["player"]["strict"] = True
    command["player"]["deck"].append({"id": "CARD.DOES_NOT_EXIST"})

    state = game.send(command)

    assert state["type"] == "error"
    assert "CARD.DOES_NOT_EXIST" in state["message"]


def test_repeated_forced_combat_resets_do_not_retain_run_states(game):
    game.send(_scenario_command("memory-baseline"))
    before = game.send({"cmd": "runtime_stats", "collect": True})

    for reset_index in range(100):
        state = game.send(_scenario_command(f"memory-{reset_index}"))
        assert state["decision"] == "combat_play"

    after = game.send({"cmd": "runtime_stats", "collect": True})

    assert after["managed_heap_bytes"] - before["managed_heap_bytes"] < 4_000_000
