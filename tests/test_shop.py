"""Tests for shop scenarios."""
import json
import queue
import threading

import pytest


def send_with_timeout(game, cmd, timeout=5):
    out = queue.Queue()

    def worker():
        try:
            out.put(game.send(cmd))
        except Exception as exc:
            out.put(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        response = out.get(timeout=timeout)
    except queue.Empty:
        pytest.fail(f"Timed out waiting for response to {json.dumps(cmd)}")
    if isinstance(response, Exception):
        raise response
    return response


class TestShopStructure:
    def test_shop_fields(self, game):
        state = game.start(seed="ss1")
        game.skip_neow(state)
        state = game.enter_room("shop")
        assert state["decision"] == "shop"
        assert "cards" in state
        assert "relics" in state
        assert "potions" in state
        assert "card_removal_cost" in state

    def test_shop_cards_have_description(self, game):
        state = game.start(seed="ss2")
        game.skip_neow(state)
        state = game.enter_room("shop")
        for card in state["cards"]:
            assert isinstance(card["name"], str)
            assert "description" in card
            assert "cost" in card
            assert "type" in card
            assert "card_cost" in card

    def test_shop_cards_have_upgrade_preview(self, game):
        state = game.start(seed="ss3")
        game.skip_neow(state)
        state = game.enter_room("shop")
        has_upgrade = any(c.get("after_upgrade") for c in state["cards"])
        assert has_upgrade

    def test_shop_cards_export_base_stats(self, game):
        state = game.start(seed="shop-stats-probe")
        game.skip_neow(state)
        state = game.enter_room("shop")

        twin_strike = next(c for c in state["cards"] if c["name"] == "Twin Strike")
        assert twin_strike["stats"]["damage"] == 5

    def test_shop_relics_have_description(self, game):
        state = game.start(seed="ss4")
        game.skip_neow(state)
        state = game.enter_room("shop")
        for r in state["relics"]:
            assert isinstance(r["name"], str)
            assert "description" in r

    def test_shop_potions_have_description(self, game):
        state = game.start(seed="ss5")
        game.skip_neow(state)
        state = game.enter_room("shop")
        for p in state["potions"]:
            assert isinstance(p["name"], str)
            assert "description" in p


class TestShopBuy:
    def test_buy_card_reduces_gold(self, game):
        state = game.start(seed="sb1")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("shop")
        gold_before = state["player"]["gold"]
        deck_before = state["player"]["deck_size"]
        stocked = [c for c in state["cards"] if c.get("is_stocked")]
        assert stocked
        card = stocked[0]
        state = game.act("buy_card", card_index=card["index"])
        if state.get("decision") == "shop":
            assert state["player"]["gold"] < gold_before
            assert state["player"]["deck_size"] == deck_before + 1

    def test_bought_card_keeps_shop_metadata(self, game):
        state = game.start(seed="sb-card-metadata")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("shop")

        stocked = [c for c in state["cards"] if c.get("is_stocked")]
        assert stocked
        card = stocked[0]
        state = game.act("buy_card", card_index=card["index"])

        bought = state["cards"][card["index"]]
        assert bought["is_stocked"] is False
        assert bought["name"] == card["name"]
        assert bought["type"] == card["type"]
        assert bought["rarity"] == card["rarity"]
        assert bought["description"] == card["description"]

    def test_bought_relic_keeps_shop_metadata(self, game):
        state = game.start(seed="sb-relic-metadata")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("shop")

        stocked = [r for r in state["relics"] if r.get("is_stocked")]
        assert stocked
        relic = stocked[0]
        state = game.act("buy_relic", relic_index=relic["index"])

        bought = state["relics"][relic["index"]]
        assert bought["is_stocked"] is False
        assert bought["name"] == relic["name"]
        assert bought["description"] == relic["description"]

    def test_buy_relic_returns_pickup_card_selection(self, game):
        state = game.start(seed="kifuda-shop-4")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("shop")

        relic = next(relic for relic in state["relics"] if relic["id"] == "KIFUDA")
        state = send_with_timeout(
            game,
            {"cmd": "action", "action": "buy_relic", "args": {"relic_index": relic["index"]}},
        )

        assert state["decision"] == "card_select"
        assert state["min_select"] == 0
        assert state["max_select"] == 3
        assert state["cards"]

        state = game.act("select_cards", indices="0,1,2")
        assert state["decision"] == "shop"
        assert any(relic["id"] == "KIFUDA" for relic in state["player"]["relics"])
        assert state["player"]["deck"][0].get("enchantment") == "Adroit"

    def test_buy_insufficient_gold(self, game):
        state = game.start(seed="sb2")
        game.skip_neow(state)
        game.set_player(gold=0)
        state = game.enter_room("shop")
        stocked = [c for c in state["cards"] if c.get("is_stocked")]
        if stocked:
            state = game.act("buy_card", card_index=stocked[0]["index"])
            assert state.get("type") == "error"

    def test_leave_shop(self, game):
        state = game.start(seed="sb3")
        game.skip_neow(state)
        state = game.enter_room("shop")
        state = game.act("leave_room")
        assert state["decision"] == "map_select"

    def test_proceed_leaves_shop(self, game):
        state = game.start(seed="sb4")
        game.skip_neow(state)
        state = game.enter_room("shop")
        state = game.act("proceed")
        assert state["decision"] == "map_select"


class TestShopRemove:
    def test_remove_card_flow(self, game):
        state = game.start(seed="sr1")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("shop")
        deck_before = state["player"]["deck_size"]
        state = game.act("remove_card")
        # Should trigger card_select
        if state["decision"] == "card_select":
            state = game.act("select_cards", indices="0")
            # Should return to shop with deck_size - 1
            if state.get("decision") == "shop":
                assert state["player"]["deck_size"] == deck_before - 1
