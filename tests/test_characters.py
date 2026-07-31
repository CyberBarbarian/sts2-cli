"""Tests for all 5 characters."""
import pytest

CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]


class TestCharacterMechanics:
    def test_defect_has_orbs(self, game):
        state = game.start(character="Defect", seed="dm1")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        assert "orbs" in state or "orb_slots" in state

    def test_defect_without_orbs_still_exports_empty_queue_and_slot_capacity(self, game):
        state = game.start(character="Defect", seed="defect-empty-orb-queue")
        game.skip_neow(state)
        game.set_player(relics=[])
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        assert state["orbs"] == []
        assert state["orb_slots"] > 0

    def test_combat_hand_explicitly_exports_upgrade_state_and_preview(self, game):
        state = game.start(character="Ironclad", seed="combat-hand-upgrade-fields")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        assert state["hand"]
        assert all("upgraded" in card for card in state["hand"])
        assert all("after_upgrade" in card for card in state["hand"])

    def test_defect_orbs_export_engine_evoke_order(self, game):
        state = game.start(character="Defect", seed="defect-orb-order")
        game.skip_neow(state)
        game.set_player(
            relics=[],
            deck=[
                "COOLHEADED",
                "COOLHEADED",
                "GLASSWORK",
                "QUADCAST",
                "DEFEND_DEFECT",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        for name in ["Coolheaded", "Coolheaded", "Glasswork"]:
            card = next(c for c in state["hand"] if c["name"] == name)
            state = game.act("play_card", card_index=card["index"])

        orbs = state["orbs"]
        assert [orb["type"] for orb in orbs] == ["Frost", "Frost", "Glass"]
        assert orbs[0]["is_next_to_evoke"] is True
        assert orbs[0]["position_label"] == "rightmost"
        assert orbs[-1]["is_next_to_evoke"] is False
        assert orbs[-1]["position_label"] == "leftmost"

        state = game.act("end_turn")
        quadcast = next(c for c in state["hand"] if c["name"] == "Quadcast")
        state = game.act("play_card", card_index=quadcast["index"])
        assert state["player"]["block"] == 20
        assert [orb["type"] for orb in state["orbs"]] == ["Frost", "Glass"]

    def test_defect_orb_cards_export_hover_tips(self, game):
        state = game.start(character="Defect", seed="defect-orb-card-hover-tips")
        game.skip_neow(state)
        game.set_player(
            relics=[],
            deck=[
                "GLASSWORK",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        glasswork = next(c for c in state["hand"] if c["name"] == "Glasswork")
        tips = glasswork.get("hover_tips") or []
        glass = next(tip for tip in tips if tip.get("kind") == "orb" and tip.get("title") == "Glass")

        assert "Deals damage to ALL enemies" in glass["description"]

    def test_card_hover_tips_do_not_export_room_tooltips_for_plain_enemy_text(self, game):
        state = game.start(character="Defect", seed="defect-card-hover-tip-room-filter")
        game.skip_neow(state)
        game.set_player(
            relics=[],
            deck=[
                "TESLA_COIL",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
                "DEFEND_DEFECT",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        tesla = next(c for c in state["hand"] if c["name"] == "Tesla Coil")
        tips = tesla.get("hover_tips") or []

        assert not any(tip.get("id") == "ROOM_ENEMY" for tip in tips)
        assert not any(tip.get("title") == "Enemy" for tip in tips)

    def test_necrobinder_inky_hover_tip_resolves_dynamic_values(self, game):
        state = game.start(character="Necrobinder", seed="necrobinder-inky-hover-tip")
        game.skip_neow(state)
        game.set_player(
            relics=[],
            deck=[
                "BLADE_OF_INK",
                "STRIKE_NECROBINDER",
                "DEFEND_NECROBINDER",
                "DEFEND_NECROBINDER",
                "DEFEND_NECROBINDER",
            ],
        )
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")

        blade = next(c for c in state["hand"] if c["name"] == "Blade of Ink")
        tips = blade.get("hover_tips") or []
        inky = next(tip for tip in tips if tip.get("title") == "Inky")

        assert "{Damage}" not in inky["description"]
        assert "{WeakPower}" not in inky["description"]
        assert "additional damage" in inky["description"]

        state = game.act("play_card", card_index=blade["index"])
        shiv = next(c for c in state["hand"] if c["id"] == "CARD.SHIV")
        assert "INKY.extraCardText" not in shiv["description"]
        assert "Apply 1 Weak." in shiv["description"]

    def test_regent_has_stars(self, game):
        state = game.start(character="Regent", seed="dm2")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        assert "stars" in state

    def test_necrobinder_has_osty(self, game):
        state = game.start(character="Necrobinder", seed="dm3")
        game.skip_neow(state)
        state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
        assert "osty" in state
        assert "hp" in state["osty"]
        assert "alive" in state["osty"]
        assert "powers" in state["osty"]


class TestFullRun:
    @pytest.mark.parametrize("character", CHARACTERS)
    @pytest.mark.slow
    def test_full_run(self, game, character):
        state = game.start(character=character, seed=f"full_{character.lower()}")
        steps = 0
        while steps < 2000:
            dec = state.get("decision", "")
            if dec == "game_over":
                assert "victory" in state
                return
            if state.get("type") == "error":
                pytest.fail(f"{character} action failed at step {steps}: {state}")
            elif dec == "combat_play":
                state = game.auto_combat(state)
            elif dec == "map_select":
                state = game.act("select_map_node",
                                 col=state["choices"][0]["col"],
                                 row=state["choices"][0]["row"])
            elif dec == "event_choice":
                opts = [o for o in state["options"] if o.get("is_locked") is False]
                if opts:
                    state = game.act("choose_option", option_index=opts[0]["index"])
                elif state.get("can_leave") is True:
                    state = game.act("leave_room")
                else:
                    pytest.fail(f"{character} event has no legal action at step {steps}: {state}")
            elif dec == "combat_reward":
                rewards = state.get("rewards", [])
                non_card = next(
                    (r for r in rewards if r.get("kind") != "card_reward" and r.get("can_claim") is True),
                    None,
                )
                if non_card:
                    state = game.act("claim_reward", reward_index=non_card["index"])
                else:
                    blocked = next(
                        (r for r in rewards if r.get("can_claim") is False and r.get("can_skip") is True),
                        None,
                    )
                    if blocked:
                        state = game.act("skip_reward", reward_index=blocked["index"])
                    else:
                        card_reward = next((r for r in rewards if r.get("kind") == "card_reward"), None)
                        if card_reward:
                            if card_reward.get("can_claim") is True:
                                state = game.act("claim_reward", reward_index=card_reward["index"])
                            elif card_reward.get("can_skip") is True:
                                state = game.act("skip_reward", reward_index=card_reward["index"])
                            else:
                                pytest.fail(
                                    f"{character} card reward has no legal action at step {steps}: {state}"
                                )
                        else:
                            pytest.fail(f"{character} combat reward has no legal action at step {steps}: {state}")
            elif dec == "card_reward":
                if state.get("cards"):
                    state = game.act("select_card_reward", card_index=state["cards"][0]["index"])
                elif state.get("can_skip") is True:
                    state = game.act("skip_card_reward")
                else:
                    pytest.fail(f"{character} card reward has no legal action at step {steps}: {state}")
            elif dec == "bundle_select":
                state = game.act("select_bundle", bundle_index=state["bundles"][0]["index"])
            elif dec == "card_select":
                if state.get("can_skip") is True:
                    state = game.act("skip_select")
                else:
                    count = state["min_select"]
                    indices = ",".join(str(card["index"]) for card in state["cards"][:count])
                    state = game.act("select_cards", indices=indices)
            elif dec == "event_result":
                if state.get("can_proceed") is not True:
                    pytest.fail(f"{character} event result cannot proceed at step {steps}: {state}")
                state = game.act("proceed")
            elif dec == "rest_site":
                opts = [o for o in state["options"] if o.get("is_enabled") is True]
                if not opts:
                    pytest.fail(f"{character} rest site has no legal action at step {steps}: {state}")
                state = game.act("choose_option", option_index=opts[0]["index"])
            elif dec == "shop":
                state = game.act("leave_room")
            elif dec == "fake_merchant_shop":
                if state.get("can_leave") is not True:
                    pytest.fail(f"{character} fake merchant cannot be left at step {steps}: {state}")
                state = game.act("leave_room")
            elif dec == "treasure":
                relics = state.get("relics", [])
                if relics:
                    state = game.act("claim_relic", relic_index=relics[0]["index"])
                elif state.get("can_proceed") is True:
                    state = game.act("proceed")
                else:
                    pytest.fail(f"{character} treasure has no legal action at step {steps}: {state}")
            elif dec == "crystal_sphere":
                if state.get("can_proceed") is True:
                    state = game.act("crystal_sphere_proceed")
                elif state.get("clickable_cells"):
                    cell = state["clickable_cells"][0]
                    state = game.act("crystal_sphere_click_cell", x=cell["x"], y=cell["y"])
                elif state.get("can_use_small_tool") is True:
                    state = game.act("crystal_sphere_set_tool", tool="small")
                elif state.get("can_use_big_tool") is True:
                    state = game.act("crystal_sphere_set_tool", tool="big")
                else:
                    pytest.fail(f"{character} crystal sphere has no legal action at step {steps}: {state}")
            else:
                pytest.fail(f"{character} exported unsupported decision at step {steps}: {state}")
            steps += 1
        pytest.fail(f"{character} did not finish in {steps} steps; final state: {state}")
