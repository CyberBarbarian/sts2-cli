"""Tests for rest site / campfire."""
import pytest


class TestRestSiteStructure:
    def test_rest_site_fields(self, game):
        state = game.start(seed="rs1")
        game.skip_neow(state)
        state = game.enter_room("rest_site")
        assert state["decision"] == "rest_site"
        for opt in state["options"]:
            assert "index" in opt
            assert "option_id" in opt
            assert "is_enabled" in opt

    def test_has_heal_and_smith(self, game):
        state = game.start(seed="rs2")
        game.skip_neow(state)
        state = game.enter_room("rest_site")
        ids = {o["option_id"] for o in state["options"]}
        assert "HEAL" in ids
        assert "SMITH" in ids

    def test_rest_site_options_include_readable_title_and_description(self, game):
        state = game.start(seed="rs-readable-options")
        game.skip_neow(state)
        state = game.enter_room("rest_site")

        heal = next(o for o in state["options"] if o["option_id"] == "HEAL")
        smith = next(o for o in state["options"] if o["option_id"] == "SMITH")

        assert heal["title"] == "Rest"
        assert "Heal" in heal["description"]
        assert heal["vars"]["Heal"] > 0
        assert smith["title"] == "Smith"
        assert "Upgrade" in smith["description"]
        assert "{Count:plural" not in smith["description"]
        assert smith["vars"]["Count"] >= 1


class TestRestSiteActions:
    def test_out_of_range_option_is_rejected_without_leaving_rest_site(self, game):
        state = game.start(seed="rest-option-range")
        game.skip_neow(state)
        state = game.enter_room("rest_site")
        valid = next(option for option in state["options"] if option["is_enabled"] is True)

        rejected = game.act("choose_option", option_index=999)

        assert rejected["type"] == "error"
        assert rejected["decision"] == "rest_site"
        assert rejected["options"] == state["options"]
        assert "Invalid rest site option 999" in rejected["message"]
        resumed = game.act("choose_option", option_index=valid["index"])
        assert resumed.get("decision") in {"map_select", "card_select"}

    def test_disabled_option_is_rejected_by_engine_contract(self, game):
        state = game.start(seed="rest-disabled-option")
        game.skip_neow(state)
        maximum_hp = state["player"]["max_hp"]
        game.set_player(hp=maximum_hp, max_hp=maximum_hp)
        state = game.enter_room("rest_site")
        disabled = next(
            (option for option in state["options"] if option["is_enabled"] is False),
            None,
        )
        if disabled is None:
            pytest.skip("This deterministic state exported no disabled rest option")

        rejected = game.act("choose_option", option_index=disabled["index"])

        assert rejected["type"] == "error"
        assert rejected["decision"] == "rest_site"
        assert rejected["options"] == state["options"]
        assert "is disabled" in rejected["message"]

    def test_heal_restores_hp(self, game):
        state = game.start(seed="rsa1")
        game.skip_neow(state)
        game.set_player(hp=30, max_hp=80)
        state = game.enter_room("rest_site")
        heal = next((o for o in state["options"] if o["option_id"] == "HEAL" and o["is_enabled"]), None)
        assert heal, "HEAL not available"
        hp_before = state["player"]["hp"]
        state = game.act("choose_option", option_index=heal["index"])
        new_hp = state.get("player", {}).get("hp", hp_before)
        assert new_hp > hp_before

    def test_heal_caps_at_max(self, game):
        state = game.start(seed="rsa2")
        game.skip_neow(state)
        max_hp = state["player"]["max_hp"]
        game.set_player(hp=max_hp - 1)
        state = game.enter_room("rest_site")
        heal = next((o for o in state["options"] if o["option_id"] == "HEAL" and o["is_enabled"]), None)
        if not heal:
            pytest.skip("HEAL not available at near-full HP")
        state = game.act("choose_option", option_index=heal["index"])
        player = state.get("player", {})
        assert player.get("hp", 0) <= player.get("max_hp", 0)

    def test_smith_triggers_card_select(self, game):
        state = game.start(seed="rsa3")
        game.skip_neow(state)
        state = game.enter_room("rest_site")
        smith = next((o for o in state["options"] if o["option_id"] == "SMITH" and o["is_enabled"]), None)
        assert smith, "SMITH not available"
        state = game.act("choose_option", option_index=smith["index"])
        assert state["decision"] == "card_select"
        assert state["prompt"] == f"{smith['title']}: {smith['description']}"
        assert state["source_room_option"]["option_id"] == "SMITH"
        assert state["source_room_option"]["description"] == smith["description"]
        assert len(state.get("cards", [])) > 0
