from sts2_bench.actions import build_legal_actions
from sts2_bench.agents import OpenAICompatAgent
from sts2_bench.runner import run_one


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
    action = build_legal_actions(
        {
            **state,
            "choices": [{"col": 1, "row": 3, "type": "Monster"}],
        }
    )[2]

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
    action = build_legal_actions(state)[2]

    agent.record_transition(state, action, {"parsed": {"reason": "No energy."}})
    assert "Episode memory:" in agent.build_prompt(state, build_legal_actions(state))

    agent.reset_episode()

    assert "Episode memory:" not in agent.build_prompt(state, build_legal_actions(state))
