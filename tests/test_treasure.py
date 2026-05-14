"""Regression tests for treasure room relic handling."""


def relic_count(state):
    return len(state.get("player", {}).get("relics", []))


def test_multiple_treasure_rooms_clear_relic_picking_session(game):
    state = game.start(seed="treasure-session-regression")
    starting_relics = relic_count(state)

    state = game.enter_room("treasure")
    assert state["decision"] == "map_select"
    after_first = relic_count(state)
    assert after_first == starting_relics + 1

    state = game.enter_room("treasure")
    assert state["decision"] == "map_select"
    assert relic_count(state) == after_first + 1
