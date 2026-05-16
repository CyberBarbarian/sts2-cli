"""Tests for card rewards."""
import pytest


class TestCardReward:
    def test_non_card_combat_rewards_require_explicit_claim(self, game):
        state = game.start(seed="cr-explicit-reward")
        game.skip_neow(state)
        gold_before = state["player"]["gold"]
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)

        assert state["decision"] == "combat_reward"
        gold_rewards = [r for r in state["rewards"] if r["kind"] == "gold"]
        assert gold_rewards
        assert state["player"]["gold"] == gold_before

        state = game.act("claim_reward", reward_index=gold_rewards[0]["index"])
        assert state["player"]["gold"] > gold_before

    def test_card_reward_after_combat(self, game):
        state = game.start(seed="cr1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)
        # After combat we expect card_reward (or bundle_select, card_select)
        assert state["decision"] in ("combat_reward", "card_reward", "bundle_select", "card_select", "map_select")

    def test_card_reward_structure(self, game):
        state = game.start(seed="cr2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)
        state = game.claim_combat_rewards(state)
        if state["decision"] != "card_reward":
            pytest.skip("No card_reward after this fight")
        assert len(state["cards"]) > 0
        for card in state["cards"]:
            assert isinstance(card["name"], str)
            assert "cost" in card
            assert "type" in card
            assert "upgraded" in card

    def test_special_card_reward_exports_card_details(self, game):
        state = game.start(seed="hopper-special-reward-2")
        game.skip_neow(state)
        game.set_player(
            hp=80,
            max_hp=80,
            relics=["BURNING_BLOOD", "VERY_HOT_COCOA"],
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "THUNDERCLAP",
                "PERFECTED_STRIKE",
                "PERFECTED_STRIKE",
                "BLUDGEON",
                "BLUDGEON",
                "TWIN_STRIKE",
                "DISMANTLE",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="THIEVING_HOPPER_WEAK")

        thunderclap = next(c for c in state["hand"] if c["name"] == "Thunderclap")
        state = game.act("play_card", card_index=thunderclap["index"])
        perfected = next(c for c in state["hand"] if c["name"] == "Perfected Strike")
        state = game.act("play_card", card_index=perfected["index"], target_index=0)
        game.set_draw_order([
            "BLUDGEON",
            "BLUDGEON",
            "TWIN_STRIKE",
            "DISMANTLE",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
        ])
        state = game.act("end_turn")

        for _ in range(20):
            if state["decision"] != "combat_play":
                break
            playable_attacks = []
            for card in state["hand"]:
                if not card.get("can_play"):
                    continue
                if card.get("target_type") not in ("AnyEnemy", "AllEnemies"):
                    continue
                stats = card.get("stats") or {}
                rows = stats.get("damage_by_target") or stats.get("calculateddamage_by_target") or []
                damage = 0
                if rows:
                    damage = (
                        rows[0].get("total_damage")
                        or rows[0].get("calculateddamage")
                        or rows[0].get("damage")
                        or 0
                    )
                playable_attacks.append((damage, card))
            if not playable_attacks:
                state = game.act("end_turn")
                continue
            card = max(playable_attacks, key=lambda item: item[0])[1]
            args = {"card_index": card["index"]}
            if card["target_type"] == "AnyEnemy":
                args["target_index"] = 0
            state = game.act("play_card", **args)

        assert state["decision"] == "combat_reward"
        special = next(r for r in state["rewards"] if r["type_name"] == "SpecialCardReward")

        assert special["kind"] == "card"
        assert special["id"].startswith("CARD.")
        assert special["name"]
        assert special["cost"] is not None
        assert special["type"]
        assert special["rarity"]
        assert "stats" in special

    def test_select_card_adds_to_deck(self, game):
        state = game.start(seed="cr3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)
        state = game.claim_combat_rewards(state)
        if state["decision"] != "card_reward":
            pytest.skip("No card_reward")
        deck_before = state["player"]["deck_size"]
        state = game.act("select_card_reward", card_index=state["cards"][0]["index"])
        deck_after = state.get("player", {}).get("deck_size", deck_before)
        assert deck_after == deck_before + 1

    def test_skip_card(self, game):
        state = game.start(seed="cr4")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)
        state = game.claim_combat_rewards(state)
        if state["decision"] != "card_reward":
            pytest.skip("No card_reward")
        deck_before = state["player"]["deck_size"]
        state = game.act("skip_card_reward")
        deck_after = state.get("player", {}).get("deck_size", deck_before)
        assert deck_after == deck_before
