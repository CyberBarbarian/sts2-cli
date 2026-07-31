"""Regression tests for native save/load behavior."""

def _resolve_to_map(game, state):
    for _ in range(80):
        decision = state.get("decision")
        if decision == "map_select":
            return state
        if decision == "combat_play":
            state = game.auto_play_combat(state)
        elif decision == "combat_reward":
            rewards = state.get("rewards", [])
            non_card = next((r for r in rewards if r.get("kind") != "card_reward"), None)
            if non_card:
                state = game.act("claim_reward", reward_index=non_card["index"])
            else:
                card_reward = next((r for r in rewards if r.get("kind") == "card_reward"), None)
                if card_reward:
                    state = game.act("skip_reward", reward_index=card_reward["index"])
                else:
                    state = game.act("proceed")
        elif decision == "card_reward":
            state = game.act("skip_card_reward")
        elif decision == "event_choice":
            options = [o for o in state["options"] if not o.get("is_locked")]
            state = game.act("choose_option", option_index=options[0]["index"])
        elif decision == "bundle_select":
            state = game.act("select_bundle", bundle_index=0)
        elif decision == "card_select":
            if state.get("can_skip", state.get("min_select", 0) == 0):
                state = game.act("skip_select")
            else:
                state = game.act("select_cards", indices="0")
        else:
            state = game.act("proceed")
    raise AssertionError("room did not resolve to map_select")


def _reach_seeded_shop(game):
    state = game.start(seed="shop-map-scan")
    state = game.skip_neow(state)
    game.set_player(hp=999, max_hp=999, deck=["BLUDGEON"] * 20)

    for col, row in [(0, 1), (0, 2)]:
        state = game.act("select_map_node", col=col, row=row)
        state = _resolve_to_map(game, state)

    shop = next(choice for choice in state["choices"] if choice["type"] == "Shop")
    return game.act("select_map_node", col=shop["col"], row=shop["row"])


def _shop_signature(state):
    return {
        "cards": [(c["name"], c["price"], c["is_stocked"]) for c in state["cards"]],
        "relics": [(r["id"], r["cost"], r["is_stocked"]) for r in state["relics"]],
        "potions": [(p["id"], p["cost"], p["is_stocked"]) for p in state["potions"]],
        "card_removal_cost": state["card_removal_cost"],
    }


def _combat_reward_signature(state):
    return [
        (
            reward.get("type"),
            reward.get("id"),
            reward.get("name"),
            reward.get("amount"),
            reward.get("gold_amount"),
        )
        for reward in state.get("rewards", [])
    ]


def test_load_map_save_does_not_retrigger_neow(tmp_path, game):
    save_path = tmp_path / "map_select.save"

    state = game.start(seed="sl1")
    state = game.skip_neow(state)
    assert state["decision"] == "map_select"

    save_result = game.send({"cmd": "write_continue_save", "path": str(save_path)})
    assert save_result["type"] == "save_result"
    assert save_result["success"] is True

    game.reset()
    state = game.send({"cmd": "load_save", "path": str(save_path)})
    assert state["decision"] == "map_select"


def test_combat_reward_checkpoint_refuses_reward_screen_rollback(tmp_path, game):
    save_path = tmp_path / "combat_reward.save"

    state = game.start(seed="combat-reward-save")
    state = game.skip_neow(state)
    game.set_player(hp=999, max_hp=999, deck=["BLUDGEON"] * 12)
    state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
    state = game.auto_play_combat(state)

    assert state["decision"] == "combat_reward"
    assert _combat_reward_signature(state)
    save_result = game.send({"cmd": "write_continue_save", "path": str(save_path)})

    assert save_result["type"] == "error"
    assert "combat rewards are pending" in save_result["message"]
    assert not save_path.exists()


def test_shop_checkpoint_preserves_pre_room_rng(tmp_path, game):
    save_path = tmp_path / "in_shop.save"

    state = _reach_seeded_shop(game)
    assert state["decision"] == "shop"
    before = _shop_signature(state)

    save_result = game.send({"cmd": "write_continue_save", "path": str(save_path)})
    assert save_result["type"] == "save_result"
    assert save_result["success"] is True

    game.reset()
    state = game.send({"cmd": "load_save", "path": str(save_path)})
    assert state["decision"] == "map_select"
    shop = next(choice for choice in state["choices"] if choice["type"] == "Shop")
    state = game.act("select_map_node", col=shop["col"], row=shop["row"])

    assert state["decision"] == "shop"
    assert _shop_signature(state) == before


def test_load_pre_neow_save_preserves_neow_choice(tmp_path, game):
    save_path = tmp_path / "pre_neow.save"

    state = game.start(seed="sl2")
    assert state["decision"] == "event_choice"

    save_result = game.send({"cmd": "write_continue_save", "path": str(save_path)})
    assert save_result["type"] == "save_result"
    assert save_result["success"] is True

    game.reset()
    state = game.send({"cmd": "load_save", "path": str(save_path)})
    assert state["decision"] == "event_choice"


def test_load_save_replaces_active_card_selector(tmp_path, game):
    save_path = tmp_path / "selector_reset.save"

    state = game.start(seed="selector-reset-load")
    state = game.skip_neow(state)
    assert state["decision"] == "map_select"

    save_result = game.send({"cmd": "write_continue_save", "path": str(save_path)})
    assert save_result["type"] == "save_result"
    assert save_result["success"] is True

    state = game.enter_room("event", event="AMALGAMATOR")
    combine = next(o for o in state["options"] if o["title"] == "Combine Defends")
    state = game.act("choose_option", option_index=combine["index"])
    assert state["decision"] == "card_select"

    state = game.send({"cmd": "load_save", "path": str(save_path)})

    assert state.get("type") != "error"
    assert state["decision"] == "map_select"
