"""Tests for events."""
from collections import Counter

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

    def test_slippery_bridge_random_card_matches_removed_card(self, game):
        state = game.start(seed="bridge-removal-var")
        game.skip_neow(state)
        game.set_player(deck=[
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "BASH",
            "SETUP_STRIKE",
            "SWORD_BOOMERANG",
            "ARMAMENTS",
            "POMMEL_STRIKE",
            "BLOODLETTING",
        ])
        state = game.enter_room("event", event="SLIPPERY_BRIDGE")

        overcome = next(o for o in state["options"] if o["title"] == "Overcome")
        random_card = overcome["vars"]["RandomCard"]
        before = Counter(c["name"] for c in state["player"]["deck"])

        state = game.act("choose_option", option_index=overcome["index"])

        after = Counter(c["name"] for c in state["player"]["deck"])
        assert before[random_card] == after[random_card] + 1

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

    def test_rest_option_advances_to_fight_page(self, game):
        state = game.start(seed="dense-vegetation-rest")
        game.skip_neow(state)
        state = game.enter_room("event", event="DENSE_VEGETATION")

        rest = next(o for o in state["options"] if o["title"] == "Rest")
        state = game.act("choose_option", option_index=rest["index"])

        assert state["decision"] == "event_choice"
        assert state["event_name"] == "Dense Vegetation"
        assert [o["title"] for o in state["options"]] == ["Fight!"]

        state = game.act("choose_option", option_index=state["options"][0]["index"])

        assert state["decision"] == "combat_play"
        assert state["context"]["room_type"] == "Monster"
        assert state["enemies"]


class TestAmalgamator:
    def test_combine_defends_finishes_after_card_selection(self, game):
        state = game.start(seed="amalgamator-combine-defends")
        game.skip_neow(state)
        state = game.enter_room("event", event="AMALGAMATOR")

        combine = next(o for o in state["options"] if o["title"] == "Combine Defends")
        state = game.act("choose_option", option_index=combine["index"])

        assert state["decision"] == "card_select"
        assert state["min_select"] == 2
        assert state["max_select"] == 2

        state = game.act("select_cards", indices="0,1")

        assert state["decision"] == "map_select"
        assert any(card["name"] == "Ultimate Defend" for card in state["player"]["deck"])


class TestCrystalSphere:
    def test_choose_option_opens_headless_crystal_sphere_state(self, game):
        state = game.start(seed="crystal-sphere-headless")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("event", event="CRYSTAL_SPHERE")

        option = next(o for o in state["options"] if o["title"] == "Uncover Future")
        state = game.act("choose_option", option_index=option["index"])

        assert state["decision"] == "crystal_sphere"
        assert state["event_name"] == "Crystal Sphere"
        assert state["grid_width"] == 11
        assert state["grid_height"] == 11
        assert state["divinations_remaining"] == 3
        assert state["tool"] == "big"
        assert state["clickable_cells"]
        assert any(cell["is_hidden"] is False for cell in state["cells"])

    def test_crystal_sphere_clicks_can_finish_and_proceed(self, game):
        state = game.start(seed="crystal-sphere-clicks")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("event", event="CRYSTAL_SPHERE")

        option = next(o for o in state["options"] if o["title"] == "Uncover Future")
        state = game.act("choose_option", option_index=option["index"])
        state = game.act("crystal_sphere_set_tool", tool="small")

        for _ in range(5):
            if state["decision"] != "crystal_sphere" or state.get("can_proceed"):
                break
            cell = state["clickable_cells"][0]
            state = game.act("crystal_sphere_click_cell", x=cell["x"], y=cell["y"])

        assert state["decision"] == "crystal_sphere"
        assert state["can_proceed"] is True

        state = game.act("crystal_sphere_proceed")

        assert not (
            state["decision"] == "event_choice"
            and state.get("event_name") == "Crystal Sphere"
            and any(o["title"] == "Uncover Future" for o in state.get("options", []))
        )

    def test_crystal_sphere_exports_partial_item_fragments(self, game):
        state = game.start(seed="crystal-partial-0")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("event", event="CRYSTAL_SPHERE")

        option = next(o for o in state["options"] if o["title"] == "Payment Plan")
        state = game.act("choose_option", option_index=option["index"])
        state = game.act("crystal_sphere_set_tool", tool="small")

        for x, y in [(3, 0), (4, 0), (5, 0)]:
            state = game.act("crystal_sphere_click_cell", x=x, y=y)

        partial_items = [
            item for item in state["visible_items"]
            if item["is_fully_revealed"] is False
        ]
        assert partial_items
        partial = partial_items[0]
        assert partial["item_kind"] == "card_reward"
        assert partial["card_rarity"] == "Uncommon"
        assert partial["reward_preview"]["category"] == "card_reward"
        assert partial["reward_preview"]["card_rarity"] == "Uncommon"
        assert partial["reward_preview"]["card_choices"] == 3
        assert partial["visible_cells"] == [{"x": 5, "y": 0}]
        assert partial["revealed_cells"] == 1
        assert partial["total_cells"] == 4

        revealed_indexes = {item["index"] for item in state["revealed_items"]}
        assert partial["index"] not in revealed_indexes

        gold = next(item for item in state["revealed_items"] if item["item_kind"] == "gold")
        assert gold["gold_amount"] == 10
        assert gold["reward_preview"] == {
            "category": "gold",
            "amount": 10,
            "size": "small",
        }

    def test_crystal_sphere_exports_all_visual_reward_variants(self, game):
        state = game.start(seed="crystal-all-0")
        game.skip_neow(state)
        game.set_player(gold=999)
        state = game.enter_room("event", event="CRYSTAL_SPHERE")

        option = next(o for o in state["options"] if o["title"] == "Payment Plan")
        state = game.act("choose_option", option_index=option["index"])

        for x, y in [(3, 3), (7, 3), (3, 7), (7, 7), (5, 5), (5, 1)]:
            state = game.act("crystal_sphere_click_cell", x=x, y=y)

        visible = state["visible_items"]
        kinds = {item["item_kind"] for item in visible}
        assert {"relic", "potion", "card_reward", "curse", "gold"} <= kinds

        assert any(
            item["item_kind"] == "potion"
            and item["potion_rarity"] == "Rare"
            and item["visual_variant"] == "rare_potion"
            for item in visible
        )
        assert any(
            item["item_kind"] == "card_reward"
            and item["card_rarity"] == "Rare"
            and item["visual_variant"] == "rare_card_reward"
            and item["reward_preview"]["card_choices"] == 3
            for item in visible
        )
        assert any(
            item["item_kind"] == "gold"
            and item["gold_size"] == "big"
            and item["gold_amount"] == 30
            and item["visual_variant"] == "big_gold"
            for item in visible
        )
        assert any(
            item["item_kind"] == "curse"
            and item["is_good"] is False
            and item["reward_preview"]["curse_card"] == "Doubt"
            for item in visible
        )
        assert any(
            item["item_kind"] == "relic"
            and item["reward_preview"] == {"category": "relic"}
            for item in visible
        )


class TestByrdonisNest:
    def test_take_option_names_byrdonis_egg(self, game):
        state = game.start(seed="byrdonis-nest-card-var")
        game.skip_neow(state)
        state = game.enter_room("event", event="BYRDONIS_NEST")

        take = next(o for o in state["options"] if o["title"] == "Take the Egg")

        assert take["vars"]["Card"] == "Byrdonis Egg"
        assert "Byrdonis Egg" in take["description"]

    def test_eat_option_finishes_event(self, game):
        state = game.start(seed="byrdonis-nest-eat")
        game.skip_neow(state)
        state = game.enter_room("event", event="BYRDONIS_NEST")
        eat = next(o for o in state["options"] if o["title"] == "Eat the Egg")

        state = game.act("choose_option", option_index=eat["index"])

        assert state["decision"] == "map_select"


class TestBugslayer:
    def test_technique_options_name_reward_cards(self, game):
        state = game.start(seed="bugslayer-card-vars")
        game.skip_neow(state)
        state = game.enter_room("event", event="BUGSLAYER")

        extermination = next(o for o in state["options"] if o["title"] == "Learn Extermination Technique")
        squash = next(o for o in state["options"] if o["title"] == "Learn Squash Technique")

        assert extermination["vars"]["Card1"] == "Exterminate"
        assert "Exterminate" in extermination["description"]
        assert squash["vars"]["Card2"] == "Squash"
        assert "Squash" in squash["description"]


class TestLostWisp:
    def test_capture_option_names_curse_and_relic(self, game):
        state = game.start(seed="lost-wisp-vars")
        game.skip_neow(state)
        state = game.enter_room("event", event="LOST_WISP")

        capture = next(o for o in state["options"] if o["title"] == "Capture the Wisp")

        assert capture["vars"]["Curse"] == "Decay"
        assert capture["vars"]["Relic"] == "Lost Wisp"
        assert "Decay" in capture["description"]
        assert "Lost Wisp" in capture["description"]


class TestRanwidTheElder:
    def test_give_potion_option_names_current_potion(self, game):
        state = game.start(seed="ranwid-vars")
        game.skip_neow(state)
        game.set_player(potions=["BLOOD_POTION"])
        state = game.enter_room("event", event="RANWID_THE_ELDER")

        potion = next(o for o in state["options"] if o["text_key"].endswith(".POTION"))
        gold = next(o for o in state["options"] if o["text_key"].endswith(".GOLD"))

        assert potion["vars"]["Potion"] == "Blood Potion"
        assert potion["title"] == "Give Blood Potion"
        assert gold["title"] == "Give 100 Gold"


class TestJungleMazeAdventure:
    def test_join_forces_awards_gold_and_finishes_event(self, game):
        state = game.start(seed="jungle-maze-join")
        game.skip_neow(state)
        state = game.enter_room("event", event="JUNGLE_MAZE_ADVENTURE")
        gold_before = state["player"]["gold"]

        join_forces = next(o for o in state["options"] if o["title"] == "Join Forces")
        gold_reward = join_forces["vars"]["JoinForcesGold"]
        state = game.act("choose_option", option_index=join_forces["index"])

        assert state["decision"] == "map_select"
        assert state["player"]["gold"] == gold_before + gold_reward


class TestSpiritGrafter:
    def test_let_it_in_heals_adds_metamorphosis_and_finishes_event(self, game):
        state = game.start(seed="spirit-grafter-let-in")
        game.skip_neow(state)
        game.set_player(hp=60, max_hp=87)
        state = game.enter_room("event", event="SPIRIT_GRAFTER")

        let_it_in = next(o for o in state["options"] if o["title"] == "Let It In")
        heal_amount = let_it_in["vars"]["LetItInHealAmount"]
        deck_size_before = state["player"]["deck_size"]

        state = game.act("choose_option", option_index=let_it_in["index"])

        assert state["decision"] == "map_select"
        assert state["player"]["hp"] == min(87, 60 + heal_amount)
        assert state["player"]["deck_size"] == deck_size_before + 1
        assert any(c["name"] == "Metamorphosis" for c in state["player"]["deck"])


class TestSapphireSeed:
    def test_plant_option_names_sown_enchantment(self, game):
        state = game.start(seed="sapphire-seed-enchantment-var")
        game.skip_neow(state)
        state = game.enter_room("event", event="SAPPHIRE_SEED")

        plant = next(o for o in state["options"] if o["title"] == "Plant and Nourish")

        assert plant["vars"]["Enchantment"] == "Sown"
        assert "Sown" in plant["description"]
        assert "with 0" not in plant["description"]


class TestWoodCarvings:
    def test_snake_enchantment_is_exported_on_deck_card(self, game):
        state = game.start(seed="wood-carvings-slither-export")
        game.skip_neow(state)
        game.set_player(deck=[
            "PERFECTED_STRIKE",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
        ])
        state = game.enter_room("event", event="WOOD_CARVINGS")
        snake = next(o for o in state["options"] if o["title"] == "Snake")

        state = game.act("choose_option", option_index=snake["index"])
        perfected = next(c for c in state["cards"] if c["name"] == "Perfected Strike")
        state = game.act("select_cards", indices=str(perfected["index"]))

        deck_card = next(c for c in state["player"]["deck"] if c["name"] == "Perfected Strike")
        assert deck_card["enchantment"] == "Slither"
        assert deck_card["enchantment_id"] == "SLITHER"
        assert "randomize its cost" in deck_card["enchantment_description"]
