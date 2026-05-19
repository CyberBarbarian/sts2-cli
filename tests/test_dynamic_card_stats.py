"""Tests for dynamic card stat exports."""


class TestDynamicCardStats:
    def test_regent_sprite_font_icons_do_not_leak_resource_paths(self, game):
        state = game.start(character="Regent", seed="regent-sprite-font-icons")
        deck = {card["name"]: card for card in state["player"]["deck"]}

        venerate = deck["Venerate"]

        assert "res://" not in venerate["description"]
        assert "[S]" in venerate["description"]
        assert "star_icon.png" not in venerate["description"]

        game.skip_neow(state)
        game.set_player(relics=["DIVINE_RIGHT"])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        divine_right = next(r for r in state["player"]["relics"] if r["id"] == "DIVINE_RIGHT")

        assert "res://" not in divine_right["description"]
        assert "[S]" in divine_right["description"]
        assert "star_icon.png" not in divine_right["description"]

    def test_perfected_strike_exports_current_calculated_damage(self, game):
        state = game.start(seed="perfected-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "PERFECTED_STRIKE",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "SETUP_STRIKE",
            "ASHEN_STRIKE",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        card = next(c for c in state["hand"] if c["name"] == "Perfected Strike")
        stats = card["stats"]

        assert stats["calculateddamage"] > stats["calculationbase"]

    def test_perfected_strike_does_not_double_count_hand_copy(self, game):
        state = game.start(seed="perfected-stats-exact")
        game.skip_neow(state)
        game.set_player(deck=[
            "PERFECTED_STRIKE",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        card = next(c for c in state["hand"] if c["name"] == "Perfected Strike")

        assert card["stats"]["calculateddamage"] == 16

    def test_perfected_strike_after_upgrade_uses_engine_noncombat_preview(self, game):
        state = game.start(seed="perfected-upgrade-preview")
        game.skip_neow(state)
        state = game.set_player(deck=[
            "PERFECTED_STRIKE",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
        ])

        card = next(c for c in state["player"]["deck"] if c["name"] == "Perfected Strike")
        upgraded_stats = card["after_upgrade"]["stats"]

        assert upgraded_stats["extradamage"] == 3
        assert upgraded_stats["calculateddamage"] == upgraded_stats["calculationbase"]

    def test_barrage_after_upgrade_preview_uses_current_orb_count(self, game):
        state = game.start(character="Defect", seed="barrage-upgrade-preview")
        game.skip_neow(state)
        game.set_player(
            relics=["CRACKED_CORE"],
            deck=[
                "STRIKE_DEFECT",
                "DEFEND_DEFECT",
                "ZAP",
                "DUALCAST",
                "STRIKE_DEFECT",
                "DEFEND_DEFECT",
                "STRIKE_DEFECT",
                "DEFEND_DEFECT",
                "BARRAGE",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        barrage = next(c for c in state["draw_pile"] if c["name"] == "Barrage")
        upgraded = barrage["after_upgrade"]

        assert barrage["stats"]["calculatedhits"] == 1
        assert upgraded["stats"]["calculatedhits"] == 1
        assert "(Hits 1 time)" in upgraded["description"]
        assert upgraded["stats"]["damage_by_target"][0]["unblocked_damage"] == 7

    def test_adaptive_strike_description_uses_current_damage_preview(self, game):
        state = game.start(character="Defect", seed="adaptive-strike-preview-text")
        game.skip_neow(state)
        game.set_player(
            deck=[
                "ADAPTIVE_STRIKE",
                "STRIKE_DEFECT",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
            ],
            potions=["FLEX_POTION"],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        state = game.act("use_potion", potion_index=0)

        adaptive = next(c for c in state["hand"] if c["name"] == "Adaptive Strike")

        assert adaptive["description"].startswith(
            f"Deal {adaptive['stats']['damage']} damage."
        )

    def test_bully_exports_vulnerable_damage_by_target(self, game):
        state = game.start(seed="bully-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "BASH",
            "BULLY",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        bash = next(c for c in state["hand"] if c["name"] == "Bash")

        state = game.act("play_card", card_index=bash["index"], target_index=0)

        bully = next(c for c in state["hand"] if c["name"] == "Bully")
        stats = bully["stats"]
        target_stats = stats["calculateddamage_by_target"][0]
        assert stats["calculateddamage"] == stats["calculationbase"]
        assert target_stats["calculateddamage"] > stats["calculationbase"]

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=bully["index"], target_index=0)
        assert hp_before - state["enemies"][0]["hp"] == target_stats["calculateddamage"]

    def test_bully_exports_target_specific_vulnerable_damage(self, game):
        state = game.start(seed="bully-target-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "BASH",
            "BULLY",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="NIBBITS_NORMAL")
        bash = next(c for c in state["hand"] if c["name"] == "Bash")

        state = game.act("play_card", card_index=bash["index"], target_index=0)

        bully = next(c for c in state["hand"] if c["name"] == "Bully")
        target_stats = bully["stats"]["calculateddamage_by_target"]
        assert len(target_stats) >= 2
        assert target_stats[0]["calculateddamage"] > target_stats[1]["calculateddamage"]
        assert target_stats[0]["vulnerable"] == 2
        assert target_stats[1]["vulnerable"] == 0

    def test_attack_damage_exports_target_specific_vulnerable_damage(self, game):
        state = game.start(seed="attack-target-vulnerable-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "BASH",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="NIBBITS_NORMAL")
        bash = next(c for c in state["hand"] if c["name"] == "Bash")

        state = game.act("play_card", card_index=bash["index"], target_index=0)

        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        target_stats = strike["stats"]["damage_by_target"]
        assert len(target_stats) >= 2
        assert strike["stats"]["damage"] == 6
        assert target_stats[0]["damage"] == 9
        assert target_stats[1]["damage"] == 6
        assert target_stats[0]["vulnerable"] == 2
        assert target_stats[1]["vulnerable"] == 0

    def test_attack_damage_stats_include_target_slow(self, game):
        state = game.start(seed="attack-target-slow-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "VICIOUS",
            "INFLAME",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "BLOOD_WALL",
        ])
        state = game.enter_room("combat", encounter="BYGONE_EFFIGY_ELITE")
        vicious = next(c for c in state["hand"] if c["name"] == "Vicious")

        state = game.act("play_card", card_index=vicious["index"])
        inflame = next(c for c in state["hand"] if c["name"] == "Inflame")
        state = game.act("play_card", card_index=inflame["index"])

        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        target_stats = strike["stats"]["damage_by_target"][0]
        assert strike["stats"]["damage"] == 8
        assert target_stats["damage"] == 9

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=strike["index"], target_index=0)
        assert hp_before - state["enemies"][0]["hp"] == target_stats["damage"]

    def test_dismantle_exports_target_specific_vulnerable_repeat(self, game):
        state = game.start(seed="dismantle-target-repeat-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "BASH",
            "DISMANTLE",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        bash = next(c for c in state["hand"] if c["name"] == "Bash")

        state = game.act("play_card", card_index=bash["index"], target_index=0)

        dismantle = next(c for c in state["hand"] if c["name"] == "Dismantle")
        target_stats = dismantle["stats"]["damage_by_target"][0]
        assert target_stats["damage"] == 12
        assert target_stats["repeat"] == 2
        assert target_stats["total_damage"] == 24

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=dismantle["index"], target_index=0)
        assert hp_before - state["enemies"][0]["hp"] == target_stats["total_damage"]

    def test_fiend_fire_exports_hand_exhaust_total_damage(self, game):
        state = game.start(seed="fiend-fire-hand-repeat-stats")
        game.skip_neow(state)
        game.set_player(
            hp=999,
            max_hp=999,
            deck=[
                "FIEND_FIRE",
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "BASH",
                "TWIN_STRIKE",
            ],
        )
        state = game.enter_room("combat", encounter="ENTOMANCER_ELITE")

        fiend_fire = next(c for c in state["hand"] if c["name"] == "Fiend Fire")
        target_stats = fiend_fire["stats"]["damage_by_target"][0]
        expected_repeat = len(state["hand"]) - 1
        assert target_stats["repeat"] == expected_repeat
        assert target_stats["total_damage"] == target_stats["damage"] * expected_repeat

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=fiend_fire["index"], target_index=0)
        assert hp_before - state["enemies"][0]["hp"] == target_stats["total_damage"]

    def test_x_cost_details_are_limited_to_combat_hand(self, game):
        state = game.start(seed="whirlwind-x-cost-display-only")
        game.skip_neow(state)
        game.set_player(deck=[
            "WHIRLWIND",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])

        state = game.enter_room("rest_site")
        deck_whirlwind = next(c for c in state["player"]["deck"] if c["name"] == "Whirlwind")
        assert deck_whirlwind["cost"] == "X"
        assert "energy_cost" not in deck_whirlwind
        assert "x_value" not in deck_whirlwind
        assert deck_whirlwind["after_upgrade"]["cost"] == "X"
        assert "energy_cost" not in deck_whirlwind["after_upgrade"]
        assert "x_value" not in deck_whirlwind["after_upgrade"]

        state = game.enter_room("combat", encounter="SLIMES_WEAK")
        hand_whirlwind = next(c for c in state["hand"] if c["name"] == "Whirlwind")
        assert hand_whirlwind["cost"] == "X"
        assert hand_whirlwind["energy_cost"] == state["energy"]
        assert hand_whirlwind["x_value"] == state["energy"]

    def test_energy_icon_upgrade_preview_repeats_cli_energy_tokens(self, game):
        state = game.start(seed="forgotten-ritual-energy-icon-preview")
        game.skip_neow(state)
        state = game.set_player(deck=[
            "FORGOTTEN_RITUAL",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "BASH",
        ])

        ritual = next(c for c in state["player"]["deck"] if c["name"] == "Forgotten Ritual")
        upgraded_description = ritual["after_upgrade"]["description"]

        assert "4[E]" not in upgraded_description
        assert "energy_icon.png" not in upgraded_description
        assert upgraded_description.count("[E]") == 4

    def test_x_cost_aoe_exports_current_repeat_damage(self, game):
        state = game.start(seed="whirlwind-current-repeat-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "WHIRLWIND",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SLIMES_WEAK")

        whirlwind = next(c for c in state["hand"] if c["name"] == "Whirlwind")
        assert whirlwind["cost"] == "X"
        assert whirlwind["energy_cost"] == state["energy"]
        assert whirlwind["x_value"] == state["energy"]
        target_stats = whirlwind["stats"]["damage_by_target"]
        assert len(target_stats) >= 2
        target = next(
            t for t in target_stats
            if next(e for e in state["enemies"] if e["index"] == t["target_index"])["hp"]
            > t["damage"] * whirlwind["x_value"]
        )
        assert target["repeat"] == whirlwind["x_value"]
        assert target["total_damage"] == (
            target["damage"] * whirlwind["x_value"]
        )

        hp_before = next(
            e["hp"] for e in state["enemies"] if e["index"] == target["target_index"]
        )
        state = game.act("play_card", card_index=whirlwind["index"])
        hp_after = next(
            (e["hp"] for e in state.get("enemies", []) if e["name"] == target["target_name"]),
            0,
        )
        assert hp_before - hp_after == target["total_damage"]

    def test_x_cost_repeat_exports_consumed_slippery_total_damage(self, game):
        state = game.start(seed="whirlwind-slippery-consumed-repeat")
        game.skip_neow(state)
        game.set_player(
            hp=999,
            max_hp=999,
            deck=(["ANGER"] * 16) + (["WHIRLWIND"] * 4) + ["DEFEND_IRONCLAD"],
        )
        state = game.enter_room("combat", encounter="VANTOM_BOSS")

        game.set_draw_order([
            "ANGER",
            "ANGER",
            "ANGER",
            "ANGER",
            "ANGER",
        ])
        state = game.act("end_turn")

        for _ in range(5):
            anger = next(card for card in state["hand"] if card["name"] == "Anger")
            state = game.act("play_card", card_index=anger["index"], target_index=0)

        game.set_draw_order([
            "ANGER",
            "ANGER",
            "ANGER",
            "WHIRLWIND",
            "DEFEND_IRONCLAD",
        ])
        state = game.act("end_turn")
        for _ in range(3):
            anger = next(card for card in state["hand"] if card["name"] == "Anger")
            state = game.act("play_card", card_index=anger["index"], target_index=0)

        slippery = next(power for power in state["enemies"][0]["powers"] if power["name"] == "Slippery")
        assert slippery["amount"] == 1

        whirlwind = next(card for card in state["hand"] if card["name"] == "Whirlwind")
        target = whirlwind["stats"]["damage_by_target"][0]
        assert target["repeat"] == state["energy"]

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=whirlwind["index"])
        hp_after = state["enemies"][0]["hp"]

        assert hp_before - hp_after == target["total_damage"]

    def test_x_cost_aoe_exports_zero_repeat_damage(self, game):
        state = game.start(seed="whirlwind-zero-repeat-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "WHIRLWIND",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SLIMES_WEAK")

        while state["energy"] > 0:
            defend = next(c for c in state["hand"] if c["name"] == "Defend")
            state = game.act("play_card", card_index=defend["index"])

        whirlwind = next(c for c in state["hand"] if c["name"] == "Whirlwind")
        assert whirlwind["x_value"] == 0
        assert whirlwind["stats"]["repeat"] == 0
        target = whirlwind["stats"]["damage_by_target"][0]
        assert target["repeat"] == 0
        assert target["total_damage"] == 0
        assert target["unblocked_total_damage"] == 0
        assert "unblocked_damage" not in target

    def test_heavenly_drill_exports_doubled_x_target_repeat_at_threshold(self, game):
        state = game.start(character="Regent", seed="heavenly-drill-threshold-stats")
        game.skip_neow(state)
        game.set_player(
            relics=[],
            deck=[
                "BIG_BANG",
                "HEAVENLY_DRILL",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
            ],
        )
        state = game.enter_room("combat", encounter="FROG_KNIGHT_NORMAL")

        big_bang = next(c for c in state["hand"] if c["name"] == "Big Bang")
        state = game.act("play_card", card_index=big_bang["index"])

        drill = next(c for c in state["hand"] if c["name"] == "Heavenly Drill")
        assert drill["cost"] == "X"
        assert drill["x_value"] == 4
        target = drill["stats"]["damage_by_target"][0]
        assert target["repeat"] == 8
        assert target["total_damage"] == target["damage"] * target["repeat"]
        assert target["unblocked_total_damage"] == max(
            0,
            target["total_damage"] - target["block"],
        )

        hp_before = state["enemies"][0]["hp"]
        state = game.act(
            "play_card",
            card_index=drill["index"],
            target_index=target["target_index"],
        )
        hp_after = next(
            (
                enemy["hp"]
                for enemy in state.get("enemies", [])
                if enemy["name"] == target["target_name"]
            ),
            0,
        )
        assert hp_before - hp_after == target["unblocked_total_damage"]

    def test_dynamic_zero_hit_attack_exports_zero_target_damage(self, game):
        state = game.start(character="Regent", seed="radiate-zero-hit-stats")
        game.skip_neow(state)
        game.set_player(
            relics=[],
            deck=[
                "RADIATE",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        radiate = next(c for c in state["hand"] if c["name"] == "Radiate")
        assert radiate["stats"]["calculatedhits"] == 0
        target = radiate["stats"]["damage_by_target"][0]
        assert target["repeat"] == 0
        assert target["total_damage"] == 0
        assert target["unblocked_total_damage"] == 0
        assert "unblocked_damage" not in target

    def test_radiate_export_matches_throne_on_play_star_gain(self, game):
        state = game.start(character="Regent", seed="radiate-repro-seed-1")
        game.skip_neow(state)
        game.set_player(
            relics=["DIVINE_RIGHT"],
            deck=[
                "THE_SEALED_THRONE",
                "RADIATE",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "STRIKE_REGENT",
                "STRIKE_REGENT",
                "STRIKE_REGENT",
                "STRIKE_REGENT",
                "STRIKE_REGENT",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        game.set_draw_order(["RADIATE"])

        throne = next(c for c in state["hand"] if c["name"] == "The Sealed Throne")
        state = game.act("play_card", card_index=throne["index"])

        defend = next(c for c in state["hand"] if c["name"] == "Defend")
        state = game.act("play_card", card_index=defend["index"])
        state = game.act("end_turn")

        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        state = game.act("play_card", card_index=strike["index"], target_index=0)

        radiate = next(c for c in state["hand"] if c["name"] == "Radiate")
        target = radiate["stats"]["damage_by_target"][0]
        hp_before = state["enemies"][0]["hp"]

        state = game.act("play_card", card_index=radiate["index"])

        hp_after = state["enemies"][0]["hp"]
        exported_unblocked = target.get(
            "unblocked_total_damage",
            target.get("unblocked_damage"),
        )
        assert hp_before - hp_after == exported_unblocked

    def test_star_spend_strength_relic_updates_target_damage_export(self, game):
        state = game.start(character="Regent", seed="mini-regent-comet-stats")
        game.skip_neow(state)
        game.set_player(
            relics=["DIVINE_RIGHT", "MINI_REGENT"],
            deck=[
                "VENERATE",
                "COMET",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
            ],
        )
        state = game.enter_room("combat", encounter="FROG_KNIGHT_NORMAL")

        venerate = next(c for c in state["hand"] if c["name"] == "Venerate")
        state = game.act("play_card", card_index=venerate["index"])

        comet = next(c for c in state["hand"] if c["name"] == "Comet")
        target = comet["stats"]["damage_by_target"][0]
        hp_before = state["enemies"][0]["hp"]

        state = game.act(
            "play_card",
            card_index=comet["index"],
            target_index=target["target_index"],
        )

        hp_after = state["enemies"][0]["hp"]
        assert hp_before - hp_after == target["unblocked_damage"]

    def test_star_spend_strength_relic_updates_vulnerable_target_damage_export(self, game):
        state = game.start(character="Regent", seed="mini-regent-comet-vulnerable-stats")
        game.skip_neow(state)
        game.set_player(
            relics=["DIVINE_RIGHT", "MINI_REGENT", "BAG_OF_MARBLES"],
            deck=[
                "VENERATE",
                "COMET",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
            ],
        )
        state = game.enter_room("combat", encounter="FROG_KNIGHT_NORMAL")

        venerate = next(c for c in state["hand"] if c["name"] == "Venerate")
        state = game.act("play_card", card_index=venerate["index"])

        comet = next(c for c in state["hand"] if c["name"] == "Comet")
        target = comet["stats"]["damage_by_target"][0]
        assert target["vulnerable"] > 0
        hp_before = state["enemies"][0]["hp"]

        state = game.act(
            "play_card",
            card_index=comet["index"],
            target_index=target["target_index"],
        )

        hp_after = state["enemies"][0]["hp"]
        assert hp_before - hp_after == target["unblocked_damage"]

    def test_star_spend_strength_relic_applies_once_per_turn_export(self, game):
        state = game.start(character="Regent", seed="mini-regent-second-star-spend")
        game.skip_neow(state)
        game.set_player(
            relics=["DIVINE_RIGHT", "MINI_REGENT"],
            deck=[
                "BIG_BANG",
                "GUIDING_STAR",
                "FALLING_STAR",
                "DEFEND_REGENT",
                "DEFEND_REGENT",
            ],
        )
        state = game.enter_room("combat", encounter="FROG_KNIGHT_NORMAL")

        big_bang = next(card for card in state["hand"] if card["name"] == "Big Bang")
        state = game.act("play_card", card_index=big_bang["index"])

        guiding_star = next(card for card in state["hand"] if card["name"] == "Guiding Star")
        state = game.act("play_card", card_index=guiding_star["index"], target_index=0)

        falling_star = next(card for card in state["hand"] if card["name"] == "Falling Star")
        target = falling_star["stats"]["damage_by_target"][0]
        assert "pre_attack_strength_delta" not in target

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=falling_star["index"], target_index=0)
        assert hp_before - state["enemies"][0]["hp"] == target["unblocked_damage"]

    def test_star_spend_strength_relic_respects_intangible_export(self, game):
        state = game.start(character="Regent", seed="mini-regent-intangible-stats")
        game.skip_neow(state)
        game.set_player(
            hp=9999,
            max_hp=9999,
            relics=["DIVINE_RIGHT", "MINI_REGENT", "LANTERN"],
            deck=(
                ["BLUDGEON"] * 12
                + ["VENERATE"] * 6
                + ["ASTRAL_PULSE"] * 6
                + ["SOLAR_STRIKE"] * 6
                + ["DEFEND_REGENT"] * 10
            ),
        )
        state = game.enter_room("combat", encounter="TEST_SUBJECT_BOSS")

        for _ in range(90):
            if state.get("decision") != "combat_play":
                state = game.act("proceed")
                continue

            enemies = state.get("enemies") or []
            enemy = enemies[0] if enemies else {}
            is_phase_three = enemy.get("max_hp", 0) >= 300
            is_intangible = any(
                power.get("name") == "Intangible"
                for power in enemy.get("powers", [])
            )

            if is_phase_three:
                if is_intangible:
                    astral = next(
                        (card for card in state["hand"] if card["name"] == "Astral Pulse"),
                        None,
                    )
                    if state.get("stars", 0) >= 3 and astral and astral.get("can_play"):
                        target = astral["stats"]["damage_by_target"][0]
                        assert target["damage"] == 1
                        assert target["unblocked_damage"] == 1

                        hp_before = enemy["hp"]
                        state = game.act("play_card", card_index=astral["index"])
                        assert hp_before - state["enemies"][0]["hp"] == target["unblocked_damage"]
                        return

                    if state.get("stars", 0) < 3:
                        venerate = next(
                            (card for card in state["hand"] if card["name"] == "Venerate" and card.get("can_play")),
                            None,
                        )
                        if venerate:
                            state = game.act("play_card", card_index=venerate["index"])
                            continue

                        solar = next(
                            (card for card in state["hand"] if card["name"] == "Solar Strike" and card.get("can_play")),
                            None,
                        )
                        if solar:
                            state = game.act("play_card", card_index=solar["index"], target_index=0)
                            continue

                state = game.act("end_turn")
                continue

            bludgeon = next(
                (card for card in state["hand"] if card["name"] == "Bludgeon" and card.get("can_play")),
                None,
            )
            if bludgeon:
                state = game.act("play_card", card_index=bludgeon["index"], target_index=0)
            else:
                state = game.act("end_turn")

        raise AssertionError("Did not reach Intangible Astral Pulse regression state")

    def test_fixed_multi_hit_attack_exports_repeat_damage(self, game):
        state = game.start(seed="twin-strike-repeat-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "TWIN_STRIKE",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        twin_strike = next(c for c in state["hand"] if c["name"] == "Twin Strike")
        target_stats = twin_strike["stats"]["damage_by_target"][0]
        assert target_stats["repeat"] == 2
        assert target_stats["total_damage"] == target_stats["damage"] * 2

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=twin_strike["index"], target_index=0)
        assert hp_before - state["enemies"][0]["hp"] == target_stats["total_damage"]

    def test_other_fixed_multi_hit_attack_exports_engine_repeat_damage(self, game):
        state = game.start(seed="dagger-spray-repeat-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "DAGGER_SPRAY",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        dagger_spray = next(c for c in state["hand"] if c["name"] == "Dagger Spray")
        target_stats = dagger_spray["stats"]["damage_by_target"][0]
        assert target_stats["repeat"] == 2
        assert target_stats["total_damage"] == target_stats["damage"] * 2

        hp_before = state["enemies"][0]["hp"]
        state = game.act("play_card", card_index=dagger_spray["index"])
        assert hp_before - state["enemies"][0]["hp"] == target_stats["total_damage"]

    def test_non_repeat_attack_does_not_use_channel_count_as_damage_repeat(self, game):
        state = game.start(character="Defect", seed="ice-lance-repeat-stats")
        game.skip_neow(state)
        state = game.set_player(deck=[
            "ICE_LANCE",
            "STRIKE_DEFECT",
            "DEFEND_DEFECT",
            "DEFEND_DEFECT",
            "DEFEND_DEFECT",
        ])
        deck_ice_lance = next(c for c in state["player"]["deck"] if c["name"] == "Ice Lance")
        assert "Channel 3 Frost" in deck_ice_lance["description"]
        assert deck_ice_lance["vars"]["Repeat"] == 3
        assert "repeat" not in deck_ice_lance["stats"]
        assert "total_damage" not in deck_ice_lance["stats"]
        assert "Channel 3 Frost" in deck_ice_lance["after_upgrade"]["description"]
        assert deck_ice_lance["after_upgrade"]["vars"]["Repeat"] == 3
        assert "repeat" not in deck_ice_lance["after_upgrade"]["stats"]
        assert "total_damage" not in deck_ice_lance["after_upgrade"]["stats"]

        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        ice_lance = next(c for c in state["hand"] if c["name"] == "Ice Lance")
        target_stats = ice_lance["stats"]["damage_by_target"][0]

        damage = ice_lance["stats"]["damage"]
        assert damage > 0
        assert ice_lance["vars"]["Repeat"] == 3
        assert "repeat" not in ice_lance["stats"]
        assert "repeat" not in target_stats
        assert "total_damage" not in target_stats
        assert target_stats["damage"] == damage
        assert target_stats["unblocked_damage"] == damage

    def test_attack_damage_stats_include_player_strength(self, game):
        state = game.start(seed="strength-damage-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "SETUP_STRIKE",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        setup_strike = next(c for c in state["hand"] if c["name"] == "Setup Strike")

        state = game.act("play_card", card_index=setup_strike["index"], target_index=0)

        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        assert strike["stats"]["damage"] == 8

    def test_attack_damage_stats_include_player_weak(self, game):
        state = game.start(seed="weak-damage-stats")
        game.skip_neow(state)
        game.set_player(
            hp=80,
            max_hp=80,
            deck=["STRIKE_IRONCLAD"] * 10 + ["DEFEND_IRONCLAD"] * 10,
        )
        state = game.enter_room("combat", encounter="THE_KIN_BOSS")

        state = game.act("end_turn")
        state = game.act("end_turn")

        assert any(
            power["name"] == "Weak"
            for power in state["player_powers"]
        )
        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        assert strike["stats"]["damage"] == 4

    def test_attack_damage_stats_include_player_shrink(self, game):
        state = game.start(seed="shrink-damage-stats")
        game.skip_neow(state)
        game.set_player(deck=["STRIKE_IRONCLAD"] * 10)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        state = game.act("end_turn")

        assert any(
            power["name"] == "Shrink"
            for power in state["player_powers"]
        )
        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        assert strike["stats"]["damage"] == 4

    def test_status_damage_stats_do_not_include_player_strength(self, game):
        state = game.start(seed="strength-status-damage-stats")
        game.skip_neow(state)
        game.set_player(deck=[
            "SETUP_STRIKE",
            "INFECTION",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        setup_strike = next(c for c in state["hand"] if c["name"] == "Setup Strike")

        state = game.act("play_card", card_index=setup_strike["index"], target_index=0)

        infection = next(c for c in state["hand"] if c["name"] == "Infection")
        strike = next(c for c in state["hand"] if c["name"] == "Strike")
        assert infection["stats"]["damage"] == 3
        assert strike["stats"]["damage"] == 8

    def test_card_temp_power_has_readable_name(self, game):
        state = game.start(seed="setup-strike-power-name")
        game.skip_neow(state)
        game.set_player(deck=[
            "SETUP_STRIKE",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        setup_strike = next(c for c in state["hand"] if c["name"] == "Setup Strike")

        state = game.act("play_card", card_index=setup_strike["index"], target_index=0)

        power_names = [power["name"] for power in state["player_powers"]]
        power_descriptions = [power["description"] for power in state["player_powers"]]
        assert "Setup Strike" in power_names
        assert all(not name.endswith(".title") for name in power_names)
        assert all(not description.endswith(".description") for description in power_descriptions)
        assert all("{" not in description for description in power_descriptions)
        assert any("Gain 2 Strength" in description for description in power_descriptions)

    def test_power_descriptions_interpolate_amount(self, game):
        state = game.start(seed="power-description-amount")
        game.skip_neow(state)
        game.set_player(deck=[
            "DRUM_OF_BATTLE",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        drum = next(c for c in state["hand"] if c["name"] == "Drum of Battle")

        state = game.act("play_card", card_index=drum["index"])
        power = next(p for p in state["player_powers"] if p["name"] == "Drum of Battle")

        assert "{Amount:plural" not in power["description"]
        assert "Exhaust the top card" in power["description"]

    def test_power_description_removes_empty_plural_spacing(self, game):
        state = game.start(character="Defect", seed="power-description-empty-plural")
        game.skip_neow(state)
        game.set_player(deck=[
            "CONSUMING_SHADOW",
            "STRIKE_DEFECT",
            "DEFEND_DEFECT",
            "DEFEND_DEFECT",
            "DEFEND_DEFECT",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        consuming_shadow = next(c for c in state["hand"] if c["name"] == "Consuming Shadow")

        state = game.act("play_card", card_index=consuming_shadow["index"])
        power = next(p for p in state["player_powers"] if p["name"] == "Consuming Shadow")

        assert "  " not in power["description"]
        assert power["description"] == "At the end of your turn, Evoke your leftmost Orb."

    def test_card_descriptions_resolve_conditional_upgrade_formatters(self, game):
        state = game.start(seed="card-description-ifupgraded")
        state = game.skip_neow(state)
        state = game.set_player(deck=["CASCADE", "PRIMAL_FORCE", "CRUELTY", "CINDER"])

        deck = {card["name"]: card for card in state["player"]["deck"]}
        assert deck["Cascade"]["description"] == "Play the top X cards of your Draw Pile."
        assert deck["Cascade"]["after_upgrade"]["description"] == "Play the top X+1 cards of your Draw Pile."
        assert deck["Primal Force"]["description"] == "Transform all Attacks in your Hand into Giant Rock."
        assert deck["Primal Force"]["after_upgrade"]["description"] == "Transform all Attacks in your Hand into Giant Rock+."
        assert deck["Cruelty"]["description"] == "Vulnerable enemies take an additional 25% damage."
        assert deck["Cruelty"]["after_upgrade"]["description"] == "Vulnerable enemies take an additional 50% damage."
        assert deck["Cinder"]["description"] == "Deal 18 damage.\nExhaust 1 card at random."
        assert deck["Cinder"]["after_upgrade"]["description"] == "Deal 24 damage.\nExhaust 1 card at random."

    def test_unrelenting_description_preserves_zero_cost_energy_icon(self, game):
        state = game.start(seed="unrelenting-cost-icon")
        state = game.skip_neow(state)
        state = game.set_player(deck=["UNRELENTING"])

        unrelenting = next(card for card in state["player"]["deck"] if card["id"] == "CARD.UNRELENTING")

        assert "costs 0 [E]" in unrelenting["description"]
        assert "costs ." not in unrelenting["description"]
        assert "costs 0 [E]" in unrelenting["after_upgrade"]["description"]
        assert "costs ." not in unrelenting["after_upgrade"]["description"]

    def test_unrelenting_zh_description_preserves_zero_cost_energy_icon(self, game):
        state = game.start(seed="unrelenting-zh-cost-icon", lang="zh")
        state = game.skip_neow(state)
        state = game.set_player(deck=["UNRELENTING"])

        unrelenting = next(card for card in state["player"]["deck"] if card["id"] == "CARD.UNRELENTING")

        assert "0[E]" in unrelenting["description"]
        assert "{energyPrefix" not in unrelenting["description"]
        assert "0[E]" in unrelenting["after_upgrade"]["description"]
        assert "{energyPrefix" not in unrelenting["after_upgrade"]["description"]

    def test_block_stats_include_player_frail(self, game):
        state = game.start(seed="codex-frail-block")
        game.skip_neow(state)
        game.set_player(deck=["DEFEND_IRONCLAD"] * 10)
        state = game.enter_room("combat", encounter="RUBY_RAIDERS_NORMAL")

        state = game.act("end_turn")

        frail = next(power for power in state["player_powers"] if power["name"] == "Frail")
        assert "less Block" in frail["description"]
        assert "prevents damage" not in frail["description"]
        defend = next(c for c in state["hand"] if c["name"] == "Defend")
        assert defend["stats"]["block"] == 3
        assert defend["description"] == "Gain 3 Block."
        assert defend["vars"]["Block"] == 3

    def test_player_vulnerable_power_description_resolves_percent_formatter(self, game):
        state = game.start(seed="codex-player-vulnerable-description")
        game.skip_neow(state)
        game.set_player(hp=300, max_hp=300, deck=["DEFEND_IRONCLAD"] * 10)
        state = game.enter_room("combat", encounter="OVICOPTER_NORMAL")

        state = game.act("end_turn")
        state = game.act("end_turn")
        state = game.act("end_turn")

        vulnerable = next(power for power in state["player_powers"] if power["name"] == "Vulnerable")

        assert "{" not in vulnerable["description"]
        assert "50% more damage" in vulnerable["description"]

    def test_block_stats_include_player_dexterity(self, game):
        state = game.start(seed="codex-dexterity-block")
        game.skip_neow(state)
        game.set_player(
            deck=["DEFEND_IRONCLAD"] * 10,
            potions=["SPEED_POTION"],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        state = game.act("use_potion", potion_index=0)

        assert any(
            power["name"] == "Dexterity" and power["amount"] == 5
            for power in state["player_powers"]
        )
        defend = next(c for c in state["hand"] if c["name"] == "Defend")
        assert defend["stats"]["block"] == 10

    def test_body_slam_exports_current_block_damage(self, game):
        state = game.start(seed="body-slam-current-block")
        game.skip_neow(state)
        game.set_player(
            hp=80,
            max_hp=80,
            deck=[
                "BLOOD_WALL",
                "BODY_SLAM",
                "STRIKE_IRONCLAD",
                "DEFEND_IRONCLAD",
                "DEFEND_IRONCLAD",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        blood_wall = next(c for c in state["hand"] if c["name"] == "Blood Wall")

        state = game.act("play_card", card_index=blood_wall["index"])

        assert state["player"]["block"] == 16
        body_slam = next(c for c in state["hand"] if c["name"] == "Body Slam")
        assert body_slam["stats"]["calculateddamage"] == 16
        assert "(Deals 16 damage)" in body_slam["description"]

    def test_spite_exports_single_hit_before_hp_loss(self, game):
        state = game.start(seed="spite-repeat-no-hp-loss")
        game.skip_neow(state)
        game.set_player(deck=[
            "SPITE",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        spite = next(c for c in state["hand"] if c["name"] == "Spite")
        target_stats = spite["stats"]["damage_by_target"][0]

        assert spite["stats"]["repeat"] == 1
        assert target_stats.get("repeat", 1) == 1
        assert target_stats["unblocked_damage"] == target_stats["damage"]
        assert "{Cards:" not in spite["description"]
        assert "hits 2 times" in spite["description"]

    def test_spite_exports_repeat_after_hp_loss(self, game):
        state = game.start(seed="spite-repeat-after-hp-loss")
        game.skip_neow(state)
        game.set_player(deck=[
            "BLOODLETTING",
            "SPITE",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        bloodletting = next(c for c in state["hand"] if c["name"] == "Bloodletting")

        state = game.act("play_card", card_index=bloodletting["index"])
        spite = next(c for c in state["hand"] if c["name"] == "Spite")

        assert spite["stats"]["repeat"] == 2
        assert "{Cards:" not in spite["description"]
        assert "hits 2 times" in spite["description"]
