"""Tests for events."""
import pytest


class TestNeowEvent:
    def test_neow_is_first_event(self, game):
        state = game.start(seed="ne1")
        assert state["decision"] == "event_choice"
        assert "Neow" in str(state.get("event_name", ""))

    def test_neow_options(self, game):
        state = game.start(seed="ne2")
        for opt in state["options"]:
            assert "title" in opt
            assert isinstance(opt["title"], str)
            assert "is_locked" in opt

    def test_neow_option_vars(self, game):
        state = game.start(seed="ne3")
        for opt in state["options"]:
            if opt.get("vars"):
                for k, v in opt["vars"].items():
                    assert isinstance(v, (int, float))

    def test_choose_neow(self, game):
        state = game.start(seed="ne4")
        opts = [o for o in state["options"] if not o.get("is_locked")]
        state = game.act("choose_option", option_index=opts[0]["index"])
        assert state.get("decision") is not None

    def test_neow_pomander_upgrades_selected_card_and_reaches_map(self, game):
        state = game.start(seed="codex-manual-20260514_171724")
        pomander = next(o for o in state["options"] if o["title"] == "Pomander")

        state = game.act("choose_option", option_index=pomander["index"])

        assert state["decision"] == "card_select"
        bash = next(c for c in state["cards"] if c["name"] == "Bash")

        state = game.act("select_cards", indices=str(bash["index"]))

        deck_bash = next(c for c in state["player"]["deck"] if c["name"] == "Bash")
        assert deck_bash["upgraded"] is True
        assert state["decision"] == "map_select"


class TestEventDescriptions:
    def test_no_ismultiplayer_tag(self, game):
        state = game.start(seed="ed1")
        for opt in state.get("options", []):
            d = opt.get("description") or ""
            assert "IsMultiplayer" not in d


class TestSlipperyBridge:
    def test_slippery_bridge_random_card_var_is_card_name(self, game):
        state = game.start(seed="bridge-vars")
        game.skip_neow(state)
        state = game.enter_room("event", event="SLIPPERY_BRIDGE")

        assert state["decision"] == "event_choice"
        overcome = next(o for o in state["options"] if o["title"] == "Overcome")
        random_card = overcome["vars"]["RandomCard"]

        assert isinstance(random_card, str)
        assert random_card
        assert random_card != "0"

    def test_slippery_bridge_hold_on_stays_in_event(self, game):
        state = game.start(seed="bridge-hold")
        game.skip_neow(state)
        state = game.enter_room("event", event="SLIPPERY_BRIDGE")
        hp_before = state["player"]["hp"]
        deck_size_before = state["player"]["deck_size"]

        state = game.act("choose_option", option_index=1)

        assert state["decision"] == "event_choice"
        assert state["event_name"] == "Slippery Bridge"
        assert state["player"]["hp"] == hp_before - 3
        assert state["player"]["deck_size"] == deck_size_before


class TestDenseVegetation:
    def test_trudge_on_description_matches_observed_effect(self, game):
        state = game.start(seed="dense-vegetation")
        game.skip_neow(state)
        state = game.enter_room("event", event="DENSE_VEGETATION")

        trudge = next(o for o in state["options"] if o["title"] == "Trudge On")

        assert "Gold" in trudge["description"]
        assert "Remove a card" not in trudge["description"]

        hp_before = state["player"]["hp"]
        gold_before = state["player"]["gold"]
        deck_size_before = state["player"]["deck_size"]

        state = game.act("choose_option", option_index=trudge["index"])

        assert state["player"]["hp"] == hp_before - trudge["vars"]["HpLoss"]
        assert state["player"]["gold"] == gold_before + trudge["vars"]["Gold"]
        assert state["player"]["deck_size"] == deck_size_before
