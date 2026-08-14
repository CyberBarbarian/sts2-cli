import base64
import copy
import json
from pathlib import Path
import subprocess
import zlib

from conftest import run_headless_jsonl


def _canonical_json_bytes_like_system_text_json(value):
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    for character, escaped in {
        "+": r"\u002B",
        "&": r"\u0026",
        "'": r"\u0027",
        "<": r"\u003C",
        ">": r"\u003E",
    }.items():
        text = text.replace(character, escaped)
    return text.encode("utf-8")


def _supported_scenario(seed="proof-state-token"):
    return {
        "cmd": "start_combat",
        "character": "Ironclad",
        "seed": seed,
        "encounter": "ENCOUNTER.SHRINKER_BEETLE_WEAK",
        "observation_mode": "training_compact",
        "player": {
            "hp": 70,
            "max_hp": 80,
            "gold": 0,
            "relics": ["RELIC.BURNING_BLOOD"],
            "relic_setup_mode": "direct",
            "potions": ["POTION.FIRE_POTION"],
            "deck": [
                "CARD.STRIKE_IRONCLAD",
                "CARD.DEFEND_IRONCLAD",
                "CARD.BASH",
            ],
        },
    }


def test_proof_state_token_fails_closed_without_combat(game):
    result = game.send({"cmd": "proof_state_token"})

    assert result["type"] == "proof_state_token"
    assert result["schema"] == "proof_state_token_v1"
    assert result["supported"] is False
    assert "not_in_combat" in result["reasons"]
    assert "token" not in result
    assert "token_sha256" not in result


def test_proof_state_token_is_canonical_for_registered_combat(game):
    state = game.send(_supported_scenario())
    assert state["decision"] == "combat_play"

    first = game.send({"cmd": "proof_state_token"})
    second = game.send({"cmd": "proof_state_token"})

    assert first["supported"] is True, first.get("reasons")
    assert first["schema"] == "proof_state_token_v1"
    assert first["token_sha256"] == second["token_sha256"]
    assert first["canonical_json"] == second["canonical_json"]
    assert first["token"]["combat"]["round_number"] == 1
    assert first["token"]["combat"]["next_creature_id"] == 2
    run_rng = first["token"]["run"]["run_rng"]
    assert set(run_rng) - {"registry"} == {
        "property:CombatCardGeneration",
        "property:CombatCardSelection",
        "property:CombatEnergyCosts",
        "property:CombatOrbGeneration",
        "property:CombatPotionGeneration",
        "property:CombatTargets",
        "property:MonsterAi",
        "property:Niche",
        "property:Shuffle",
        "property:TreasureRoomRelics",
        "property:UnknownMapPoint",
        "property:UpFront",
    }
    assert set(run_rng["registry"]) == {
        "CombatCardGeneration",
        "CombatCardSelection",
        "CombatEnergyCosts",
        "CombatOrbs",
        "CombatPotionGeneration",
        "CombatTargets",
        "MonsterAi",
        "Niche",
        "Shuffle",
        "TreasureRoomRelics",
        "UnknownMapPoint",
        "UpFront",
    }
    player_rng = first["token"]["run"]["players"][0]["player_rng"]
    assert set(player_rng) - {"registry"} == {
        "property:Rewards",
        "property:Shops",
        "property:Transformations",
    }
    assert set(player_rng["registry"]) == {"Rewards", "Shops", "Transformations"}
    monster_states = first["token"]["combat"]["creatures"][1]["monster"]["states"]
    assert all(
        row["state"]["type"]
        == "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState"
        for row in monster_states
    )
    piles = first["token"]["run"]["players"][0]["piles"]
    assert [pile["type"] for pile in piles] == ["Hand", "Draw", "Discard", "Exhaust", "Play"]
    hand = piles[0]["cards"]
    assert [card["id"] for card in hand] == [card["id"] for card in state["hand"]]
    assert len({card["instance_id"] for card in hand}) == len(hand)
    all_cards = first["token"]["combat"]["all_cards"]
    assert [card["instance_id"] for card in all_cards] == first["token"]["combat"][
        "all_card_instance_ids"
    ]
    assert all(card["instance_id"].startswith("player:0:combat:") for card in all_cards)
    assert all(not card["instance_id"].startswith("combat:all:") for card in all_cards)
    assert all(
        card["card_type"]["type"] == "MegaCrit.Sts2.Core.Entities.Cards.CardType"
        for card in all_cards
    )
    history_statistics = first["token"]["combat"]["history_statistics"]
    assert history_statistics["schema"] == "combat_history_statistics_v1"
    assert history_statistics["round_number"] == first["token"]["combat"]["round_number"]
    assert history_statistics["current_side"]["name"] == first["token"]["combat"]["current_side"]
    assert [row["creature_id"] for row in history_statistics["creatures"]] == [0, 1]


def test_proof_state_token_encodes_registered_history_entries(game):
    state = game.send(_supported_scenario("proof-state-history"))
    assert state["decision"] == "combat_play"
    game.act("end_turn")

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is True, result.get("reasons")
    history = result["token"]["combat"]["history"]
    assert all(row["history_sentinel"] == "current_combat_history" for row in history)
    assert any(row["type"].endswith("MonsterPerformedMoveEntry") for row in history)


def test_proof_state_token_accepts_fieldless_card_and_enchantment_types(game):
    scenario = _supported_scenario("proof-state-fieldless-card-enchantment")
    scenario["player"]["deck"].append(
        {
            "id": "CARD.STAMPEDE",
            "enchantment": {"id": "ENCHANTMENT.SWIFT", "amount": 2},
        }
    )
    state = game.send(scenario)
    assert state["decision"] == "combat_play"

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is True, result.get("reasons")
    cards = result["token"]["combat"]["all_cards"]
    stampede = next(card for card in cards if card["id"] == "CARD.STAMPEDE")
    assert stampede["type"] == "MegaCrit.Sts2.Core.Models.Cards.Stampede"
    assert stampede["enchantment"] == {
        "amount": 2,
        "card_instance_id": stampede["instance_id"],
        "dynamic_vars": None,
        "id": "ENCHANTMENT.SWIFT",
        "saved_properties": None,
        "status": "Normal",
        "type": "MegaCrit.Sts2.Core.Models.Enchantments.Swift",
    }


def test_proof_state_token_rejects_field_bearing_concrete_card_type(game):
    scenario = _supported_scenario("proof-state-field-bearing-card")
    scenario["player"]["deck"].append("CARD.SPOILS_MAP")
    state = game.send(scenario)
    assert state["decision"] == "combat_play"

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is False
    assert any(
        reason.startswith(
            "field_bearing_card_type:MegaCrit.Sts2.Core.Models.Cards.SpoilsMap:"
        )
        and "MegaCrit.Sts2.Core.Models.Cards.SpoilsMap._spoilsActIndex" in reason
        for reason in result["reasons"]
    )
    assert "token" not in result
    assert "token_sha256" not in result


def test_proof_state_token_encodes_active_fieldless_power_history_reference(game):
    state = game.send(_supported_scenario("proof-state-fieldless-power"))
    bash = next(card for card in state["hand"] if card["id"] == "CARD.BASH")
    game.act("play_card", card_index=bash["index"], target_index=0)

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is True, result.get("reasons")
    received = next(
        row
        for row in result["token"]["combat"]["history"]
        if row["type"].endswith("PowerReceivedEntry")
    )
    assert received["power_type"] == "MegaCrit.Sts2.Core.Models.Powers.VulnerablePower"
    assert received["power_instance_id"].startswith("creature:1:power:")


def test_proof_state_token_rejects_unregistered_history_entry(game):
    state = game.send(_supported_scenario("proof-state-unregistered-potion-history"))
    assert state["decision"] == "combat_play"
    game.act("use_potion", potion_index=0, target_index=0)

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is False
    assert any(
        reason.startswith(
            "combat_history_type_not_registered:"
            "MegaCrit.Sts2.Core.Combat.History.Entries.PotionUsedEntry"
        )
        for reason in result["reasons"]
    )
    assert "token" not in result
    assert "token_sha256" not in result


def test_proof_state_token_encodes_audited_act3_relic_state(game):
    scenario = _supported_scenario("proof-state-act3-relics")
    scenario["player"]["relics"] = [
        "RELIC.BELLOWS",
        "RELIC.BURNING_BLOOD",
        "RELIC.CURSED_PEARL",
        "RELIC.DAUGHTER_OF_THE_WIND",
        "RELIC.LANTERN",
        "RELIC.LASTING_CANDY",
        "RELIC.PANDORAS_BOX",
        "RELIC.PRESERVED_FOG",
        "RELIC.VAJRA",
        "RELIC.VENERABLE_TEA_SET",
        "RELIC.WHETSTONE",
    ]
    state = game.send(scenario)
    assert state["decision"] == "combat_play"

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is True, result.get("reasons")
    relics = {row["id"]: row for row in result["token"]["run"]["players"][0]["relics"]}
    assert relics["RELIC.LASTING_CANDY"]["concrete_state"] == {
        "combats_seen": 0,
        "is_activating": False,
    }
    assert relics["RELIC.VENERABLE_TEA_SET"]["concrete_state"] == {
        "gain_energy_in_next_combat": False,
    }
    assert relics["RELIC.BELLOWS"]["concrete_state"] is None


def test_proof_state_token_owl_flying_state_changes_token(game):
    scenario = _supported_scenario("proof-state-owl-flying")
    scenario["encounter"] = "ENCOUNTER.OWL_MAGISTRATE_NORMAL"
    scenario["player"]["hp"] = 999
    scenario["player"]["max_hp"] = 999
    state = game.send(scenario)
    assert state["decision"] == "combat_play"

    before = game.send({"cmd": "proof_state_token"})
    assert before["supported"] is True, before.get("reasons")
    before_monster = before["token"]["combat"]["creatures"][1]["monster"]
    assert before_monster["concrete_state"]["is_flying"] is False

    after = None
    for _ in range(3):
        game.act("end_turn")
        after = game.send({"cmd": "proof_state_token"})
        assert after["supported"] is True, after.get("reasons")
    assert after is not None
    after_monster = after["token"]["combat"]["creatures"][1]["monster"]
    assert after_monster["concrete_state"]["is_flying"] is True
    assert after["token_sha256"] != before["token_sha256"]


def test_proof_state_token_detached_power_registry_is_stable_and_preserves_instances(game):
    scenario = _supported_scenario("proof-state-detached-power")
    scenario["player"]["hp"] = 999
    scenario["player"]["max_hp"] = 999
    scenario["player"]["deck"] = ["CARD.FLAME_BARRIER"]

    def play_first_copy():
        state = game.send(scenario)
        flame_barrier = next(card for card in state["hand"] if card["id"] == "CARD.FLAME_BARRIER")
        game.act("play_card", card_index=flame_barrier["index"])
        return game.send({"cmd": "proof_state_token"})

    first_active = play_first_copy()
    assert first_active["supported"] is True, first_active.get("reasons")
    first_registry = first_active["token"]["combat"]["power_identity_registry"]
    first_power = next(
        row
        for row in first_registry
        if row["state"]["type"] == "MegaCrit.Sts2.Core.Models.Powers.FlameBarrierPower"
    )
    assert first_power["active"] is True
    assert first_power["instance_id"].startswith("creature:0:power:")

    replay_active = play_first_copy()
    assert replay_active["supported"] is True, replay_active.get("reasons")
    assert replay_active["token_sha256"] == first_active["token_sha256"]

    state = game.act("end_turn")
    detached = game.send({"cmd": "proof_state_token"})
    assert detached["supported"] is True, detached.get("reasons")
    detached_rows = [
        row
        for row in detached["token"]["combat"]["power_identity_registry"]
        if row["state"]["type"] == "MegaCrit.Sts2.Core.Models.Powers.FlameBarrierPower"
    ]
    assert len(detached_rows) == 1
    assert detached_rows[0]["active"] is False
    assert detached_rows[0]["instance_id"].startswith("history:power:")

    flame_barrier = next(card for card in state["hand"] if card["id"] == "CARD.FLAME_BARRIER")
    game.act("play_card", card_index=flame_barrier["index"])
    reapplied = game.send({"cmd": "proof_state_token"})
    assert reapplied["supported"] is True, reapplied.get("reasons")
    reapplied_rows = [
        row
        for row in reapplied["token"]["combat"]["power_identity_registry"]
        if row["state"]["type"] == "MegaCrit.Sts2.Core.Models.Powers.FlameBarrierPower"
    ]
    assert len(reapplied_rows) == 2
    assert len({row["instance_id"] for row in reapplied_rows}) == 2
    assert {row["active"] for row in reapplied_rows} == {False, True}


def test_proof_state_token_encodes_locked_test_subject_branch_shape(game):
    scenario = _supported_scenario("proof-state-test-subject-branch")
    scenario["encounter"] = "ENCOUNTER.TEST_SUBJECT_BOSS"
    state = game.send(scenario)
    assert state["decision"] == "combat_play"

    result = game.send({"cmd": "proof_state_token"})

    assert result["supported"] is True, result.get("reasons")
    monster = result["token"]["combat"]["creatures"][1]["monster"]
    assert monster["concrete_state"] == {
        "dead_state_id": "RESPAWN_MOVE",
        "extra_multi_claw_count": 0,
        "respawns": 0,
    }
    branch = next(row["state"] for row in monster["states"] if row["key"] == "REVIVE_BRANCH")
    assert [row["target_state_id"] for row in branch["branches"]] == [
        "MULTI_CLAW_MOVE",
        "PHASE3_LACERATE_MOVE",
    ]
    assert [row["condition"] for row in branch["branches"]] == [
        "test_subject_respawns_lt_2",
        "test_subject_respawns_gte_2",
    ]
    adaptable = next(
        row
        for row in result["token"]["combat"]["creatures"][1]["powers"]
        if row["type"] == "MegaCrit.Sts2.Core.Models.Powers.AdaptablePower"
    )
    assert adaptable["internal_state"] == {"is_reviving": False}

    process, outputs = run_headless_jsonl([scenario, {"cmd": "proof_state_token"}])
    assert process.returncode == 0, process.stderr
    replay = outputs[-1]
    assert replay["supported"] is True, replay.get("reasons")
    assert replay["token_sha256"] == result["token_sha256"]
    assert replay["canonical_json"] == result["canonical_json"]


def test_compact_boss_key_uses_engine_stable_shuffle_discard_order(game):
    scenario = _supported_scenario("proof-state-boss-stable-shuffle-discard")
    scenario["encounter"] = "ENCOUNTER.TEST_SUBJECT_BOSS"
    scenario["player"]["potions"] = []
    scenario["player"]["deck"] = [
        "CARD.STRIKE_IRONCLAD",
        "CARD.DEFEND_IRONCLAD",
    ]

    def play_in_order(card_ids):
        state = game.send(scenario)
        for card_id in card_ids:
            card = next(card for card in state["hand"] if card["id"] == card_id)
            args = {"card_index": card["index"]}
            if card["target_type"] == "AnyEnemy":
                args["target_index"] = 0
            state = game.act("play_card", **args)
        full = game.send({"cmd": "proof_state_token"})
        compact = game.send({"cmd": "proof_state_compact_key"})
        compact_again = game.send({"cmd": "proof_state_compact_key"})
        assert full["supported"] is True, full.get("reasons")
        assert compact["supported"] is True, compact.get("reasons")
        assert compact_again["manifest"] == compact["manifest"]
        assert compact_again["canonical_sha256"] == compact["canonical_sha256"]
        assert (
            compact_again["compressed_canonical_b64"]
            == compact["compressed_canonical_b64"]
        )
        return full, compact

    strike_first = play_in_order(
        ["CARD.STRIKE_IRONCLAD", "CARD.DEFEND_IRONCLAD"]
    )
    defend_first = play_in_order(
        ["CARD.DEFEND_IRONCLAD", "CARD.STRIKE_IRONCLAD"]
    )

    assert strike_first[0]["token_sha256"] != defend_first[0]["token_sha256"]
    assert strike_first[1]["canonical_sha256"] == defend_first[1]["canonical_sha256"]
    assert (
        strike_first[1]["compressed_canonical_b64"]
        == defend_first[1]["compressed_canonical_b64"]
    )
    compact_token = json.loads(
        zlib.decompress(
            base64.b64decode(strike_first[1]["compressed_canonical_b64"])
        )
    )
    assert "deck" not in compact_token["run"]["players"][0]
    assert "all_cards" not in compact_token["combat"]
    assert "all_card_instance_ids" not in compact_token["combat"]
    assert compact_token["combat"]["registry_only_cards"] == []
    assert compact_token["search_state_reduction"]["run_deck"]["schema"] == (
        "test_subject_battle_only_deck_version_ignored_v1"
    )
    card_rows = compact_token["search_state_reduction"]["card_rows"]
    assert card_rows["schema"] == "boss_card_row_positional_v1"
    assert card_rows["fields"] == sorted(card_rows["fields"])
    assert len(card_rows["fields"]) == len(set(card_rows["fields"]))
    for pile in compact_token["run"]["players"][0]["piles"]:
        assert all(isinstance(card, list) for card in pile["cards"])
        assert all(len(card) == len(card_rows["fields"]) for card in pile["cards"])

    positional_canonical = _canonical_json_bytes_like_system_text_json(compact_token)
    assert len(positional_canonical) == strike_first[1]["canonical_length"]
    dictionary_token = copy.deepcopy(compact_token)
    dictionary_token["search_state_reduction"].pop("card_rows")
    for pile in dictionary_token["run"]["players"][0]["piles"]:
        pile["cards"] = [
            dict(zip(card_rows["fields"], card)) for card in pile["cards"]
        ]
    dictionary_token["combat"]["registry_only_cards"] = [
        dict(zip(card_rows["fields"], card))
        for card in dictionary_token["combat"]["registry_only_cards"]
    ]
    dictionary_canonical = _canonical_json_bytes_like_system_text_json(dictionary_token)
    assert len(positional_canonical) < len(dictionary_canonical)
    print(
        "boss_card_row_positional_v1 lengths",
        {
            "canonical_before": len(dictionary_canonical),
            "canonical_after": len(positional_canonical),
            "compressed_before": len(zlib.compress(dictionary_canonical, level=1)),
            "compressed_after": strike_first[1]["compressed_length"],
        },
    )


def test_proof_state_token_encodes_nemesis_power_toggle(game):
    scenario = _supported_scenario("proof-state-test-subject-nemesis")
    scenario["encounter"] = "ENCOUNTER.TEST_SUBJECT_BOSS"
    scenario["player"]["hp"] = 999
    scenario["player"]["max_hp"] = 999
    scenario["player"]["deck"] = ["CARD.BLUDGEON"] * 10
    state = game.send(scenario)

    def nemesis_state():
        result = game.send({"cmd": "proof_state_token"})
        if not result["supported"]:
            return result, None
        power = next(
            (
                row
                for row in result["token"]["combat"]["creatures"][1]["powers"]
                if row["type"] == "MegaCrit.Sts2.Core.Models.Powers.NemesisPower"
            ),
            None,
        )
        return result, None if power is None else power["concrete_state"]

    before = None
    before_result = None
    for _ in range(12):
        before_result, before = nemesis_state()
        if before is not None:
            break
        game.send({"cmd": "debug_set_enemy_hp", "enemy_index": 0, "hp": 1})
        playable = next(
            (
                card
                for card in state["hand"]
                if isinstance(card.get("cost"), int) and card["cost"] <= state["energy"]
            ),
            None,
        )
        state = (
            game.act("play_card", card_index=playable["index"], target_index=0)
            if playable is not None
            else game.act("end_turn")
        )

    assert before is not None, before_result
    assert set(before) == {"should_apply_intangible"}
    state = game.act("end_turn")
    after_result, after = nemesis_state()
    assert after_result["supported"] is True, after_result.get("reasons")
    assert after is not None
    assert after["should_apply_intangible"] is not before["should_apply_intangible"]
    assert after_result["token_sha256"] != before_result["token_sha256"]


def test_proof_state_token_encodes_boss_card_and_relic_mutable_state(game):
    scenario = _supported_scenario("proof-state-boss-mutable-fields")
    scenario["encounter"] = "ENCOUNTER.TEST_SUBJECT_BOSS"
    scenario["player"]["hp"] = 999
    scenario["player"]["max_hp"] = 999
    scenario["player"]["potions"] = []
    scenario["player"]["deck"] = [
        "CARD.MAD_SCIENCE",
        "CARD.RAMPAGE",
        "CARD.THRASH",
        "CARD.DEFEND_IRONCLAD",
    ]
    scenario["player"]["relics"] = [
        "RELIC.BURNING_BLOOD",
        "RELIC.CENTENNIAL_PUZZLE",
        "RELIC.JOSS_PAPER",
        "RELIC.KUSARIGAMA",
        "RELIC.NUNCHAKU",
        "RELIC.PAELS_TEARS",
        "RELIC.PEN_NIB",
        "RELIC.PENDULUM",
        "RELIC.RAINBOW_RING",
        "RELIC.TUNING_FORK",
    ]
    state = game.send(scenario)
    before = game.send({"cmd": "proof_state_token"})
    assert before["supported"] is True, before.get("reasons")

    before_cards = {row["id"]: row for row in before["token"]["combat"]["all_cards"]}
    assert before_cards["CARD.RAMPAGE"]["concrete_state"]["extra_damage_from_plays"] == 0
    assert before_cards["CARD.THRASH"]["concrete_state"]["extra_damage"] == 0
    assert set(before_cards["CARD.MAD_SCIENCE"]["concrete_state"]) == {
        "mocked_chaos_card_instance_id",
        "tinker_time_rider",
        "tinker_time_type",
    }
    before_relics = {
        row["id"]: row["concrete_state"]
        for row in before["token"]["run"]["players"][0]["relics"]
    }
    assert before_relics["RELIC.NUNCHAKU"]["attacks_played"] == 0
    assert before_relics["RELIC.KUSARIGAMA"]["attacks_played_this_turn"] == 0
    assert before_relics["RELIC.RAINBOW_RING"]["attacks_played_this_turn"] == 0

    rampage = next(card for card in state["hand"] if card["id"] == "CARD.RAMPAGE")
    game.act("play_card", card_index=rampage["index"], target_index=0)
    after = game.send({"cmd": "proof_state_token"})
    assert after["supported"] is True, after.get("reasons")
    after_cards = {row["id"]: row for row in after["token"]["combat"]["all_cards"]}
    after_relics = {
        row["id"]: row["concrete_state"]
        for row in after["token"]["run"]["players"][0]["relics"]
    }
    assert after_cards["CARD.RAMPAGE"]["concrete_state"]["extra_damage_from_plays"] > 0
    assert after_relics["RELIC.NUNCHAKU"]["attacks_played"] == 1
    assert after_relics["RELIC.KUSARIGAMA"]["attacks_played_this_turn"] == 1
    assert after_relics["RELIC.RAINBOW_RING"]["attacks_played_this_turn"] == 1
    player_history = next(
        row
        for row in after["token"]["combat"]["history_statistics"]["creatures"]
        if row["creature_id"] == 0
    )
    assert player_history["current_epoch_finished_attack_count"] == 1
    assert player_history["current_epoch_positive_unblocked_damage"] is False
    assert player_history["total_positive_unblocked_damage_count"] == 0
    assert after["token_sha256"] != before["token_sha256"]


def test_compact_boss_key_preserves_mutable_card_and_relic_differences(game):
    scenario = _supported_scenario("proof-state-boss-compact-mutable-fields")
    scenario["encounter"] = "ENCOUNTER.TEST_SUBJECT_BOSS"
    scenario["player"]["hp"] = 999
    scenario["player"]["max_hp"] = 999
    scenario["player"]["potions"] = []
    scenario["player"]["deck"] = [
        "CARD.RAMPAGE",
        "CARD.THRASH",
        "CARD.DEFEND_IRONCLAD",
    ]
    scenario["player"]["relics"] = [
        "RELIC.BURNING_BLOOD",
        "RELIC.KUSARIGAMA",
        "RELIC.NUNCHAKU",
        "RELIC.PEN_NIB",
        "RELIC.RAINBOW_RING",
    ]
    state = game.send(scenario)
    before = game.send({"cmd": "proof_state_compact_key"})
    assert before["supported"] is True, before.get("reasons")

    rampage = next(card for card in state["hand"] if card["id"] == "CARD.RAMPAGE")
    game.act("play_card", card_index=rampage["index"], target_index=0)
    after = game.send({"cmd": "proof_state_compact_key"})

    assert after["supported"] is True, after.get("reasons")
    assert after["canonical_sha256"] != before["canonical_sha256"]


def test_boss_card_positional_helper_rejects_missing_and_extra_fields(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dotnet = root / ".tools" / "dotnet" / "dotnet.exe"
    headless = root / "src" / "Sts2Headless" / "bin" / "Debug" / "net9.0" / "Sts2Headless.dll"
    project = tmp_path / "PositionalSchemaProbe.csproj"
    project.write_text(
        """<Project Sdk=\"Microsoft.NET.Sdk\">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net9.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )
    (tmp_path / "Program.cs").write_text(
        r"""
using System.Reflection;
using System.Runtime.Loader;

var headless = Path.GetFullPath(args[0]);
var lib = Path.GetFullPath(args[1]);
AssemblyLoadContext.Default.Resolving += (context, name) =>
{
    foreach (var directory in new[] { Path.GetDirectoryName(headless)!, lib })
    {
        var candidate = Path.Combine(directory, name.Name + ".dll");
        if (File.Exists(candidate))
            return context.LoadFromAssemblyPath(candidate);
    }
    return null;
};
var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(headless);
var type = assembly.GetType("Sts2Headless.ProofStateExporter", throwOnError: true)!;
var fields = (string[])type.GetField(
    "BossCardRowPositionalFields",
    BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null)!;
var encode = type.GetMethod(
    "EncodeBossCardRowPositional",
    BindingFlags.NonPublic | BindingFlags.Static)!;

Dictionary<string, object?> Exact() => fields.ToDictionary(field => field, field => (object?)field);
bool Rejected(Dictionary<string, object?> row)
{
    try
    {
        encode.Invoke(null, new object?[] { row });
        return false;
    }
    catch (TargetInvocationException exception)
        when (exception.InnerException is InvalidOperationException)
    {
        return true;
    }
}

var exact = Exact();
var encoded = (List<object?>)encode.Invoke(null, new object?[] { exact })!;
if (encoded.Count != fields.Length)
    return 2;
var missing = Exact();
missing.Remove(fields[0]);
var extra = Exact();
extra["unexpected"] = 1;
if (!Rejected(missing) || !Rejected(extra))
    return 3;
Console.WriteLine("POSITIONAL_SCHEMA_PROBE=OK");
return 0;
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(dotnet),
            "run",
            "--project",
            str(project),
            "--",
            str(headless),
            str(root / "lib"),
        ],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "POSITIONAL_SCHEMA_PROBE=OK" in result.stdout
