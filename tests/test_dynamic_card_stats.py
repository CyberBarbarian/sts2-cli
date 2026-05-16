"""Tests for dynamic card stat exports."""


class TestDynamicCardStats:
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

    def test_card_descriptions_resolve_conditional_upgrade_formatters(self, game):
        state = game.start(seed="card-description-ifupgraded")
        state = game.skip_neow(state)
        state = game.set_player(deck=["CASCADE", "PRIMAL_FORCE", "CRUELTY"])

        deck = {card["name"]: card for card in state["player"]["deck"]}
        assert deck["Cascade"]["description"] == "Play the top X cards of your Draw Pile."
        assert deck["Cascade"]["after_upgrade"]["description"] == "Play the top X+1 cards of your Draw Pile."
        assert deck["Primal Force"]["description"] == "Transform all Attacks in your Hand into Giant Rock."
        assert deck["Primal Force"]["after_upgrade"]["description"] == "Transform all Attacks in your Hand into Giant Rock+."
        assert deck["Cruelty"]["description"] == "Vulnerable enemies take an additional 25% damage."
        assert deck["Cruelty"]["after_upgrade"]["description"] == "Vulnerable enemies take an additional 50% damage."

    def test_block_stats_include_player_frail(self, game):
        state = game.start(seed="codex-frail-block")
        game.skip_neow(state)
        game.set_player(deck=["DEFEND_IRONCLAD"] * 10)
        state = game.enter_room("combat", encounter="RUBY_RAIDERS_NORMAL")

        state = game.act("end_turn")

        assert any(power["name"] == "Frail" for power in state["player_powers"])
        defend = next(c for c in state["hand"] if c["name"] == "Defend")
        assert defend["stats"]["block"] == 3

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
        assert "2 cards" in spite["description"]

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
        assert "2 cards" in spite["description"]
