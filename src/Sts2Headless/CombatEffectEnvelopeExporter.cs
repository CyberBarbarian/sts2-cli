using System.Reflection;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Runs;

namespace Sts2Headless;

/// <summary>
/// A fail-closed resource envelope for the locked Test Subject phase-two search.
/// This is intentionally not a general card-semantics layer.
/// </summary>
internal static class CombatEffectEnvelopeExporter
{
    private const string Schema = "combat_effect_envelope_v1";
    private const string TestSubjectType = "MegaCrit.Sts2.Core.Models.Monsters.TestSubject";
    private const int MaxAuditedHandCards = 10;
    private const int FutureStrengthDamageMultiplierUpperBound = 4;

    private sealed record EnergyFeasibleSubsetBounds(
        int KillDamageUpperBound,
        int BlockUpperBound,
        int TerminalHpUpperBound,
        int FeasibleSubsetCount,
        int ZeroLossKillSubsetCount,
        int ZeroLossBlockSubsetCount,
        IReadOnlyList<int?> RequiredCardTerminalHpUpperBounds,
        int EmptySubsetTerminalHpUpperBound);

    private static readonly HashSet<string> SupportedCardTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Cards.",
        "Anger", "BattleTrance", "Bloodletting", "DarkEmbrace",
        "DefendIronclad", "FeedingFrenzy", "FiendFire", "FightMe",
        "Headbutt", "IronWave", "MadScience", "Thrash");

    private static readonly HashSet<string> SupportedRelicTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Relics.",
        "BagOfPreparation", "BurningBlood", "CentennialPuzzle", "Crossbow",
        "EternalFeather", "Gorget", "JossPaper", "Kusarigama", "Nunchaku",
        "PaelsTears", "Pendulum", "PenNib", "PrecariousShears", "RainbowRing",
        "TuningFork", "WarPaint");

    private static readonly HashSet<string> SupportedPlayerPowerTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Powers.",
        "CrimsonMantlePower", "DarkEmbracePower", "DexterityPower",
        "FeedingFrenzyPower", "FeelNoPainPower", "FreeAttackPower",
        "ManglePower", "NoDrawPower", "PlatingPower", "SetupStrikePower",
        "StrengthPower", "ViciousPower", "VulnerablePower", "WeakPower");

    private static readonly HashSet<string> SupportedEnemyPowerTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Powers.",
        "AdaptablePower", "EnragePower", "PainfulStabsPower", "StranglePower",
        "StrengthPower", "VulnerablePower", "WeakPower");

    private static readonly HashSet<string> SupportedPotionTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Potions.", "BlockPotion", "FyshOil");

    private static readonly HashSet<string> SupportedDamageMultiplierTypes = new(StringComparer.Ordinal)
    {
        "MegaCrit.Sts2.Core.Models.Powers.VulnerablePower",
        "MegaCrit.Sts2.Core.Models.Powers.WeakPower",
        "MegaCrit.Sts2.Core.Models.Relics.PenNib",
    };

    private static readonly HashSet<string> FuturePlayerHealingCardTypes = PrefixTypes(
        "MegaCrit.Sts2.Core.Models.Cards.", "Feed", "NotYet");

    public static Dictionary<string, object?> Export(
        RunState? runState,
        IReadOnlyCollection<string> simulatorPendingReasons,
        Func<CardModel, int> cardInstanceId)
    {
        var reasons = new SortedSet<string>(simulatorPendingReasons, StringComparer.Ordinal);
        Dictionary<string, object?>? proof = null;
        try
        {
            proof = ProofStateExporter.Export(runState, simulatorPendingReasons);
            if (!Equals(proof.GetValueOrDefault("supported"), true))
            {
                foreach (var reason in proof.GetValueOrDefault("reasons") as IEnumerable<string>
                                       ?? Array.Empty<string>())
                    reasons.Add($"proof_state:{reason}");
                return Unsupported(proof, reasons);
            }

            if (runState == null)
            {
                reasons.Add("run_state_unavailable");
                return Unsupported(proof, reasons);
            }

            var combat = CombatManager.Instance.DebugOnlyGetState();
            if (combat == null)
            {
                reasons.Add("combat_state_unavailable");
                return Unsupported(proof, reasons);
            }

            var players = runState.Players.ToList();
            if (players.Count != 1 || players[0].Creature == null || players[0].PlayerCombatState == null)
            {
                reasons.Add($"expected_exactly_one_combat_player:{players.Count}");
                return Unsupported(proof, reasons);
            }
            var player = players[0];
            var playerCreature = player.Creature;
            var playerCombat = player.PlayerCombatState!;

            var enemies = combat.Enemies.Where(enemy => enemy != null && enemy.IsAlive).ToList();
            if (enemies.Count != 1 || !string.Equals(TypeName(enemies[0].Monster), TestSubjectType, StringComparison.Ordinal))
            {
                reasons.Add($"expected_one_live_test_subject:{enemies.Count}:{TypeName(enemies.SingleOrDefault()?.Monster)}");
                return Unsupported(proof, reasons);
            }
            var enemy = enemies[0];
            var monster = enemy.Monster!;
            var respawns = ReadIntField(monster, "_respawns", reasons, "test_subject_respawns");
            var extraMultiClaw = ReadIntField(monster, "_extraMultiClawCount", reasons, "test_subject_extra_multi_claw");
            if (respawns != 1)
                reasons.Add($"test_subject_not_phase2:{respawns}");
            if (!string.Equals(monster.NextMove?.Id, "MULTI_CLAW_MOVE", StringComparison.Ordinal))
                reasons.Add($"test_subject_next_move_not_multi_claw:{monster.NextMove?.Id}");

            ValidateClosure(player, playerCreature, enemy, playerCombat, reasons);
            if (reasons.Count > 0)
                return Unsupported(proof, reasons);

            var incoming = ExportIncoming(combat, playerCreature, enemy, monster, extraMultiClaw, reasons);
            var cards = new List<Dictionary<string, object?>>();
            foreach (var (card, index) in playerCombat.Hand.Cards.Select((card, index) => (card, index)))
            {
                ValidateCardVariant(card, reasons);
                if (reasons.Count > 0)
                    continue;
                var currentlyLegal = IsLegal(card, playerCombat);
                cards.Add(ExportCardEnvelope(
                    card,
                    index,
                    player,
                    playerCreature,
                    enemy,
                    cardInstanceId(card),
                    currentlyLegal,
                    reasons));
            }
            if (reasons.Count > 0)
                return Unsupported(proof, reasons);

            var turnCertificate = ExportTurnCertificate(
                player,
                playerCreature,
                enemy,
                incoming,
                cards,
                playerCombat.Energy);
            var staticPreviewDamageMultiplierUpperBound =
                StaticPreviewDamageMultiplierUpperBound(player);
            var result = new Dictionary<string, object?>
            {
                ["type"] = "combat_effect_envelope",
                ["schema"] = Schema,
                ["supported"] = true,
                ["scope"] = "locked_test_subject_phase2_current_hand",
                ["proof_state_token_sha256"] = proof.GetValueOrDefault("token_sha256"),
                ["closure"] = new Dictionary<string, object?>
                {
                    ["game_dll_sha256"] = ManifestValue(proof, "game_dll_sha256"),
                    ["game_dll_mvid"] = ManifestValue(proof, "game_dll_mvid"),
                    ["headless_dll_sha256"] = ManifestValue(proof, "headless_dll_sha256"),
                    ["whitelist_manifest_sha256"] = ManifestValue(proof, "whitelist_manifest_sha256"),
                    ["hit_count_modifiers"] = "audited_none",
                    ["hp_loss_redirectors"] = "audited_none",
                    ["in_combat_healing"] = "audited_none",
                    ["future_player_healing_sources"] = "audited_absent_locked_dll_v1",
                    ["future_strength_damage_multiplier_upper_bound"] = (
                        FutureStrengthDamageMultiplierUpperBound
                    ),
                    ["static_preview_damage_multiplier_upper_bound"] = (
                        staticPreviewDamageMultiplierUpperBound
                    ),
                    ["static_preview_damage_multiplier_contract"] = (
                        "engine_preview_plus_pen_nib_presence_v1"
                    ),
                    ["card_types"] = SupportedCardTypes.OrderBy(value => value, StringComparer.Ordinal).ToList(),
                },
                ["incoming"] = incoming,
                ["hand_cards"] = cards,
                ["legal_cards"] = cards.Where(CardCurrentlyLegal).ToList(),
                ["turn_terminal_hp_upper_bound"] = turnCertificate?.GetValueOrDefault("terminal_hp_upper_bound"),
                ["turn_legacy_v8_terminal_hp_upper_bound"] = (
                    turnCertificate?.GetValueOrDefault("legacy_v8_terminal_hp_upper_bound")
                ),
                ["turn_certificate"] = turnCertificate,
            };
            return result;
        }
        catch (Exception exception)
        {
            var root = exception is TargetInvocationException { InnerException: not null }
                ? exception.InnerException
                : exception;
            reasons.Add($"export_failure:{root!.GetType().FullName}:{root.Message}");
            return Unsupported(proof, reasons);
        }
    }

    private static Dictionary<string, object?> ExportIncoming(
        CombatState combat,
        Creature player,
        Creature enemy,
        MonsterModel monster,
        int extraMultiClaw,
        SortedSet<string> reasons)
    {
        var intents = monster.NextMove?.Intents?.ToList();
        if (intents == null || intents.Count != 1 || intents[0] is not AttackIntent attack)
        {
            reasons.Add($"multi_claw_attack_intent_shape_mismatch:{intents?.Count ?? 0}:{TypeName(intents?.SingleOrDefault())}");
            return new Dictionary<string, object?>();
        }
        var repeats = attack.Repeats;
        var expectedRepeats = checked(3 + extraMultiClaw);
        if (repeats != expectedRepeats || repeats <= 0)
            reasons.Add($"multi_claw_repeat_mismatch:{repeats}:{expectedRepeats}");
        var totalDamage = attack.GetTotalDamage(combat.PlayerCreatures.ToList(), enemy);
        if (repeats <= 0 || totalDamage % repeats != 0)
            reasons.Add($"multi_claw_total_not_divisible:{totalDamage}:{repeats}");
        var singleDamage = repeats > 0 ? totalDamage / repeats : 0;
        var plating = PowerAmount(player, "MegaCrit.Sts2.Core.Models.Powers.PlatingPower");
        var block = Convert.ToInt32(player.Block);
        var postBlockLoss = Math.Max(0, totalDamage - checked(block + plating));
        return new Dictionary<string, object?>
        {
            ["move_id"] = monster.NextMove?.Id,
            ["base_hits"] = 3,
            ["extra_hits"] = extraMultiClaw,
            ["intent_hits"] = repeats,
            ["execution_hits"] = repeats,
            ["single_damage"] = singleDamage,
            ["total_damage"] = totalDamage,
            ["player_block_now"] = block,
            ["pre_attack_plating_block"] = plating,
            ["hp_loss_after_current_and_plating_block"] = postBlockLoss,
        };
    }

    private static Dictionary<string, object?> ExportCardEnvelope(
        CardModel card,
        int handIndex,
        Player player,
        Creature playerCreature,
        Creature enemy,
        int instanceId,
        bool currentlyLegal,
        SortedSet<string> reasons)
    {
        var type = TypeName(card)!;
        var observedEnergyCost = card.EnergyCost?.GetAmountToSpend() ?? 0;
        var energyCostLowerBound = observedEnergyCost;
        if (card.Type == CardType.Attack && PowerAmount(
                playerCreature,
                "MegaCrit.Sts2.Core.Models.Powers.FreeAttackPower") > 0)
        {
            // The power may be consumed by an earlier Attack.  Treat every
            // current-hand Attack as free so this remains a lower bound for
            // every possible ordering.
            energyCostLowerBound = 0;
        }
        if (card.EnergyCost?.CostsX == true)
            reasons.Add($"unsupported_x_energy_cost:{type}");
        if (observedEnergyCost < 0)
            reasons.Add($"negative_energy_cost:{type}:{observedEnergyCost}");
        var preview = Preview(card, enemy, reasons);
        var damagePerHit = preview.GetValueOrDefault("Damage");
        var hits = type[(type.LastIndexOf('.') + 1)..] switch
        {
            "Anger" or "Headbutt" or "IronWave" or "MadScience" => 1,
            "FiendFire" => Math.Max(0, player.PlayerCombatState!.Hand.Cards.Count - 1),
            "FightMe" => VarInt(card, "Repeat", reasons),
            "Thrash" => 2,
            _ => 0,
        };
        var directDamage = checked(damagePerHit * hits);
        var exhaustOtherCards = type[(type.LastIndexOf('.') + 1)..] switch
        {
            // Fiend Fire snapshots the hand after it has moved to the play pile.
            "FiendFire" => Math.Max(0, player.PlayerCombatState!.Hand.Cards.Count - 1),
            "Thrash" when player.PlayerCombatState!.Hand.Cards.Any(
                other => !ReferenceEquals(other, card) && other.Type == CardType.Attack) => 1,
            _ => 0,
        };
        var exhaustTriggers = checked(
            exhaustOtherCards + (card.Keywords.Contains(CardKeyword.Exhaust) ? 1 : 0));

        var strangleDamage = PowerAmount(enemy, "MegaCrit.Sts2.Core.Models.Powers.StranglePower");
        var kusarigamaDamage = 0;
        // GainBlock clamps the engine-modified amount at zero.  The raw preview
        // may be negative under sufficiently negative Dexterity, so exporting it
        // directly would underestimate both the actual zero block and any later
        // positive Dexterity relaxation.
        var directBlock = Math.Max(0, preview.GetValueOrDefault("Block"));
        var tuningForkBlock = SkillRelicTrigger(
            player,
            card,
            "MegaCrit.Sts2.Core.Models.Relics.TuningFork",
            "_skillsPlayed",
            threshold: 10,
            amount: 7,
            reasons);
        var feelNoPainBlock = checked(exhaustTriggers * PowerAmount(
            playerCreature,
            "MegaCrit.Sts2.Core.Models.Powers.FeelNoPainPower"));

        var requestedDraw = type.EndsWith(".BattleTrance", StringComparison.Ordinal)
            ? VarInt(card, "Cards", reasons)
            : 0;
        requestedDraw += checked(exhaustTriggers * PowerAmount(
            playerCreature,
            "MegaCrit.Sts2.Core.Models.Powers.DarkEmbracePower"));
        requestedDraw += JossPaperDraw(player, exhaustTriggers, reasons);
        var selfLoss = type.EndsWith(".Bloodletting", StringComparison.Ordinal)
            ? VarInt(card, "HpLoss", reasons)
            : 0;
        requestedDraw += CentennialPuzzleDraw(player, selfLoss, reasons);
        var noDrawActive = PowerAmount(
            playerCreature,
            "MegaCrit.Sts2.Core.Models.Powers.NoDrawPower") > 0;
        var availableDrawCards = player.PlayerCombatState!.DrawPile.Cards.Count
                                 + player.PlayerCombatState.DiscardPile.Cards.Count;
        var drawUpperBound = noDrawActive ? 0 : Math.Min(requestedDraw, availableDrawCards);

        var energyGain = type.EndsWith(".Bloodletting", StringComparison.Ordinal)
            ? VarInt(card, "Energy", reasons)
            : 0;

        var playerStrength = type[(type.LastIndexOf('.') + 1)..] switch
        {
            "FeedingFrenzy" => VarInt(card, "StrengthPower", reasons),
            "FightMe" => VarInt(card, "StrengthPower", reasons),
            _ => 0,
        };
        var enemyStrength = type.EndsWith(".FightMe", StringComparison.Ordinal)
            ? VarInt(card, "EnemyStrength", reasons)
            : 0;
        enemyStrength += card.Type == CardType.Skill
            ? PowerAmount(enemy, "MegaCrit.Sts2.Core.Models.Powers.EnragePower")
            : 0;
        var rainbowDexterity = 0;

        var strangleApplied = type.EndsWith(".MadScience", StringComparison.Ordinal)
            ? VarInt(card, "ChokingDamage", reasons)
            : 0;
        var generatedToDiscard = type.EndsWith(".Anger", StringComparison.Ordinal) ? 1 : 0;
        var discardToDrawTop = type.EndsWith(".Headbutt", StringComparison.Ordinal)
                               && player.PlayerCombatState.DiscardPile.Cards.Count > 0
            ? 1
            : 0;
        var thrashGrowth = exhaustOtherCards > 0
            ? player.PlayerCombatState.Hand.Cards
                .Where(other => !ReferenceEquals(other, card) && other.Type == CardType.Attack)
                .Select(other => Preview(other, enemy, reasons).GetValueOrDefault("Damage"))
                .DefaultIfEmpty(0)
                .Max()
            : 0;

        return new Dictionary<string, object?>
        {
            ["hand_index"] = handIndex,
            ["instance_id"] = instanceId,
            ["id"] = card.Id.ToString(),
            ["concrete_type"] = type,
            ["card_type"] = card.Type.ToString(),
            ["gains_block"] = card.GainsBlock,
            ["upgrade_level"] = card.CurrentUpgradeLevel,
            ["currently_legal"] = currentlyLegal,
            ["energy_cost"] = observedEnergyCost,
            ["energy_cost_lower_bound"] = energyCostLowerBound,
            ["star_cost"] = card.CurrentStarCost,
            ["effects"] = new Dictionary<string, object?>
            {
                ["damage_per_hit_upper_bound"] = damagePerHit,
                ["card_damage_hits"] = hits,
                ["card_damage_upper_bound"] = directDamage,
                ["strangle_damage_upper_bound"] = strangleDamage,
                ["relic_damage_upper_bound"] = kusarigamaDamage,
                ["total_immediate_enemy_damage_upper_bound"] = checked(directDamage + strangleDamage + kusarigamaDamage),
                ["card_block_upper_bound"] = directBlock,
                ["block_upper_bound"] = checked(directBlock + tuningForkBlock + feelNoPainBlock),
                ["requested_draw_upper_bound"] = requestedDraw,
                ["draw_upper_bound"] = drawUpperBound,
                ["generated_directly_to_hand_upper_bound"] = 0,
                ["generated_to_discard_upper_bound"] = generatedToDiscard,
                ["discard_to_draw_top_upper_bound"] = discardToDrawTop,
                ["exhaust_other_card_upper_bound"] = exhaustOtherCards,
                ["exhaust_trigger_count_upper_bound"] = exhaustTriggers,
                ["persistent_card_damage_growth_upper_bound"] = thrashGrowth,
                ["energy_gain_upper_bound"] = energyGain,
                ["self_hp_loss_lower_bound"] = selfLoss,
                ["self_hp_loss_upper_bound"] = selfLoss,
                ["heal_upper_bound"] = 0,
                ["player_strength_gain_upper_bound"] = playerStrength,
                ["player_dexterity_gain_upper_bound"] = rainbowDexterity,
                ["enemy_strength_gain_lower_bound"] = enemyStrength,
                ["enemy_strength_gain_upper_bound"] = enemyStrength,
                ["enemy_strangle_gain_upper_bound"] = strangleApplied,
                ["player_weak_gain_upper_bound"] = 0,
                ["enemy_weak_gain_upper_bound"] = 0,
                ["player_vulnerable_gain_upper_bound"] = 0,
                ["enemy_vulnerable_gain_upper_bound"] = 0,
                ["player_intangible_gain_upper_bound"] = 0,
                ["enemy_intangible_gain_upper_bound"] = 0,
                ["player_buffer_gain_upper_bound"] = 0,
                ["enemy_buffer_gain_upper_bound"] = 0,
                ["player_no_draw_gain_upper_bound"] = type.EndsWith(".BattleTrance", StringComparison.Ordinal) ? 1 : 0,
                ["player_dark_embrace_gain_upper_bound"] = type.EndsWith(".DarkEmbrace", StringComparison.Ordinal) ? 1 : 0,
            },
        };
    }

    private static Dictionary<string, object?> ExportTurnCertificate(
        Player runPlayer,
        Creature player,
        Creature enemy,
        IReadOnlyDictionary<string, object?> incoming,
        IReadOnlyList<Dictionary<string, object?>> cards,
        int currentEnergy)
    {
        var noDrawActive = PowerAmount(
            player,
            "MegaCrit.Sts2.Core.Models.Powers.NoDrawPower") > 0;
        var noDirectHandGeneration = cards.All(card => Effect(card, "generated_directly_to_hand_upper_bound") == 0);
        var noHealing = cards.All(card => Effect(card, "heal_upper_bound") == 0);
        var result = new Dictionary<string, object?>
        {
            ["schema"] = "whole_turn_terminal_hp_upper_bound_v7",
            ["no_draw_active"] = noDrawActive,
            ["all_hand_cards_accounted"] = true,
            ["no_direct_generation_to_hand"] = noDirectHandGeneration,
            ["no_in_combat_healing"] = noHealing,
            ["resource_relaxation"] = "joint_terminal_hp_energy_feasible_current_hand_subset_v7",
            ["first_card_conditioning"] = (
                "selected_subset_contains_exact_currently_legal_card_instance_v1"
            ),
            ["end_turn_conditioning"] = "empty_selected_subset_v1",
            ["energy_cost_lower_bound_contract"] = "audited_no_future_cost_reduction_v1",
            ["energy_feasibility"] = "selected_cost_le_current_plus_selected_gain_upper_bound_v1",
            ["self_hp_loss_accounting"] = "per_selected_subset_lower_bound_v1",
            ["self_hp_loss_trigger_contract"] = (
                "redirectors_absent_centennial_draw_accounted_no_draw_required_v1"
            ),
            ["current_energy"] = currentEnergy,
            ["relic_energy_gain_upper_bound"] = null,
            ["optimistic_energy_gain_upper_bound"] = null,
            ["optimistic_energy_budget"] = null,
            ["energy_feasible_subset_count"] = null,
            ["zero_loss_kill_subset_count"] = null,
            ["zero_loss_block_subset_count"] = null,
            ["enemy_hp"] = enemy.CurrentHp,
            ["player_current_hp"] = player.CurrentHp,
            ["player_max_hp"] = player.MaxHp,
            ["independent_enemy_kill_damage_upper_bound"] = null,
            ["legacy_v8_independent_enemy_kill_damage_upper_bound"] = null,
            ["independent_optimistic_block_upper_bound"] = null,
            ["enemy_kill_damage_upper_bound"] = null,
            ["legacy_v8_enemy_kill_damage_upper_bound"] = null,
            ["optimistic_block_upper_bound"] = null,
            ["unavoidable_hp_loss_lower_bound"] = null,
            ["joint_terminal_hp_upper_bound"] = null,
            ["terminal_hp_upper_bound"] = null,
            ["legacy_v8_terminal_hp_upper_bound"] = null,
            ["first_card_terminal_hp_upper_bounds"] = null,
            ["end_turn_terminal_hp_upper_bound"] = null,
        };
        if (!noDrawActive || !noDirectHandGeneration || !noHealing)
            return result;
        if (currentEnergy < 0)
            throw new InvalidOperationException($"negative current combat energy:{currentEnergy}");
        if (cards.Count > MaxAuditedHandCards)
            throw new InvalidOperationException($"hand exceeds audited energy envelope:{cards.Count}");

        var attackCards = cards.Where(card => IsAttackCard(card)).ToList();
        var skillCount = cards.Count(card => IsSkillCard(card));
        var powerCount = cards.Count(card => IsPowerCard(card));
        var futureRainbow = RainbowRingGainUpperBound(
            runPlayer,
            attackCards.Count,
            skillCount,
            powerCount);
        var futureStrength = checked(
            cards.Sum(card => Effect(card, "player_strength_gain_upper_bound"))
            + futureRainbow);
        var staticPreviewDamageMultiplierUpperBound =
            StaticPreviewDamageMultiplierUpperBound(runPlayer);
        var directAttackUpperBound = attackCards.Sum(card => checked(
            checked(
                staticPreviewDamageMultiplierUpperBound
                * Math.Max(0, Effect(card, "damage_per_hit_upper_bound"))
                + FutureStrengthDamageMultiplierUpperBound * futureStrength)
            * Effect(card, "card_damage_hits")));
        var legacyV8DirectAttackUpperBound = attackCards.Sum(card => checked(
            FutureStrengthDamageMultiplierUpperBound
            * checked(Math.Max(0, Effect(card, "damage_per_hit_upper_bound")) + futureStrength)
            * Effect(card, "card_damage_hits")));
        var currentStrangle = PowerAmount(
            enemy,
            "MegaCrit.Sts2.Core.Models.Powers.StranglePower");
        var futureStrangle = cards.Sum(card => Effect(card, "enemy_strangle_gain_upper_bound"));
        var strangleUpperBound = checked(cards.Count * checked(currentStrangle + futureStrangle));
        var independentKillDamageUpperBound = checked(
            directAttackUpperBound
            + PeriodicAttackRelicUpperBound(
                runPlayer,
                "MegaCrit.Sts2.Core.Models.Relics.Kusarigama",
                "_attacksPlayedThisTurn",
                threshold: 3,
                amount: 6,
                attackCards.Count)
            + strangleUpperBound);
        var legacyV8IndependentKillDamageUpperBound = checked(
            legacyV8DirectAttackUpperBound
            + PeriodicAttackRelicUpperBound(
                runPlayer,
                "MegaCrit.Sts2.Core.Models.Relics.Kusarigama",
                "_attacksPlayedThisTurn",
                threshold: 3,
                amount: 6,
                attackCards.Count)
            + strangleUpperBound);

        var futureDexterity = checked(
            cards.Sum(card => Effect(card, "player_dexterity_gain_upper_bound"))
            + futureRainbow);
        var blockCardCount = cards.Count(card => GainsBlock(card));
        var exhaustCount = cards.Sum(card => Effect(card, "exhaust_trigger_count_upper_bound"));
        var feelNoPain = PowerAmount(
            player,
            "MegaCrit.Sts2.Core.Models.Powers.FeelNoPainPower");
        var independentOptimisticBlockUpperBound = checked(
            RequiredInt(incoming, "player_block_now")
            + RequiredInt(incoming, "pre_attack_plating_block")
            + cards.Sum(card => Effect(card, "block_upper_bound"))
            + checked(futureDexterity * blockCardCount)
            + checked(7 * skillCount)
            + checked(feelNoPain * exhaustCount));

        var relicEnergyGainUpperBound = PeriodicAttackRelicUpperBound(
            runPlayer,
            "MegaCrit.Sts2.Core.Models.Relics.Nunchaku",
            "_attacksPlayed",
            threshold: 10,
            amount: 1,
            attackCards.Count);
        var optimisticEnergyGain = checked(
            cards.Sum(card => NonNegativeEffect(card, "energy_gain_upper_bound"))
            + relicEnergyGainUpperBound);
        var optimisticEnergyBudget = checked(currentEnergy + optimisticEnergyGain);
        var energyFeasibleBounds = EvaluateEnergyFeasibleSubsets(
            cards,
            runPlayer,
            currentEnergy,
            incoming,
            currentStrangle,
            feelNoPain,
            staticPreviewDamageMultiplierUpperBound,
            enemy.CurrentHp,
            player.CurrentHp,
            player.MaxHp);
        var legacyV8EnergyFeasibleBounds = EvaluateEnergyFeasibleSubsets(
            cards,
            runPlayer,
            currentEnergy,
            incoming,
            currentStrangle,
            feelNoPain,
            FutureStrengthDamageMultiplierUpperBound,
            enemy.CurrentHp,
            player.CurrentHp,
            player.MaxHp);
        var energyFeasibleKillDamageUpperBound = (
            energyFeasibleBounds.KillDamageUpperBound
        );
        var legacyV8EnergyFeasibleKillDamageUpperBound = (
            legacyV8EnergyFeasibleBounds.KillDamageUpperBound
        );
        var energyFeasibleOptimisticBlockUpperBound = (
            energyFeasibleBounds.BlockUpperBound
        );
        if (energyFeasibleKillDamageUpperBound > independentKillDamageUpperBound)
            throw new InvalidOperationException("energy-feasible kill envelope exceeds independent envelope");
        if (energyFeasibleOptimisticBlockUpperBound > independentOptimisticBlockUpperBound)
            throw new InvalidOperationException("energy-feasible block envelope exceeds independent envelope");
        if (independentKillDamageUpperBound > legacyV8IndependentKillDamageUpperBound
            || energyFeasibleKillDamageUpperBound > legacyV8EnergyFeasibleKillDamageUpperBound)
        {
            throw new InvalidOperationException("tightened kill envelope exceeds legacy v8 envelope");
        }

        result["relic_energy_gain_upper_bound"] = relicEnergyGainUpperBound;
        result["optimistic_energy_gain_upper_bound"] = optimisticEnergyGain;
        result["optimistic_energy_budget"] = optimisticEnergyBudget;
        result["energy_feasible_subset_count"] = 1 << cards.Count;
        result["energy_feasible_accepted_subset_count"] = (
            energyFeasibleBounds.FeasibleSubsetCount
        );
        result["zero_loss_kill_subset_count"] = (
            energyFeasibleBounds.ZeroLossKillSubsetCount
        );
        result["zero_loss_block_subset_count"] = (
            energyFeasibleBounds.ZeroLossBlockSubsetCount
        );
        result["independent_enemy_kill_damage_upper_bound"] = independentKillDamageUpperBound;
        result["legacy_v8_independent_enemy_kill_damage_upper_bound"] = (
            legacyV8IndependentKillDamageUpperBound
        );
        result["independent_optimistic_block_upper_bound"] = independentOptimisticBlockUpperBound;
        result["enemy_kill_damage_upper_bound"] = energyFeasibleKillDamageUpperBound;
        result["legacy_v8_enemy_kill_damage_upper_bound"] = (
            legacyV8EnergyFeasibleKillDamageUpperBound
        );
        result["optimistic_block_upper_bound"] = energyFeasibleOptimisticBlockUpperBound;
        var jointTerminalHpUpperBound = energyFeasibleBounds.TerminalHpUpperBound;
        var jointUnavoidableLoss = Math.Max(
            0,
            player.CurrentHp - jointTerminalHpUpperBound);
        result["unavoidable_hp_loss_lower_bound"] = jointUnavoidableLoss;
        result["joint_terminal_hp_upper_bound"] = jointTerminalHpUpperBound;
        result["terminal_hp_upper_bound"] = jointTerminalHpUpperBound;
        result["first_card_terminal_hp_upper_bounds"] = cards
            .Select((card, index) => new Dictionary<string, object?>
            {
                ["hand_index"] = RequiredInt(card, "hand_index"),
                ["instance_id"] = card.GetValueOrDefault("instance_id"),
                ["currently_legal"] = CardCurrentlyLegal(card),
                ["terminal_hp_upper_bound"] = CardCurrentlyLegal(card)
                    ? energyFeasibleBounds.RequiredCardTerminalHpUpperBounds[index]
                    : null,
            })
            .ToList();
        result["end_turn_terminal_hp_upper_bound"] = (
            energyFeasibleBounds.EmptySubsetTerminalHpUpperBound
        );
        if (legacyV8EnergyFeasibleKillDamageUpperBound < enemy.CurrentHp)
        {
            var unavoidableLoss = Math.Max(
                0,
                RequiredInt(incoming, "total_damage") - energyFeasibleOptimisticBlockUpperBound);
            result["legacy_v8_terminal_hp_upper_bound"] = Math.Min(
                player.MaxHp,
                Math.Max(0, player.CurrentHp - unavoidableLoss));
        }
        return result;
    }

    private static EnergyFeasibleSubsetBounds EvaluateEnergyFeasibleSubsets(
        IReadOnlyList<Dictionary<string, object?>> cards,
        Player runPlayer,
        int currentEnergy,
        IReadOnlyDictionary<string, object?> incoming,
        int currentStrangle,
        int feelNoPain,
        int staticPreviewDamageMultiplierUpperBound,
        int enemyHp,
        int playerCurrentHp,
        int playerMaxHp)
    {
        var costs = cards.Select(card => RequiredInt(card, "energy_cost_lower_bound")).ToArray();
        if (costs.Any(cost => cost < 0))
            throw new InvalidOperationException("energy envelope contains a negative cost");
        var maximumDamage = 0;
        var maximumBlock = 0;
        var maximumTerminalHp = 0;
        var feasibleSubsetCount = 0;
        var zeroLossKillSubsetCount = 0;
        var zeroLossBlockSubsetCount = 0;
        var requiredCardTerminalHpUpperBounds = new int?[cards.Count];
        int? emptySubsetTerminalHpUpperBound = null;
        var incomingDamage = RequiredInt(incoming, "total_damage");
        var subsetCount = 1 << cards.Count;
        for (var mask = 0; mask < subsetCount; mask++)
        {
            var cost = 0;
            var energyGain = 0;
            var futureStrength = 0;
            var futureDexterity = 0;
            var futureStrangle = 0;
            var selectedCards = 0;
            var attackCards = 0;
            var blockCards = 0;
            var skillCards = 0;
            var powerCards = 0;
            var exhausts = 0;
            var directBlock = 0;
            var selfHpLoss = 0;
            for (var index = 0; index < cards.Count; index++)
            {
                if ((mask & (1 << index)) == 0)
                    continue;
                var card = cards[index];
                cost = checked(cost + costs[index]);
                energyGain = checked(energyGain + NonNegativeEffect(card, "energy_gain_upper_bound"));
                futureStrength = checked(futureStrength + Effect(card, "player_strength_gain_upper_bound"));
                futureDexterity = checked(futureDexterity + Effect(card, "player_dexterity_gain_upper_bound"));
                futureStrangle = checked(futureStrangle + Effect(card, "enemy_strangle_gain_upper_bound"));
                selectedCards++;
                if (IsAttackCard(card))
                    attackCards++;
                if (GainsBlock(card))
                    blockCards++;
                if (IsSkillCard(card))
                    skillCards++;
                if (IsPowerCard(card))
                    powerCards++;
                exhausts = checked(exhausts + Effect(card, "exhaust_trigger_count_upper_bound"));
                directBlock = checked(directBlock + Effect(card, "block_upper_bound"));
                selfHpLoss = checked(
                    selfHpLoss
                    + NonNegativeEffect(card, "self_hp_loss_lower_bound"));
            }
            energyGain = checked(
                energyGain
                + PeriodicAttackRelicUpperBound(
                    runPlayer,
                    "MegaCrit.Sts2.Core.Models.Relics.Nunchaku",
                    "_attacksPlayed",
                    threshold: 10,
                    amount: 1,
                    attackCards));
            if (cost > checked(currentEnergy + energyGain))
                continue;
            feasibleSubsetCount++;
            var futureRainbow = RainbowRingGainUpperBound(
                runPlayer,
                attackCards,
                skillCards,
                powerCards);
            futureStrength = checked(futureStrength + futureRainbow);
            futureDexterity = checked(futureDexterity + futureRainbow);
            var block = checked(
                RequiredInt(incoming, "player_block_now")
                + RequiredInt(incoming, "pre_attack_plating_block")
                + directBlock
                + checked(futureDexterity * blockCards)
                + checked(7 * skillCards)
                + checked(feelNoPain * exhausts));
            var damage = checked(
                selectedCards * checked(currentStrangle + futureStrangle)
                + PeriodicAttackRelicUpperBound(
                    runPlayer,
                    "MegaCrit.Sts2.Core.Models.Relics.Kusarigama",
                    "_attacksPlayedThisTurn",
                    threshold: 3,
                    amount: 6,
                    attackCards));
            for (var index = 0; index < cards.Count; index++)
            {
                if ((mask & (1 << index)) == 0)
                    continue;
                var card = cards[index];
                var hits = Effect(card, "card_damage_hits");
                if (hits <= 0)
                    continue;
                damage = checked(
                    damage
                    + checked(checked(
                        staticPreviewDamageMultiplierUpperBound
                        * Math.Max(0, Effect(card, "damage_per_hit_upper_bound"))
                        + FutureStrengthDamageMultiplierUpperBound * futureStrength) * hits)
                    + Effect(card, "relic_damage_upper_bound"));
            }
            var postSelfLossHp = Math.Max(0, playerCurrentHp - selfHpLoss);
            var incomingHpLoss = (
                damage >= enemyHp ? 0 : Math.Max(0, incomingDamage - block)
            );
            var terminalHp = Math.Min(
                playerMaxHp,
                Math.Max(0, postSelfLossHp - incomingHpLoss));
            maximumDamage = Math.Max(maximumDamage, damage);
            maximumBlock = Math.Max(maximumBlock, block);
            maximumTerminalHp = Math.Max(maximumTerminalHp, terminalHp);
            if (mask == 0)
                emptySubsetTerminalHpUpperBound = terminalHp;
            for (var index = 0; index < cards.Count; index++)
            {
                if ((mask & (1 << index)) == 0)
                    continue;
                requiredCardTerminalHpUpperBounds[index] = Math.Max(
                    requiredCardTerminalHpUpperBounds[index] ?? 0,
                    terminalHp);
            }
            zeroLossKillSubsetCount += (
                selfHpLoss == 0 && damage >= enemyHp ? 1 : 0
            );
            zeroLossBlockSubsetCount += (
                selfHpLoss == 0 && block >= incomingDamage ? 1 : 0
            );
        }
        return new EnergyFeasibleSubsetBounds(
            maximumDamage,
            maximumBlock,
            maximumTerminalHp,
            feasibleSubsetCount,
            zeroLossKillSubsetCount,
            zeroLossBlockSubsetCount,
            requiredCardTerminalHpUpperBounds,
            emptySubsetTerminalHpUpperBound
                ?? throw new InvalidOperationException("empty subset was not evaluated"));
    }

    private static bool CardCurrentlyLegal(IReadOnlyDictionary<string, object?> card)
    {
        return card.GetValueOrDefault("currently_legal") is true;
    }

    private static int StaticPreviewDamageMultiplierUpperBound(Player player)
    {
        return player.Relics.Any(relic => string.Equals(
            TypeName(relic),
            "MegaCrit.Sts2.Core.Models.Relics.PenNib",
            StringComparison.Ordinal))
            ? 2
            : 1;
    }

    private static bool IsAttackCard(IReadOnlyDictionary<string, object?> card)
    {
        return string.Equals(
            card.GetValueOrDefault("card_type")?.ToString(),
            CardType.Attack.ToString(),
            StringComparison.Ordinal);
    }

    private static bool IsSkillCard(IReadOnlyDictionary<string, object?> card)
    {
        return string.Equals(
            card.GetValueOrDefault("card_type")?.ToString(),
            CardType.Skill.ToString(),
            StringComparison.Ordinal);
    }

    private static bool IsPowerCard(IReadOnlyDictionary<string, object?> card)
    {
        return string.Equals(
            card.GetValueOrDefault("card_type")?.ToString(),
            CardType.Power.ToString(),
            StringComparison.Ordinal);
    }

    private static bool GainsBlock(IReadOnlyDictionary<string, object?> card)
    {
        return card.GetValueOrDefault("gains_block") is true;
    }

    private static int Effect(IReadOnlyDictionary<string, object?> card, string key)
    {
        if (card.GetValueOrDefault("effects") is not IReadOnlyDictionary<string, object?> effects)
            throw new InvalidOperationException($"card envelope effects missing:{card.GetValueOrDefault("instance_id")}");
        return RequiredInt(effects, key);
    }

    private static int NonNegativeEffect(
        IReadOnlyDictionary<string, object?> card,
        string key)
    {
        var value = Effect(card, key);
        if (value < 0)
            throw new InvalidOperationException($"effect envelope is negative:{key}:{value}");
        return value;
    }

    private static int RequiredInt(IReadOnlyDictionary<string, object?> values, string key)
    {
        if (!values.TryGetValue(key, out var value) || value == null)
            throw new InvalidOperationException($"effect envelope integer missing:{key}");
        return Convert.ToInt32(value);
    }

    private static void ValidateClosure(
        Player player,
        Creature playerCreature,
        Creature enemy,
        PlayerCombatState playerCombat,
        SortedSet<string> reasons)
    {
        ValidateTypes(player.Relics, SupportedRelicTypes, "relic", reasons);
        ValidateTypes(player.Potions.Where(potion => potion != null), SupportedPotionTypes, "potion", reasons);
        ValidateTypes(playerCreature.Powers, SupportedPlayerPowerTypes, "player_power", reasons);
        ValidateTypes(enemy.Powers, SupportedEnemyPowerTypes, "enemy_power", reasons);
        if (PowerAmount(
                playerCreature,
                "MegaCrit.Sts2.Core.Models.Powers.VulnerablePower") > 0)
        {
            reasons.Add("player_vulnerable_end_turn_timing_unproven");
        }
        foreach (var card in playerCombat.Hand.Cards)
        {
            var type = TypeName(card)!;
            if (!SupportedCardTypes.Contains(type))
                reasons.Add($"unsupported_hand_card_type:{type}");
            if (card.Enchantment != null)
                reasons.Add($"unsupported_hand_card_enchantment:{type}:{TypeName(card.Enchantment)}");
            if (card.Affliction != null)
                reasons.Add($"unsupported_hand_card_affliction:{type}:{TypeName(card.Affliction)}");
        }

        var futureCards = player.Deck.Cards
            .Concat(playerCombat.Hand.Cards)
            .Concat(playerCombat.DrawPile.Cards)
            .Concat(playerCombat.DiscardPile.Cards)
            .Concat(playerCombat.ExhaustPile.Cards)
            .Concat(playerCombat.PlayPile.Cards);
        foreach (var type in futureCards.Select(TypeName).Where(type => type != null).Distinct())
        {
            if (FuturePlayerHealingCardTypes.Contains(type!))
                reasons.Add($"future_player_healing_card:{type}");
        }

        foreach (var model in player.Relics.Cast<object>()
                     .Concat(playerCreature.Powers)
                     .Concat(enemy.Powers)
                     .Concat(playerCombat.Hand.Cards))
        {
            if (model.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
                .Any(method => string.Equals(method.Name, "ModifyAttackHitCount", StringComparison.Ordinal)))
            {
                reasons.Add($"active_hit_count_modifier:{TypeName(model)}");
            }
            if (model.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
                .Any(method => method.Name is "ModifyHpLost" or "ModifyHpLostAfterOsty"))
            {
                reasons.Add($"active_hp_loss_redirector:{TypeName(model)}");
            }
            if (model.GetType().GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
                    .Any(method => string.Equals(method.Name, "ModifyDamageMultiplicative", StringComparison.Ordinal))
                && !SupportedDamageMultiplierTypes.Contains(TypeName(model)!))
            {
                reasons.Add($"unsupported_damage_multiplier:{TypeName(model)}");
            }
        }
    }

    private static void ValidateCardVariant(CardModel card, SortedSet<string> reasons)
    {
        var type = TypeName(card)!;
        var allowedUpgrades = type.EndsWith(".DefendIronclad", StringComparison.Ordinal)
                              || type.EndsWith(".FeedingFrenzy", StringComparison.Ordinal)
                              || type.EndsWith(".FiendFire", StringComparison.Ordinal)
                              || type.EndsWith(".FightMe", StringComparison.Ordinal)
                              || type.EndsWith(".IronWave", StringComparison.Ordinal)
            ? new[] { 0, 1 }
            : type.EndsWith(".BattleTrance", StringComparison.Ordinal)
              || type.EndsWith(".Bloodletting", StringComparison.Ordinal)
                ? new[] { 1 }
                : new[] { 0 };
        if (!allowedUpgrades.Contains(card.CurrentUpgradeLevel))
            reasons.Add($"unsupported_card_upgrade:{type}:{card.CurrentUpgradeLevel}");

        var expectedVars = type[(type.LastIndexOf('.') + 1)..] switch
        {
            "Anger" => new[] { "Damage" },
            "BattleTrance" => new[] { "Cards" },
            "Bloodletting" => new[] { "Energy", "HpLoss" },
            "DarkEmbrace" => Array.Empty<string>(),
            "DefendIronclad" => new[] { "Block" },
            "FeedingFrenzy" => new[] { "StrengthPower" },
            "FiendFire" => new[] { "Damage" },
            "FightMe" => new[] { "Damage", "EnemyStrength", "Repeat", "StrengthPower" },
            "Headbutt" => new[] { "Damage" },
            "IronWave" => new[] { "Block", "Damage" },
            "MadScience" => new[]
            {
                "Block", "ChokingDamage", "CuriousReduction", "Damage",
                "EnergizedEnergy", "ExpertiseDexterity", "ExpertiseStrength",
                "SappingVulnerable", "SappingWeak", "ViolenceHits", "WisdomCards",
            },
            "Thrash" => new[] { "Damage" },
            _ => Array.Empty<string>(),
        };
        var actualVars = card.DynamicVars.Values.Select(value => value.Name)
            .OrderBy(value => value, StringComparer.Ordinal).ToList();
        if (!actualVars.SequenceEqual(expectedVars.OrderBy(value => value, StringComparer.Ordinal), StringComparer.Ordinal))
            reasons.Add($"unsupported_card_dynamic_vars:{type}:{string.Join(',', actualVars)}");

        if (type.EndsWith(".MadScience", StringComparison.Ordinal))
        {
            var cardType = ReadProperty(card, "TinkerTimeType")?.ToString();
            var rider = ReadProperty(card, "TinkerTimeRider")?.ToString();
            var mocked = ReadField(card, "_mockedChaosCard");
            if (!string.Equals(cardType, "Attack", StringComparison.Ordinal)
                || !string.Equals(rider, "Choking", StringComparison.Ordinal)
                || mocked != null)
            {
                reasons.Add($"unsupported_mad_science_variant:{cardType}:{rider}:{TypeName(mocked)}");
            }
        }
    }

    private static Dictionary<string, int> Preview(
        CardModel card,
        Creature target,
        SortedSet<string> reasons)
    {
        try
        {
            var dynamicVars = card.DynamicVars.Clone(card);
            dynamicVars.ClearPreview();
            card.UpdateDynamicVarPreview(CardPreviewMode.Normal, target, dynamicVars);
            var result = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var variable in dynamicVars.Values)
            {
                if (variable.PreviewValue != decimal.Truncate(variable.PreviewValue))
                    reasons.Add($"non_integral_preview:{card.Id}:{variable.Name}:{variable.PreviewValue}");
                result[variable.Name] = checked((int)variable.PreviewValue);
            }
            return result;
        }
        catch (Exception exception)
        {
            reasons.Add($"card_preview_failure:{card.Id}:{exception.GetType().FullName}:{exception.Message}");
            return new Dictionary<string, int>(StringComparer.Ordinal);
        }
    }

    private static bool IsLegal(CardModel card, PlayerCombatState combat)
    {
        return card.Type != CardType.None
               && card.CanPlay(out _, out _)
               && combat.Stars >= card.CurrentStarCost;
    }

    private static int VarInt(CardModel card, string name, SortedSet<string> reasons)
    {
        if (!card.DynamicVars.ContainsKey(name))
        {
            reasons.Add($"card_var_missing:{card.Id}:{name}");
            return 0;
        }
        var value = card.DynamicVars[name].BaseValue;
        if (value != decimal.Truncate(value))
            reasons.Add($"card_var_non_integral:{card.Id}:{name}:{value}");
        return checked((int)value);
    }

    private static int PowerAmount(Creature creature, string type)
    {
        return creature.Powers
            .Where(power => string.Equals(TypeName(power), type, StringComparison.Ordinal))
            .Sum(power => Math.Max(0, power.Amount));
    }

    private static int PeriodicAttackRelicUpperBound(
        Player player,
        string relicType,
        string counterField,
        int threshold,
        int amount,
        int attackCount)
    {
        if (attackCount <= 0)
            return 0;
        var relic = player.Relics.SingleOrDefault(value => string.Equals(TypeName(value), relicType, StringComparison.Ordinal));
        if (relic == null)
            return 0;
        var counter = RequiredIntField(relic, counterField, relicType);
        if (counter < 0 || threshold <= 0 || amount < 0)
            throw new InvalidOperationException($"invalid periodic relic counter:{relicType}:{counter}:{threshold}:{amount}");
        var triggerCount = checked(
            checked(counter + attackCount) / threshold - counter / threshold);
        return checked(triggerCount * amount);
    }

    private static int SkillRelicTrigger(
        Player player,
        CardModel card,
        string relicType,
        string counterField,
        int threshold,
        int amount,
        SortedSet<string> reasons)
    {
        if (card.Type != CardType.Skill)
            return 0;
        var relic = player.Relics.SingleOrDefault(value => string.Equals(TypeName(value), relicType, StringComparison.Ordinal));
        if (relic == null)
            return 0;
        var counter = ReadIntField(relic, counterField, reasons, relicType);
        return counter + 1 >= threshold ? amount : 0;
    }

    private static int JossPaperDraw(Player player, int exhausts, SortedSet<string> reasons)
    {
        if (exhausts <= 0)
            return 0;
        const string type = "MegaCrit.Sts2.Core.Models.Relics.JossPaper";
        var relic = player.Relics.SingleOrDefault(value => string.Equals(TypeName(value), type, StringComparison.Ordinal));
        if (relic == null)
            return 0;
        var counter = ReadIntField(relic, "_cardsExhausted", reasons, type);
        return (counter + exhausts) / 5;
    }

    private static int CentennialPuzzleDraw(Player player, int selfLoss, SortedSet<string> reasons)
    {
        if (selfLoss <= 0)
            return 0;
        const string type = "MegaCrit.Sts2.Core.Models.Relics.CentennialPuzzle";
        var relic = player.Relics.SingleOrDefault(value => string.Equals(TypeName(value), type, StringComparison.Ordinal));
        if (relic == null)
            return 0;
        var used = ReadBoolField(relic, "_usedThisCombat", reasons, type);
        return used ? 0 : 3;
    }

    private static int RainbowRingGainUpperBound(
        Player player,
        int selectedAttacks,
        int selectedSkills,
        int selectedPowers)
    {
        const string type = "MegaCrit.Sts2.Core.Models.Relics.RainbowRing";
        var relic = player.Relics.SingleOrDefault(value => string.Equals(TypeName(value), type, StringComparison.Ordinal));
        if (relic == null)
            return 0;
        var attacks = RequiredIntField(relic, "_attacksPlayedThisTurn", type);
        var skills = RequiredIntField(relic, "_skillsPlayedThisTurn", type);
        var powers = RequiredIntField(relic, "_powersPlayedThisTurn", type);
        var activations = RequiredIntField(relic, "_activationCountThisTurn", type);
        if (attacks < 0 || skills < 0 || powers < 0 || activations < 0)
            throw new InvalidOperationException($"invalid Rainbow Ring counters:{attacks}:{skills}:{powers}:{activations}");
        if (activations >= 1)
            return 0;
        return attacks + selectedAttacks > 0
               && skills + selectedSkills > 0
               && powers + selectedPowers > 0
            ? 1
            : 0;
    }

    private static void ValidateTypes<T>(
        IEnumerable<T> models,
        IReadOnlySet<string> supported,
        string category,
        SortedSet<string> reasons)
    {
        foreach (var model in models)
        {
            var type = TypeName(model)!;
            if (!supported.Contains(type))
                reasons.Add($"unsupported_{category}_type:{type}");
        }
    }

    private static int ReadIntField(object value, string name, SortedSet<string> reasons, string context)
    {
        var field = FindField(value.GetType(), name);
        if (field?.FieldType != typeof(int) || field.GetValue(value) is not int result)
        {
            reasons.Add($"int_field_not_exportable:{context}:{name}");
            return 0;
        }
        return result;
    }

    private static int RequiredIntField(object value, string name, string context)
    {
        var field = FindField(value.GetType(), name);
        if (field?.FieldType != typeof(int) || field.GetValue(value) is not int result)
            throw new InvalidOperationException($"int field not exportable:{context}:{name}");
        return result;
    }

    private static bool ReadBoolField(object value, string name, SortedSet<string> reasons, string context)
    {
        var field = FindField(value.GetType(), name);
        if (field?.FieldType != typeof(bool) || field.GetValue(value) is not bool result)
        {
            reasons.Add($"bool_field_not_exportable:{context}:{name}");
            return false;
        }
        return result;
    }

    private static object? ReadField(object value, string name) => FindField(value.GetType(), name)?.GetValue(value);

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

    private static object? ReadProperty(object value, string name)
    {
        return value.GetType().GetProperty(
            name,
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(value);
    }

    private static object? ManifestValue(Dictionary<string, object?> proof, string key)
    {
        return proof.GetValueOrDefault("manifest") is Dictionary<string, object?> manifest
            ? manifest.GetValueOrDefault(key)
            : null;
    }

    private static Dictionary<string, object?> Unsupported(
        Dictionary<string, object?>? proof,
        IEnumerable<string> reasons)
    {
        var result = new Dictionary<string, object?>
        {
            ["type"] = "combat_effect_envelope",
            ["schema"] = Schema,
            ["supported"] = false,
            ["reasons"] = reasons.Distinct(StringComparer.Ordinal).OrderBy(value => value, StringComparer.Ordinal).ToList(),
        };
        if (proof?.GetValueOrDefault("token_sha256") is string tokenSha)
            result["proof_state_token_sha256"] = tokenSha;
        return result;
    }

    private static HashSet<string> PrefixTypes(string prefix, params string[] names)
    {
        return names.Select(name => prefix + name).ToHashSet(StringComparer.Ordinal);
    }

    private static string? TypeName(object? value) => value?.GetType().FullName ?? value?.GetType().Name;
}
