"""Tests for potion action handling."""


class TestPotionActions:
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
