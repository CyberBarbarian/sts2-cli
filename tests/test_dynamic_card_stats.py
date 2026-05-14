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

    def test_perfected_strike_after_upgrade_exports_dynamic_calculated_damage(self, game):
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

        assert upgraded_stats["calculateddamage"] == (
            upgraded_stats["calculationbase"] + upgraded_stats["extradamage"] * 5
        )

    def test_bully_exports_damage_from_enemy_vulnerable(self, game):
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
        assert stats["calculateddamage"] > stats["calculationbase"]
        assert stats["calculateddamage"] == 8

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
