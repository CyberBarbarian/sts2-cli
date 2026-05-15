"""Tests for combat scenarios."""
import pytest


class TestCombatStructure:
    def test_combat_play_fields(self, game):
        state = game.start(seed="cs1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        assert state["decision"] == "combat_play"
        for key in ("round", "energy", "max_energy", "hand", "enemies",
                    "player", "draw_pile_count", "discard_pile_count", "player_powers"):
            assert key in state, f"Missing: {key}"

    def test_card_fields(self, game):
        state = game.start(seed="cs2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        for card in state["hand"]:
            assert isinstance(card["name"], str)
            assert "cost" in card
            assert "can_play" in card
            assert card["type"] in ("Attack", "Skill", "Power", "Status", "Curse")

    def test_enemy_fields(self, game):
        state = game.start(seed="cs3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        for e in state["enemies"]:
            assert isinstance(e["name"], str)
            assert e["hp"] > 0
            assert e["max_hp"] > 0
            assert "block" in e

    def test_enemy_name_interpolates_dynamic_vars(self, game):
        state = game.start(seed="test-subject-enemy-name")
        state = game.enter_room("combat", encounter="TEST_SUBJECT_BOSS")

        assert state["decision"] == "combat_play"
        names = [enemy["name"] for enemy in state["enemies"]]
        assert any("Test Subject" in name for name in names)
        assert all("{" not in name and "}" not in name for name in names)
        assert all("#C" not in name for name in names)

    def test_enemy_state_exports_next_move_name(self, game):
        state = game.start(seed="devoted-sculptor-move-name")
        state = game.enter_room("combat", encounter="DEVOTED_SCULPTOR_WEAK")

        assert state["decision"] == "combat_play"
        enemy = state["enemies"][0]
        assert enemy["move_id"] == "FORBIDDEN_INCANTATION_MOVE"
        assert enemy["move_name"] == "Forbidden Incantation"

    def test_enemy_move_name_humanizes_unlocalized_move_id(self, game):
        state = game.start(seed="slime-move-name")
        state = game.enter_room("combat", encounter="SLIMES_WEAK")

        butt_move = next(
            enemy for enemy in state["enemies"]
            if enemy.get("move_id") == "BUTT_MOVE"
        )
        assert butt_move["move_name"] == "Butt"

    def test_multi_hit_intent_exports_per_hit_and_total_damage(self, game):
        state = game.start(seed="multi-hit-intent")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="MAWLER_NORMAL")

        intent = next(
            it for it in state["enemies"][0]["intents"]
            if it["type"] == "Attack"
        )
        assert intent["hits"] == 2
        assert intent["damage"] == 4
        assert intent["total_damage"] == 8

    def test_bag_of_marbles_applies_vulnerable_at_combat_start(self, game):
        state = game.start(seed="bag-of-marbles-start")
        game.skip_neow(state)
        game.set_player(relics=["BAG_OF_MARBLES"])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        assert state["decision"] == "combat_play"
        enemy = state["enemies"][0]
        powers = enemy.get("powers") or []
        vulnerable = next((p for p in powers if p.get("name") == "Vulnerable"), None)
        assert vulnerable is not None
        assert vulnerable.get("amount") == 1


class TestPlayCards:
    def test_enemy_target_card_requires_target_index(self, game):
        state = game.start(seed="explicit-card-target")
        game.skip_neow(state)
        game.set_player(deck=["STRIKE_IRONCLAD"] * 5)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        strike = next(c for c in state["hand"] if c["name"] == "Strike")

        result = game.act("play_card", card_index=strike["index"])

        assert result["type"] == "error"
        assert "target_index" in result["message"]

    def test_all_enemies_card_does_not_require_target_index(self, game):
        state = game.start(seed="whirlwind-all-enemies")
        game.skip_neow(state)
        game.set_player(deck=["WHIRLWIND"] * 5)
        state = game.enter_room("combat", encounter="SLIMES_WEAK")

        whirlwind = next(c for c in state["hand"] if c["name"] == "Whirlwind")
        hp_before = sum(e["hp"] for e in state["enemies"])

        result = game.act("play_card", card_index=whirlwind["index"])

        assert result.get("type") != "error"
        assert whirlwind["target_type"] == "AllEnemies"
        assert sum(e["hp"] for e in result.get("enemies", [])) < hp_before

    def test_play_card_costs_energy(self, game):
        state = game.start(seed="cp1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        energy_before = state["energy"]
        playable = [c for c in state["hand"] if c.get("can_play") and c["cost"] <= energy_before]
        assert playable
        card = playable[0]
        args = {"card_index": card["index"]}
        if card.get("target_type") == "AnyEnemy":
            args["target_index"] = state["enemies"][0]["index"]
        state = game.act("play_card", **args)
        if state["decision"] == "combat_play":
            assert state["energy"] == energy_before - card["cost"]

    def test_play_attack_reduces_enemy_hp(self, game):
        state = game.start(seed="cp2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        target = state["enemies"][0]
        hp_before = target["hp"]
        attacks = [c for c in state["hand"] if c.get("can_play") and c["type"] == "Attack"
                   and c["cost"] <= state["energy"]]
        if not attacks:
            pytest.skip("No attacks in hand")
        card = attacks[0]
        args = {"card_index": card["index"]}
        if card.get("target_type") == "AnyEnemy":
            args["target_index"] = target["index"]
        state = game.act("play_card", **args)
        if state["decision"] == "combat_play":
            new_target = next((e for e in state["enemies"] if e["index"] == target["index"]), None)
            if new_target and target.get("block", 0) == 0:
                assert new_target["hp"] < hp_before

    def test_play_defend_adds_block(self, game):
        state = game.start(seed="cp3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        block_before = state["player"].get("block", 0)
        defends = [c for c in state["hand"] if c.get("can_play") and c["type"] == "Skill"
                   and c["cost"] <= state["energy"]]
        if not defends:
            pytest.skip("No skill cards")
        state = game.act("play_card", card_index=defends[0]["index"])
        if state["decision"] == "combat_play":
            assert state["player"].get("block", 0) >= block_before


class TestTurnFlow:
    def test_end_turn_advances_round(self, game):
        state = game.start(seed="tf1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        rnd = state["round"]
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            assert state["round"] == rnd + 1

    def test_end_turn_resets_energy(self, game):
        state = game.start(seed="tf2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        max_e = state["max_energy"]
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            assert state["energy"] == max_e

    def test_end_turn_draws_new_hand(self, game):
        state = game.start(seed="tf3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            assert len(state["hand"]) > 0


class TestCombatEnd:
    def test_win_combat_leads_to_reward(self, game):
        state = game.start(seed="cw1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.auto_play_combat(state)
        assert state["decision"] in ("card_reward", "map_select", "card_select", "bundle_select")

    def test_player_powers_after_enemy_debuff(self, game):
        """Shrinker Beetle applies Shrink debuff to player after its turn."""
        state = game.start(seed="ep1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        # End turn so beetle acts (applies Shrink to player)
        state = game.act("end_turn")
        if state["decision"] == "combat_play":
            pp = state.get("player_powers") or []
            assert len(pp) > 0, "Expected player debuff after Shrinker Beetle turn"
            for pw in pp:
                assert "name" in pw
                assert "amount" in pw
                assert "description" in pw


class TestCombatEdgeCases:
    def test_chomper_screech_talk_vfx_does_not_force_game_over_headless(self, game):
        state = game.start(seed="chomper-screech-talk")
        game.skip_neow(state)
        game.set_player(
            hp=80,
            max_hp=80,
            deck=["DEFEND_IRONCLAD"] * 20,
        )
        state = game.enter_room("combat", encounter="CHOMPERS_NORMAL")

        state = game.act("end_turn")

        assert state.get("type") != "error"
        assert state.get("decision") != "game_over"
        assert state["decision"] == "combat_play"
        assert state["player"]["hp"] > 0

    def test_bygone_effigy_wake_talk_vfx_does_not_deadlock_headless(self, game):
        state = game.start(seed="effigy-wake-talk")
        game.skip_neow(state)
        game.set_player(
            hp=80,
            max_hp=80,
            deck=["BREAKTHROUGH"] * 20,
        )
        state = game.enter_room("combat", encounter="BYGONE_EFFIGY_ELITE")

        for _ in range(4):
            while state.get("decision") == "combat_play":
                playable_attacks = [
                    card for card in state.get("hand", [])
                    if card.get("type") == "Attack"
                    and card.get("can_play")
                    and card.get("cost", 99) <= state.get("energy", 0)
                ]
                if not playable_attacks:
                    break
                card = playable_attacks[0]
                args = {"card_index": card["index"]}
                if card.get("target_type") == "AnyEnemy":
                    args["target_index"] = state["enemies"][0]["index"]
                state = game.act("play_card", **args)

            assert state.get("decision") == "combat_play"
            state = game.act("end_turn")
            assert state.get("decision") != "game_over"
            assert state.get("type") != "error"

        assert state["decision"] == "combat_play"
        assert state["player"]["hp"] > 0

    def test_kin_priest_ritual_talk_vfx_does_not_deadlock_headless(self, game):
        state = game.start(seed="kin-ritual-talk")
        game.skip_neow(state)
        game.set_player(
            hp=80,
            max_hp=80,
            deck=["DEFEND_IRONCLAD"] * 10 + ["SHRUG_IT_OFF"] * 10,
        )
        state = game.enter_room("combat", encounter="THE_KIN_BOSS")

        for _ in range(4):
            while state.get("decision") == "combat_play":
                playable_skills = [
                    card for card in state.get("hand", [])
                    if card.get("type") == "Skill"
                    and card.get("can_play")
                    and card.get("cost", 99) <= state.get("energy", 0)
                ]
                if not playable_skills:
                    break
                state = game.act("play_card", card_index=playable_skills[0]["index"])

            assert state.get("decision") == "combat_play"
            state = game.act("end_turn")
            assert state.get("type") != "error"

        assert state["decision"] == "combat_play"
        assert state["round"] == 5
        assert state["player"]["hp"] > 0

    def test_end_turn_during_card_select_keeps_selection(self, game):
        state = game.start(seed="pending-select-end-turn")
        game.skip_neow(state)
        game.set_player(deck=[
            "BURNING_PACT",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "STRIKE_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        burning_pact = next(c for c in state["hand"] if c["name"] == "Burning Pact")

        state = game.act("play_card", card_index=burning_pact["index"])

        assert state["decision"] == "card_select"
        state = game.act("end_turn")
        assert state["decision"] == "card_select"
        assert state["player"]["hp"] > 0

    def test_exhaust_all_and_end_turn(self, game):
        state = game.start(seed="ce1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        for _ in range(20):
            if state.get("decision") != "combat_play":
                break
            playable = [c for c in state["hand"] if c.get("can_play") and c["cost"] <= state["energy"]]
            if not playable:
                break
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state["enemies"]:
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
        if state.get("decision") == "combat_play":
            state = game.act("end_turn")
            assert state.get("type") != "error"

    def test_many_cards_per_turn(self, game):
        """Play all playable cards in a single turn without errors."""
        state = game.start(seed="inf1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        plays = 0
        for _ in range(20):
            if state.get("decision") != "combat_play":
                break
            playable = [c for c in state["hand"] if c.get("can_play")
                        and c["cost"] <= state["energy"] and c["type"] not in ("Status", "Curse")]
            if not playable:
                break
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state["enemies"]:
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
            plays += 1
            assert state.get("type") != "error", f"Error after {plays} plays: {state.get('message')}"
        assert plays >= 2

    def test_infinite_card_loop(self, game):
        """Pommel Strike + Bloodletting infinite loop doesn't crash.

        Pommel Strike (1e): damage + draw 1
        Bloodletting (0e): lose HP + gain 2 energy
        Each cycle: net +1 energy, draws next card. Truly infinite.
        """
        state = game.start(seed="inf2")
        game.skip_neow(state)
        game.set_player(hp=80, max_hp=80, deck=["POMMEL_STRIKE"] * 5 + ["BLOODLETTING"] * 5)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        plays = 0
        for _ in range(60):
            if state.get("decision") != "combat_play":
                break
            hand = state.get("hand", [])
            energy = state.get("energy", 0)
            playable = [c for c in hand if c.get("can_play") and c["cost"] <= energy
                        and c["type"] not in ("Status", "Curse")]
            if not playable:
                break
            card = playable[0]
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and state["enemies"]:
                args["target_index"] = state["enemies"][0]["index"]
            state = game.act("play_card", **args)
            plays += 1
            assert state.get("type") != "error", f"Error after {plays} plays: {state.get('message')}"

        # With Pommel Strike + Bloodletting, should play many cards before enemy dies
        assert plays >= 5, f"Expected infinite loop plays >= 5, got {plays}"

    def test_low_hp_death(self, game):
        """Player with 1 HP should die to any attack."""
        state = game.start(seed="ce2")
        game.skip_neow(state)
        game.set_player(hp=1)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        # Just end turn, beetle will kill us
        state = game.act("end_turn")
        # Might need another turn
        for _ in range(10):
            if state.get("decision") == "game_over":
                break
            if state.get("decision") == "combat_play":
                state = game.act("end_turn")
            else:
                break
        assert state["decision"] == "game_over"
        assert state["victory"] is False

    def test_enemy_turn_card_selection_is_returned_before_retrying_end_turn(self, game):
        state = game.start(seed="knowledge-demon-selection")
        game.skip_neow(state)
        game.set_player(
            hp=999,
            max_hp=999,
            deck=["STRIKE_IRONCLAD"] * 5 + ["DEFEND_IRONCLAD"] * 5,
        )
        state = game.enter_room("combat", encounter="KNOWLEDGE_DEMON_BOSS")

        assert state["decision"] == "combat_play"
        assert state["enemies"][0]["move_name"] == "Curse of Knowledge"

        state = game.act("end_turn")

        assert state["decision"] == "card_select"
        assert state["min_select"] == 0
        assert state["max_select"] == 1
        assert state["cards"]

    def test_soul_nexus_death_does_not_leave_combat_active(self, game):
        state = game.start(seed="soul-nexus-death-cleanup")
        game.skip_neow(state)
        game.set_player(hp=999, max_hp=999, deck=["BLUDGEON"] * 12)
        state = game.enter_room("combat", encounter="SOUL_NEXUS_ELITE")

        for _ in range(80):
            if state.get("decision") != "combat_play":
                break
            playable = [card for card in state["hand"] if card.get("can_play")]
            if playable:
                card = playable[0]
                state = game.act("play_card", card_index=card["index"], target_index=0)
            else:
                state = game.act("end_turn")

        assert state["decision"] == "card_reward"

        state = game.act("skip_card_reward")
        assert state["decision"] == "map_select"

        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        assert state["decision"] == "combat_play"
