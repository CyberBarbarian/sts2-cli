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


def test_unrecognized_exported_decisions_block_every_raw_action():
    source = Path("src/Sts2Headless/RunSimulator.cs").read_text(encoding="utf-8")
    execute_source = _slice_between(
        source,
        "public Dictionary<string, object?> ExecuteAction",
        "private static HashSet<string> AllowedActionNamesForDecision",
    )
    detection_source = _slice_between(
        source,
        "private Dictionary<string, object?> DetectDecisionPoint()",
        "private Dictionary<string, object?> MapSelectState()",
    )
    policy_source = _slice_between(
        source,
        "private static HashSet<string> AllowedActionNamesForDecision",
        "private static bool StateFlag",
    )

    assert "ExportedDecisionActionError(action)" in execute_source
    assert "PendingDecisionActionError" not in source
    assert "BlockedExportedDecisionActionError" not in source
    assert 'case "event_blocked":' in policy_source
    assert 'case "unrecognized_state":' in policy_source
    assert 'case "unknown":' in policy_source
    assert "return TrackExportedDecision(DetectDecisionPointCore());" in detection_source
    assert "_lastExportedDecisionPolicy = new ExportedDecisionPolicy(" in detection_source
    assert "AllowedActionNamesForDecision(state)" in detection_source
    assert "_lastExportedDecision =" not in source
    assert "_lastExportedActionNames =" not in source


def test_full_run_driver_never_proceeds_through_an_unhandled_decision():
    source = Path("python/play_full_run.py").read_text(encoding="utf-8")

    assert 'decision in {"unrecognized_state", "unknown", "event_blocked"}' in source
    assert 'elif decision == "event_result":' in source
    assert '"treasure_empty"' not in source
    assert "Unhandled decision {decision!r}; refusing implicit proceed" in source
    assert 'elif decision == "unknown":' not in source
    assert "Try proceeding instead" not in source
    event_and_rest_source = _slice_between(
        source,
        'elif decision == "event_choice":',
        'elif decision == "combat_reward":',
    )
    assert 'action": "leave_room"' not in event_and_rest_source


def test_human_cli_does_not_expose_non_stateful_command_replay():
    play_source = Path("python/play.py").read_text(encoding="utf-8")
    launch_source = Path("launch.py").read_text(encoding="utf-8")

    assert 'parser.add_argument("--load"' not in play_source
    assert "replay_action_with_validation" not in play_source
    assert 'raw == "save"' not in play_source
    assert '["--load", rel_path]' not in launch_source
