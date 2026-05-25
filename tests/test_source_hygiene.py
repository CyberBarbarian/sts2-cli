from pathlib import Path


def _slice_between(text: str, start: str, end: str) -> str:
    start_idx = text.index(start)
    end_idx = text.index(end, start_idx)
    return text[start_idx:end_idx]


def test_combat_preview_avoids_known_card_and_relic_id_branches():
    source = Path("src/Sts2Headless/RunSimulator.cs").read_text(encoding="utf-8")
    preview_source = _slice_between(
        source,
        "private Dictionary<string, object?> ExtractCardStats",
        "private object? ExportEventDynamicVar",
    )

    forbidden = [
        '"SPITE"',
        '"RADIATE"',
        '"MINI_REGENT"',
        "card is HeavenlyDrill",
        "card is not FiendFire",
        "card is MegaCrit.Sts2.Core.Models.Cards.Dismantle",
    ]
    for token in forbidden:
        assert token not in preview_source


def test_event_dynamic_vars_do_not_restate_fixed_event_model_mappings():
    source = Path("src/Sts2Headless/RunSimulator.cs").read_text(encoding="utf-8")
    event_var_source = _slice_between(
        source,
        "private object? ExportEventDynamicVar",
        "private Dictionary<string, object?>? GetUpgradedInfo",
    )

    forbidden = [
        '"RELIC_TRADER"',
        '"LOST_WISP"',
        '"BYRDONIS_NEST"',
        '"BUGSLAYER"',
        '"RANWID_THE_ELDER"',
        '"DECAY"',
        '"BYRDONIS_EGG"',
        '"EXTERMINATE"',
        '"SQUASH"',
    ]
    for token in forbidden:
        assert token not in event_var_source


def test_name_export_avoids_known_monster_and_boss_fallback_branches():
    source = Path("src/Sts2Headless/RunSimulator.cs").read_text(encoding="utf-8")
    name_source = _slice_between(
        source,
        "private string MonsterDisplayName",
        "private Dictionary<string, object?> PowerInfo",
    )

    forbidden = ['"TEST_SUBJECT"', '"THE_KIN"', '"KIN_PRIEST"', '"ADAPTABLE_POWER"']
    for token in forbidden:
        assert token not in name_source


def test_forced_headless_combat_terminal_states_expose_engine_errors():
    source = Path("src/Sts2Headless/RunSimulator.cs").read_text(encoding="utf-8")

    forced_game_over_source = _slice_between(
        source,
        'Log("Nuclear fallback FAILED',
        'catch (Exception ex)',
    )
    assert 'FlagEngineError(' in forced_game_over_source
    assert "return GameOverState(false);" not in forced_game_over_source

    game_over_source = _slice_between(
        source,
        "private Dictionary<string, object?> GameOverState",
        "#endregion",
    )
    assert "AddEngineErrorFields(state);" in game_over_source

    reward_source = _slice_between(
        source,
        "private Dictionary<string, object?> CombatRewardState",
        "private Dictionary<string, object?> CombatRewardInfo",
    )
    assert "AddEngineErrorFields(state);" in reward_source
