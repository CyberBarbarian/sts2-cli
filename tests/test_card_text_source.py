"""Regression tests for engine-sourced card text export."""


def test_card_text_audit_uses_engine_descriptions(game):
    result = game.send({"cmd": "audit_card_texts", "lang": "en"})

    assert result["type"] == "card_text_audit"
    assert result["lang"] == "en"
    assert result["card_count"] > 500
    assert result["problems"] == []
    non_engine = {
        card["id"]: card["source"]
        for card in result["cards"]
        if card["source"] != "engine"
    }
    assert non_engine == {"MAD_SCIENCE": "context_required"}


def test_zh_card_text_audit_uses_engine_descriptions(game):
    result = game.send({"cmd": "audit_card_texts", "lang": "zh"})

    assert result["type"] == "card_text_audit"
    assert result["lang"] == "zh"
    assert result["card_count"] > 500
    assert result["problems"] == []
    non_engine = {
        card["id"]: card["source"]
        for card in result["cards"]
        if card["source"] != "engine"
    }
    assert non_engine == {
        "BORROWED_TIME": "engine_fallback_en",
        "FOLLOW_THROUGH": "engine_fallback_en",
        "MAD_SCIENCE": "context_required",
        "SHIV": "engine_fallback_en",
    }


def test_card_text_audit_does_not_leak_language_into_next_run(game):
    game.send({"cmd": "audit_card_texts", "lang": "zh"})
    game.reset()

    state = game.start(seed="audit-language-reset", lang="en")
    game.skip_neow(state)
    game.set_player(
        potions=["CURE_ALL"],
        deck=[
            "STRIKE_IRONCLAD",
            "DEFEND_IRONCLAD",
            "DEFEND_IRONCLAD",
            "STRIKE_IRONCLAD",
            "STRIKE_IRONCLAD",
        ],
    )

    state = game.enter_room("combat", encounter="SHRINKER_BEETLE_WEAK")
    cure_all = state["player"]["potions"][0]

    assert "2 cards" in cure_all["description"]
    assert "2 card." not in cure_all["description"]
