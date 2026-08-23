def _reach_test_subject_phase2(
    game,
    deck=None,
    relics=None,
    preserve_card_ids=(),
):
    state = game.send({
        "cmd": "start_combat",
        "character": "Ironclad",
        "seed": "combat-effect-envelope-phase2",
        "encounter": "ENCOUNTER.TEST_SUBJECT_BOSS",
        "observation_mode": "training_compact",
        "player": {
            "hp": 999,
            "max_hp": 999,
            "gold": 0,
            "relics": relics or ["RELIC.BURNING_BLOOD"],
            "relic_setup_mode": "direct",
            "potions": [],
            "deck": deck or ["CARD.ANGER"] * 12,
        },
    })

    for _ in range(200):
        enemies = state.get("enemies") or []
        if (
            state.get("decision") == "combat_play"
            and len(enemies) == 1
            and enemies[0].get("max_hp") == 200
            and enemies[0].get("move_id") == "MULTI_CLAW_MOVE"
        ):
            return state

        assert state.get("decision") == "combat_play", state
        playable = [
            card for card in state.get("hand") or []
            if card.get("can_play")
            and card.get("id") != "CARD.HEADBUTT"
            and card.get("id") not in preserve_card_ids
        ]
        if enemies and playable:
            state = game.act(
                "play_card",
                card_index=playable[0]["index"],
                target_index=0,
            )
        else:
            state = game.act("end_turn")
    raise AssertionError("did not reach the locked Test Subject phase-two boundary")


def _reach_test_subject_phase2_with_card(game, card_id, deck):
    state = _reach_test_subject_phase2(game, deck)
    for _ in range(100):
        enemies = state.get("enemies") or []
        if (
            state.get("decision") == "combat_play"
            and len(enemies) == 1
            and enemies[0].get("max_hp") == 200
            and enemies[0].get("move_id") == "MULTI_CLAW_MOVE"
            and any(card.get("id") == card_id for card in state.get("hand") or [])
        ):
            return state
        assert state.get("decision") == "combat_play", state
        state = game.act("end_turn")
    raise AssertionError(f"did not draw {card_id} at a locked phase-two boundary")


def test_combat_effect_envelope_fails_closed_outside_phase2(game):
    state = game.send({
        "cmd": "start_combat",
        "character": "Ironclad",
        "seed": "combat-effect-envelope-phase1",
        "encounter": "ENCOUNTER.TEST_SUBJECT_BOSS",
        "observation_mode": "training_compact",
        "player": {
            "hp": 80,
            "max_hp": 80,
            "gold": 0,
            "relics": ["RELIC.BURNING_BLOOD"],
            "relic_setup_mode": "direct",
            "potions": [],
            "deck": ["CARD.ANGER"] * 12,
        },
    })
    assert state["decision"] == "combat_play"

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["type"] == "combat_effect_envelope"
    assert result["schema"] == "combat_effect_envelope_v1"
    assert result["supported"] is False
    assert "test_subject_not_phase2:0" in result["reasons"]


def test_combat_effect_envelope_exports_locked_multi_claw_and_legal_anger(game):
    _reach_test_subject_phase2(game)

    first = game.send({"cmd": "combat_effect_envelope"})
    second = game.send({"cmd": "combat_effect_envelope"})

    assert first["supported"] is True, first.get("reasons")
    assert first == second
    assert first["proof_state_token_sha256"]
    assert first["closure"]["headless_dll_sha256"]
    assert first["closure"]["whitelist_manifest_sha256"]
    assert first["hand_cards"] == first["legal_cards"]
    assert first["turn_terminal_hp_upper_bound"] is None
    assert first["turn_certificate"]["no_draw_active"] is False
    assert first["incoming"] == {
        "move_id": "MULTI_CLAW_MOVE",
        "base_hits": 3,
        "extra_hits": 0,
        "intent_hits": 3,
        "execution_hits": 3,
        "single_damage": 10,
        "total_damage": 30,
        "player_block_now": 0,
        "pre_attack_plating_block": 0,
        "hp_loss_after_current_and_plating_block": 30,
    }
    assert first["legal_cards"]
    for row in first["legal_cards"]:
        assert row["id"] == "CARD.ANGER"
        assert isinstance(row["instance_id"], int)
        assert row["energy_cost"] == 0
        assert row["energy_cost_lower_bound"] == 0
        assert row["effects"]["card_damage_hits"] == 1
        assert row["effects"]["card_damage_upper_bound"] == 6
        assert row["effects"]["generated_to_discard_upper_bound"] == 1
        assert row["effects"]["heal_upper_bound"] == 0
        assert row["effects"]["player_intangible_gain_upper_bound"] == 0
        assert row["effects"]["player_buffer_gain_upper_bound"] == 0


def test_combat_effect_envelope_rejects_unregistered_phase2_hand_card(game):
    _reach_test_subject_phase2(game, ["CARD.STRIKE_IRONCLAD"] * 12)

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is False
    assert (
        "unsupported_hand_card_type:MegaCrit.Sts2.Core.Models.Cards.StrikeIronclad"
        in result["reasons"]
    )
    assert "incoming" not in result
    assert "legal_cards" not in result


def test_combat_effect_envelope_accepts_the_registered_phase2_card_variants(game):
    registered = [
        "CARD.ANGER",
        {"id": "CARD.BATTLE_TRANCE", "current_upgrade_level": 1},
        {"id": "CARD.BLOODLETTING", "current_upgrade_level": 1},
        "CARD.DARK_EMBRACE",
        "CARD.DEFEND_IRONCLAD",
        {"id": "CARD.DEFEND_IRONCLAD", "current_upgrade_level": 1},
        "CARD.FEEDING_FRENZY",
        {"id": "CARD.FIEND_FIRE", "current_upgrade_level": 1},
        "CARD.FIGHT_ME",
        "CARD.HEADBUTT",
        {"id": "CARD.IRON_WAVE", "current_upgrade_level": 1},
        {
            "id": "CARD.MAD_SCIENCE",
            "props": {
                "ints": [
                    {"name": "TinkerTimeType", "value": 1},
                    {"name": "TinkerTimeRider", "value": 3},
                ],
            },
        },
        "CARD.THRASH",
    ]
    _reach_test_subject_phase2(game, registered * 2)

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is True, result.get("reasons")
    assert result["legal_cards"]
    assert {
        row["concrete_type"].rsplit(".", 1)[-1]
        for row in result["legal_cards"]
    } <= {
        "Anger",
        "BattleTrance",
        "Bloodletting",
        "DarkEmbrace",
        "DefendIronclad",
        "FeedingFrenzy",
        "FiendFire",
        "FightMe",
        "Headbutt",
        "IronWave",
        "MadScience",
        "Thrash",
    }


def test_combat_effect_envelope_exports_feeding_frenzy_strength(game):
    for upgrade_level, expected_strength in ((0, 5), (1, 7)):
        _reach_test_subject_phase2_with_card(
            game,
            "CARD.FEEDING_FRENZY",
            ["CARD.ANGER"] * 20
            + [{
                "id": "CARD.FEEDING_FRENZY",
                "current_upgrade_level": upgrade_level,
            }] * 8,
        )

        result = game.send({"cmd": "combat_effect_envelope"})

        assert result["supported"] is True, result.get("reasons")
        rows = [
            row for row in result["hand_cards"]
            if row["id"] == "CARD.FEEDING_FRENZY"
        ]
        assert rows
        assert all(row["upgrade_level"] == upgrade_level for row in rows)
        assert all(
            row["effects"]["player_strength_gain_upper_bound"] == expected_strength
            for row in rows
        )


def test_combat_effect_envelope_exports_fiend_fire_hand_snapshot(game):
    for upgrade_level, expected_damage in ((0, 7), (1, 10)):
        state = _reach_test_subject_phase2_with_card(
            game,
            "CARD.FIEND_FIRE",
            ["CARD.ANGER"] * 20
            + [{
                "id": "CARD.FIEND_FIRE",
                "current_upgrade_level": upgrade_level,
            }] * 8,
        )

        result = game.send({"cmd": "combat_effect_envelope"})

        assert result["supported"] is True, result.get("reasons")
        hand_size = len(state["hand"])
        rows = [
            row for row in result["hand_cards"] if row["id"] == "CARD.FIEND_FIRE"
        ]
        assert rows
        for row in rows:
            effects = row["effects"]
            assert row["upgrade_level"] == upgrade_level
            assert row["card_type"] == "Attack"
            assert effects["damage_per_hit_upper_bound"] == expected_damage
            assert effects["card_damage_hits"] == hand_size - 1
            assert effects["card_damage_upper_bound"] == (
                effects["damage_per_hit_upper_bound"] * effects["card_damage_hits"]
            )
            assert effects["exhaust_other_card_upper_bound"] == hand_size - 1
            assert effects["exhaust_trigger_count_upper_bound"] == hand_size


def test_combat_effect_envelope_exports_iron_wave_damage_and_block(game):
    for upgrade_level, expected_value in ((0, 5), (1, 7)):
        _reach_test_subject_phase2_with_card(
            game,
            "CARD.IRON_WAVE",
            ["CARD.ANGER"] * 20
            + [{
                "id": "CARD.IRON_WAVE",
                "current_upgrade_level": upgrade_level,
            }] * 8,
        )

        result = game.send({"cmd": "combat_effect_envelope"})

        assert result["supported"] is True, result.get("reasons")
        rows = [
            row for row in result["hand_cards"] if row["id"] == "CARD.IRON_WAVE"
        ]
        assert rows
        for row in rows:
            effects = row["effects"]
            assert row["upgrade_level"] == upgrade_level
            assert row["card_type"] == "Attack"
            assert row["gains_block"] is True
            assert effects["card_damage_hits"] == 1
            assert effects["card_damage_upper_bound"] == expected_value
            assert effects["card_block_upper_bound"] == expected_value


def test_combat_effect_envelope_certifies_mixed_new_cards_under_no_draw(game):
    target_ids = {
        "CARD.FEEDING_FRENZY",
        "CARD.FIEND_FIRE",
        "CARD.IRON_WAVE",
    }
    battle_trance = {"id": "CARD.BATTLE_TRANCE", "current_upgrade_level": 1}
    deck = (
        ["CARD.ANGER"] * 30
        + [battle_trance] * 12
        + ["CARD.FEEDING_FRENZY"] * 12
        + ["CARD.FIEND_FIRE"] * 12
        + ["CARD.IRON_WAVE"] * 12
    )
    state = _reach_test_subject_phase2(
        game,
        deck,
        preserve_card_ids=("CARD.FIEND_FIRE", "CARD.BATTLE_TRANCE"),
    )
    result = None
    candidate = None
    for _ in range(100):
        battle = next(
            (
                card for card in state.get("hand") or []
                if card.get("id") == "CARD.BATTLE_TRANCE" and card.get("can_play")
            ),
            None,
        )
        if battle is not None:
            state = game.act("play_card", card_index=battle["index"])
            candidate = game.send({"cmd": "combat_effect_envelope"})
            visible_ids = {row["id"] for row in candidate.get("hand_cards") or []}
            if candidate.get("supported") is True and target_ids <= visible_ids:
                result = candidate
                break
        state = game.act("end_turn")
    else:
        raise AssertionError(
            "did not reach a mixed v13 no-draw certificate boundary: "
            f"{None if candidate is None else candidate.get('reasons')}"
        )

    assert result is not None
    certificate = result["turn_certificate"]
    assert certificate["no_draw_active"] is True
    assert isinstance(certificate["terminal_hp_upper_bound"], int)
    conditioned = {
        row["instance_id"]: row["terminal_hp_upper_bound"]
        for row in certificate["first_card_terminal_hp_upper_bounds"]
    }
    for row in result["hand_cards"]:
        if row["id"] in target_ids and row["currently_legal"]:
            assert isinstance(conditioned[row["instance_id"]], int)


def test_combat_effect_envelope_includes_hand_card_currently_blocked_by_energy(game):
    state = _reach_test_subject_phase2(game, ["CARD.FIGHT_ME"] * 12)
    fight_me = next(card for card in state["hand"] if card["id"] == "CARD.FIGHT_ME")
    state = game.act("play_card", card_index=fight_me["index"], target_index=0)
    assert state["energy"] == 1

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is True, result.get("reasons")
    assert result["hand_cards"]
    assert all(row["id"] == "CARD.FIGHT_ME" for row in result["hand_cards"])
    assert all(row["currently_legal"] is False for row in result["hand_cards"])
    assert result["legal_cards"] == []


def test_combat_effect_envelope_whole_turn_bound_does_not_underestimate_composition(game):
    deck = (
        ["CARD.ANGER"] * 4
        + [{"id": "CARD.BATTLE_TRANCE", "current_upgrade_level": 1}] * 8
        + [{"id": "CARD.DEFEND_IRONCLAD", "current_upgrade_level": 1}] * 12
    )
    state = _reach_test_subject_phase2(game, deck)
    for _ in range(20):
        battle_trance = next(
            (card for card in state["hand"] if card["id"] == "CARD.BATTLE_TRANCE"),
            None,
        )
        if battle_trance is not None:
            state = game.act("play_card", card_index=battle_trance["index"])
            break
        state = game.act("end_turn")
    else:
        raise AssertionError("did not draw Battle Trance in phase two")

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is True, result.get("reasons")
    certificate = result["turn_certificate"]
    assert certificate["schema"] == "whole_turn_terminal_hp_upper_bound_v7"
    assert certificate["no_draw_active"] is True
    assert certificate["all_hand_cards_accounted"] is True
    assert certificate["resource_relaxation"] == (
        "joint_terminal_hp_energy_feasible_current_hand_subset_v7"
    )
    assert certificate["energy_feasibility"] == (
        "selected_cost_le_current_plus_selected_gain_upper_bound_v1"
    )
    assert certificate["current_energy"] == state["energy"]
    assert certificate["player_current_hp"] == state["player"]["hp"]
    assert certificate["player_max_hp"] == state["player"]["max_hp"]
    assert certificate["optimistic_energy_budget"] == (
        certificate["current_energy"]
        + certificate["optimistic_energy_gain_upper_bound"]
    )
    assert certificate["energy_feasible_subset_count"] == 2 ** len(result["hand_cards"])
    direct_damage = sum(
        row["effects"]["card_damage_upper_bound"] for row in result["hand_cards"]
    )
    visible_block = (
        result["incoming"]["player_block_now"]
        + result["incoming"]["pre_attack_plating_block"]
        + sum(row["effects"]["block_upper_bound"] for row in result["hand_cards"])
    )
    assert certificate["independent_enemy_kill_damage_upper_bound"] >= direct_damage
    assert certificate["independent_optimistic_block_upper_bound"] >= visible_block
    assert certificate["enemy_kill_damage_upper_bound"] <= (
        certificate["independent_enemy_kill_damage_upper_bound"]
    )
    assert certificate["independent_enemy_kill_damage_upper_bound"] <= (
        certificate["legacy_v8_independent_enemy_kill_damage_upper_bound"]
    )
    assert certificate["enemy_kill_damage_upper_bound"] <= (
        certificate["legacy_v8_enemy_kill_damage_upper_bound"]
    )
    assert certificate["optimistic_block_upper_bound"] <= (
        certificate["independent_optimistic_block_upper_bound"]
    )
    assert certificate["joint_terminal_hp_upper_bound"] == (
        certificate["terminal_hp_upper_bound"]
    )
    assert certificate["unavoidable_hp_loss_lower_bound"] == (
        certificate["player_current_hp"]
        - certificate["joint_terminal_hp_upper_bound"]
    )
    assert certificate["unavoidable_hp_loss_lower_bound"] is not None
    assert result["turn_terminal_hp_upper_bound"] == certificate["terminal_hp_upper_bound"]
    assert result["turn_legacy_v8_terminal_hp_upper_bound"] == (
        certificate["legacy_v8_terminal_hp_upper_bound"]
    )
    first_card_bounds = certificate["first_card_terminal_hp_upper_bounds"]
    assert len(first_card_bounds) == len(result["hand_cards"])
    for card, conditioned in zip(result["hand_cards"], first_card_bounds, strict=True):
        assert conditioned["hand_index"] == card["hand_index"]
        assert conditioned["instance_id"] == card["instance_id"]
        assert conditioned["currently_legal"] is card["currently_legal"]
        if card["currently_legal"]:
            assert isinstance(conditioned["terminal_hp_upper_bound"], int)
            assert conditioned["terminal_hp_upper_bound"] <= (
                certificate["terminal_hp_upper_bound"]
            )
        else:
            assert conditioned["terminal_hp_upper_bound"] is None
    assert isinstance(certificate["end_turn_terminal_hp_upper_bound"], int)
    assert certificate["end_turn_terminal_hp_upper_bound"] <= (
        certificate["terminal_hp_upper_bound"]
    )
    assert isinstance(result["turn_terminal_hp_upper_bound"], int)


def test_combat_effect_envelope_joint_bound_charges_bloodletting_self_loss(game):
    deck = (
        ["CARD.ANGER"] * 20
        + [{"id": "CARD.BATTLE_TRANCE", "current_upgrade_level": 1}] * 8
        + [{"id": "CARD.BLOODLETTING", "current_upgrade_level": 1}] * 16
        + [{"id": "CARD.DEFEND_IRONCLAD", "current_upgrade_level": 1}] * 20
    )
    state = _reach_test_subject_phase2(game, deck)
    result = None
    for _ in range(100):
        battle_trance = next(
            (card for card in state["hand"] if card["id"] == "CARD.BATTLE_TRANCE"),
            None,
        )
        if battle_trance is not None:
            state = game.act("play_card", card_index=battle_trance["index"])
            candidate = game.send({"cmd": "combat_effect_envelope"})
            if candidate["supported"] is True and any(
                row["effects"]["self_hp_loss_lower_bound"] > 0
                for row in candidate["hand_cards"]
            ):
                result = candidate
                break
        state = game.act("end_turn")
    else:
        raise AssertionError("did not reach a supported Bloodletting no-draw hand")

    assert result is not None
    certificate = result["turn_certificate"]
    assert any(
        row["effects"]["self_hp_loss_lower_bound"] > 0
        for row in result["hand_cards"]
    )
    independently_relaxed_terminal = max(
        0,
        certificate["player_current_hp"]
        - max(
            0,
            result["incoming"]["total_damage"]
            - certificate["optimistic_block_upper_bound"],
        ),
    )
    assert certificate["joint_terminal_hp_upper_bound"] <= (
        independently_relaxed_terminal
    )
    assert certificate["joint_terminal_hp_upper_bound"] < (
        certificate["player_current_hp"]
    )


def test_combat_effect_envelope_static_preview_multiplier_tracks_pen_nib(game):
    _reach_test_subject_phase2(game)
    without_pen_nib = game.send({"cmd": "combat_effect_envelope"})
    assert without_pen_nib["supported"] is True, without_pen_nib.get("reasons")
    assert without_pen_nib["closure"][
        "static_preview_damage_multiplier_upper_bound"
    ] == 1

    _reach_test_subject_phase2(
        game,
        relics=["RELIC.BURNING_BLOOD", "RELIC.PEN_NIB"],
    )
    with_pen_nib = game.send({"cmd": "combat_effect_envelope"})
    assert with_pen_nib["supported"] is True, with_pen_nib.get("reasons")
    assert with_pen_nib["closure"][
        "static_preview_damage_multiplier_upper_bound"
    ] == 2


def test_combat_effect_envelope_rejects_future_not_yet_healing_under_no_draw(game):
    deck = (
        ["CARD.ANGER"] * 30
        + [{"id": "CARD.BATTLE_TRANCE", "current_upgrade_level": 1}] * 8
        + ["CARD.NOT_YET"]
    )
    state = _reach_test_subject_phase2(game, deck)
    for _ in range(20):
        battle_trance = next(
            (card for card in state["hand"] if card["id"] == "CARD.BATTLE_TRANCE"),
            None,
        )
        if battle_trance is not None:
            game.act("play_card", card_index=battle_trance["index"])
            break
        state = game.act("end_turn")
    else:
        raise AssertionError("did not draw Battle Trance in phase two")

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is False
    assert (
        "future_player_healing_card:MegaCrit.Sts2.Core.Models.Cards.NotYet"
        in result["reasons"]
    )


def test_combat_effect_envelope_rejects_future_feed_max_hp_gain(game):
    _reach_test_subject_phase2(game, ["CARD.ANGER"] * 20 + ["CARD.FEED"])

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is False
    assert (
        "future_player_healing_card:MegaCrit.Sts2.Core.Models.Cards.Feed"
        in result["reasons"]
    )


def test_combat_effect_envelope_accounts_nunchaku_once_at_turn_level(game):
    state = _reach_test_subject_phase2(
        game,
        ["CARD.ANGER"] * 12
        + [{"id": "CARD.BATTLE_TRANCE", "current_upgrade_level": 1}] * 8,
        ["RELIC.BURNING_BLOOD", "RELIC.NUNCHAKU"],
    )
    for _ in range(20):
        battle_trance = next(
            (card for card in state["hand"] if card["id"] == "CARD.BATTLE_TRANCE"),
            None,
        )
        if battle_trance is not None:
            state = game.act("play_card", card_index=battle_trance["index"])
            break
        state = game.act("end_turn")
    else:
        raise AssertionError("did not draw Battle Trance in phase two")

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is True, result.get("reasons")
    attacks = [
        row
        for row in result["hand_cards"]
        if row["effects"]["card_damage_hits"] > 0
    ]
    assert attacks
    intrinsic_gain = sum(
        row["effects"]["energy_gain_upper_bound"] for row in result["hand_cards"]
    )
    certificate = result["turn_certificate"]
    assert 0 <= certificate["relic_energy_gain_upper_bound"] <= len(attacks)
    assert certificate["optimistic_energy_gain_upper_bound"] == (
        intrinsic_gain + certificate["relic_energy_gain_upper_bound"]
    )


def test_combat_effect_envelope_does_not_repeat_rainbow_gain_per_card(game):
    _reach_test_subject_phase2(
        game,
        ["CARD.ANGER"] * 12,
        ["RELIC.BURNING_BLOOD", "RELIC.RAINBOW_RING"],
    )

    result = game.send({"cmd": "combat_effect_envelope"})

    assert result["supported"] is True, result.get("reasons")
    assert result["hand_cards"]
    assert all(
        row["effects"]["player_strength_gain_upper_bound"] == 0
        and row["effects"]["player_dexterity_gain_upper_bound"] == 0
        for row in result["hand_cards"]
    )
