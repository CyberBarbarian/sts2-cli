"""Tests for reusing the headless process in local pytest runs."""

def test_reset_allows_second_start_run_in_same_process(game):
    state = game.start(seed="reset-first")
    assert state.get("decision") == "event_choice"

    reset = game.send({"cmd": "reset"})
    assert reset == {"type": "reset_result", "success": True}

    state = game.start(seed="reset-second")
    assert state.get("decision") == "event_choice"
    assert state.get("type") != "error"


def test_reset_abandons_play_card_selection_before_second_run(game):
    state = game.start(seed="reset-pending-play-card")
    game.skip_neow(state)
    game.set_player(deck=[
        "BURNING_PACT",
        "STRIKE_IRONCLAD",
        "DEFEND_IRONCLAD",
        "DEFEND_IRONCLAD",
        "STRIKE_IRONCLAD",
    ])
    state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
    burning_pact = next(card for card in state["hand"] if card["name"] == "Burning Pact")
    state = game.act("play_card", card_index=burning_pact["index"])
    assert state["decision"] == "card_select"

    reset = game.send({"cmd": "reset"})
    assert reset == {"type": "reset_result", "success": True}

    state = game.start(seed="reset-after-pending-play-card")
    assert state.get("decision") == "event_choice"
    assert state.get("type") != "error"
