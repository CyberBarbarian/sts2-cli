from sts2_bench.actions import build_legal_actions
from sts2_bench.agents import OpenAICompatAgent
from sts2_bench.runner import run_one


def test_meta_view_actions_include_combat_piles():
    state = {
        "decision": "combat_play",
        "player": {"hp": 80, "max_hp": 80, "gold": 0, "deck_size": 10},
        "hand": [],
        "enemies": [],
    }

    actions = build_legal_actions(state)
    by_kind = {action.kind: action for action in actions}

    assert by_kind["view_deck"].command == {"cmd": "bench_view", "view": "deck"}
    assert by_kind["view_map"].command == {"cmd": "bench_view", "view": "map"}
    assert by_kind["view_draw_pile"].command == {"cmd": "bench_view", "view": "draw"}
    assert by_kind["view_discard_pile"].command == {"cmd": "bench_view", "view": "discard"}
    assert by_kind["view_exhaust_pile"].command == {"cmd": "bench_view", "view": "exhaust"}


def test_meta_view_actions_do_not_repeat_by_default():
    state = {
        "decision": "map_select",
        "view_deck": True,
        "view_draw_pile": True,
        "choices": [],
    }

    actions = build_legal_actions(state)
    kinds = {action.kind for action in actions}

    assert "view_deck" not in kinds
    assert "view_draw_pile" not in kinds
    assert "view_map" in kinds
    assert "view_discard_pile" in kinds
    assert "view_exhaust_pile" in kinds


def test_card_select_requires_multi_card_actions_when_min_select_is_two():
    state = {
        "decision": "card_select",
        "min_select": 2,
        "max_select": 2,
        "cards": [
            {"index": 0, "name": "Bloodletting"},
            {"index": 1, "name": "Setup Strike"},
            {"index": 2, "name": "Sword Boomerang"},
        ],
    }

    actions = build_legal_actions(state)
    select_actions = [action for action in actions if action.kind == "card_select"]

    assert select_actions
    assert {action.command["args"]["indices"] for action in select_actions} == {
        "0,1",
        "0,2",
        "1,2",
    }
    assert all("," in action.command["args"]["indices"] for action in select_actions)
    assert not any(action.label.startswith("select card ") for action in select_actions)


def test_card_select_keeps_single_card_actions_when_min_select_is_one():
    state = {
        "decision": "card_select",
        "min_select": 1,
        "max_select": 1,
        "cards": [
            {"index": 3, "name": "Bash"},
            {"index": 4, "name": "Armaments"},
        ],
    }

    actions = build_legal_actions(state)
    select_actions = [action for action in actions if action.kind == "card_select"]

    assert [action.command["args"]["indices"] for action in select_actions] == ["3", "4"]
    assert [action.label for action in select_actions] == [
        "select card 3: Bash",
        "select card 4: Armaments",
    ]


def test_card_select_single_card_choices_are_not_capped():
    state = {
        "decision": "card_select",
        "min_select": 1,
        "max_select": 1,
        "cards": [{"index": idx, "name": f"Card {idx}"} for idx in range(70)],
    }

    actions = build_legal_actions(state)
    select_actions = [action for action in actions if action.kind == "card_select"]

    assert len(select_actions) == 70
    assert select_actions[-1].command["args"]["indices"] == "69"
    assert select_actions[-1].label == "select card 69: Card 69"


def test_card_select_can_skip_even_when_min_select_is_positive():
    state = {
        "decision": "card_select",
        "min_select": 1,
        "max_select": 1,
        "can_skip": True,
        "cards": [{"index": 0, "name": "Strike"}],
    }

    actions = build_legal_actions(state)

    assert any(action.kind == "card_select_skip" for action in actions)


def test_combat_reward_exposes_skip_and_potion_discard_shortcuts():
    state = {
        "decision": "combat_reward",
        "rewards": [
            {"index": 0, "kind": "potion", "can_claim": False, "can_skip": True},
            {"index": 1, "kind": "gold", "amount": 12, "can_claim": True},
        ],
        "player": {
            "potions": [
                {"index": 0, "name": "Potion A"},
                {"index": 2, "name": "Potion B"},
            ]
        },
    }

    actions = build_legal_actions(state)
    by_kind = {action.kind: action for action in actions}

    assert "combat_reward_skip" in by_kind
    assert by_kind["combat_reward_skip"].command == {
        "cmd": "action",
        "action": "skip_reward",
        "args": {"reward_index": 0},
    }
    assert not any(
        action.kind == "combat_reward" and action.command["args"]["reward_index"] == 0
        for action in actions
    )
    assert any(action.kind == "combat_reward" and action.command["args"]["reward_index"] == 1 for action in actions)
    assert {
        action.command["args"]["potion_index"]
        for action in actions
        if action.kind == "combat_reward_discard_potion"
    } == {0, 2}


def test_event_choice_exposes_leave_when_available():
    state = {
        "decision": "event_choice",
        "can_leave": True,
        "options": [{"index": 0, "title": "Search", "is_locked": False}],
    }

    actions = build_legal_actions(state)

    assert any(action.kind == "event" for action in actions)
    leave = next(action for action in actions if action.kind == "event_leave")
    assert leave.command == {"cmd": "action", "action": "leave_room"}


def test_crystal_sphere_exposes_tool_and_cell_actions():
    state = {
        "decision": "crystal_sphere",
        "can_proceed": False,
        "clickable_cells": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
    }

    actions = build_legal_actions(state)

    assert {action.command["args"]["tool"] for action in actions if action.kind == "crystal_sphere_tool"} == {
        "big",
        "small",
    }
    assert {
        (action.command["args"]["x"], action.command["args"]["y"])
        for action in actions
        if action.kind == "crystal_sphere_cell"
    } == {(1, 2), (3, 4)}
    assert not any(action.kind == "crystal_sphere" for action in actions)


class _ChooseEndTurnAgent:
    def build_prompt(self, state, legal_actions):
        return ""

    def choose(self, state, legal_actions, *, prompt=None):
        action = next(action for action in legal_actions if action.kind == "combat_end_turn")
        return action, {"agent": "test"}


class _ErrorProcess:
    def start(self):
        pass

    def start_run(self, **kwargs):
        return {
            "decision": "combat_play",
            "context": {"act": 1, "floor": 1},
            "player": {"hp": 80, "max_hp": 80, "gold": 0, "deck_size": 10},
            "energy": 0,
            "hand": [],
            "enemies": [],
        }

    def send(self, command):
        return {"type": "error", "message": "forced engine error"}

    def close(self):
        pass


def test_runner_stops_after_engine_error_state():
    result = run_one(
        agent=_ChooseEndTurnAgent(),
        seed="test",
        process=_ErrorProcess(),
        max_steps=20,
    )

    assert result.error == "forced engine error"
    assert result.invalid_states == 1
    assert result.steps == 1
    assert not result.truncated


def test_openai_compat_agent_prompt_includes_short_term_memory():
    agent = OpenAICompatAgent(
        base_url="http://127.0.0.1:1",
        model="test",
        memory_enabled=True,
        memory_window=2,
    )
    state = {
        "decision": "map_select",
        "context": {"act": 1, "floor": 3, "room_type": "Map"},
        "player": {"hp": 70, "max_hp": 80, "gold": 120, "deck_size": 12},
        "choices": [],
    }
    action = next(
        action
        for action in build_legal_actions(
            {
                **state,
                "choices": [{"col": 1, "row": 3, "type": "Monster"}],
            }
        )
        if action.kind == "map"
    )

    agent.record_transition(
        state,
        action,
        {"parsed": {"reason": "Need one more hallway reward before resting."}},
    )
    prompt = agent.build_prompt(state, build_legal_actions(state))

    assert "Episode memory:" in prompt
    assert "decision=map_select" in prompt
    assert "floor=3" in prompt
    assert "action=go to Monster at col=1 row=3" in prompt
    assert "Need one more hallway reward before resting." in prompt


def test_agent_memory_resets_between_runs():
    agent = OpenAICompatAgent(
        base_url="http://127.0.0.1:1",
        model="test",
        memory_enabled=True,
    )
    state = {
        "decision": "combat_play",
        "context": {"act": 1, "floor": 1, "room_type": "Monster"},
        "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
        "energy": 0,
        "hand": [],
        "enemies": [],
    }
    action = next(action for action in build_legal_actions(state) if action.kind == "combat_end_turn")

    agent.record_transition(state, action, {"parsed": {"reason": "No energy."}})
    assert "Episode memory:" in agent.build_prompt(state, build_legal_actions(state))

    agent.reset_episode()

    assert "Episode memory:" not in agent.build_prompt(state, build_legal_actions(state))
