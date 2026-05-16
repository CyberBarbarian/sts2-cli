"""Tests for reusing the headless process in local pytest runs."""

from conftest import Game


def test_reset_allows_second_start_run_in_same_process():
    game = Game()
    try:
        state = game.start(seed="reset-first")
        assert state.get("decision") == "event_choice"

        reset = game.send({"cmd": "reset"})
        assert reset == {"type": "reset_result", "success": True}

        state = game.start(seed="reset-second")
        assert state.get("decision") == "event_choice"
        assert state.get("type") != "error"
    finally:
        game.close()
