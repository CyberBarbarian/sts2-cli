using System.Collections;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Combat.History;
using MegaCrit.Sts2.Core.Combat.History.Entries;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves.Runs;

namespace Sts2Headless;

/// <summary>
/// A deliberately small, fail-closed combat-state identity exporter.
/// Unknown model types and state that is not yet encoded never receive a token.
/// </summary>
internal static class ProofStateExporter
{
    private const string Schema = "proof_state_token_v1";
    private const string ExpectedGameDllSha256 =
        "554096f7790d340999a37e2239aff81ced701b58e857ec628df27c7798f5bf31";
    private const string ExpectedGameDllMvid = "623673a3-2f6a-4e15-a560-4f44f2297867";
    private static readonly Lazy<Dictionary<string, object?>> CachedManifest =
        new(BuildManifestUncached, isThreadSafe: true);

    private static readonly HashSet<string> RegisteredCardTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Cards.Bash",
        "MegaCrit.Sts2.Core.Models.Cards.DefendIronclad",
        "MegaCrit.Sts2.Core.Models.Cards.MadScience",
        "MegaCrit.Sts2.Core.Models.Cards.Rampage",
        "MegaCrit.Sts2.Core.Models.Cards.StrikeIronclad",
        "MegaCrit.Sts2.Core.Models.Cards.Thrash",
    };

    private static readonly HashSet<string> RegisteredMonsterTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Monsters.OwlMagistrate",
        "MegaCrit.Sts2.Core.Models.Monsters.ShrinkerBeetle",
        "MegaCrit.Sts2.Core.Models.Monsters.TestSubject",
    };

    private static readonly HashSet<string> RegisteredEncounterTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Encounters.ShrinkerBeetleWeak",
    };

    private static readonly HashSet<string> RegisteredCharacterTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Characters.Ironclad",
    };

    private static readonly HashSet<string> RegisteredMoveStateTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.ConditionalBranchState",
        "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState",
    };

    private static readonly HashSet<string> RegisteredMultiplayerScalingTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Singleton.MultiplayerScalingModel",
    };

    private static readonly string[] ExpectedRunRngMembers =
    {
        "property:CombatCardGeneration", "property:CombatCardSelection",
        "property:CombatEnergyCosts", "property:CombatOrbGeneration",
        "property:CombatPotionGeneration", "property:CombatTargets",
        "property:MonsterAi", "property:Niche", "property:Shuffle",
        "property:TreasureRoomRelics", "property:UnknownMapPoint", "property:UpFront",
    };

    private static readonly string[] ExpectedPlayerRngMembers =
    {
        "property:Rewards", "property:Shops", "property:Transformations",
    };

    private static readonly string[] ExpectedRunRngRegistryKeys =
    {
        "CombatCardGeneration", "CombatCardSelection", "CombatEnergyCosts",
        "CombatOrbs", "CombatPotionGeneration", "CombatTargets", "MonsterAi",
        "Niche", "Shuffle", "TreasureRoomRelics", "UnknownMapPoint", "UpFront",
    };

    private static readonly string[] ExpectedPlayerRngRegistryKeys =
    {
        "Rewards", "Shops", "Transformations",
    };

    private static readonly HashSet<string> RegisteredRelicTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Relics.BurningBlood",
        "MegaCrit.Sts2.Core.Models.Relics.CentennialPuzzle",
        "MegaCrit.Sts2.Core.Models.Relics.JossPaper",
        "MegaCrit.Sts2.Core.Models.Relics.Kusarigama",
        "MegaCrit.Sts2.Core.Models.Relics.LastingCandy",
        "MegaCrit.Sts2.Core.Models.Relics.Nunchaku",
        "MegaCrit.Sts2.Core.Models.Relics.PaelsTears",
        "MegaCrit.Sts2.Core.Models.Relics.Pendulum",
        "MegaCrit.Sts2.Core.Models.Relics.PenNib",
        "MegaCrit.Sts2.Core.Models.Relics.RainbowRing",
        "MegaCrit.Sts2.Core.Models.Relics.TuningFork",
        "MegaCrit.Sts2.Core.Models.Relics.VenerableTeaSet",
    };

    private static readonly HashSet<string> RegisteredPotionTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Potions.FirePotion",
    };

    private static readonly HashSet<string> RegisteredEnchantmentTypes = new(StringComparer.Ordinal);

    private static readonly HashSet<string> RegisteredPowerTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Powers.FeedingFrenzyPower",
        "MegaCrit.Sts2.Core.Models.Powers.NemesisPower",
    };

    private static readonly HashSet<string> BossHistorySummaryCardTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Cards.",
        "Anger", "Armaments", "AshenStrike", "Bash", "BattleTrance", "Burn",
        "Bloodletting", "Bludgeon", "BodySlam", "Breakthrough", "Bully",
        "BurningPact", "Cinder", "Clumsy", "Conflagration", "CrimsonMantle",
        "DarkEmbrace", "Debt", "DefendIronclad", "Dismantle", "FeedingFrenzy",
        "FeelNoPain", "FiendFire", "FightMe", "Headbutt", "Hemokinesis",
        "HowlFromBeyond", "IronWave", "MadScience", "Mangle", "Metamorphosis",
        "MoltenFist", "PactsEnd", "PerfectedStrike", "Pillage", "PommelStrike",
        "Rampage", "SetupStrike", "ShrugItOff", "Spite", "Stomp",
        "StrikeIronclad", "SwordBoomerang", "TearAsunder", "Thrash",
        "Thunderclap", "TwinStrike", "Unrelenting", "Uppercut", "Vicious",
        "Whirlwind", "Wound");

    private static readonly HashSet<string> BossHistorySummaryRelicTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Relics.",
        "BagOfPreparation", "BurningBlood", "CentennialPuzzle", "Crossbow",
        "EternalFeather", "Gorget", "JossPaper", "Kusarigama", "Nunchaku",
        "PaelsTears", "Pendulum", "PenNib", "PrecariousShears", "RainbowRing",
        "TuningFork", "WarPaint");

    private static readonly HashSet<string> BossHistorySummaryPowerTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Powers.",
        "AdaptablePower", "CrimsonMantlePower", "DarkEmbracePower",
        "DexterityPower", "EnragePower", "FeedingFrenzyPower", "FeelNoPainPower",
        "FreeAttackPower", "IntangiblePower", "ManglePower", "NemesisPower",
        "NoDrawPower", "PainfulStabsPower", "PlatingPower", "SetupStrikePower",
        "StranglePower", "StrengthPower", "ViciousPower", "VulnerablePower",
        "WeakPower");

    private static readonly HashSet<string> BossHistorySummaryPotionTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Potions.", "BlockPotion", "FyshOil");

    private static readonly HashSet<string> BossHistorySummaryHistoryTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Combat.History.Entries.",
        "BlockGainedEntry", "CardDrawnEntry", "CardExhaustedEntry",
        "CardGeneratedEntry", "CardPlayFinishedEntry", "CardPlayStartedEntry",
        "CreatureAttackedEntry", "DamageReceivedEntry", "EnergySpentEntry",
        "MonsterPerformedMoveEntry", "PowerReceivedEntry");

    private const string BossHistorySummaryMonsterType =
        "MegaCrit.Sts2.Core.Models.Monsters.TestSubject";
    private const string BossHistorySummaryEncounterType =
        "MegaCrit.Sts2.Core.Models.Encounters.TestSubjectBoss";
    private const string BossHistorySummaryCharacterType =
        "MegaCrit.Sts2.Core.Models.Characters.Ironclad";
    private const string BossHistorySummaryEnchantmentType =
        "MegaCrit.Sts2.Core.Models.Enchantments.SoulsPower";

    private static readonly string[] BossCardRowPositionalFields =
    {
        "affliction_amount",
        "affliction_id",
        "base_replay_count",
        "base_star_cost",
        "canonical_star_cost",
        "card_type",
        "clone_of",
        "concrete_state",
        "context",
        "current_star_cost",
        "current_target_id",
        "dupe_of",
        "dynamic_vars",
        "enchantment",
        "energy_cost",
        "exhaust_on_next_play",
        "floor_added_to_deck",
        "has_temporary_star_cost",
        "id",
        "index",
        "instance_id",
        "is_dupe",
        "is_enchantment_preview",
        "is_sly_this_turn",
        "keywords",
        "last_stars_spent",
        "removed_from_state",
        "saved_properties",
        "should_retain_this_turn",
        "single_turn_retain",
        "single_turn_sly",
        "star_cost_set",
        "tags",
        "temporary_star_costs",
        "type",
        "upgrade_level",
        "upgrade_preview_type",
        "was_star_cost_just_upgraded",
    };

    private const string WhitelistManifest = """
        proof_state_token_v1
        scope=registered_combat_decision_boundary
        order=players,creatures,piles,cards,relics,potion_slots,move_state_log
        cards=Bash,DefendIronclad,StrikeIronclad,MadScience,Rampage,Thrash,fieldless
        characters=Ironclad
        monsters=ShrinkerBeetle,OwlMagistrate(_isFlying),TestSubject(_deadState,_respawns,_extraMultiClawCount)
        encounters=ShrinkerBeetleWeak
        move_states=MoveState,TestSubject.REVIVE_BRANCH(exact_conditional_delegate_shape)
        multiplayer_scaling=MultiplayerScalingModel(single_player_only)
        relics=BurningBlood,fieldless,LastingCandy,VenerableTeaSet,CentennialPuzzle,JossPaper,Kusarigama,Nunchaku,PaelsTears,PenNib,Pendulum,RainbowRing,TuningFork
        potions=FirePotion
        powers=fieldless_without_internal_data,FeedingFrenzyPower(_shouldIgnoreNextInstance),NemesisPower(_shouldApplyIntangible),AdaptablePower(isReviving),DarkEmbracePower(etherealCount),StranglePower(card_amount_map)
        combat_history=CardDrawnEntry,BlockGainedEntry,CardExhaustedEntry,CardGeneratedEntry,CardPlayFinishedEntry,CardPlayStartedEntry,CreatureAttackedEntry,DamageReceivedEntry,EnergySpentEntry,MonsterPerformedMoveEntry,PowerReceivedEntry(active_then_chronological_history_power_identity)
        combat_history_statistics=per_creature_current_epoch_finished_attack_count,current_epoch_positive_unblocked_damage,total_positive_unblocked_damage_count
        pending_actions=none
        pending_choices=none
        pending_hooks=none
        run_rng_members=CombatCardGeneration,CombatCardSelection,CombatEnergyCosts,CombatOrbGeneration,CombatPotionGeneration,CombatTargets,MonsterAi,Niche,Shuffle,TreasureRoomRelics,UnknownMapPoint,UpFront
        player_rng_members=Rewards,Shops,Transformations
        run_rng_registry=CombatCardGeneration,CombatCardSelection,CombatEnergyCosts,CombatOrbs,CombatPotionGeneration,CombatTargets,MonsterAi,Niche,Shuffle,TreasureRoomRelics,UnknownMapPoint,UpFront
        player_rng_registry=Rewards,Shops,Transformations
        fieldless_auto_accept=card,potion,encounter,enchantment,relic,power_without_internal_data
        """;

    public static Dictionary<string, object?> Export(
        RunState? runState,
        IReadOnlyCollection<string> simulatorPendingReasons)
    {
        var reasons = new SortedSet<string>(simulatorPendingReasons, StringComparer.Ordinal);
        var manifest = BuildManifest();
        try
        {
            return ExportCore(runState, manifest, reasons);
        }
        catch (Exception exception)
        {
            var root = exception is TargetInvocationException { InnerException: not null }
                ? exception.InnerException
                : exception;
            reasons.Add($"export_failure:{root!.GetType().FullName}:{root.Message}");
            return Unsupported(manifest, reasons);
        }
    }

    public static Dictionary<string, object?> ExportCompactBossHistoryKey(
        RunState? runState,
        IReadOnlyCollection<string> simulatorPendingReasons)
    {
        var reasons = new SortedSet<string>(simulatorPendingReasons, StringComparer.Ordinal);
        var manifest = BuildManifest();
        try
        {
            var token = BuildToken(
                runState,
                manifest,
                reasons,
                canonicalizeDiscardForStableShuffle: true);
            if (token == null)
            {
                var unsupported = Unsupported(manifest, reasons);
                unsupported["type"] = "proof_state_compact_key";
                unsupported["schema"] = "proof_state_compact_key_v1";
                return unsupported;
            }
            ReduceBossHistoryToken(token);
            ReduceBossStableShuffleDiscardToken(token);
            ReduceBossDuplicateCardStateToken(token);
            ReduceBossCardRowsToPositionalToken(token);
            var canonicalJson = CanonicalJson(token);
            var canonicalBytes = Encoding.UTF8.GetBytes(canonicalJson);
            using var output = new MemoryStream();
            using (var compressor = new ZLibStream(output, CompressionLevel.Fastest, leaveOpen: true))
                compressor.Write(canonicalBytes, 0, canonicalBytes.Length);
            var compressed = output.ToArray();
            return new Dictionary<string, object?>
            {
                ["type"] = "proof_state_compact_key",
                ["schema"] = "proof_state_compact_key_v1",
                ["supported"] = true,
                ["manifest"] = manifest,
                ["encoding"] = "zlib_canonical_json_v1",
                ["canonical_sha256"] = Sha256(canonicalJson),
                ["canonical_length"] = canonicalBytes.Length,
                ["compressed_length"] = compressed.Length,
                ["compressed_canonical_b64"] = Convert.ToBase64String(compressed),
            };
        }
        catch (Exception exception)
        {
            return new Dictionary<string, object?>
            {
                ["type"] = "proof_state_compact_key",
                ["schema"] = "proof_state_compact_key_v1",
                ["supported"] = false,
                ["manifest"] = manifest,
                ["reasons"] = new List<string>
                {
                    $"boss_history_summary_failure:{exception.GetType().FullName}:{exception.Message}",
                },
            };
        }
    }

    private static HashSet<string> PrefixTypes(string prefix, params string[] names) =>
        names.Select(name => prefix + name).ToHashSet(StringComparer.Ordinal);

    private static void ReduceBossHistoryToken(Dictionary<string, object?> token)
    {
        if (token.GetValueOrDefault("run") is not Dictionary<string, object?> run
            || token.GetValueOrDefault("combat") is not Dictionary<string, object?> combat)
        {
            throw new InvalidOperationException("proof token run/combat shape is unavailable");
        }
        if (!string.Equals(run.GetValueOrDefault("encounter_type")?.ToString(), BossHistorySummaryEncounterType, StringComparison.Ordinal)
            || run.GetValueOrDefault("encounter") is not Dictionary<string, object?> encounter
            || !string.Equals(encounter.GetValueOrDefault("type")?.ToString(), BossHistorySummaryEncounterType, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Boss encounter contract does not match");
        }
        if (run.GetValueOrDefault("players") is not List<Dictionary<string, object?>> players
            || players.Count != 1
            || !string.Equals(players[0].GetValueOrDefault("character_type")?.ToString(), BossHistorySummaryCharacterType, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("single Ironclad player contract does not match");
        }
        if (combat.GetValueOrDefault("history") is not List<Dictionary<string, object?>> history
            || combat.GetValueOrDefault("history_statistics") is not Dictionary<string, object?> statistics
            || combat.GetValueOrDefault("power_identity_registry") is not List<Dictionary<string, object?>>)
        {
            throw new InvalidOperationException("Boss history export shape is unavailable");
        }
        if (history.Any(entry => !BossHistorySummaryHistoryTypes.Contains(entry.GetValueOrDefault("type")?.ToString() ?? "")))
            throw new InvalidOperationException("Boss history contains an unregistered entry type");

        foreach (var value in VisitStrings(token))
        {
            HashSet<string>? allowed = null;
            if (value.StartsWith("MegaCrit.Sts2.Core.Models.Cards.", StringComparison.Ordinal))
                allowed = BossHistorySummaryCardTypes;
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Relics.", StringComparison.Ordinal))
                allowed = BossHistorySummaryRelicTypes;
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Powers.", StringComparison.Ordinal))
                allowed = BossHistorySummaryPowerTypes;
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Potions.", StringComparison.Ordinal))
                allowed = BossHistorySummaryPotionTypes;
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Monsters.", StringComparison.Ordinal))
                allowed = new HashSet<string>(StringComparer.Ordinal) { BossHistorySummaryMonsterType };
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Encounters.", StringComparison.Ordinal))
                allowed = new HashSet<string>(StringComparer.Ordinal) { BossHistorySummaryEncounterType };
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Enchantments.", StringComparison.Ordinal))
                allowed = new HashSet<string>(StringComparer.Ordinal) { BossHistorySummaryEnchantmentType };
            else if (value.StartsWith("MegaCrit.Sts2.Core.Models.Characters.", StringComparison.Ordinal))
                allowed = new HashSet<string>(StringComparer.Ordinal) { BossHistorySummaryCharacterType };
            if (allowed != null && !allowed.Contains(value))
                throw new InvalidOperationException($"Boss behavior type is not registered: {value}");
        }

        var behaviorCards = new List<Dictionary<string, object?>>();
        if (combat.GetValueOrDefault("all_cards") is List<Dictionary<string, object?>> allCards)
        {
            behaviorCards.AddRange(allCards);
        }
        else
        {
            foreach (var player in players)
            {
                if (player.GetValueOrDefault("piles") is not List<object?> piles)
                    throw new InvalidOperationException("Boss combat piles are unavailable");
                behaviorCards.AddRange(piles
                    .OfType<Dictionary<string, object?>>()
                    .SelectMany(pile =>
                        pile.GetValueOrDefault("cards") is List<Dictionary<string, object?>> cards
                            ? cards
                            : throw new InvalidOperationException("Boss pile cards are unavailable")));
            }
            if (combat.GetValueOrDefault("registry_only_cards")
                is List<Dictionary<string, object?>> registryOnly)
            {
                behaviorCards.AddRange(registryOnly);
            }
        }
        foreach (var card in behaviorCards.Where(card => string.Equals(
                     card.GetValueOrDefault("type")?.ToString(),
                     "MegaCrit.Sts2.Core.Models.Cards.MadScience",
                     StringComparison.Ordinal)))
        {
            if (card.GetValueOrDefault("concrete_state") is not Dictionary<string, object?> concrete
                || EnumName(concrete.GetValueOrDefault("tinker_time_type")) != "Attack"
                || EnumName(concrete.GetValueOrDefault("tinker_time_rider")) != "Choking")
            {
                throw new InvalidOperationException("MadScience saved variant is not registered");
            }
        }

        combat["history"] = new Dictionary<string, object?>
        {
            ["schema"] = "test_subject_history_summary_v1",
            ["statistics"] = statistics,
        };
        combat.Remove("history_statistics");
        combat["power_identity_registry"] = new Dictionary<string, object?>
        {
            ["schema"] = "boss_detached_power_history_ignored_v1",
            ["active_power_state_source"] = "combat.creatures[].powers",
        };
        token["search_state_reduction"] = new Dictionary<string, object?>
        {
            ["contract"] = "test_subject_none_history_readers_v1",
            ["strategy"] = "test_subject_history_summary_v1",
            ["behavior_allowlist_counts"] = new Dictionary<string, object?>
            {
                ["cards"] = BossHistorySummaryCardTypes.Count,
                ["relics"] = BossHistorySummaryRelicTypes.Count,
                ["powers"] = BossHistorySummaryPowerTypes.Count,
                ["history_entries"] = BossHistorySummaryHistoryTypes.Count,
            },
        };
        if (VisitStrings(token).Any(value => value.StartsWith("history:", StringComparison.Ordinal)))
            throw new InvalidOperationException("reduced Boss token retains a historical identity");
    }

    private static void ReduceBossStableShuffleDiscardToken(
        Dictionary<string, object?> token)
    {
        if (token.GetValueOrDefault("run") is not Dictionary<string, object?> run
            || run.GetValueOrDefault("players") is not List<Dictionary<string, object?>> players
            || players.Count != 1
            || players[0].GetValueOrDefault("piles") is not List<object?> piles
            || token.GetValueOrDefault("combat") is not Dictionary<string, object?> combat)
        {
            throw new InvalidOperationException("Boss discard reduction shape is unavailable");
        }

        var discardPiles = piles
            .OfType<Dictionary<string, object?>>()
            .Where(pile => string.Equals(
                pile.GetValueOrDefault("type")?.ToString(),
                "Discard",
                StringComparison.Ordinal))
            .ToList();
        if (discardPiles.Count != 1
            || discardPiles[0].GetValueOrDefault("cards") is not List<Dictionary<string, object?>> discard)
        {
            throw new InvalidOperationException("Boss discard pile export is unavailable");
        }

        static string CardIdentity(Dictionary<string, object?> card) =>
            card.GetValueOrDefault("instance_id")?.ToString()
            ?? throw new InvalidOperationException("Boss card identity is unavailable");

        discard.Sort((left, right) =>
            StableShuffleDiscardIndex(CardIdentity(left)).CompareTo(
                StableShuffleDiscardIndex(CardIdentity(right))));
        for (var index = 0; index < discard.Count; index++)
        {
            discard[index]["index"] = index;
            discard[index]["context"] = "player:0:combat:Discard";
        }

        // CombatState._allCards is a membership registry.  Its insertion order
        // is not read by gameplay; normalize only the duplicate export, while
        // preserving every card and every identity-bearing field.
        var registryRows = combat.GetValueOrDefault("all_cards")
            as List<Dictionary<string, object?>>
            ?? combat.GetValueOrDefault("registry_only_cards")
            as List<Dictionary<string, object?>>
            ?? throw new InvalidOperationException("Boss card registry export is unavailable");
        registryRows.Sort((left, right) => StringComparer.Ordinal.Compare(
            CardIdentity(left),
            CardIdentity(right)));
        for (var index = 0; index < registryRows.Count; index++)
        {
            registryRows[index]["index"] = index;
            registryRows[index]["context"] = "combat:all";
        }
        if (combat.ContainsKey("all_cards"))
        {
            combat["all_card_instance_ids"] = registryRows
                .Select(CardIdentity)
                .Cast<object?>()
                .ToList();
        }

        if (token.GetValueOrDefault("search_state_reduction")
            is not Dictionary<string, object?> reduction)
        {
            throw new InvalidOperationException("Boss reduction manifest is unavailable");
        }
        reduction["discard_order"] = new Dictionary<string, object?>
        {
            ["schema"] = "test_subject_engine_stable_shuffle_discard_v1",
            ["normalizer"] = "CardModel.List.Sort on copied discard under locked runtime",
            ["gameplay_readers"] = "Headbutt identity-remapped choice; shuffle empty/Any",
            ["all_cards_registry_order"] = "ignored; exact membership retained",
        };
    }

    private static int StableShuffleDiscardIndex(string identity)
    {
        const string marker = ":combat:Discard:";
        var markerIndex = identity.LastIndexOf(marker, StringComparison.Ordinal);
        if (markerIndex < 0
            || !int.TryParse(
                identity.AsSpan(markerIndex + marker.Length),
                out var index)
            || index < 0)
        {
            throw new InvalidOperationException(
                $"Boss discard identity is not canonical: {identity}");
        }
        return index;
    }

    private static void ReduceBossDuplicateCardStateToken(
        Dictionary<string, object?> token)
    {
        if (token.GetValueOrDefault("run") is not Dictionary<string, object?> run
            || run.GetValueOrDefault("players") is not List<Dictionary<string, object?>> players
            || players.Count != 1
            || players[0].GetValueOrDefault("piles") is not List<object?> piles
            || token.GetValueOrDefault("combat") is not Dictionary<string, object?> combat)
        {
            throw new InvalidOperationException("Boss duplicate-card reduction shape is unavailable");
        }

        static string CardIdentity(Dictionary<string, object?> card) =>
            card.GetValueOrDefault("instance_id")?.ToString()
            ?? throw new InvalidOperationException("Boss card identity is unavailable");

        var pileCards = piles
            .OfType<Dictionary<string, object?>>()
            .SelectMany(pile =>
                pile.GetValueOrDefault("cards") is List<Dictionary<string, object?>> cards
                    ? cards
                    : throw new InvalidOperationException("Boss pile cards are unavailable"))
            .ToList();
        var pileIds = pileCards.Select(CardIdentity).ToList();
        if (pileIds.Count != pileIds.Distinct(StringComparer.Ordinal).Count())
            throw new InvalidOperationException("Boss live card identity is repeated across piles");

        // The locked Boss card/relic/power/monster closure has no DeckVersion
        // gameplay reader.  Combat cards therefore retain every mutable combat
        // field while dropping only this layer-resource back-reference.
        foreach (var card in pileCards)
            card.Remove("deck_version");

        // CombatState._allCards is only a membership registry.  Live members are
        // already represented exactly once in the ordered piles.  Preserve any
        // registry-only tombstone in full, but remove duplicate live rows.
        List<Dictionary<string, object?>> registryOnly;
        if (combat.GetValueOrDefault("all_cards") is List<Dictionary<string, object?>> allCards
            && combat.GetValueOrDefault("all_card_instance_ids") is List<object?> allCardIds)
        {
            var registryIds = allCards.Select(CardIdentity).ToList();
            if (registryIds.Count != registryIds.Distinct(StringComparer.Ordinal).Count()
                || !registryIds.SequenceEqual(
                    allCardIds.Select(value => value?.ToString()),
                    StringComparer.Ordinal))
            {
                throw new InvalidOperationException("Boss all-card registry identity is inconsistent");
            }
            var registrySet = registryIds.ToHashSet(StringComparer.Ordinal);
            if (pileIds.Any(identity => !registrySet.Contains(identity)))
                throw new InvalidOperationException("Boss live card is absent from the all-card registry");
            var liveSet = pileIds.ToHashSet(StringComparer.Ordinal);
            registryOnly = allCards
                .Where(card => !liveSet.Contains(CardIdentity(card)))
                .OrderBy(CardIdentity, StringComparer.Ordinal)
                .ToList();
        }
        else if (combat.GetValueOrDefault("registry_only_cards")
                 is List<Dictionary<string, object?>> compactRegistryOnly)
        {
            registryOnly = compactRegistryOnly;
            var registryOnlyIds = registryOnly.Select(CardIdentity).ToList();
            if (registryOnlyIds.Count != registryOnlyIds.Distinct(StringComparer.Ordinal).Count()
                || registryOnlyIds.Intersect(pileIds, StringComparer.Ordinal).Any())
            {
                throw new InvalidOperationException("Boss compact card registry identity is inconsistent");
            }
        }
        else
        {
            throw new InvalidOperationException("Boss card registry identity is unavailable");
        }
        foreach (var card in registryOnly)
            card.Remove("deck_version");
        combat.Remove("all_cards");
        combat.Remove("all_card_instance_ids");
        combat["registry_only_cards"] = registryOnly;

        // The run deck is a layer resource and is not read by the audited
        // battle-only closure.  Its former references were removed above.
        players[0].Remove("deck");

        if (token.GetValueOrDefault("search_state_reduction")
            is not Dictionary<string, object?> reduction)
        {
            throw new InvalidOperationException("Boss reduction manifest is unavailable");
        }
        reduction["combat_card_registry"] = new Dictionary<string, object?>
        {
            ["schema"] = "test_subject_live_piles_plus_tombstones_v1",
            ["live_cards"] = "ordered player combat piles",
            ["registry_only_cards"] = "full rows sorted by canonical identity",
            ["all_cards_registry_order"] = "ignored after exact membership validation",
        };
        reduction["run_deck"] = new Dictionary<string, object?>
        {
            ["schema"] = "test_subject_battle_only_deck_version_ignored_v1",
            ["reader_audit"] = "locked 52-card,16-relic,20-power,TestSubject closure",
            ["combat_card_deck_version"] = "removed",
        };
    }

    private static void ReduceBossCardRowsToPositionalToken(
        Dictionary<string, object?> token)
    {
        if (token.GetValueOrDefault("run") is not Dictionary<string, object?> run
            || run.GetValueOrDefault("players") is not List<Dictionary<string, object?>> players
            || players.Count != 1
            || players[0].GetValueOrDefault("piles") is not List<object?> piles
            || token.GetValueOrDefault("combat") is not Dictionary<string, object?> combat
            || combat.GetValueOrDefault("registry_only_cards")
                is not List<Dictionary<string, object?>> registryOnly
            || token.GetValueOrDefault("search_state_reduction")
                is not Dictionary<string, object?> reduction)
        {
            throw new InvalidOperationException("Boss positional card-row shape is unavailable");
        }

        foreach (var pile in piles.OfType<Dictionary<string, object?>>())
        {
            if (pile.GetValueOrDefault("cards")
                is not List<Dictionary<string, object?>> cards)
            {
                throw new InvalidOperationException("Boss positional pile cards are unavailable");
            }
            pile["cards"] = cards
                .Select(EncodeBossCardRowPositional)
                .Cast<object?>()
                .ToList();
        }
        combat["registry_only_cards"] = registryOnly
            .Select(EncodeBossCardRowPositional)
            .Cast<object?>()
            .ToList();
        reduction["card_rows"] = new Dictionary<string, object?>
        {
            ["schema"] = "boss_card_row_positional_v1",
            ["fields"] = BossCardRowPositionalFields.Cast<object?>().ToList(),
            ["encoding"] = "field values in fixed ordinal order; no value reduction",
        };
    }

    private static List<object?> EncodeBossCardRowPositional(
        Dictionary<string, object?> card)
    {
        var actualFields = card.Keys.OrderBy(value => value, StringComparer.Ordinal).ToArray();
        if (!actualFields.SequenceEqual(BossCardRowPositionalFields, StringComparer.Ordinal))
        {
            var missing = BossCardRowPositionalFields.Except(actualFields, StringComparer.Ordinal);
            var extra = actualFields.Except(BossCardRowPositionalFields, StringComparer.Ordinal);
            throw new InvalidOperationException(
                $"Boss card row fields do not match boss_card_row_positional_v1; "
                + $"missing=[{string.Join(',', missing)}];extra=[{string.Join(',', extra)}]");
        }
        return BossCardRowPositionalFields.Select(field => card[field]).ToList();
    }

    private static string? EnumName(object? value) =>
        value is Dictionary<string, object?> row ? row.GetValueOrDefault("name")?.ToString() : null;

    private static IEnumerable<string> VisitStrings(object? value)
    {
        switch (value)
        {
            case string text:
                yield return text;
                break;
            case IDictionary dictionary:
                foreach (DictionaryEntry entry in dictionary)
                foreach (var child in VisitStrings(entry.Value))
                    yield return child;
                break;
            case IEnumerable sequence:
                foreach (var item in sequence)
                foreach (var child in VisitStrings(item))
                    yield return child;
                break;
        }
    }

    private static Dictionary<string, object?> ExportCore(
        RunState? runState,
        Dictionary<string, object?> manifest,
        SortedSet<string> reasons)
    {
        var token = BuildToken(runState, manifest, reasons);
        if (token == null)
            return Unsupported(manifest, reasons);

        var canonicalJson = CanonicalJson(token);
        return new Dictionary<string, object?>
        {
            ["type"] = "proof_state_token",
            ["schema"] = Schema,
            ["supported"] = true,
            ["manifest"] = manifest,
            ["token_sha256"] = Sha256(canonicalJson),
            ["canonical_json"] = canonicalJson,
            ["token"] = token,
        };
    }

    private static Dictionary<string, object?>? BuildToken(
        RunState? runState,
        Dictionary<string, object?> manifest,
        SortedSet<string> reasons,
        bool canonicalizeDiscardForStableShuffle = false)
    {
        if (runState == null || !CombatManager.Instance.IsInProgress)
        {
            reasons.Add("not_in_combat");
            return null;
        }

        var combatState = CombatManager.Instance.DebugOnlyGetState();
        if (combatState == null)
        {
            reasons.Add("combat_state_unavailable");
            return null;
        }

        if (!string.Equals(manifest["game_dll_sha256"]?.ToString(), ExpectedGameDllSha256, StringComparison.Ordinal))
            reasons.Add($"game_dll_hash_not_whitelisted:{manifest["game_dll_sha256"]}");
        if (!string.Equals(manifest["game_dll_mvid"]?.ToString(), ExpectedGameDllMvid, StringComparison.Ordinal))
            reasons.Add($"game_dll_mvid_not_whitelisted:{manifest["game_dll_mvid"]}");

        var cardIds = BuildCardIdentityMap(
            runState,
            combatState,
            canonicalizeDiscardForStableShuffle);
        var token = new Dictionary<string, object?>
        {
            ["schema"] = Schema,
            ["scope"] = "registered_combat_decision_boundary",
            ["manifest"] = manifest,
            ["run"] = ExportRun(
                runState,
                combatState,
                cardIds,
                reasons,
                compactBoss: canonicalizeDiscardForStableShuffle),
            ["combat"] = ExportCombat(
                combatState,
                runState,
                cardIds,
                reasons,
                compactBoss: canonicalizeDiscardForStableShuffle),
            ["synchronization"] = ExportSynchronization(reasons),
        };

        ValidateStableBoundary(reasons);
        if (reasons.Count > 0)
            return null;
        return token;
    }

    private static Dictionary<string, object?> Unsupported(
        Dictionary<string, object?> manifest,
        IEnumerable<string> reasons)
    {
        return new Dictionary<string, object?>
        {
            ["type"] = "proof_state_token",
            ["schema"] = Schema,
            ["supported"] = false,
            ["manifest"] = manifest,
            ["reasons"] = reasons.Distinct(StringComparer.Ordinal).OrderBy(value => value, StringComparer.Ordinal).ToList(),
        };
    }

    private static Dictionary<string, object?> BuildManifest()
    {
        // Runtime assemblies are immutable for the lifetime of this process.
        // Return a shallow copy so callers cannot mutate the cached values.
        return new Dictionary<string, object?>(CachedManifest.Value, StringComparer.Ordinal);
    }

    private static Dictionary<string, object?> BuildManifestUncached()
    {
        var gameAssembly = typeof(RunState).Assembly;
        var headlessAssembly = typeof(ProofStateExporter).Assembly;
        return new Dictionary<string, object?>
        {
            ["schema"] = Schema,
            ["scope"] = "registered_combat_decision_boundary",
            ["game_dll_sha256"] = FileSha256(gameAssembly.Location),
            ["game_dll_mvid"] = gameAssembly.ManifestModule.ModuleVersionId.ToString("D"),
            ["headless_dll_sha256"] = FileSha256(headlessAssembly.Location),
            ["godot_dll_sha256"] = FileSha256(typeof(Godot.Node).Assembly.Location),
            ["whitelist_manifest_sha256"] = Sha256(WhitelistManifest.Replace("\r\n", "\n", StringComparison.Ordinal)),
        };
    }

    private static Dictionary<string, object?> ExportRun(
        RunState runState,
        CombatState combatState,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons,
        bool compactBoss = false)
    {
        var encounter = combatState.Encounter;
        if (encounter == null)
            reasons.Add("combat_encounter_missing");
        else
            RegisterTypeOrFieldless(
                encounter,
                typeof(EncounterModel),
                RegisteredEncounterTypes,
                "encounter",
                reasons);
        var encounterState = encounter == null
            ? null
            : ExportEncounter(encounter, combatState, reasons);
        var modifiers = combatState.Modifiers?.ToList() ?? new List<ModifierModel>();
        foreach (var modifier in modifiers)
            reasons.Add($"unregistered_combat_modifier:{TypeName(modifier)}");
        if (runState.Players.Count != 1)
            reasons.Add($"player_count_not_registered:{runState.Players.Count}");

        return new Dictionary<string, object?>
        {
            ["act_index"] = runState.CurrentActIndex,
            ["act_floor"] = runState.ActFloor,
            ["ascension"] = runState.AscensionLevel,
            ["encounter_id"] = encounter?.Id.ToString(),
            ["encounter_type"] = encounter == null ? null : TypeName(encounter),
            ["encounter"] = encounterState,
            ["run_rng"] = ExportRngSet(
                runState.Rng,
                ExpectedRunRngMembers,
                ExpectedRunRngRegistryKeys,
                reasons,
                "run_rng"),
            ["players"] = runState.Players.Select((player, index) =>
                ExportPlayer(player, index, cardIds, reasons, compactBoss)).ToList(),
            ["combat_modifiers"] = modifiers.Select(TypeName).ToList(),
        };
    }

    private static Dictionary<string, object?> ExportEncounter(
        EncounterModel encounter,
        CombatState combatState,
        SortedSet<string> reasons)
    {
        var generated = ReadField(encounter, "_monstersWithSlots") as IEnumerable;
        if (generated == null)
            reasons.Add($"encounter_monsters_not_exportable:{TypeName(encounter)}");
        var generatedRows = AsObjects(generated).Select((entry, index) =>
        {
            var monster = ReadMember(entry, "Item1") as MonsterModel;
            var slot = ReadMember(entry, "Item2")?.ToString();
            if (monster == null)
                reasons.Add($"encounter_monster_value_not_exportable:{TypeName(encounter)}:{index}");
            else if (!combatState.Enemies.Any(creature => ReferenceEquals(creature.Monster, monster)))
                reasons.Add($"encounter_monster_identity_mismatch:{TypeName(encounter)}:{index}");
            return new Dictionary<string, object?>
            {
                ["index"] = index,
                ["monster_id"] = monster?.Id.ToString(),
                ["monster_type"] = monster == null ? null : TypeName(monster),
                ["slot"] = slot,
            };
        }).ToList();
        var customState = encounter.SaveCustomState();
        return new Dictionary<string, object?>
        {
            ["id"] = encounter.Id.ToString(),
            ["type"] = TypeName(encounter),
            ["rng"] = ExportRng(ReadField(encounter, "_rng"), reasons, $"encounter_rng:{encounter.Id}"),
            ["have_monsters_been_generated"] = encounter.HaveMonstersBeenGenerated,
            ["monsters_with_slots"] = generatedRows,
            ["custom_state"] = customState.ToDictionary(
                pair => pair.Key,
                pair => (object?)pair.Value,
                StringComparer.Ordinal),
            ["room_type"] = encounter.RoomType.ToString(),
            ["is_weak"] = encounter.IsWeak,
            ["should_give_rewards"] = encounter.ShouldGiveRewards,
            ["min_gold_reward"] = encounter.MinGoldReward,
            ["max_gold_reward"] = encounter.MaxGoldReward,
            ["is_debug_encounter"] = encounter.IsDebugEncounter,
            ["tags"] = encounter.Tags.Select(value => value.ToString())
                .OrderBy(value => value, StringComparer.Ordinal).ToList(),
            ["slots"] = encounter.Slots.ToList(),
            ["fully_center_players"] = encounter.FullyCenterPlayers,
            ["custom_bgm"] = encounter.CustomBgm,
            ["ambient_sfx"] = encounter.AmbientSfx,
        };
    }

    private static Dictionary<string, object?> ExportCombat(
        CombatState combatState,
        RunState runState,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons,
        bool compactBoss = false)
    {
        if (!ReferenceEquals(combatState.RunState, runState))
            reasons.Add("combat_run_state_identity_mismatch");
        var multiplayerScaling = ExportMultiplayerScaling(
            combatState.MultiplayerScalingModel,
            combatState,
            runState,
            reasons);
        var history = CombatManager.Instance.History;
        RequireExactDeclaredInstanceFields(
            history,
            typeof(CombatHistory),
            "combat_history",
            reasons,
            ("Changed", typeof(Action)),
            ("_entries", typeof(List<CombatHistoryEntry>)));
        var historyEntries = history.Entries.ToList();
        var historyBacking = ReadField(history, "_entries") as List<CombatHistoryEntry>;
        if (historyBacking == null
            || historyBacking.Count != historyEntries.Count
            || historyBacking.Where((entry, index) => !ReferenceEquals(entry, historyEntries[index])).Any())
        {
            reasons.Add("combat_history_order_or_identity_mismatch");
        }
        var cardPlayIds = BuildCardPlayIdentityMap(historyEntries);
        var damageResultIds = BuildDamageResultIdentityMap(historyEntries);
        var powerIds = BuildPowerIdentityMap(combatState, historyEntries, reasons);
        var powerRegistry = ExportPowerIdentityRegistry(
            combatState,
            historyEntries,
            powerIds,
            reasons);
        var moveIds = BuildMoveIdentityMap(combatState);
        var historyStatistics = ExportHistoryStatistics(combatState, historyEntries);
        var nextCreatureIdField = FindField(combatState.GetType(), "_nextCreatureId");
        var nextCreatureId = nextCreatureIdField?.GetValue(combatState);
        if (nextCreatureIdField == null || nextCreatureIdField.FieldType != typeof(uint) || nextCreatureId is not uint)
            reasons.Add("combat_next_creature_id_not_exportable");

        var allCardsField = FindField(combatState.GetType(), "_allCards");
        var allCards = allCardsField?.GetValue(combatState) as IEnumerable;
        if (allCards == null)
            reasons.Add("combat_all_cards_not_exportable");
        var allCardModels = new List<CardModel>();
        foreach (var card in AsObjects(allCards))
        {
            if (card is CardModel model)
                allCardModels.Add(model);
            else
                reasons.Add($"combat_all_cards_value_not_registered:{TypeName(card)}");
        }
        IEnumerable<CardModel> exportedRegistryCards = allCardModels;
        var registryContext = "combat:all";
        if (compactBoss)
        {
            var liveCards = new HashSet<CardModel>(ReferenceEqualityComparer.Instance);
            foreach (var player in runState.Players)
            {
                var combat = player.PlayerCombatState;
                if (combat == null)
                    continue;
                liveCards.UnionWith(combat.Hand.Cards);
                liveCards.UnionWith(combat.DrawPile.Cards);
                liveCards.UnionWith(combat.DiscardPile.Cards);
                liveCards.UnionWith(combat.ExhaustPile.Cards);
                liveCards.UnionWith(combat.PlayPile.Cards);
            }
            var registrySet = allCardModels.ToHashSet(ReferenceEqualityComparer.Instance);
            if (liveCards.Any(card => !registrySet.Contains(card)))
                reasons.Add("combat_live_card_missing_from_all_cards");
            exportedRegistryCards = allCardModels.Where(card => !liveCards.Contains(card));
            registryContext = "combat:registry_only";
        }
        var allCardRows = exportedRegistryCards.Select((card, index) =>
            ExportCard(card, index, registryContext, cardIds, reasons)).ToList();

        var result = new Dictionary<string, object?>
        {
            ["round_number"] = combatState.RoundNumber,
            ["current_side"] = combatState.CurrentSide.ToString(),
            ["next_creature_id"] = nextCreatureId,
            ["multiplayer_scaling"] = multiplayerScaling,
            ["creatures"] = combatState.Creatures.Select((creature, index) =>
                ExportCreature(creature, index, runState.Rng, reasons)).ToList(),
            ["escaped_creature_ids"] = combatState.EscapedCreatures
                .Select(creature => Convert.ToUInt64(creature.CombatId))
                .ToList(),
            ["history"] = historyEntries.Select((entry, index) =>
                ExportHistoryEntry(
                    entry,
                    index,
                    history,
                    combatState,
                    cardIds,
                    cardPlayIds,
                    damageResultIds,
                    powerIds,
                    moveIds,
                    reasons)).ToList(),
            ["history_statistics"] = historyStatistics,
            ["power_identity_registry"] = powerRegistry,
            ["phase"] = new Dictionary<string, object?>
            {
                ["is_play_phase"] = CombatManager.Instance.IsPlayPhase,
                ["is_enemy_turn_started"] = CombatManager.Instance.IsEnemyTurnStarted,
                ["ending_player_turn_phase_one"] = CombatManager.Instance.EndingPlayerTurnPhaseOne,
                ["ending_player_turn_phase_two"] = CombatManager.Instance.EndingPlayerTurnPhaseTwo,
                ["player_actions_disabled"] = CombatManager.Instance.PlayerActionsDisabled,
                ["is_paused"] = CombatManager.Instance.IsPaused,
            },
        };
        if (compactBoss)
        {
            result["registry_only_cards"] = allCardRows;
        }
        else
        {
            result["all_card_instance_ids"] = allCardRows
                .Select(row => row.GetValueOrDefault("instance_id"))
                .ToList();
            result["all_cards"] = allCardRows;
        }
        return result;
    }

    private static Dictionary<string, object?> ExportHistoryStatistics(
        CombatState combatState,
        IReadOnlyList<CombatHistoryEntry> historyEntries)
    {
        return new Dictionary<string, object?>
        {
            ["schema"] = "combat_history_statistics_v1",
            ["round_number"] = combatState.RoundNumber,
            ["current_side"] = StableValueForKnownEnum(combatState.CurrentSide),
            ["creatures"] = combatState.Creatures.Select(creature =>
            {
                var currentEpochEntries = historyEntries.Where(entry =>
                    ReferenceEquals(entry.Actor, creature)
                    && entry.RoundNumber == combatState.RoundNumber
                    && entry.CurrentSide == combatState.CurrentSide);
                return new Dictionary<string, object?>
                {
                    ["creature_id"] = Convert.ToUInt64(creature.CombatId),
                    ["current_epoch_finished_attack_count"] = currentEpochEntries
                        .OfType<CardPlayFinishedEntry>()
                        .Count(entry => entry.CardPlay.Card.Type == CardType.Attack),
                    ["current_epoch_positive_unblocked_damage"] = currentEpochEntries
                        .OfType<DamageReceivedEntry>()
                        .Any(entry => entry.Result.UnblockedDamage > 0),
                    ["total_positive_unblocked_damage_count"] = historyEntries
                        .OfType<DamageReceivedEntry>()
                        .Count(entry => ReferenceEquals(entry.Actor, creature)
                                        && entry.Result.UnblockedDamage > 0),
                };
            }).ToList(),
        };
    }

    private static Dictionary<string, object?> StableValueForKnownEnum<T>(T value)
        where T : struct, Enum
    {
        return new Dictionary<string, object?>
        {
            ["type"] = TypeName(value),
            ["name"] = value.ToString(),
            ["numeric"] = Convert.ToInt64(value),
        };
    }

    private static Dictionary<string, object?>? ExportMultiplayerScaling(
        object? scaling,
        CombatState combatState,
        RunState runState,
        SortedSet<string> reasons)
    {
        if (scaling == null)
        {
            reasons.Add("multiplayer_scaling_model_missing");
            return null;
        }
        RegisterType(scaling, RegisteredMultiplayerScalingTypes, "multiplayer_scaling", reasons);
        if (!ReferenceEquals(ReadField(scaling, "_runState"), runState))
            reasons.Add("multiplayer_scaling_run_state_identity_mismatch");
        if (!ReferenceEquals(ReadField(scaling, "_combatState"), combatState))
            reasons.Add("multiplayer_scaling_combat_state_identity_mismatch");
        return new Dictionary<string, object?>
        {
            ["type"] = TypeName(scaling),
            ["run_state_bound"] = true,
            ["combat_state_bound"] = true,
        };
    }

    private static Dictionary<string, object?> ExportHistoryEntry(
        CombatHistoryEntry entry,
        int index,
        CombatHistory history,
        CombatState combatState,
        IReadOnlyDictionary<CardModel, string> cardIds,
        IReadOnlyDictionary<CardPlay, string> cardPlayIds,
        IReadOnlyDictionary<DamageResult, string> damageResultIds,
        IReadOnlyDictionary<PowerModel, string> powerIds,
        IReadOnlyDictionary<object, string> moveIds,
        SortedSet<string> reasons)
    {
        RequireExactDeclaredInstanceFields(
            entry,
            typeof(CombatHistoryEntry),
            "combat_history_base",
            reasons,
            ("<Actor>k__BackingField", typeof(Creature)),
            ("<RoundNumber>k__BackingField", typeof(int)),
            ("<CurrentSide>k__BackingField", typeof(CombatSide)),
            ("<History>k__BackingField", typeof(CombatHistory)));
        if (!ReferenceEquals(entry.History, history))
            reasons.Add($"combat_history_sentinel_mismatch:index={index}:{TypeName(entry)}");
        if (entry.RoundNumber < 0 || entry.RoundNumber > combatState.RoundNumber)
            reasons.Add($"combat_history_round_out_of_range:index={index}:{entry.RoundNumber}");
        if (!Enum.IsDefined(typeof(CombatSide), entry.CurrentSide))
            reasons.Add($"combat_history_side_not_registered:index={index}:{Convert.ToInt64(entry.CurrentSide)}");

        var result = new Dictionary<string, object?>
        {
            ["index"] = index,
            ["type"] = TypeName(entry),
            ["round_number"] = entry.RoundNumber,
            ["current_side"] = StableValue(entry.CurrentSide, reasons, $"history:{index}:current_side"),
            ["actor_id"] = ResolveCreatureIdentity(entry.Actor, combatState, reasons, $"history:{index}:actor"),
            ["history_sentinel"] = "current_combat_history",
        };

        switch (entry)
        {
            case CardDrawnEntry drawn:
                RequireHistoryFields(
                    drawn,
                    reasons,
                    ("<Card>k__BackingField", typeof(CardModel)),
                    ("<FromHandDraw>k__BackingField", typeof(bool)));
                result["card_instance_id"] = ResolveCardIdentity(drawn.Card, cardIds, reasons);
                result["from_hand_draw"] = drawn.FromHandDraw;
                RequireCardOwnerActor(drawn.Card, entry.Actor, reasons, $"history:{index}:drawn_card");
                break;
            case BlockGainedEntry gained:
                RequireHistoryFields(
                    gained,
                    reasons,
                    ("<Amount>k__BackingField", typeof(int)),
                    ("<Props>k__BackingField", typeof(MegaCrit.Sts2.Core.ValueProps.ValueProp)),
                    ("<CardPlay>k__BackingField", typeof(CardPlay)));
                result["amount"] = gained.Amount;
                result["props"] = StableValue(gained.Props, reasons, $"history:{index}:block_props");
                result["card_play"] = gained.CardPlay == null
                    ? null
                    : ExportCardPlay(gained.CardPlay, cardPlayIds, combatState, cardIds, reasons, $"history:{index}:card_play");
                break;
            case CardExhaustedEntry exhausted:
                RequireHistoryFields(exhausted, reasons, ("<Card>k__BackingField", typeof(CardModel)));
                result["card_instance_id"] = ResolveCardIdentity(exhausted.Card, cardIds, reasons);
                RequireCardOwnerActor(exhausted.Card, entry.Actor, reasons, $"history:{index}:exhausted_card");
                break;
            case CardGeneratedEntry generated:
                RequireHistoryFields(
                    generated,
                    reasons,
                    ("<Card>k__BackingField", typeof(CardModel)),
                    ("<GeneratedByPlayer>k__BackingField", typeof(bool)));
                result["card_instance_id"] = ResolveCardIdentity(generated.Card, cardIds, reasons);
                result["generated_by_player"] = generated.GeneratedByPlayer;
                RequireCardOwnerActor(generated.Card, entry.Actor, reasons, $"history:{index}:generated_card");
                break;
            case CardPlayFinishedEntry finished:
                RequireHistoryFields(
                    finished,
                    reasons,
                    ("<CardPlay>k__BackingField", typeof(CardPlay)),
                    ("<WasEthereal>k__BackingField", typeof(bool)));
                result["card_play"] = ExportCardPlay(
                    finished.CardPlay,
                    cardPlayIds,
                    combatState,
                    cardIds,
                    reasons,
                    $"history:{index}:card_play");
                result["was_ethereal"] = finished.WasEthereal;
                RequireCardOwnerActor(finished.CardPlay.Card, entry.Actor, reasons, $"history:{index}:finished_card_play");
                break;
            case CardPlayStartedEntry started:
                RequireHistoryFields(started, reasons, ("<CardPlay>k__BackingField", typeof(CardPlay)));
                result["card_play"] = ExportCardPlay(
                    started.CardPlay,
                    cardPlayIds,
                    combatState,
                    cardIds,
                    reasons,
                    $"history:{index}:card_play");
                RequireCardOwnerActor(started.CardPlay.Card, entry.Actor, reasons, $"history:{index}:started_card_play");
                break;
            case CreatureAttackedEntry attacked:
                RequireHistoryFields(
                    attacked,
                    reasons,
                    ("<DamageResults>k__BackingField", typeof(IReadOnlyList<DamageResult>)));
                result["damage_results"] = attacked.DamageResults.Select((damage, damageIndex) =>
                    ExportDamageResult(
                        damage,
                        damageResultIds,
                        combatState,
                        reasons,
                        $"history:{index}:damage:{damageIndex}")).ToList();
                break;
            case DamageReceivedEntry received:
                RequireHistoryFields(
                    received,
                    reasons,
                    ("<Result>k__BackingField", typeof(DamageResult)),
                    ("<Dealer>k__BackingField", typeof(Creature)),
                    ("<CardSource>k__BackingField", typeof(CardModel)));
                result["damage_result"] = ExportDamageResult(
                    received.Result,
                    damageResultIds,
                    combatState,
                    reasons,
                    $"history:{index}:damage");
                result["dealer_id"] = received.Dealer == null
                    ? null
                    : ResolveCreatureIdentity(received.Dealer, combatState, reasons, $"history:{index}:dealer");
                result["card_source_instance_id"] = received.CardSource == null
                    ? null
                    : ResolveCardIdentity(received.CardSource, cardIds, reasons);
                if (!ReferenceEquals(received.Result.Receiver, entry.Actor))
                    reasons.Add($"history_damage_receiver_actor_mismatch:index={index}");
                break;
            case EnergySpentEntry spent:
                RequireHistoryFields(spent, reasons, ("<Amount>k__BackingField", typeof(int)));
                result["amount"] = spent.Amount;
                if (entry.Actor.Player == null)
                    reasons.Add($"history_energy_actor_not_player:index={index}");
                break;
            case MonsterPerformedMoveEntry performed:
                RequireHistoryFields(
                    performed,
                    reasons,
                    ("<Monster>k__BackingField", typeof(MonsterModel)),
                    ("<Move>k__BackingField", typeof(MoveState)),
                    ("<Targets>k__BackingField", typeof(IEnumerable<Creature>)));
                result["monster_creature_id"] = ResolveMonsterIdentity(
                    performed.Monster,
                    combatState,
                    reasons,
                    $"history:{index}:monster");
                result["move_state_id"] = ResolveObjectIdentity(
                    performed.Move,
                    moveIds,
                    reasons,
                    $"history_move_outside_current_state_machine:index={index}");
                result["target_ids"] = ExportCreatureTargets(
                    performed.Targets,
                    combatState,
                    reasons,
                    $"history:{index}:targets");
                if (!ReferenceEquals(performed.Monster.Creature, entry.Actor))
                    reasons.Add($"history_monster_actor_mismatch:index={index}");
                var performedMachine = performed.Monster.MoveStateMachine;
                if (performedMachine == null || !performedMachine.States.Any(
                        state => ReferenceEquals(state.Value, performed.Move)))
                {
                    reasons.Add($"history_move_monster_state_machine_mismatch:index={index}");
                }
                break;
            case PowerReceivedEntry powerReceived:
                RequireHistoryFields(
                    powerReceived,
                    reasons,
                    ("<Power>k__BackingField", typeof(PowerModel)),
                    ("<Amount>k__BackingField", typeof(decimal)),
                    ("<Applier>k__BackingField", typeof(Creature)));
                result["power_instance_id"] = ResolveObjectIdentity(
                    powerReceived.Power,
                    powerIds,
                    reasons,
                    $"history_power_outside_current_creatures:index={index}:{TypeName(powerReceived.Power)}");
                result["power_type"] = TypeName(powerReceived.Power);
                result["power_id"] = powerReceived.Power.Id.ToString();
                result["amount"] = powerReceived.Amount;
                result["applier_id"] = powerReceived.Applier == null
                    ? null
                    : ResolveCreatureIdentity(powerReceived.Applier, combatState, reasons, $"history:{index}:applier");
                if (!ReferenceEquals(powerReceived.Power.Owner, entry.Actor))
                    reasons.Add($"history_power_owner_actor_mismatch:index={index}");
                break;
            default:
                reasons.Add($"combat_history_type_not_registered:{TypeName(entry)}");
                break;
        }
        return result;
    }

    private static void RequireHistoryFields(
        CombatHistoryEntry entry,
        SortedSet<string> reasons,
        params (string Name, Type FieldType)[] fields)
    {
        RequireExactDeclaredInstanceFields(
            entry,
            entry.GetType(),
            $"combat_history:{TypeName(entry)}",
            reasons,
            fields);
    }

    private static Dictionary<CardPlay, string> BuildCardPlayIdentityMap(
        IReadOnlyList<CombatHistoryEntry> entries)
    {
        var result = new Dictionary<CardPlay, string>(ReferenceEqualityComparer.Instance);
        foreach (var (entry, index) in entries.Select((value, itemIndex) => (value, itemIndex)))
        {
            CardPlay? cardPlay = entry switch
            {
                BlockGainedEntry gained => gained.CardPlay,
                CardPlayFinishedEntry finished => finished.CardPlay,
                CardPlayStartedEntry started => started.CardPlay,
                _ => null,
            };
            if (cardPlay != null)
                result.TryAdd(cardPlay, $"history:card_play:{index}");
        }
        return result;
    }

    private static Dictionary<DamageResult, string> BuildDamageResultIdentityMap(
        IReadOnlyList<CombatHistoryEntry> entries)
    {
        var result = new Dictionary<DamageResult, string>(ReferenceEqualityComparer.Instance);
        foreach (var (entry, index) in entries.Select((value, itemIndex) => (value, itemIndex)))
        {
            switch (entry)
            {
                case CreatureAttackedEntry attacked:
                    foreach (var (damage, damageIndex) in attacked.DamageResults.Select(
                                 (value, itemIndex) => (value, itemIndex)))
                    {
                        result.TryAdd(damage, $"history:damage:{index}:{damageIndex}");
                    }
                    break;
                case DamageReceivedEntry received:
                    result.TryAdd(received.Result, $"history:damage:{index}:result");
                    break;
            }
        }
        return result;
    }

    private static Dictionary<PowerModel, string> BuildPowerIdentityMap(
        CombatState combatState,
        IReadOnlyList<CombatHistoryEntry> historyEntries,
        SortedSet<string> reasons)
    {
        var result = new Dictionary<PowerModel, string>(ReferenceEqualityComparer.Instance);
        foreach (var creature in combatState.Creatures)
        {
            foreach (var (power, index) in creature.Powers.Select((value, itemIndex) => (value, itemIndex)))
            {
                if (!result.TryAdd(power, $"creature:{Convert.ToUInt64(creature.CombatId)}:power:{index}"))
                    reasons.Add($"active_power_registered_multiple_times:{TypeName(power)}");
            }
        }
        foreach (var (entry, index) in historyEntries.Select((value, itemIndex) => (value, itemIndex)))
        {
            if (entry is PowerReceivedEntry received)
                result.TryAdd(received.Power, $"history:power:{index}");
        }
        return result;
    }

    private static List<Dictionary<string, object?>> ExportPowerIdentityRegistry(
        CombatState combatState,
        IReadOnlyList<CombatHistoryEntry> historyEntries,
        IReadOnlyDictionary<PowerModel, string> powerIds,
        SortedSet<string> reasons)
    {
        var active = new HashSet<PowerModel>(ReferenceEqualityComparer.Instance);
        var ordered = new List<PowerModel>();
        var emitted = new HashSet<PowerModel>(ReferenceEqualityComparer.Instance);
        foreach (var creature in combatState.Creatures)
        {
            foreach (var power in creature.Powers)
            {
                active.Add(power);
                if (emitted.Add(power))
                    ordered.Add(power);
            }
        }
        var firstHistoryIndex = new Dictionary<PowerModel, int>(ReferenceEqualityComparer.Instance);
        foreach (var (entry, index) in historyEntries.Select((value, itemIndex) => (value, itemIndex)))
        {
            if (entry is not PowerReceivedEntry received)
                continue;
            firstHistoryIndex.TryAdd(received.Power, index);
            if (emitted.Add(received.Power))
                ordered.Add(received.Power);
        }
        return ordered.Select((power, index) => new Dictionary<string, object?>
        {
            ["index"] = index,
            ["instance_id"] = ResolveObjectIdentity(
                power,
                powerIds,
                reasons,
                $"power_registry_identity_missing:{TypeName(power)}"),
            ["active"] = active.Contains(power),
            ["first_history_index"] = firstHistoryIndex.TryGetValue(power, out var historyIndex)
                ? historyIndex
                : null,
            ["state"] = ExportPower(power, index, reasons),
        }).ToList();
    }

    private static Dictionary<object, string> BuildMoveIdentityMap(CombatState combatState)
    {
        var result = new Dictionary<object, string>(ReferenceEqualityComparer.Instance);
        foreach (var creature in combatState.Creatures)
        {
            var machine = creature.Monster?.MoveStateMachine;
            if (machine == null)
                continue;
            foreach (var entry in machine.States)
            {
                result.TryAdd(
                    entry.Value,
                    $"creature:{Convert.ToUInt64(creature.CombatId)}:move:{entry.Key}");
            }
        }
        return result;
    }

    private static Dictionary<string, object?> ExportCardPlay(
        CardPlay cardPlay,
        IReadOnlyDictionary<CardPlay, string> cardPlayIds,
        CombatState combatState,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons,
        string context)
    {
        RequireExactDeclaredInstanceFields(
            cardPlay,
            typeof(CardPlay),
            "card_play",
            reasons,
            ("<Card>k__BackingField", typeof(CardModel)),
            ("<Target>k__BackingField", typeof(Creature)),
            ("<ResultPile>k__BackingField", typeof(PileType)),
            ("<Resources>k__BackingField", typeof(ResourceInfo)),
            ("<IsAutoPlay>k__BackingField", typeof(bool)),
            ("<PlayIndex>k__BackingField", typeof(int)),
            ("<PlayCount>k__BackingField", typeof(int)));
        RequireExactDeclaredInstanceFields(
            cardPlay.Resources,
            typeof(ResourceInfo),
            "card_play_resources",
            reasons,
            ("<EnergySpent>k__BackingField", typeof(int)),
            ("<EnergyValue>k__BackingField", typeof(int)),
            ("<StarsSpent>k__BackingField", typeof(int)),
            ("<StarValue>k__BackingField", typeof(int)));
        return new Dictionary<string, object?>
        {
            ["instance_id"] = ResolveObjectIdentity(
                cardPlay,
                cardPlayIds,
                reasons,
                $"card_play_outside_history:{context}"),
            ["card_instance_id"] = ResolveCardIdentity(cardPlay.Card, cardIds, reasons),
            ["target_id"] = cardPlay.Target == null
                ? null
                : ResolveCreatureIdentity(cardPlay.Target, combatState, reasons, $"{context}:target"),
            ["result_pile"] = StableValue(cardPlay.ResultPile, reasons, $"{context}:result_pile"),
            ["resources"] = new Dictionary<string, object?>
            {
                ["energy_spent"] = cardPlay.Resources.EnergySpent,
                ["energy_value"] = cardPlay.Resources.EnergyValue,
                ["stars_spent"] = cardPlay.Resources.StarsSpent,
                ["star_value"] = cardPlay.Resources.StarValue,
            },
            ["is_auto_play"] = cardPlay.IsAutoPlay,
            ["play_index"] = cardPlay.PlayIndex,
            ["play_count"] = cardPlay.PlayCount,
        };
    }

    private static Dictionary<string, object?> ExportDamageResult(
        DamageResult damage,
        IReadOnlyDictionary<DamageResult, string> damageResultIds,
        CombatState combatState,
        SortedSet<string> reasons,
        string context)
    {
        RequireExactDeclaredInstanceFields(
            damage,
            typeof(DamageResult),
            "damage_result",
            reasons,
            ("<Receiver>k__BackingField", typeof(Creature)),
            ("<Props>k__BackingField", typeof(MegaCrit.Sts2.Core.ValueProps.ValueProp)),
            ("<BlockedDamage>k__BackingField", typeof(int)),
            ("<UnblockedDamage>k__BackingField", typeof(int)),
            ("<OverkillDamage>k__BackingField", typeof(int)),
            ("<WasBlockBroken>k__BackingField", typeof(bool)),
            ("<WasFullyBlocked>k__BackingField", typeof(bool)),
            ("<WasTargetKilled>k__BackingField", typeof(bool)));
        return new Dictionary<string, object?>
        {
            ["instance_id"] = ResolveObjectIdentity(
                damage,
                damageResultIds,
                reasons,
                $"damage_result_outside_history:{context}"),
            ["receiver_id"] = ResolveCreatureIdentity(damage.Receiver, combatState, reasons, $"{context}:receiver"),
            ["props"] = StableValue(damage.Props, reasons, $"{context}:props"),
            ["blocked_damage"] = damage.BlockedDamage,
            ["unblocked_damage"] = damage.UnblockedDamage,
            ["overkill_damage"] = damage.OverkillDamage,
            ["was_block_broken"] = damage.WasBlockBroken,
            ["was_fully_blocked"] = damage.WasFullyBlocked,
            ["was_target_killed"] = damage.WasTargetKilled,
        };
    }

    private static List<object?>? ExportCreatureTargets(
        IEnumerable<Creature>? targets,
        CombatState combatState,
        SortedSet<string> reasons,
        string context)
    {
        if (targets == null)
            return null;
        if (targets is not IReadOnlyList<Creature> ordered)
        {
            reasons.Add($"history_targets_collection_not_registered:{context}:{TypeName(targets)}");
            return null;
        }
        return ordered.Select((target, index) =>
                ResolveCreatureIdentity(target, combatState, reasons, $"{context}:{index}"))
            .Cast<object?>()
            .ToList();
    }

    private static ulong? ResolveCreatureIdentity(
        Creature creature,
        CombatState combatState,
        SortedSet<string> reasons,
        string context)
    {
        if (combatState.Creatures.Any(candidate => ReferenceEquals(candidate, creature)))
            return Convert.ToUInt64(creature.CombatId);
        reasons.Add($"creature_reference_outside_current_combat:{context}:{Convert.ToUInt64(creature.CombatId)}");
        return null;
    }

    private static void RequireCardOwnerActor(
        CardModel card,
        Creature actor,
        SortedSet<string> reasons,
        string context)
    {
        var owner = ReadField(card, "_owner") as Player;
        if (owner == null || !ReferenceEquals(owner.Creature, actor))
            reasons.Add($"history_card_owner_actor_mismatch:{context}:{card.Id}");
    }

    private static ulong? ResolveMonsterIdentity(
        MonsterModel monster,
        CombatState combatState,
        SortedSet<string> reasons,
        string context)
    {
        var creature = combatState.Creatures.FirstOrDefault(
            candidate => ReferenceEquals(candidate.Monster, monster));
        if (creature != null)
            return Convert.ToUInt64(creature.CombatId);
        reasons.Add($"monster_reference_outside_current_combat:{context}:{TypeName(monster)}");
        return null;
    }

    private static string? ResolveObjectIdentity<T>(
        T value,
        IReadOnlyDictionary<T, string> identities,
        SortedSet<string> reasons,
        string reason)
        where T : notnull
    {
        if (identities.TryGetValue(value, out var identity))
            return identity;
        reasons.Add(reason);
        return null;
    }

    private static Dictionary<CardModel, string> BuildCardIdentityMap(
        RunState runState,
        CombatState combatState,
        bool canonicalizeDiscardForStableShuffle = false)
    {
        var result = new Dictionary<CardModel, string>(ReferenceEqualityComparer.Instance);
        foreach (var (player, playerIndex) in runState.Players.Select((value, index) => (value, index)))
        {
            AddCards(player.Deck?.Cards, $"player:{playerIndex}:deck", result);
            var combat = player.PlayerCombatState;
            if (combat == null)
                continue;
            AddCards(combat.Hand.Cards, $"player:{playerIndex}:combat:{combat.Hand.Type}", result);
            AddCards(combat.DrawPile.Cards, $"player:{playerIndex}:combat:{combat.DrawPile.Type}", result);
            if (canonicalizeDiscardForStableShuffle)
            {
                var stableShuffleInput = combat.DiscardPile.Cards.ToList();
                stableShuffleInput.Sort();
                AddCards(
                    stableShuffleInput,
                    $"player:{playerIndex}:combat:{combat.DiscardPile.Type}",
                    result);
            }
            else
            {
                AddCards(
                    combat.DiscardPile.Cards,
                    $"player:{playerIndex}:combat:{combat.DiscardPile.Type}",
                    result);
            }
            AddCards(combat.ExhaustPile.Cards, $"player:{playerIndex}:combat:{combat.ExhaustPile.Type}", result);
            AddCards(combat.PlayPile.Cards, $"player:{playerIndex}:combat:{combat.PlayPile.Type}", result);
        }
        AddCards(
            FindField(combatState.GetType(), "_allCards")?.GetValue(combatState) as IEnumerable<CardModel>,
            "combat:all",
            result);
        return result;
    }

    private static void AddCards(
        IEnumerable<CardModel>? cards,
        string context,
        IDictionary<CardModel, string> result)
    {
        if (cards == null)
            return;
        foreach (var (card, index) in cards.Select((value, index) => (value, index)))
            result.TryAdd(card, $"{context}:{index}");
    }

    private static Dictionary<string, object?> ExportPlayer(
        Player player,
        int index,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons,
        bool compactBoss = false)
    {
        var combat = player.PlayerCombatState;
        if (combat == null)
        {
            reasons.Add($"player_combat_state_missing:index={index}");
            return new Dictionary<string, object?> { ["index"] = index };
        }
        if (player.Character == null)
            reasons.Add($"player_character_missing:index={index}");
        else
            RegisterType(player.Character, RegisteredCharacterTypes, "character", reasons);

        var potionSlots = player.PotionSlots.Select((potion, slot) =>
        {
            if (potion == null)
                return null;
            RegisterTypeOrFieldless(
                potion,
                typeof(PotionModel),
                RegisteredPotionTypes,
                "potion",
                reasons);
            var owner = ReadField(potion, "_owner") as Player;
            if (!ReferenceEquals(owner, player))
                reasons.Add($"potion_owner_identity_mismatch:slot={slot}:{TypeName(potion)}");
            return new Dictionary<string, object?>
            {
                ["slot"] = slot,
                ["id"] = potion.Id.ToString(),
                ["type"] = TypeName(potion),
                ["owner_net_id"] = owner == null ? null : Convert.ToUInt64(owner.NetId),
                ["rarity"] = potion.Rarity.ToString(),
                ["usage"] = potion.Usage.ToString(),
                ["target_type"] = potion.TargetType.ToString(),
                ["is_queued"] = potion.IsQueued,
                ["removed_from_state"] = potion.HasBeenRemovedFromState,
                ["dynamic_vars"] = ExportDynamicVars(potion, reasons),
            };
        }).ToList();

        var relics = player.Relics.Select((relic, relicIndex) =>
        {
            RegisterTypeOrFieldless(relic, typeof(RelicModel), RegisteredRelicTypes, "relic", reasons);
            var owner = ReadField(relic, "_owner") as Player;
            if (!ReferenceEquals(owner, player))
                reasons.Add($"relic_owner_identity_mismatch:index={relicIndex}:{TypeName(relic)}");
            var serialized = relic.ToSerializable();
            return new Dictionary<string, object?>
            {
                ["index"] = relicIndex,
                ["id"] = relic.Id.ToString(),
                ["type"] = TypeName(relic),
                ["owner_net_id"] = owner == null ? null : Convert.ToUInt64(owner.NetId),
                ["rarity"] = relic.Rarity.ToString(),
                ["saved_properties"] = ExportSavedProperties(serialized.Props, reasons, $"relic:{relic.Id}"),
                ["floor_added_to_deck"] = serialized.FloorAddedToDeck,
                ["is_used_up"] = relic.IsUsedUp,
                ["is_wax"] = relic.IsWax,
                ["is_melted"] = relic.IsMelted,
                ["stack_count"] = relic.StackCount,
                ["status"] = relic.Status.ToString(),
                ["show_counter"] = relic.ShowCounter,
                ["display_amount"] = relic.DisplayAmount,
                ["dynamic_vars"] = ExportDynamicVars(relic, reasons),
                ["concrete_state"] = ExportRelicConcreteState(relic, cardIds, reasons),
            };
        }).ToList();

        var powers = player.Creature?.Powers?.Select((power, powerIndex) =>
            ExportPower(power, powerIndex, reasons)).ToList() ?? new List<Dictionary<string, object?>>();
        var pets = combat.Pets.ToList();
        foreach (var pet in pets)
            reasons.Add($"unregistered_player_pet:{TypeName(pet)}");

        var result = new Dictionary<string, object?>
        {
            ["index"] = index,
            ["net_id"] = Convert.ToUInt64(player.NetId),
            ["character_id"] = player.Character?.Id.ToString(),
            ["character_type"] = player.Character == null ? null : TypeName(player.Character),
            ["active_for_hooks"] = player.IsActiveForHooks,
            ["hp"] = player.Creature?.CurrentHp ?? 0,
            ["max_hp"] = player.Creature?.MaxHp ?? 0,
            ["block"] = player.Creature?.Block ?? 0,
            ["gold"] = player.Gold,
            ["max_energy"] = player.MaxEnergy,
            ["energy"] = combat.Energy,
            ["stars"] = combat.Stars,
            ["max_potion_count"] = player.MaxPotionCount,
            ["can_remove_potions"] = player.CanRemovePotions,
            ["base_orb_slot_count"] = player.BaseOrbSlotCount,
            ["extra_fields"] = new Dictionary<string, object?>
            {
                ["card_shop_removals_used"] = player.ExtraFields.CardShopRemovalsUsed,
                ["wongo_points"] = player.ExtraFields.WongoPoints,
            },
            ["player_rng"] = ExportRngSet(
                player.PlayerRng,
                ExpectedPlayerRngMembers,
                ExpectedPlayerRngRegistryKeys,
                reasons,
                $"player_rng:{index}"),
            ["piles"] = new List<object?>
            {
                ExportPile(combat.Hand, index, cardIds, reasons),
                ExportPile(combat.DrawPile, index, cardIds, reasons),
                ExportPile(combat.DiscardPile, index, cardIds, reasons),
                ExportPile(combat.ExhaustPile, index, cardIds, reasons),
                ExportPile(combat.PlayPile, index, cardIds, reasons),
            },
            ["potions"] = potionSlots,
            ["relics"] = relics,
            ["powers"] = powers,
            ["orbs"] = ExportOrbs(combat.OrbQueue?.Orbs, reasons),
            ["orb_capacity"] = combat.OrbQueue?.Capacity ?? 0,
            ["pet_count"] = pets.Count,
        };
        if (!compactBoss)
        {
            result["deck"] = ExportCards(
                player.Deck?.Cards,
                $"player:{index}:deck",
                cardIds,
                reasons);
        }
        return result;
    }

    private static Dictionary<string, object?>? ExportRelicConcreteState(
        RelicModel relic,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons)
    {
        switch (TypeName(relic))
        {
            case "MegaCrit.Sts2.Core.Models.Relics.LastingCandy":
                RequireExactDeclaredInstanceFields(
                    relic,
                    relic.GetType(),
                    "relic:LastingCandy",
                    reasons,
                    ("_isActivating", typeof(bool)),
                    ("_combatsSeen", typeof(int)));
                return new Dictionary<string, object?>
                {
                    ["is_activating"] = ReadRequiredField(relic, "_isActivating", typeof(bool), reasons),
                    ["combats_seen"] = ReadRequiredField(relic, "_combatsSeen", typeof(int), reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Relics.VenerableTeaSet":
                RequireExactDeclaredInstanceFields(
                    relic,
                    relic.GetType(),
                    "relic:VenerableTeaSet",
                    reasons,
                    ("_gainEnergyInNextCombat", typeof(bool)));
                return new Dictionary<string, object?>
                {
                    ["gain_energy_in_next_combat"] = ReadRequiredField(
                        relic,
                        "_gainEnergyInNextCombat",
                        typeof(bool),
                        reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Relics.CentennialPuzzle":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:CentennialPuzzle",
                    reasons,
                    ("_usedThisCombat", "used_this_combat", typeof(bool)));
            case "MegaCrit.Sts2.Core.Models.Relics.JossPaper":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:JossPaper",
                    reasons,
                    ("_isActivating", "is_activating", typeof(bool)),
                    ("_cardsExhausted", "cards_exhausted", typeof(int)),
                    ("_etherealCount", "ethereal_count", typeof(int)));
            case "MegaCrit.Sts2.Core.Models.Relics.Kusarigama":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:Kusarigama",
                    reasons,
                    ("_isActivating", "is_activating", typeof(bool)),
                    ("_attacksPlayedThisTurn", "attacks_played_this_turn", typeof(int)));
            case "MegaCrit.Sts2.Core.Models.Relics.Nunchaku":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:Nunchaku",
                    reasons,
                    ("_isActivating", "is_activating", typeof(bool)),
                    ("_attacksPlayed", "attacks_played", typeof(int)));
            case "MegaCrit.Sts2.Core.Models.Relics.PaelsTears":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:PaelsTears",
                    reasons,
                    ("_hadLeftoverEnergy", "had_leftover_energy", typeof(bool)));
            case "MegaCrit.Sts2.Core.Models.Relics.Pendulum":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:Pendulum",
                    reasons,
                    ("_isActivating", "is_activating", typeof(bool)),
                    ("_turnsSeen", "turns_seen", typeof(int)));
            case "MegaCrit.Sts2.Core.Models.Relics.PenNib":
                RequireExactDeclaredInstanceFields(
                    relic,
                    relic.GetType(),
                    "relic:PenNib",
                    reasons,
                    ("_isActivating", typeof(bool)),
                    ("_attacksPlayed", typeof(int)),
                    ("_attackToDouble", typeof(CardModel)));
                var attackToDouble = ReadField(relic, "_attackToDouble") as CardModel;
                return new Dictionary<string, object?>
                {
                    ["is_activating"] = ReadRequiredField(relic, "_isActivating", typeof(bool), reasons),
                    ["attacks_played"] = ReadRequiredField(relic, "_attacksPlayed", typeof(int), reasons),
                    ["attack_to_double_instance_id"] = attackToDouble == null
                        ? null
                        : ResolveCardIdentity(attackToDouble, cardIds, reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Relics.RainbowRing":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:RainbowRing",
                    reasons,
                    ("_attacksPlayedThisTurn", "attacks_played_this_turn", typeof(int)),
                    ("_skillsPlayedThisTurn", "skills_played_this_turn", typeof(int)),
                    ("_powersPlayedThisTurn", "powers_played_this_turn", typeof(int)),
                    ("_activationCountThisTurn", "activation_count_this_turn", typeof(int)));
            case "MegaCrit.Sts2.Core.Models.Relics.TuningFork":
                return ExportExactPrimitiveFields(
                    relic,
                    "relic:TuningFork",
                    reasons,
                    ("_isActivating", "is_activating", typeof(bool)),
                    ("_skillsPlayed", "skills_played", typeof(int)));
            default:
                return null;
        }
    }

    private static Dictionary<string, object?> ExportExactPrimitiveFields(
        object model,
        string context,
        SortedSet<string> reasons,
        params (string FieldName, string TokenName, Type FieldType)[] fields)
    {
        RequireExactDeclaredInstanceFields(
            model,
            model.GetType(),
            context,
            reasons,
            fields.Select(field => (field.FieldName, field.FieldType)).ToArray());
        return fields.ToDictionary(
            field => field.TokenName,
            field => ReadRequiredField(model, field.FieldName, field.FieldType, reasons),
            StringComparer.Ordinal);
    }

    private static Dictionary<string, object?> ExportPile(
        CardPile pile,
        int playerIndex,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons)
    {
        return new Dictionary<string, object?>
        {
            ["type"] = pile.Type.ToString(),
            ["cards"] = ExportCards(
                pile.Cards,
                $"player:{playerIndex}:combat:{pile.Type}",
                cardIds,
                reasons),
        };
    }

    private static List<Dictionary<string, object?>> ExportCards(
        IEnumerable<CardModel>? cards,
        string context,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons)
    {
        return cards?.Select((card, index) => ExportCard(card, index, context, cardIds, reasons)).ToList()
               ?? new List<Dictionary<string, object?>>();
    }

    private static Dictionary<string, object?> ExportCard(
        CardModel card,
        int index,
        string context,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons)
    {
        RegisterTypeOrFieldless(card, typeof(CardModel), RegisteredCardTypes, "card", reasons);
        var serialized = card.ToSerializable();
        var enchantment = card.Enchantment;
        var currentTarget = card.CurrentTarget;
        if (enchantment != null)
        {
            RegisterTypeOrFieldless(
                enchantment,
                typeof(EnchantmentModel),
                RegisteredEnchantmentTypes,
                "enchantment",
                reasons);
            if (!ReferenceEquals(ReadField(enchantment, "_card"), card))
                reasons.Add($"enchantment_card_identity_mismatch:{TypeName(enchantment)}");
        }
        if (card.Affliction != null)
            reasons.Add($"unregistered_affliction_type:{TypeName(card.Affliction)}");
        return new Dictionary<string, object?>
        {
            ["index"] = index,
            ["instance_id"] = ResolveCardIdentity(card, cardIds, reasons),
            ["context"] = context,
            ["type"] = TypeName(card),
            ["id"] = card.Id.ToString(),
            ["card_type"] = StableValueForKnownEnum(card.Type),
            ["upgrade_level"] = serialized.CurrentUpgradeLevel,
            ["floor_added_to_deck"] = serialized.FloorAddedToDeck,
            ["saved_properties"] = ExportSavedProperties(serialized.Props, reasons, $"card:{card.Id}"),
            ["enchantment"] = enchantment == null ? null : new Dictionary<string, object?>
            {
                ["type"] = TypeName(enchantment),
                ["id"] = enchantment.Id.ToString(),
                ["amount"] = enchantment.Amount,
                ["status"] = enchantment.Status.ToString(),
                ["card_instance_id"] = ResolveCardIdentity(card, cardIds, reasons),
                ["saved_properties"] = ExportSavedProperties(
                    enchantment.Props,
                    reasons,
                    $"enchantment:{enchantment.Id}"),
                ["dynamic_vars"] = ExportDynamicVars(enchantment, reasons),
            },
            ["affliction_id"] = card.Affliction?.Id.ToString(),
            ["affliction_amount"] = card.Affliction?.Amount,
            ["energy_cost"] = ExportEnergyCost(card, reasons),
            ["canonical_star_cost"] = card.CanonicalStarCost,
            ["base_star_cost"] = card.BaseStarCost,
            ["star_cost_set"] = ReadField(card, "_starCostSet"),
            ["was_star_cost_just_upgraded"] = card.WasStarCostJustUpgraded,
            ["has_temporary_star_cost"] = card.TemporaryStarCost != null,
            ["temporary_star_costs"] = ExportTemporaryStarCosts(card, reasons),
            ["current_star_cost"] = card.CurrentStarCost,
            ["last_stars_spent"] = card.LastStarsSpent,
            ["base_replay_count"] = card.BaseReplayCount,
            ["exhaust_on_next_play"] = card.ExhaustOnNextPlay,
            ["single_turn_retain"] = ReadField(card, "_hasSingleTurnRetain"),
            ["should_retain_this_turn"] = card.ShouldRetainThisTurn,
            ["single_turn_sly"] = ReadField(card, "_hasSingleTurnSly"),
            ["is_sly_this_turn"] = card.IsSlyThisTurn,
            ["removed_from_state"] = card.HasBeenRemovedFromState,
            ["clone_of"] = card.CloneOf == null ? null : ResolveCardIdentity(card.CloneOf, cardIds, reasons),
            ["dupe_of"] = card.DupeOf == null ? null : ResolveCardIdentity(card.DupeOf, cardIds, reasons),
            ["is_dupe"] = card.IsDupe,
            ["deck_version"] = card.DeckVersion == null
                ? null
                : ResolveCardIdentity(card.DeckVersion, cardIds, reasons),
            ["upgrade_preview_type"] = card.UpgradePreviewType.ToString(),
            ["is_enchantment_preview"] = card.IsEnchantmentPreview,
            ["current_target_id"] = currentTarget == null ? null : Convert.ToUInt64(currentTarget.CombatId),
            ["keywords"] = card.Keywords.Select(value => value.ToString()).OrderBy(value => value, StringComparer.Ordinal).ToList(),
            ["tags"] = card.Tags.Select(value => value.ToString()).OrderBy(value => value, StringComparer.Ordinal).ToList(),
            ["dynamic_vars"] = ExportDynamicVars(card, reasons),
            ["concrete_state"] = ExportCardConcreteState(card, cardIds, reasons),
        };
    }

    private static Dictionary<string, object?>? ExportCardConcreteState(
        CardModel card,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons)
    {
        switch (TypeName(card))
        {
            case "MegaCrit.Sts2.Core.Models.Cards.MadScience":
                RequireExactDeclaredInstanceFields(
                    card,
                    card.GetType(),
                    "card:MadScience",
                    reasons,
                    ("_tinkerTimeType", typeof(CardType)),
                    ("_tinkerTimeRider", ResolveRequiredGameType(
                        "MegaCrit.Sts2.Core.Models.Events.TinkerTime+RiderEffect",
                        reasons)),
                    ("_mockedChaosCard", typeof(CardModel)));
                var mocked = ReadField(card, "_mockedChaosCard") as CardModel;
                return new Dictionary<string, object?>
                {
                    ["tinker_time_type"] = StableValue(
                        ReadRequiredField(card, "_tinkerTimeType", typeof(CardType), reasons),
                        reasons,
                        "card:MadScience:tinker_time_type"),
                    ["tinker_time_rider"] = StableValue(
                        ReadField(card, "_tinkerTimeRider"),
                        reasons,
                        "card:MadScience:tinker_time_rider"),
                    ["mocked_chaos_card_instance_id"] = mocked == null
                        ? null
                        : ResolveCardIdentity(mocked, cardIds, reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Cards.Thrash":
                RequireExactDeclaredInstanceFields(
                    card,
                    card.GetType(),
                    "card:Thrash",
                    reasons,
                    ("_extraDamage", typeof(decimal)));
                return new Dictionary<string, object?>
                {
                    ["extra_damage"] = ReadRequiredField(card, "_extraDamage", typeof(decimal), reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Cards.Rampage":
                RequireExactDeclaredInstanceFields(
                    card,
                    card.GetType(),
                    "card:Rampage",
                    reasons,
                    ("_extraDamageFromPlays", typeof(decimal)));
                return new Dictionary<string, object?>
                {
                    ["extra_damage_from_plays"] = ReadRequiredField(
                        card,
                        "_extraDamageFromPlays",
                        typeof(decimal),
                        reasons),
                };
            default:
                return null;
        }
    }

    private static Dictionary<string, object?>? ExportEnergyCost(
        CardModel card,
        SortedSet<string> reasons)
    {
        var energyCost = card.EnergyCost;
        if (energyCost == null)
            return null;
        var canonical = ReadMember(energyCost, "Canonical");
        var costsX = ReadMember(energyCost, "CostsX");
        var baseCost = ReadField(energyCost, "_base");
        var localModifiers = ReadField(energyCost, "_localModifiers") as IEnumerable;
        if (canonical == null || costsX == null || baseCost == null || localModifiers == null)
        {
            reasons.Add($"energy_cost_not_exportable:{card.Id}");
            return null;
        }
        return new Dictionary<string, object?>
        {
            ["canonical"] = canonical,
            ["base"] = baseCost,
            ["resolved"] = energyCost.GetResolved(),
            ["costs_x"] = costsX,
            ["was_just_upgraded"] = ReadMember(energyCost, "WasJustUpgraded"),
            ["captured_x_value"] = Convert.ToBoolean(costsX)
                ? ReadMember(energyCost, "CapturedXValue")
                : null,
            ["local_modifiers"] = AsObjects(localModifiers).Select((modifier, index) =>
            {
                const string expectedType = "MegaCrit.Sts2.Core.Entities.Cards.LocalCostModifier";
                if (!string.Equals(TypeName(modifier), expectedType, StringComparison.Ordinal))
                    reasons.Add($"unregistered_local_cost_modifier_type:{TypeName(modifier)}");
                return new Dictionary<string, object?>
                {
                    ["index"] = index,
                    ["amount"] = ReadMember(modifier, "Amount"),
                    ["type"] = ReadMember(modifier, "Type")?.ToString(),
                    ["expiration"] = ReadMember(modifier, "Expiration")?.ToString(),
                    ["reduce_only"] = ReadMember(modifier, "IsReduceOnly"),
                };
            }).ToList(),
        };
    }

    private static List<Dictionary<string, object?>> ExportTemporaryStarCosts(
        CardModel card,
        SortedSet<string> reasons)
    {
        var costs = ReadField(card, "_temporaryStarCosts") as IEnumerable;
        if (costs == null)
        {
            reasons.Add($"temporary_star_costs_not_exportable:{card.Id}");
            return new List<Dictionary<string, object?>>();
        }
        return AsObjects(costs).Select((cost, index) =>
        {
            const string expectedType = "MegaCrit.Sts2.Core.Entities.Cards.TemporaryCardCost";
            if (!string.Equals(TypeName(cost), expectedType, StringComparison.Ordinal))
                reasons.Add($"unregistered_temporary_star_cost_type:{TypeName(cost)}");
            return new Dictionary<string, object?>
            {
                ["index"] = index,
                ["cost"] = ReadMember(cost, "Cost"),
                ["clears_when_turn_ends"] = ReadMember(cost, "ClearsWhenTurnEnds"),
                ["clears_when_card_is_played"] = ReadMember(cost, "ClearsWhenCardIsPlayed"),
            };
        }).ToList();
    }

    private static Dictionary<string, object?> ExportCreature(
        Creature creature,
        int index,
        object runRng,
        SortedSet<string> reasons)
    {
        var powers = creature.Powers.Select((power, powerIndex) =>
            ExportPower(power, powerIndex, reasons)).ToList();
        var monster = creature.Monster;
        return new Dictionary<string, object?>
        {
            ["index"] = index,
            ["combat_id"] = Convert.ToUInt64(creature.CombatId),
            ["side"] = creature.Side.ToString(),
            ["slot_name"] = creature.SlotName,
            ["hp"] = creature.CurrentHp,
            ["max_hp"] = creature.MaxHp,
            ["block"] = creature.Block,
            ["alive"] = creature.IsAlive,
            ["monster_max_hp_before_modification"] = creature.MonsterMaxHpBeforeModification,
            ["shows_infinite_hp"] = creature.ShowsInfiniteHp,
            ["player_net_id"] = creature.Player == null ? null : Convert.ToUInt64(creature.Player.NetId),
            ["monster"] = monster == null ? null : ExportMonster(monster, runRng, reasons),
            ["powers"] = powers,
        };
    }

    private static Dictionary<string, object?> ExportPower(
        PowerModel power,
        int index,
        SortedSet<string> reasons)
    {
        var internalData = ReadField(power, "_internalData");
        RegisterTypeOrFieldless(
            power,
            typeof(PowerModel),
            RegisteredPowerTypes,
            "power",
            reasons);
        var internalState = ExportPowerInternalState(power, internalData, reasons);
        return new Dictionary<string, object?>
        {
            ["index"] = index,
            ["type"] = TypeName(power),
            ["id"] = power.Id.ToString(),
            ["power_type"] = power.Type.ToString(),
            ["power_type_for_current_amount"] = power.TypeForCurrentAmount.ToString(),
            ["stack_type"] = power.StackType.ToString(),
            ["is_instanced"] = power.IsInstanced,
            ["is_visible"] = power.IsVisible,
            ["allow_negative"] = power.AllowNegative,
            ["amount"] = power.Amount,
            ["amount_on_turn_start"] = power.AmountOnTurnStart,
            ["display_amount"] = power.DisplayAmount,
            ["skip_next_duration_tick"] = power.SkipNextDurationTick,
            ["owner_id"] = power.Owner == null ? null : Convert.ToUInt64(power.Owner.CombatId),
            ["applier_id"] = power.Applier == null ? null : Convert.ToUInt64(power.Applier.CombatId),
            ["target_id"] = power.Target == null ? null : Convert.ToUInt64(power.Target.CombatId),
            ["should_scale_in_multiplayer"] = power.ShouldScaleInMultiplayer,
            ["owner_is_secondary_enemy"] = power.OwnerIsSecondaryEnemy,
            ["internal_data_is_null"] = internalData == null,
            ["internal_state"] = internalState,
            ["concrete_state"] = ExportPowerConcreteState(power, reasons),
            ["dynamic_vars"] = ExportDynamicVars(power, reasons),
        };
    }

    private static Dictionary<string, object?>? ExportPowerConcreteState(
        PowerModel power,
        SortedSet<string> reasons)
    {
        switch (TypeName(power))
        {
            case "MegaCrit.Sts2.Core.Models.Powers.FeedingFrenzyPower":
                RequireExactDeclaredInstanceFields(
                    power,
                    power.GetType(),
                    "power:FeedingFrenzyPower",
                    reasons);
                var temporaryStrengthType = ResolveRequiredGameType(
                    "MegaCrit.Sts2.Core.Models.Powers.TemporaryStrengthPower",
                    reasons);
                RequireExactDeclaredInstanceFields(
                    power,
                    temporaryStrengthType,
                    "power:TemporaryStrengthPower",
                    reasons,
                    ("_shouldIgnoreNextInstance", typeof(bool)));
                return new Dictionary<string, object?>
                {
                    ["should_ignore_next_instance"] = ReadRequiredField(
                        power,
                        "_shouldIgnoreNextInstance",
                        typeof(bool),
                        reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Powers.NemesisPower":
                RequireExactDeclaredInstanceFields(
                    power,
                    power.GetType(),
                    "power:NemesisPower",
                    reasons,
                    ("_shouldApplyIntangible", typeof(bool)));
                return new Dictionary<string, object?>
                {
                    ["should_apply_intangible"] = ReadRequiredField(
                        power,
                        "_shouldApplyIntangible",
                        typeof(bool),
                        reasons),
                };
            default:
                return null;
        }
    }

    private static Dictionary<string, object?>? ExportPowerInternalState(
        PowerModel power,
        object? internalData,
        SortedSet<string> reasons)
    {
        var powerType = TypeName(power);
        var expectedInternalType = powerType switch
        {
            "MegaCrit.Sts2.Core.Models.Powers.AdaptablePower" =>
                "MegaCrit.Sts2.Core.Models.Powers.AdaptablePower+Data",
            "MegaCrit.Sts2.Core.Models.Powers.DarkEmbracePower" =>
                "MegaCrit.Sts2.Core.Models.Powers.DarkEmbracePower+Data",
            "MegaCrit.Sts2.Core.Models.Powers.StranglePower" =>
                "MegaCrit.Sts2.Core.Models.Powers.StranglePower+Data",
            _ => null,
        };
        if (expectedInternalType == null)
        {
            if (internalData != null)
                reasons.Add($"power_internal_data_not_exportable:{powerType}");
            return null;
        }
        if (internalData == null || !string.Equals(TypeName(internalData), expectedInternalType, StringComparison.Ordinal))
        {
            reasons.Add($"registered_power_internal_data_shape_mismatch:{powerType}:{(internalData == null ? "null" : TypeName(internalData))}");
            return null;
        }
        switch (powerType)
        {
            case "MegaCrit.Sts2.Core.Models.Powers.AdaptablePower":
                return ExportExactPrimitiveFields(
                    internalData,
                    "power_internal:AdaptablePower",
                    reasons,
                    ("isReviving", "is_reviving", typeof(bool)));
            case "MegaCrit.Sts2.Core.Models.Powers.DarkEmbracePower":
                return ExportExactPrimitiveFields(
                    internalData,
                    "power_internal:DarkEmbracePower",
                    reasons,
                    ("etherealCount", "ethereal_count", typeof(int)));
            case "MegaCrit.Sts2.Core.Models.Powers.StranglePower":
                RequireExactDeclaredInstanceFields(
                    internalData,
                    internalData.GetType(),
                    "power_internal:StranglePower",
                    reasons,
                    ("amountsForPlayedCards", typeof(Dictionary<CardModel, int>)));
                var amounts = ReadField(internalData, "amountsForPlayedCards") as Dictionary<CardModel, int>;
                if (amounts == null)
                {
                    reasons.Add("strangle_power_amounts_not_exportable");
                    return null;
                }
                var combatState = power.Owner.CombatState;
                var runState = combatState?.RunState as RunState;
                if (combatState == null || runState == null)
                {
                    reasons.Add("strangle_power_combat_state_missing");
                    return null;
                }
                var cardIds = BuildCardIdentityMap(runState, combatState);
                var rows = amounts.Select(pair => new Dictionary<string, object?>
                    {
                        ["card_instance_id"] = ResolveCardIdentity(pair.Key, cardIds, reasons),
                        ["amount"] = pair.Value,
                    })
                    .OrderBy(row => row["card_instance_id"]?.ToString(), StringComparer.Ordinal)
                    .ToList();
                return new Dictionary<string, object?> { ["amounts_for_played_cards"] = rows };
            default:
                return null;
        }
    }

    private static Dictionary<string, object?> ExportMonster(
        MonsterModel monster,
        object runRng,
        SortedSet<string> reasons)
    {
        RegisterType(monster, RegisteredMonsterTypes, "monster", reasons);
        if (!ReferenceEquals(monster.RunRng, runRng))
            reasons.Add($"monster_run_rng_not_shared:{monster.Id}");
        var machine = monster.MoveStateMachine;
        if (machine == null)
        {
            reasons.Add($"monster_move_state_missing:{monster.Id}");
            return new Dictionary<string, object?>
            {
                ["id"] = monster.Id.ToString(),
                ["type"] = TypeName(monster),
            };
        }

        var states = new List<Dictionary<string, object?>>();
        var registeredStateInstances = new HashSet<object>(ReferenceEqualityComparer.Instance);
        foreach (var entry in machine.States)
        {
            registeredStateInstances.Add(entry.Value);
            states.Add(new Dictionary<string, object?>
            {
                ["key"] = entry.Key,
                ["state"] = ExportMoveState(entry.Value, monster, reasons, monster.Id.ToString()),
            });
        }
        if (!registeredStateInstances.Contains(monster.NextMove))
            reasons.Add($"monster_next_move_outside_state_machine:{monster.Id}");
        var stateLog = new List<object?>();
        foreach (var value in AsObjects(machine.StateLog))
        {
            var stateId = ReadMember(value, "StateId");
            var stable = StableValue(stateId, reasons, $"monster_state_log:{monster.Id}");
            if (stateId == null)
                reasons.Add($"monster_state_log_value_not_exportable:{TypeName(value)}");
            stateLog.Add(stable);
        }

        return new Dictionary<string, object?>
        {
            ["id"] = monster.Id.ToString(),
            ["type"] = TypeName(monster),
            ["rng"] = ExportRng(monster.Rng, reasons, $"monster_rng:{monster.Id}"),
            ["uses_run_rng"] = ReferenceEquals(monster.RunRng, runRng),
            ["next_move_id"] = StableValue(ReadMember(monster.NextMove, "Id"), reasons, $"monster_next_move:{monster.Id}"),
            ["spawned_this_turn"] = monster.SpawnedThisTurn,
            ["is_performing_move"] = monster.IsPerformingMove,
            ["concrete_state"] = ExportMonsterConcreteState(monster, reasons),
            ["current_state_id"] = MoveStateId(ReadField(machine, "_currentState"), reasons, $"monster_current_state:{monster.Id}"),
            ["initial_state_id"] = MoveStateId(ReadField(machine, "_initialState"), reasons, $"monster_initial_state:{monster.Id}"),
            ["performed_first_move"] = ReadField(machine, "_performedFirstMove"),
            ["states"] = states,
            ["state_log"] = stateLog,
        };
    }

    private static Dictionary<string, object?>? ExportMonsterConcreteState(
        MonsterModel monster,
        SortedSet<string> reasons)
    {
        switch (TypeName(monster))
        {
            case "MegaCrit.Sts2.Core.Models.Monsters.OwlMagistrate":
                RequireExactDeclaredInstanceFields(
                    monster,
                    monster.GetType(),
                    "monster:OwlMagistrate",
                    reasons,
                    ("_isFlying", typeof(bool)));
                return new Dictionary<string, object?>
                {
                    ["is_flying"] = ReadRequiredField(monster, "_isFlying", typeof(bool), reasons),
                };
            case "MegaCrit.Sts2.Core.Models.Monsters.TestSubject":
                RequireExactDeclaredInstanceFields(
                    monster,
                    monster.GetType(),
                    "monster:TestSubject",
                    reasons,
                    ("_deadState", typeof(MoveState)),
                    ("_respawns", typeof(int)),
                    ("_extraMultiClawCount", typeof(int)));
                var deadState = ReadField(monster, "_deadState");
                var matchingDeadStates = monster.MoveStateMachine?.States
                    .Where(entry => ReferenceEquals(entry.Value, deadState))
                    .Select(entry => entry.Key)
                    .ToList() ?? new List<string>();
                if (matchingDeadStates.Count != 1)
                    reasons.Add($"test_subject_dead_state_identity_mismatch:count={matchingDeadStates.Count}");
                ValidateTestSubjectMoveMachineShape(monster, reasons);
                return new Dictionary<string, object?>
                {
                    ["dead_state_id"] = matchingDeadStates.SingleOrDefault(),
                    ["respawns"] = ReadRequiredField(monster, "_respawns", typeof(int), reasons),
                    ["extra_multi_claw_count"] = ReadRequiredField(
                        monster,
                        "_extraMultiClawCount",
                        typeof(int),
                        reasons),
                };
            default:
                return null;
        }
    }

    private static void ValidateTestSubjectMoveMachineShape(
        MonsterModel monster,
        SortedSet<string> reasons)
    {
        var machine = monster.MoveStateMachine;
        if (machine == null)
        {
            reasons.Add("test_subject_move_machine_missing");
            return;
        }
        RequireExactDeclaredInstanceFields(
            machine,
            machine.GetType(),
            "move_machine:TestSubject",
            reasons,
            ("_currentState", typeof(MonsterState)),
            ("_initialState", typeof(MonsterState)),
            ("_performedFirstMove", typeof(bool)),
            ("<States>k__BackingField", typeof(Dictionary<string, MonsterState>)),
            ("<StateLog>k__BackingField", typeof(List<MonsterState>)));
        var expected = new (string Id, string Type, string? FollowUp, bool MustPerform, string Method)[]
        {
            ("RESPAWN_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "REVIVE_BRANCH", true, "RespawnMove"),
            ("BITE_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "SKULL_BASH_MOVE", false, "BiteMove"),
            ("SKULL_BASH_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "BITE_MOVE", false, "SkullBashMove"),
            ("MULTI_CLAW_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "MULTI_CLAW_MOVE", false, "MultiClawMove"),
            ("PHASE3_LACERATE_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "BIG_POUNCE_MOVE", false, "Phase3LacerateMove"),
            ("BIG_POUNCE_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "BURNING_GROWL_MOVE", false, "BigPounceMove"),
            ("BURNING_GROWL_MOVE", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.MoveState", "PHASE3_LACERATE_MOVE", false, "BurningGrowlMove"),
            ("REVIVE_BRANCH", "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.ConditionalBranchState", null, false, ""),
        };
        var actual = machine.States.ToList();
        if (actual.Count != expected.Length)
        {
            reasons.Add($"test_subject_move_machine_state_count_mismatch:{actual.Count}");
            return;
        }
        for (var index = 0; index < expected.Length; index++)
        {
            var expectedState = expected[index];
            var actualState = actual[index];
            var stateId = ReadMember(actualState.Value, "Id")?.ToString();
            var followUpState = ReadMember(actualState.Value, "FollowUpState");
            var followUpMatches = followUpState == null
                ? expectedState.FollowUp == null
                : expectedState.FollowUp != null
                  && machine.States.TryGetValue(expectedState.FollowUp, out var expectedFollowUp)
                  && ReferenceEquals(followUpState, expectedFollowUp);
            if (!string.Equals(actualState.Key, expectedState.Id, StringComparison.Ordinal)
                || !string.Equals(stateId, expectedState.Id, StringComparison.Ordinal)
                || !string.Equals(TypeName(actualState.Value), expectedState.Type, StringComparison.Ordinal)
                || !followUpMatches)
            {
                reasons.Add(
                    $"test_subject_move_machine_shape_mismatch:{index}:{actualState.Key}:{TypeName(actualState.Value)}:{MoveStateId(followUpState, reasons, $"test_subject_follow_up:{index}")}");
            }
            if (actualState.Value is MoveState moveState)
            {
                var mustPerform = ReadMember(moveState, "MustPerformOnceBeforeTransitioning");
                var onPerform = ReadField(moveState, "_onPerform") as Delegate;
                if (!Equals(mustPerform, expectedState.MustPerform)
                    || onPerform == null
                    || !ReferenceEquals(onPerform.Target, monster)
                    || onPerform.Method.DeclaringType != monster.GetType()
                    || !string.Equals(onPerform.Method.Name, expectedState.Method, StringComparison.Ordinal)
                    || onPerform.Method.IsStatic)
                {
                    reasons.Add(
                        $"test_subject_move_delegate_shape_mismatch:{index}:{actualState.Key}:{onPerform?.Method.DeclaringType?.FullName}:{onPerform?.Method.Name}");
                }
            }
        }
        var initialId = MoveStateId(ReadField(machine, "_initialState"), reasons, "test_subject_initial_state")?.ToString();
        if (!string.Equals(initialId, "BITE_MOVE", StringComparison.Ordinal))
            reasons.Add($"test_subject_initial_state_mismatch:{initialId}");
    }

    private static Dictionary<string, object?> ExportMoveState(
        object state,
        MonsterModel monster,
        SortedSet<string> reasons,
        string monsterId)
    {
        RegisterType(state, RegisteredMoveStateTypes, "move_state", reasons);
        if (string.Equals(
                TypeName(state),
                "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.ConditionalBranchState",
                StringComparison.Ordinal))
        {
            return ExportTestSubjectConditionalBranch(state, monster, reasons);
        }
        var intentsType = state.GetType().GetProperty("Intents", BindingFlags.Instance | BindingFlags.Public)?.PropertyType
            ?? typeof(object);
        RequireExactDeclaredInstanceFields(
            state,
            state.GetType(),
            $"move_state:{monsterId}:{ReadMember(state, "Id")}",
            reasons,
            ("_performedAtLeastOnce", typeof(bool)),
            ("_onPerform", typeof(Func<IReadOnlyList<Creature>, Task>)),
            ("<Intents>k__BackingField", intentsType),
            ("<StateId>k__BackingField", typeof(string)),
            ("<MustPerformOnceBeforeTransitioning>k__BackingField", typeof(bool)),
            ("<FollowUpStateId>k__BackingField", typeof(string)),
            ("<FollowUpState>k__BackingField", typeof(MonsterState)));
        var performed = ReadField(state, "_performedAtLeastOnce");
        if (performed == null)
            reasons.Add($"monster_move_state_field_missing:{monsterId}:{TypeName(state)}:_performedAtLeastOnce");
        return new Dictionary<string, object?>
        {
            ["type"] = TypeName(state),
            ["state_id"] = StableValue(ReadMember(state, "StateId"), reasons, $"move_state_id:{monsterId}"),
            ["move_id"] = StableValue(ReadMember(state, "Id"), reasons, $"move_id:{monsterId}"),
            ["performed_at_least_once"] = performed,
            ["must_perform_once"] = StableValue(ReadMember(state, "MustPerformOnceBeforeTransitioning"), reasons, $"move_must_perform:{monsterId}"),
            ["follow_up_state_id"] = StableValue(ReadMember(state, "FollowUpStateId"), reasons, $"move_follow_up:{monsterId}"),
            ["follow_up_state_reference_id"] = MoveStateId(
                ReadMember(state, "FollowUpState"),
                reasons,
                $"move_follow_up_reference:{monsterId}"),
            ["is_move"] = StableValue(ReadMember(state, "IsMove"), reasons, $"move_is_move:{monsterId}"),
        };
    }

    private static Dictionary<string, object?> ExportTestSubjectConditionalBranch(
        object state,
        MonsterModel monster,
        SortedSet<string> reasons)
    {
        const string conditionalTypeName =
            "MegaCrit.Sts2.Core.MonsterMoves.MonsterMoveStateMachine.ConditionalBranchState";
        const string branchTypeName = conditionalTypeName + "+ConditionalBranch";
        if (!string.Equals(
                TypeName(monster),
                "MegaCrit.Sts2.Core.Models.Monsters.TestSubject",
                StringComparison.Ordinal))
        {
            reasons.Add($"conditional_branch_monster_not_registered:{TypeName(monster)}");
        }
        var branchType = ResolveRequiredGameType(branchTypeName, reasons);
        var branchListType = typeof(List<>).MakeGenericType(branchType);
        RequireExactDeclaredInstanceFields(
            state,
            state.GetType(),
            "move_state:TestSubject:REVIVE_BRANCH",
            reasons,
            ("<BranchId>k__BackingField", typeof(string)),
            ("<States>k__BackingField", branchListType));
        var stateId = ReadMember(state, "Id")?.ToString();
        if (!string.Equals(stateId, "REVIVE_BRANCH", StringComparison.Ordinal))
            reasons.Add($"test_subject_conditional_branch_id_mismatch:{stateId}");
        var branches = AsObjects(ReadField(state, "<States>k__BackingField") as IEnumerable).ToList();
        var expectedIds = new[] { "MULTI_CLAW_MOVE", "PHASE3_LACERATE_MOVE" };
        var expectedMethods = new[]
        {
            "<GenerateMoveStateMachine>b__67_1",
            "<GenerateMoveStateMachine>b__67_2",
        };
        if (branches.Count != expectedIds.Length)
            reasons.Add($"test_subject_conditional_branch_count_mismatch:{branches.Count}");
        var respawnsValue = ReadRequiredField(monster, "_respawns", typeof(int), reasons);
        var respawns = respawnsValue is int value ? value : 0;
        var rows = new List<Dictionary<string, object?>>();
        for (var index = 0; index < branches.Count; index++)
        {
            var branch = branches[index];
            RequireExactDeclaredInstanceFields(
                branch,
                branchType,
                $"move_state:TestSubject:REVIVE_BRANCH:branch:{index}",
                reasons,
                ("id", typeof(string)),
                ("_conditionalLambda", typeof(Func<bool>)));
            var id = ReadField(branch, "id")?.ToString();
            if (index >= expectedIds.Length || !string.Equals(id, expectedIds[index], StringComparison.Ordinal))
                reasons.Add($"test_subject_conditional_branch_order_mismatch:{index}:{id}");
            var conditional = ReadField(branch, "_conditionalLambda") as Func<bool>;
            if (conditional == null)
            {
                reasons.Add($"test_subject_conditional_delegate_missing:{index}");
            }
            else
            {
                var method = conditional.Method;
                if (!ReferenceEquals(conditional.Target, monster)
                    || method.DeclaringType != monster.GetType()
                    || method.IsStatic
                    || method.ReturnType != typeof(bool)
                    || method.GetParameters().Length != 0
                    || index >= expectedMethods.Length
                    || !string.Equals(method.Name, expectedMethods[index], StringComparison.Ordinal)
                    || !method.IsDefined(typeof(CompilerGeneratedAttribute), inherit: false)
                    || !string.Equals(method.Module.ModuleVersionId.ToString("D"), ExpectedGameDllMvid, StringComparison.Ordinal))
                {
                    reasons.Add(
                        $"test_subject_conditional_delegate_shape_mismatch:{index}:{method.DeclaringType?.FullName}:{method.Name}:{(conditional.Target == null ? "null" : TypeName(conditional.Target))}");
                }
                var expectedValue = index == 0 ? respawns < 2 : respawns >= 2;
                if (conditional() != expectedValue)
                    reasons.Add($"test_subject_conditional_delegate_value_mismatch:{index}:{respawns}");
            }
            rows.Add(new Dictionary<string, object?>
            {
                ["index"] = index,
                ["target_state_id"] = id,
                ["condition"] = index == 0 ? "test_subject_respawns_lt_2" : "test_subject_respawns_gte_2",
                ["delegate_method"] = conditional?.Method.Name,
                ["delegate_metadata_token"] = conditional?.Method.MetadataToken,
                ["delegate_target"] = "current_test_subject",
                ["captured_respawns"] = respawns,
            });
        }
        return new Dictionary<string, object?>
        {
            ["type"] = TypeName(state),
            ["state_id"] = stateId,
            ["move_id"] = stateId,
            ["performed_at_least_once"] = null,
            ["must_perform_once"] = false,
            ["follow_up_state_id"] = null,
            ["is_move"] = false,
            ["branches"] = rows,
        };
    }

    private static List<Dictionary<string, object?>> ExportOrbs(
        IEnumerable? orbs,
        SortedSet<string> reasons)
    {
        var result = new List<Dictionary<string, object?>>();
        foreach (var orb in AsObjects(orbs))
        {
            reasons.Add($"unregistered_orb_type:{TypeName(orb)}");
            result.Add(new Dictionary<string, object?>
            {
                ["type"] = TypeName(orb),
                ["id"] = StableValue(ReadMember(orb, "Id"), reasons, $"orb_id:{TypeName(orb)}"),
                ["passive"] = StableValue(ReadMember(orb, "PassiveVal"), reasons, $"orb_passive:{TypeName(orb)}"),
                ["evoke"] = StableValue(ReadMember(orb, "EvokeVal"), reasons, $"orb_evoke:{TypeName(orb)}"),
            });
        }
        return result;
    }

    private static Dictionary<string, object?> ExportSynchronization(SortedSet<string> reasons)
    {
        var manager = RunManager.Instance;
        var queueSet = manager.ActionQueueSet;
        var executor = manager.ActionExecutor;
        var synchronizer = manager.ActionQueueSynchronizer;
        var choices = manager.PlayerChoiceSynchronizer;

        if (!queueSet.IsEmpty)
            reasons.Add("pending_action_queue");
        if (executor.IsRunning || executor.CurrentlyRunningAction != null)
            reasons.Add("running_action");
        RequireEmptyCollection(synchronizer, "_hookActions", "pending_hook_action", reasons);
        RequireEmptyCollection(
            synchronizer,
            "_requestedActionsWaitingForPlayerTurn",
            "pending_requested_action",
            reasons);
        RequireEmptyCollection(choices, "_receivedChoices", "pending_received_choice", reasons);

        return new Dictionary<string, object?>
        {
            ["next_action_id"] = Convert.ToUInt64(queueSet.NextActionId),
            ["next_hook_id"] = Convert.ToUInt64(synchronizer.NextHookId),
            ["action_synchronizer_combat_state"] = synchronizer.CombatState.ToString(),
            ["choice_ids"] = choices.ChoiceIds.Select(value => Convert.ToUInt64(value)).ToList(),
            ["next_checksum_id"] = manager.ChecksumTracker?.NextId,
            ["action_queue_empty"] = queueSet.IsEmpty,
            ["action_executor_running"] = executor.IsRunning,
        };
    }

    private static void ValidateStableBoundary(SortedSet<string> reasons)
    {
        var manager = CombatManager.Instance;
        if (!manager.IsPlayPhase)
            reasons.Add("not_player_play_phase");
        if (manager.IsEnemyTurnStarted
            || manager.EndingPlayerTurnPhaseOne
            || manager.EndingPlayerTurnPhaseTwo
            || manager.PlayerActionsDisabled
            || manager.IsPaused)
        {
            reasons.Add("combat_transition_in_progress");
        }
        RequireEmptyCollection(manager, "_playersReadyToEndTurn", "players_ready_to_end_turn", reasons);
        RequireEmptyCollection(
            manager,
            "_playersReadyToBeginEnemyTurn",
            "players_ready_for_enemy_turn",
            reasons);
        var pendingLoss = ReadField(manager, "_pendingLoss");
        if (pendingLoss is true)
            reasons.Add("pending_combat_loss");
    }

    private static Dictionary<string, object?> ExportRngSet(
        object? rngSet,
        IReadOnlyCollection<string> expectedMembers,
        IReadOnlyCollection<string> expectedRegistryKeys,
        SortedSet<string> reasons,
        string context)
    {
        var result = new Dictionary<string, object?>();
        if (rngSet == null)
        {
            reasons.Add($"rng_set_missing:{context}");
            return result;
        }
        const string rngTypeName = "MegaCrit.Sts2.Core.Random.Rng";
        var members = new List<(string SchemaName, Func<object?> Read)>();
        foreach (var property in rngSet.GetType().GetProperties(
                     BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
        {
            if (property.GetIndexParameters().Length == 0
                && string.Equals(property.PropertyType.FullName, rngTypeName, StringComparison.Ordinal))
            {
                members.Add(($"property:{property.Name}", () => property.GetValue(rngSet)));
            }
        }
        foreach (var field in GetAllFields(rngSet.GetType()))
        {
            if (string.Equals(field.FieldType.FullName, rngTypeName, StringComparison.Ordinal))
                members.Add(($"field:{field.Name}", () => field.GetValue(rngSet)));
        }

        var discovered = members.Select(member => member.SchemaName)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToList();
        var expected = expectedMembers.OrderBy(name => name, StringComparer.Ordinal).ToList();
        foreach (var missing in expected.Except(discovered, StringComparer.Ordinal))
            reasons.Add($"rng_member_missing:{context}:{missing}");
        foreach (var extra in discovered.Except(expected, StringComparer.Ordinal))
            reasons.Add($"rng_member_not_registered:{context}:{extra}");
        if (discovered.Count != discovered.Distinct(StringComparer.Ordinal).Count())
            reasons.Add($"rng_member_name_collision:{context}");

        foreach (var member in members.OrderBy(member => member.SchemaName, StringComparer.Ordinal))
            result[member.SchemaName] = ExportRng(
                member.Read(),
                reasons,
                $"{context}:{member.SchemaName}");
        result["registry"] = ExportRngRegistry(
            rngSet,
            expectedRegistryKeys,
            reasons,
            context);
        return result;
    }

    private static Dictionary<string, object?> ExportRngRegistry(
        object rngSet,
        IReadOnlyCollection<string> expectedKeys,
        SortedSet<string> reasons,
        string context)
    {
        var result = new Dictionary<string, object?>();
        var registry = ReadField(rngSet, "_rngs") as IEnumerable;
        if (registry == null)
        {
            reasons.Add($"rng_registry_missing:{context}");
            return result;
        }
        foreach (var entry in AsObjects(registry))
        {
            var key = ReadMember(entry, "Key")?.ToString();
            if (string.IsNullOrWhiteSpace(key))
            {
                reasons.Add($"rng_registry_key_not_exportable:{context}");
                continue;
            }
            if (result.ContainsKey(key))
            {
                reasons.Add($"rng_registry_key_collision:{context}:{key}");
                continue;
            }
            result[key] = ExportRng(
                ReadMember(entry, "Value"),
                reasons,
                $"{context}:registry:{key}");
        }
        var discovered = result.Keys.OrderBy(key => key, StringComparer.Ordinal).ToList();
        var expected = expectedKeys.OrderBy(key => key, StringComparer.Ordinal).ToList();
        foreach (var missing in expected.Except(discovered, StringComparer.Ordinal))
            reasons.Add($"rng_registry_key_missing:{context}:{missing}");
        foreach (var extra in discovered.Except(expected, StringComparer.Ordinal))
            reasons.Add($"rng_registry_key_not_registered:{context}:{extra}");
        return result;
    }

    private static Dictionary<string, object?>? ExportRng(
        object? rng,
        SortedSet<string> reasons,
        string context)
    {
        if (rng == null)
        {
            reasons.Add($"rng_missing:{context}");
            return null;
        }
        var seed = ReadMember(rng, "Seed");
        var counter = ReadMember(rng, "Counter");
        if (seed == null || counter == null)
            reasons.Add($"rng_state_not_exportable:{context}");
        return new Dictionary<string, object?>
        {
            ["seed"] = seed,
            ["counter"] = counter,
        };
    }

    private static Dictionary<string, object?>? ExportDynamicVars(
        object model,
        SortedSet<string> reasons)
    {
        var dynamicVars = ReadMember(model, "DynamicVars");
        var values = ReadMember(dynamicVars, "Values") as IEnumerable;
        if (values == null)
            return null;
        var result = new Dictionary<string, object?>();
        foreach (var value in values)
        {
            if (value == null)
                continue;
            var name = ReadMember(value, "Name")?.ToString();
            if (!string.IsNullOrWhiteSpace(name))
                result[name] = StableValue(
                    ReadMember(value, "BaseValue"),
                    reasons,
                    $"dynamic_var:{TypeName(model)}:{name}");
        }
        return result.Count == 0 ? null : result;
    }

    private static Dictionary<string, object?>? ExportSavedProperties(
        SavedProperties? props,
        SortedSet<string> reasons,
        string context)
    {
        if (props == null)
            return null;
        var result = new Dictionary<string, object?>();
        foreach (var groupName in new[] { "ints", "bools", "strings", "intArrays", "modelIds" })
        {
            var entries = ReadField(props, groupName) as IEnumerable;
            if (entries == null)
                continue;
            var rows = new List<Dictionary<string, object?>>();
            foreach (var entry in entries)
            {
                rows.Add(new Dictionary<string, object?>
                {
                    ["name"] = ReadMember(entry, "name")?.ToString(),
                    ["value"] = StableValue(
                        ReadMember(entry, "value"),
                        reasons,
                        $"saved_property:{context}:{groupName}"),
                });
            }
            if (rows.Count > 0)
                result[ToSnakeCase(groupName)] = rows.OrderBy(row => row["name"]?.ToString(), StringComparer.Ordinal).ToList();
        }

        foreach (var unsupportedGroup in new[] { "cards", "cardArrays" })
        {
            var entries = ReadField(props, unsupportedGroup) as IEnumerable;
            if (entries != null && entries.Cast<object?>().Any())
                reasons.Add($"saved_property_group_not_registered:{context}:{unsupportedGroup}");
        }
        return result.Count == 0 ? null : result;
    }

    private static string? ResolveCardIdentity(
        CardModel card,
        IReadOnlyDictionary<CardModel, string> cardIds,
        SortedSet<string> reasons)
    {
        if (cardIds.TryGetValue(card, out var identity))
            return identity;
        reasons.Add($"card_instance_outside_registered_piles:{card.Id}");
        return null;
    }

    private static void RegisterType(
        object model,
        HashSet<string> registered,
        string category,
        SortedSet<string> reasons)
    {
        var typeName = TypeName(model);
        if (!registered.Contains(typeName))
            reasons.Add($"unregistered_{category}_type:{typeName}");
    }

    private static void RegisterTypeOrFieldless(
        object model,
        Type fullyExportedBaseType,
        HashSet<string> registered,
        string category,
        SortedSet<string> reasons)
    {
        var concreteType = model.GetType();
        var typeName = TypeName(model);
        if (registered.Contains(typeName))
            return;
        if (!fullyExportedBaseType.IsAssignableFrom(concreteType))
        {
            reasons.Add($"unregistered_{category}_type:{typeName}");
            return;
        }

        var fields = new List<FieldInfo>();
        for (var current = concreteType;
             current != null && current != fullyExportedBaseType;
             current = current.BaseType)
        {
            fields.AddRange(current.GetFields(
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly));
        }
        if (fields.Count == 0)
            return;

        var fieldNames = fields
            .Select(field => $"{field.DeclaringType?.FullName}.{field.Name}")
            .OrderBy(name => name, StringComparer.Ordinal);
        reasons.Add($"field_bearing_{category}_type:{typeName}:{string.Join(",", fieldNames)}");
    }

    private static void RequireExactDeclaredInstanceFields(
        object model,
        Type declaringType,
        string context,
        SortedSet<string> reasons,
        params (string Name, Type FieldType)[] expectedFields)
    {
        if (!declaringType.IsAssignableFrom(model.GetType()))
        {
            reasons.Add($"declared_field_owner_type_mismatch:{context}:{TypeName(model)}");
            return;
        }
        var actual = declaringType.GetFields(
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
            .Select(field => (field.Name, field.FieldType))
            .OrderBy(field => field.Name, StringComparer.Ordinal)
            .ToList();
        var expected = expectedFields
            .OrderBy(field => field.Name, StringComparer.Ordinal)
            .ToList();
        if (actual.SequenceEqual(expected))
            return;
        reasons.Add(
            $"declared_instance_fields_not_registered:{context}:actual={string.Join(",", actual.Select(FieldDescriptor))}:expected={string.Join(",", expected.Select(FieldDescriptor))}");
    }

    private static string FieldDescriptor((string Name, Type FieldType) field)
    {
        return $"{field.Name}:{field.FieldType.FullName}";
    }

    private static object? ReadRequiredField(
        object owner,
        string fieldName,
        Type expectedType,
        SortedSet<string> reasons)
    {
        var field = FindField(owner.GetType(), fieldName);
        if (field == null || field.FieldType != expectedType)
        {
            reasons.Add($"required_field_type_mismatch:{TypeName(owner)}:{fieldName}:{expectedType.FullName}");
            return null;
        }
        var value = field.GetValue(owner);
        if (value == null && expectedType.IsValueType)
        {
            reasons.Add($"required_field_value_missing:{TypeName(owner)}:{fieldName}");
            return null;
        }
        return value;
    }

    private static Type ResolveRequiredGameType(string fullName, SortedSet<string> reasons)
    {
        var type = typeof(RunState).Assembly.GetType(fullName, throwOnError: false);
        if (type != null)
            return type;
        reasons.Add($"required_game_type_missing:{fullName}");
        return typeof(object);
    }

    private static void RequireEmptyCollection(
        object owner,
        string fieldName,
        string reason,
        SortedSet<string> reasons)
    {
        var field = FindField(owner.GetType(), fieldName);
        if (field == null)
        {
            reasons.Add($"required_field_unavailable:{TypeName(owner)}:{fieldName}");
            return;
        }
        var value = field.GetValue(owner);
        if (value == null)
            return;
        var count = ReadMember(value, "Count");
        if (count == null)
        {
            reasons.Add($"required_collection_count_unavailable:{TypeName(owner)}:{fieldName}");
            return;
        }
        if (Convert.ToInt32(count) != 0)
            reasons.Add(reason);
    }

    private static object? MoveStateId(
        object? state,
        SortedSet<string> reasons,
        string context)
    {
        return state == null
            ? null
            : StableValue(ReadMember(state, "StateId"), reasons, context);
    }

    private static IEnumerable<object> AsObjects(IEnumerable? values)
    {
        if (values == null)
            yield break;
        foreach (var value in values)
        {
            if (value != null)
                yield return value;
        }
    }

    private static object? StableValue(
        object? value,
        SortedSet<string> reasons,
        string context)
    {
        if (value == null)
            return null;
        var type = value.GetType();
        if (value is string or char or bool or byte or sbyte or short or ushort or int or uint or long or ulong
            or float or double or decimal)
            return value;
        if (type.IsEnum)
        {
            var underlying = Enum.GetUnderlyingType(type);
            object numeric = underlying == typeof(byte) || underlying == typeof(ushort)
                             || underlying == typeof(uint) || underlying == typeof(ulong)
                ? Convert.ToUInt64(value)
                : Convert.ToInt64(value);
            return new Dictionary<string, object?>
            {
                ["type"] = type.FullName,
                ["name"] = value.ToString(),
                ["numeric"] = numeric,
            };
        }
        if (value is Guid guid)
            return guid.ToString("D");
        if (value is ModelId modelId)
        {
            return new Dictionary<string, object?>
            {
                ["type"] = type.FullName,
                ["category"] = modelId.Category,
                ["entry"] = modelId.Entry,
                ["value"] = modelId.ToString(),
            };
        }
        if (value is Array array && array.Rank == 1)
            return array.Cast<object?>()
                .Select((item, index) => StableValue(item, reasons, $"{context}:{index}"))
                .ToList();
        if (value is IEnumerable enumerable
            && type.IsGenericType
            && type.GetGenericTypeDefinition() == typeof(List<>))
        {
            return enumerable.Cast<object?>()
                .Select((item, index) => StableValue(item, reasons, $"{context}:{index}"))
                .ToList();
        }
        reasons.Add($"value_type_not_registered:{context}:{TypeName(value)}");
        return null;
    }

    private static object? ReadMember(object? owner, string name)
    {
        if (owner == null)
            return null;
        var type = owner.GetType();
        var property = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        if (property != null)
            return property.GetValue(owner);
        var field = FindField(type, name);
        return field?.GetValue(owner);
    }

    private static object? ReadField(object owner, string name)
    {
        return FindField(owner.GetType(), name)?.GetValue(owner);
    }

    private static FieldInfo? FindField(Type type, string name)
    {
        for (var current = type; current != null; current = current.BaseType)
        {
            var field = current.GetField(
                name,
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
            if (field != null)
                return field;
        }
        return null;
    }

    private static IEnumerable<FieldInfo> GetAllFields(Type type)
    {
        for (var current = type; current != null; current = current.BaseType)
        {
            foreach (var field in current.GetFields(
                         BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
            {
                yield return field;
            }
        }
    }

    private static string CanonicalJson(object? value)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = false }))
            WriteCanonical(writer, value);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static void WriteCanonical(Utf8JsonWriter writer, object? value)
    {
        switch (value)
        {
            case null:
                writer.WriteNullValue();
                return;
            case string text:
                writer.WriteStringValue(text);
                return;
            case IDictionary<string, object?> dictionary:
                writer.WriteStartObject();
                foreach (var pair in dictionary.OrderBy(pair => pair.Key, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(pair.Key);
                    WriteCanonical(writer, pair.Value);
                }
                writer.WriteEndObject();
                return;
            case IEnumerable enumerable when value is not string:
                writer.WriteStartArray();
                foreach (var item in enumerable)
                    WriteCanonical(writer, item);
                writer.WriteEndArray();
                return;
            case bool boolean:
                writer.WriteBooleanValue(boolean);
                return;
            case byte number:
                writer.WriteNumberValue(number);
                return;
            case sbyte number:
                writer.WriteNumberValue(number);
                return;
            case short number:
                writer.WriteNumberValue(number);
                return;
            case ushort number:
                writer.WriteNumberValue(number);
                return;
            case int number:
                writer.WriteNumberValue(number);
                return;
            case uint number:
                writer.WriteNumberValue(number);
                return;
            case long number:
                writer.WriteNumberValue(number);
                return;
            case ulong number:
                writer.WriteNumberValue(number);
                return;
            case float number:
                writer.WriteNumberValue(number);
                return;
            case double number:
                writer.WriteNumberValue(number);
                return;
            case decimal number:
                writer.WriteNumberValue(number);
                return;
            case char character:
                writer.WriteStringValue(character.ToString());
                return;
            default:
                throw new InvalidOperationException(
                    $"Canonical JSON value type is not registered: {TypeName(value)}");
        }
    }

    private static string FileSha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static string Sha256(string value)
    {
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    }

    private static string TypeName(object value) => value.GetType().FullName ?? value.GetType().Name;

    private static string ToSnakeCase(string value)
    {
        var builder = new StringBuilder();
        foreach (var character in value)
        {
            if (char.IsUpper(character) && builder.Length > 0)
                builder.Append('_');
            builder.Append(char.ToLowerInvariant(character));
        }
        return builder.ToString();
    }
}
