"""Tests for potion action handling."""


class TestPotionActions:
    def test_player_potions_export_resolved_descriptions(self, game):
        state = game.start(seed="potion-description-formatters")
        game.skip_neow(state)
        game.set_player(
            potions=["CURE_ALL", "RADIANT_TINCTURE"],
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )

        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        potions = {p["name"]: p for p in state["player"]["potions"]}

        cure_all = potions["Cure All"]
        assert "{Energy:energyIcons()}" not in cure_all["description"]
        assert "{Cards:plural" not in cure_all["description"]
        assert "2 cards" in cure_all["description"]

        radiant = potions["Radiant Tincture"]
        assert "{energyPrefix:energyIcons(1)}" not in radiant["description"]
        assert "{RadiancePower:plural" not in radiant["description"]
        assert "3 turns" in radiant["description"]

    def test_enemy_target_potion_requires_target_index(self, game):
        state = game.start(seed="explicit-potion-target")
        game.skip_neow(state)
        game.set_player(
            potions=["FIRE_POTION"],
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        assert state["player"]["potions"][0]["target_type"] == "AnyEnemy"

        result = game.act("use_potion", potion_index=0)

        assert result["type"] == "error"
        assert "target_index" in result["message"]

    def test_any_player_potion_targets_player(self, game):
        state = game.start(seed="blood-search-75")
        state = game.skip_neow(state)
        assert state["player"]["potions"][0]["name"] == "Blood Potion"

        game.set_player(
            hp=40,
            max_hp=80,
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        assert state["player"]["potions"][0]["target_type"] == "AnyPlayer"

        state = game.act("use_potion", potion_index=0)

        assert state["player"]["hp"] == 56
        assert state["player"]["potions"] == []

    def test_speed_potion_temp_power_has_readable_name(self, game):
        state = game.start(seed="speed-power-name")
        game.skip_neow(state)
        game.set_player(
            potions=["SPEED_POTION"],
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        state = game.act("use_potion", potion_index=0)

        powers = state.get("player_powers") or []
        power_names = [power["name"] for power in powers]
        assert "Speed Potion" in power_names
        assert all(not name.endswith(".title") for name in power_names)
        assert all(not power["description"].endswith(".description") for power in powers)

    def test_enemy_power_descriptions_after_potion_use_resolve_amount(self, game):
        state = game.start(seed="potion-enemy-power-description")
        game.skip_neow(state)
        game.set_player(
            potions=["POWDERED_DEMISE"],
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        state = game.act("use_potion", potion_index=0, target_index=0)

        demise = next(power for power in state["enemies"][0]["powers"] if power["name"] == "Demise")
        assert "9" in demise["description"]
        assert " X " not in demise["description"]

    def test_liquid_memories_opens_discard_selection(self, game):
        state = game.start(seed="liquid-memories-selection")
        game.skip_neow(state)
        game.set_player(
            potions=["LIQUID_MEMORIES"],
            deck=[
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        for _ in range(2):
            strike = next(card for card in state["hand"] if card["name"] == "Strike")
            state = game.act("play_card", card_index=strike["index"], target_index=0)

        assert state["discard_pile_count"] == 2

        state = game.act("use_potion", potion_index=0)

        assert state["decision"] == "card_select"
        assert state["min_select"] == 1
        assert state["max_select"] == 1
        assert [card["name"] for card in state["cards"]] == ["Strike", "Strike"]

        state = game.act("select_cards", indices="0")

        assert state["decision"] == "combat_play"
        assert state["player"]["potions"] == []
        assert any(card["name"] == "Strike" and card["cost"] == 0 for card in state["hand"])
        assert len(state["hand"]) == 4

    def test_liquid_memories_temporary_cost_does_not_change_static_upgrade_cost(self, game):
        state = game.start(seed="liquid-memories-static-upgrade-cost")
        game.skip_neow(state)
        game.set_player(
            potions=["LIQUID_MEMORIES"],
            deck=["FISTICUFFS"] * 5,
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        for _ in range(2):
            card = next(card for card in state["hand"] if card["name"] == "Fisticuffs")
            state = game.act("play_card", card_index=card["index"], target_index=0)

        state = game.act("use_potion", potion_index=0)
        state = game.act("select_cards", indices="0")

        recalled = next(card for card in state["hand"] if card["name"] == "Fisticuffs" and card["cost"] == 0)
        assert recalled["after_upgrade"]["cost"] == 1

    def test_liquid_memories_discard_selection_does_not_export_hand_target_rows(self, game):
        state = game.start(seed="liquid-memories-selection-pile-stats")
        game.skip_neow(state)
        game.set_player(
            potions=["LIQUID_MEMORIES"],
            deck=[
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
                "STRIKE_IRONCLAD",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        for _ in range(2):
            strike = next(card for card in state["hand"] if card["name"] == "Strike")
            state = game.act("play_card", card_index=strike["index"], target_index=0)
        state = game.act("use_potion", potion_index=0)

        assert state["decision"] == "card_select"
        selected = state["cards"][0]
        assert selected["name"] == "Strike"
        assert "damage_by_target" not in selected["stats"]

    def test_skill_potion_accepts_json_array_selection_indices(self, game):
        state = game.start(seed="skill-potion-array-selection")
        game.skip_neow(state)
        game.set_player(
            potions=["SKILL_POTION"],
            deck=[
                "STRIKE_SILENT",
                "DEFEND_SILENT",
                "DEFEND_SILENT",
                "STRIKE_SILENT",
                "STRIKE_SILENT",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        state = game.act("use_potion", potion_index=0)

        assert state["decision"] == "card_select"
        selected = state["cards"][0]

        state = game.act("select_cards", indices=[selected["index"]])

        assert state["decision"] == "combat_play"
        assert state["player"]["potions"] == []
        assert any(card["name"] == selected["name"] for card in state["hand"])

    def test_attack_potion_card_select_carries_source_potion_context(self, game):
        state = game.start(seed="attack-potion-select-context")
        game.skip_neow(state)
        game.set_player(
            potions=["ATTACK_POTION"],
            deck=[
                "STRIKE_DEFECT",
                "DEFEND_DEFECT",
                "ZAP",
                "DUALCAST",
                "GO_FOR_THE_EYES",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        potion = state["player"]["potions"][0]

        state = game.act("use_potion", potion_index=0)

        assert state["decision"] == "card_select"
        assert state["prompt"] == f"{potion['name']}: {potion['description']}"
        source = state["source_potion"]
        assert source["name"] == "Attack Potion"
        assert source["description"] == potion["description"]
        assert source["target_type"] == "Self"

    def test_touch_of_insanity_card_select_exports_combat_preview_stats(self, game):
        state = game.start(seed="touch-selection-combat-stats")
        game.skip_neow(state)
        game.set_player(
            potions=["TOUCH_OF_INSANITY"],
            deck=[
                "INFLAME",
                "BASH",
                "PERFECTED_STRIKE",
                "POMMEL_STRIKE",
                "STRIKE_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        inflame = next(card for card in state["hand"] if card["name"] == "Inflame")
        state = game.act("play_card", card_index=inflame["index"])

        state = game.act("use_potion", potion_index=0)

        assert state["decision"] == "card_select"
        bash = next(card for card in state["cards"] if card["name"] == "Bash")
        assert bash["description"].startswith("Deal 10 damage.")
        assert bash["stats"]["damage"] == 10

    def test_touch_of_insanity_engine_auto_selects_one_playable_card(self, game):
        state = game.start(seed="touch-selection-single-playable")
        game.skip_neow(state)
        game.set_player(
            potions=["TOUCH_OF_INSANITY"],
            deck=["BASH", "INJURY"],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        state = game.act("use_potion", potion_index=0)

        assert state["decision"] == "combat_play"
        assert state["player"]["potions"] == []
        bash = next(card for card in state["hand"] if card["name"] == "Bash")
        assert bash["cost"] == 0

    def test_full_potion_slots_block_potion_reward_claim(self, game):
        state = game.start(seed="full-potion-reward-1", ascension=10)
        game.skip_neow(state)
        game.set_player(
            hp=999,
            max_hp=999,
            potions=["STRENGTH_POTION", "STRENGTH_POTION"],
            deck=["BLUDGEON"] * 8,
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        for _ in range(10):
            if state["decision"] != "combat_play":
                break
            bludgeon = next(c for c in state["hand"] if c["name"] == "Bludgeon" and c["can_play"])
            state = game.act("play_card", card_index=bludgeon["index"], target_index=0)
            if state["decision"] == "combat_play":
                state = game.act("end_turn")

        potion_reward = next(r for r in state["rewards"] if r["kind"] == "potion")
        assert potion_reward["can_claim"] is False
        assert potion_reward["can_skip"] is True
        assert potion_reward["blocked_reason"] == "potion_slots_full"

        result = game.act("claim_reward", reward_index=potion_reward["index"])

        assert result["type"] == "error"
        assert "potion" in result["message"].lower()
        assert "full" in result["message"].lower()

        state = game.act("discard_potion", potion_index=0)
        potion_reward = next(r for r in state["rewards"] if r["kind"] == "potion")
        state = game.act("claim_reward", reward_index=potion_reward["index"])

        assert any(p["name"] == "Orobic Acid" for p in state["player"]["potions"])

    def test_full_potion_reward_can_be_skipped_without_discarding(self, game):
        state = game.start(seed="full-potion-reward-1", ascension=10)
        game.skip_neow(state)
        game.set_player(
            hp=999,
            max_hp=999,
            potions=["STRENGTH_POTION", "STRENGTH_POTION"],
            deck=["BLUDGEON"] * 8,
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        for _ in range(10):
            if state["decision"] != "combat_play":
                break
            bludgeon = next(c for c in state["hand"] if c["name"] == "Bludgeon" and c["can_play"])
            state = game.act("play_card", card_index=bludgeon["index"], target_index=0)
            if state["decision"] == "combat_play":
                state = game.act("end_turn")

        before_potions = [p["id"] for p in state["player"]["potions"]]
        potion_reward = next(r for r in state["rewards"] if r["kind"] == "potion")

        state = game.act("skip_reward", reward_index=potion_reward["index"])

        assert [p["id"] for p in state["player"]["potions"]] == before_potions
        assert all(r["kind"] != "potion" for r in state.get("rewards", []))

    def test_player_export_includes_empty_potion_slots_after_potion_belt(self, game):
        state = game.start(seed="potion-belt-slot-export")
        game.skip_neow(state)

        baseline = game.set_player(
            potions=["STRENGTH_POTION", "FIRE_POTION"],
        )
        base_slots = baseline["player"]["potion_slots"]

        state = game.set_player(
            relics=["POTION_BELT"],
            potions=["STRENGTH_POTION", "FIRE_POTION"],
        )

        player = state["player"]
        assert player["potion_slots"] == base_slots + 2
        assert player["potion_empty_slots"] == player["potion_slots"] - 2
        assert [p["index"] for p in player["potions"]] == [0, 1]
