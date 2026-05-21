"""Tests for map navigation."""
import json

import pytest


def _resolve_to_map(game, state):
    for _ in range(80):
        decision = state.get("decision")
        if decision == "map_select":
            return state
        if decision == "combat_play":
            state = game.auto_play_combat(state)
        elif decision == "combat_reward":
            rewards = state.get("rewards", [])
            non_card = next((r for r in rewards if r.get("kind") != "card_reward"), None)
            if non_card:
                state = game.act("claim_reward", reward_index=non_card["index"])
            else:
                card_reward = next((r for r in rewards if r.get("kind") == "card_reward"), None)
                if card_reward:
                    state = game.act("skip_reward", reward_index=card_reward["index"])
                else:
                    state = game.act("proceed")
        elif decision == "card_reward":
            state = game.act("skip_card_reward")
        elif decision == "event_choice":
            options = [o for o in state["options"] if not o.get("is_locked")]
            state = game.act("choose_option", option_index=options[0]["index"])
        elif decision == "bundle_select":
            state = game.act("select_bundle", bundle_index=0)
        elif decision == "card_select":
            if state.get("can_skip", state.get("min_select", 0) == 0):
                state = game.act("skip_select")
            else:
                state = game.act("select_cards", indices="0")
        else:
            state = game.act("proceed")
    raise AssertionError("room did not resolve to map_select")


def _first_off_path_next_row(game, state):
    full_map = game.get_map()
    current = full_map["current_coord"]
    assert current is not None
    current_node = next(
        node
        for row in full_map["rows"]
        for node in row
        if node["col"] == current["col"] and node["row"] == current["row"]
    )
    connected = {(child["col"], child["row"]) for child in current_node.get("children") or []}
    next_row = current["row"] + 1
    next_row_nodes = [
        node
        for row in full_map["rows"]
        for node in row
        if node["row"] == next_row
    ]
    off_path = [node for node in next_row_nodes if (node["col"], node["row"]) not in connected]
    if not off_path:
        pytest.skip("seed did not produce an off-path next-row node")
    return off_path[0]


class TestMapStructure:
    def test_new_act_map_only_exposes_ancient_node(self, game, tmp_path):
        state = game.start(seed="ms-forced-ancient")
        state = game.skip_neow(state)
        save_path = tmp_path / "act_two_start.save"
        save_result = game.send({"cmd": "write_continue_save", "path": str(save_path)})
        assert save_result["success"] is True

        save_data = json.loads(save_path.read_text())
        save_data["current_act_index"] = 1
        save_data["visited_map_coords"] = []
        save_path.write_text(json.dumps(save_data))

        state = game.send({"cmd": "load_save", "path": str(save_path), "lang": "en"})

        assert state["decision"] == "map_select"
        assert len(state["choices"]) == 1
        assert state["choices"][0]["type"] == "Ancient"

    def test_map_select_fields(self, game):
        state = game.start(seed="ms1")
        state = game.skip_neow(state)
        assert state["decision"] == "map_select"
        assert len(state["choices"]) > 0
        for ch in state["choices"]:
            assert "col" in ch
            assert "row" in ch
            assert "type" in ch

    def test_get_map_full(self, game):
        state = game.start(seed="ms2")
        game.skip_neow(state)
        m = game.get_map()
        assert m["type"] == "map"
        assert "rows" in m
        assert "boss" in m
        assert "current_coord" in m

    def test_context_fields(self, game):
        state = game.start(seed="ms3")
        state = game.skip_neow(state)
        ctx = state.get("context", {})
        assert "floor" in ctx
        assert "act_name" in ctx
        assert isinstance(ctx["act_name"], str)

    def test_node_types_valid(self, game):
        state = game.start(seed="ms4")
        state = game.skip_neow(state)
        valid = {"Monster", "Elite", "Boss", "RestSite", "Shop",
                 "Treasure", "Event", "Unknown", "Ancient"}
        for ch in state["choices"]:
            assert ch["type"] in valid


class TestMapNavigation:
    def test_select_node(self, game):
        state = game.start(seed="mn1")
        state = game.skip_neow(state)
        pick = state["choices"][0]
        state = game.act("select_map_node", col=pick["col"], row=pick["row"])
        assert state.get("decision") is not None
        assert state["decision"] != "map_select"  # should be in a room now

    def test_invalid_node_does_not_enter_engine_or_mutate_position(self, game):
        state = game.start(seed="mn-invalid")
        state = game.skip_neow(state)
        before = game.get_map()["current_coord"]

        result = game.act("select_map_node", col=99, row=99)
        after = game.get_map()["current_coord"]

        assert result["type"] == "error"
        assert "Invalid map node" in result["message"]
        assert "NullReferenceException" not in result["message"]
        assert after == before

    def test_winged_boots_exports_next_row_off_path_choices(self, game):
        state = game.start(seed="winged-boots-map")
        state = game.skip_neow(state)
        game.set_player(hp=999, max_hp=999, deck=["BLUDGEON"] * 12, relics=["WINGED_BOOTS"])

        first = state["choices"][0]
        state = game.act("select_map_node", col=first["col"], row=first["row"])
        state = _resolve_to_map(game, state)
        off_path = _first_off_path_next_row(game, state)

        choices = {(choice["col"], choice["row"]): choice for choice in state["choices"]}
        key = (off_path["col"], off_path["row"])
        assert key in choices
        assert choices[key].get("requires_winged_boots") is True

    def test_winged_boots_allows_entering_next_row_off_path_node(self, game):
        state = game.start(seed="winged-boots-map")
        state = game.skip_neow(state)
        game.set_player(hp=999, max_hp=999, deck=["BLUDGEON"] * 12, relics=["WINGED_BOOTS"])

        first = state["choices"][0]
        state = game.act("select_map_node", col=first["col"], row=first["row"])
        state = _resolve_to_map(game, state)
        off_path = _first_off_path_next_row(game, state)
        result = game.act("select_map_node", col=off_path["col"], row=off_path["row"])

        assert result.get("type") != "error"
        assert result.get("decision") != "map_select"
        winged_boots = next(r for r in result["player"]["relics"] if r["id"] == "WINGED_BOOTS")
        assert winged_boots["display_amount"] == 2
