"""Regression tests for treasure room relic handling."""


def relic_count(state):
    return len(state.get("player", {}).get("relics", []))


def test_multiple_treasure_rooms_clear_relic_picking_session(game):
    state = game.start(seed="treasure-session-regression")
    starting_relics = relic_count(state)

    state = game.enter_room("treasure")
    assert state["decision"] == "treasure"
    assert len(state["relics"]) >= 1
    state = game.act("claim_relic", relic_index=0)
    assert state["decision"] == "map_select"
    after_first = relic_count(state)
    assert after_first == starting_relics + 1

    state = game.enter_room("treasure")
    assert state["decision"] == "treasure"
    state = game.act("claim_relic", relic_index=0)
    assert state["decision"] == "map_select"
    assert relic_count(state) == after_first + 1


def test_treasure_room_does_not_auto_claim_relic(game):
    state = game.start(seed="treasure-explicit-claim")
    starting_relics = relic_count(state)

    state = game.enter_room("treasure")

    assert state["decision"] == "treasure"
    assert relic_count(state) == starting_relics
    assert state["relics"][0]["index"] == 0
    assert state["relics"][0]["name"]


def test_treasure_relic_exports_effect_vars_and_resolved_description(game):
    state = game.start(seed="relic-vars-a")
    state = game.enter_room("treasure")

    relic = state["relics"][0]

    assert relic["id"] == "BRONZE_SCALES"
    assert relic["vars"]["ThornsPower"] == 3
    assert "{ThornsPower}" not in relic["description"]
    assert "3" in relic["description"]

    state = game.act("claim_relic", relic_index=relic["index"])
    owned = next(r for r in state["player"]["relics"] if r["id"] == "BRONZE_SCALES")

    assert owned["vars"]["ThornsPower"] == 3
    assert "{ThornsPower}" not in owned["description"]


def test_empty_treasure_from_silver_crucible_is_explicit_and_proceeds(game):
    game.start(seed="silver-crucible-empty-chest")
    game.set_player(relics=["SILVER_CRUCIBLE"])

    state = game.enter_room("treasure")

    assert state["decision"] == "treasure_empty"
    assert state["relics"] == []
    assert state["can_proceed"] is True
    assert [r["id"] for r in state["player"]["relics"]] == ["SILVER_CRUCIBLE"]

    state = game.act("proceed")

    assert state["decision"] == "map_select"
    assert [r["id"] for r in state["player"]["relics"]] == ["SILVER_CRUCIBLE"]
