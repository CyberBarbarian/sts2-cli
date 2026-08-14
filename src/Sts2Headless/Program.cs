using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sts2Headless;

class Program
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    private static string? _directCombatTemplateCommand;
    private static string? _directCombatTemplateJson;
    private static int _directCombatTemplateActFloor;

    /// <summary>
    /// Locate the directory containing sts2.dll: STS2_LIB env, walk up from BaseDirectory, then BaseDirectory/lib.
    /// </summary>
    private static string ResolveLibDirectory()
    {
        var envLib = Environment.GetEnvironmentVariable("STS2_LIB");
        if (!string.IsNullOrWhiteSpace(envLib))
        {
            var p = Path.GetFullPath(envLib.Trim());
            if (Directory.Exists(p) && File.Exists(Path.Combine(p, "sts2.dll")))
                return p;
        }

        var dir = AppContext.BaseDirectory;
        for (var depth = 0; depth < 16 && !string.IsNullOrEmpty(dir); depth++)
        {
            var candidate = Path.Combine(dir, "lib");
            if (Directory.Exists(candidate) && File.Exists(Path.Combine(candidate, "sts2.dll")))
                return Path.GetFullPath(candidate);
            dir = Directory.GetParent(dir)?.FullName ?? "";
        }

        return Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "lib"));
    }

    static void Main(string[] args)
    {
        // Prevent unhandled exceptions from crashing the process
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            Console.Error.WriteLine($"[FATAL] Unhandled: {e.ExceptionObject}");
        };
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            Console.Error.WriteLine($"[WARN] Unobserved task exception: {e.Exception?.Message}");
            e.SetObserved();
        };

        var libDir = ResolveLibDirectory();

        AssemblyLoadContext.Default.Resolving += (ctx, name) =>
        {
            var path = Path.Combine(libDir, name.Name + ".dll");
            if (File.Exists(path))
                return ctx.LoadFromAssemblyPath(Path.GetFullPath(path));

            // Also check game directory (via STS2_GAME_DIR env var)
            var gameDir = Environment.GetEnvironmentVariable("STS2_GAME_DIR") ?? "";
            if (!string.IsNullOrEmpty(gameDir))
            {
                path = Path.Combine(gameDir, name.Name + ".dll");
                if (File.Exists(path))
                    return ctx.LoadFromAssemblyPath(path);
            }

            return null;
        };

        var sim = new RunSimulator();
        WriteLine(new Dictionary<string, object?> { ["type"] = "ready", ["version"] = "0.2.0" });

        string? line;
        while ((line = Console.ReadLine()) != null)
        {
            line = line.Trim();
            if (string.IsNullOrEmpty(line)) continue;

            Dictionary<string, object?>? result;
            try
            {
                var cmd = JsonSerializer.Deserialize<JsonElement>(line);
                result = HandleCommand(ref sim, cmd);
            }
            catch (JsonException ex)
            {
                result = new Dictionary<string, object?> { ["type"] = "error", ["message"] = $"Invalid JSON: {ex.Message}" };
            }
            catch (Exception ex)
            {
                result = new Dictionary<string, object?> { ["type"] = "error", ["message"] = $"{ex.GetType().Name}: {ex.Message}" };
            }

            if (result != null)
            {
                WriteLine(result);
                if (result.TryGetValue("type", out var resultTypeObj) &&
                    string.Equals(resultTypeObj as string, "quit_result", StringComparison.Ordinal))
                {
                    break;
                }
            }
        }
    }

    static Dictionary<string, object?>? HandleCommand(ref RunSimulator sim, JsonElement cmd)
    {
        var cmdType = cmd.GetProperty("cmd").GetString() ?? "";
        switch (cmdType)
        {
            case "proof_state_token":
                return sim.ProofStateToken();

            case "proof_state_compact_key":
                return sim.ProofStateCompactBossHistoryKey();

            case "runtime_stats":
            {
                var collect = cmd.TryGetProperty("collect", out var collectElement)
                    && collectElement.ValueKind == JsonValueKind.True;
                if (collect)
                {
                    GC.Collect();
                    GC.WaitForPendingFinalizers();
                    GC.Collect();
                }
                var memory = GC.GetGCMemoryInfo();
                return new Dictionary<string, object?>
                {
                    ["type"] = "runtime_stats",
                    ["collection_forced"] = collect,
                    ["managed_heap_bytes"] = GC.GetTotalMemory(forceFullCollection: false),
                    ["total_allocated_bytes"] = GC.GetTotalAllocatedBytes(precise: false),
                    ["heap_size_bytes"] = memory.HeapSizeBytes,
                    ["fragmented_bytes"] = memory.FragmentedBytes,
                    ["working_set_bytes"] = Environment.WorkingSet,
                    ["gen0_collections"] = GC.CollectionCount(0),
                    ["gen1_collections"] = GC.CollectionCount(1),
                    ["gen2_collections"] = GC.CollectionCount(2),
                };
            }

            case "reset":
                sim.CleanUp();
                sim = new RunSimulator();
                return new Dictionary<string, object?> { ["type"] = "reset_result", ["success"] = true };

            case "start_run":
                return sim.StartRun(
                    cmd.TryGetProperty("character", out var ch) ? ch.GetString() ?? "Ironclad" : "Ironclad",
                    cmd.TryGetProperty("ascension", out var asc) ? asc.GetInt32() : 0,
                    cmd.TryGetProperty("seed", out var s) ? s.GetString() : null,
                    cmd.TryGetProperty("lang", out var lang) ? lang.GetString() ?? "en" : "en"
                );

            case "start_combat":
            {
                if (!cmd.TryGetProperty("player", out var playerElement)
                    || playerElement.ValueKind != JsonValueKind.Object)
                {
                    return new Dictionary<string, object?>
                    {
                        ["type"] = "error",
                        ["message"] = "start_combat requires a player object",
                    };
                }
                List<(string Action, Dictionary<string, object?>? Args)>? actionTape = null;
                if (cmd.TryGetProperty("action_tape", out var actionTapeElement))
                {
                    var tapeError = ParseActionTape(actionTapeElement, out actionTape);
                    if (tapeError != null)
                        return tapeError;
                }
                var combatCharacterValue = cmd.TryGetProperty("character", out var combatCharacter)
                    ? combatCharacter.GetString() ?? "Ironclad"
                    : "Ironclad";
                var combatAscensionValue = cmd.TryGetProperty("ascension", out var combatAscension)
                    ? combatAscension.GetInt32()
                    : 0;
                var combatSeedValue = cmd.TryGetProperty("seed", out var combatSeed)
                    ? combatSeed.GetString()
                    : null;
                sim.CleanUp();
                sim = new RunSimulator();
                var observationModeValue = cmd.TryGetProperty("observation_mode", out var observationMode)
                    ? observationMode.GetString()
                    : null;
                sim.SetObservationMode(
                    observationModeValue);
                var combatLangValue = cmd.TryGetProperty("lang", out var combatLang)
                    ? combatLang.GetString() ?? "en"
                    : "en";
                var encounter = cmd.TryGetProperty("encounter", out var combatEncounter)
                    ? combatEncounter.GetString()
                    : null;
                var requestKey = string.Join(
                    "\0",
                    combatCharacterValue,
                    combatAscensionValue.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    combatSeedValue ?? "",
                    combatLangValue,
                    encounter ?? "",
                    observationModeValue ?? "",
                    playerElement.GetRawText());

                if (string.Equals(_directCombatTemplateCommand, requestKey, StringComparison.Ordinal)
                    && _directCombatTemplateJson != null)
                {
                    var restored = sim.RestoreDirectCombatTemplate(
                        _directCombatTemplateJson,
                        _directCombatTemplateActFloor,
                        combatLangValue);
                    if (!(restored.TryGetValue("type", out var restoredType)
                          && restoredType as string == "error"))
                    {
                        return EnterCombat(sim, encounter, actionTape);
                    }

                    _directCombatTemplateCommand = null;
                    _directCombatTemplateJson = null;
                    _directCombatTemplateActFloor = 0;
                    sim.CleanUp();
                    sim = new RunSimulator();
                    sim.SetObservationMode(observationModeValue);
                }

                var start = sim.StartRun(
                    combatCharacterValue,
                    combatAscensionValue,
                    combatSeedValue,
                    combatLangValue,
                    detectDecision: false);
                if (start.TryGetValue("type", out var startType) && startType as string == "error")
                    return start;
                var playerArgs = playerElement.EnumerateObject()
                    .ToDictionary(property => property.Name, property => property.Value);
                var configured = sim.SetPlayer(playerArgs, includeSummary: false);
                if (configured.TryGetValue("type", out var configuredType)
                    && configuredType as string == "error")
                    return configured;
                _directCombatTemplateJson = sim.CaptureDirectCombatTemplate();
                _directCombatTemplateActFloor = sim.CurrentActFloor;
                _directCombatTemplateCommand = requestKey;
                return EnterCombat(sim, encounter, actionTape);
            }

            case "action":
            {
                var action = cmd.GetProperty("action").GetString() ?? "";
                Dictionary<string, object?>? actionArgs = null;
                if (cmd.TryGetProperty("args", out var argsElem))
                {
                    actionArgs = new Dictionary<string, object?>();
                    foreach (var prop in argsElem.EnumerateObject())
                    {
                        actionArgs[prop.Name] = ConvertJsonValue(prop.Value);
                    }
                }
                return sim.ExecuteAction(action, actionArgs);
            }

            case "action_tape":
            {
                if (!cmd.TryGetProperty("actions", out var actionsElement))
                {
                    return new Dictionary<string, object?>
                    {
                        ["type"] = "error",
                        ["message"] = "action_tape requires an actions array",
                    };
                }
                var tapeError = ParseActionTape(actionsElement, out var tape);
                if (tapeError != null)
                    return tapeError;
                return sim.ExecuteActionTape(tape);
            }

            case "load_save":
            {
                var savePath = cmd.TryGetProperty("path", out var sp) ? sp.GetString() : null;
                var saveJson = cmd.TryGetProperty("json", out var sj) ? sj.GetString() : null;
                if (saveJson == null && savePath != null)
                {
                    if (!File.Exists(savePath))
                        return new Dictionary<string, object?> { ["type"] = "error", ["message"] = $"Save file not found: {savePath}" };
                    saveJson = File.ReadAllText(savePath);
                }
                if (saveJson == null)
                    return new Dictionary<string, object?> { ["type"] = "error", ["message"] = "Provide 'path' or 'json' for load_save" };
                var loadLang = cmd.TryGetProperty("lang", out var le) ? (le.GetString() ?? "en") : "en";
                return sim.LoadSave(saveJson, loadLang);
            }
            case "get_map":
                return sim.GetFullMap();

            case "audit_card_texts":
                return sim.AuditCardTexts(
                    cmd.TryGetProperty("lang", out var auditLang) ? auditLang.GetString() ?? "en" : "en"
                );

            case "set_player":
            {
                var args = new Dictionary<string, JsonElement>();
                foreach (var prop in cmd.EnumerateObject())
                    if (prop.Name != "cmd") args[prop.Name] = prop.Value;
                return sim.SetPlayer(args);
            }

            case "enter_room":
            {
                var roomType = cmd.TryGetProperty("type", out var rt) ? rt.GetString() ?? "" : "";
                var encounter = cmd.TryGetProperty("encounter", out var enc) ? enc.GetString() : null;
                var eventId = cmd.TryGetProperty("event", out var ev) ? ev.GetString() : null;
                return sim.EnterRoom(roomType, encounter, eventId);
            }

            case "set_draw_order":
            {
                var cards = new List<string>();
                if (cmd.TryGetProperty("cards", out var cardsArr))
                    foreach (var c in cardsArr.EnumerateArray())
                        cards.Add(c.GetString() ?? "");
                return sim.SetDrawOrder(cards);
            }

            case "debug_mark_ready_to_end_turn":
                return sim.DebugMarkReadyToEndTurn();

            case "debug_set_enemy_hp":
            {
                var args = new Dictionary<string, JsonElement>();
                foreach (var prop in cmd.EnumerateObject())
                    if (prop.Name != "cmd") args[prop.Name] = prop.Value;
                return sim.DebugSetEnemyHp(args);
            }

            case "write_continue_save":
            {
                var outputPath = cmd.TryGetProperty("path", out var op) ? op.GetString() : null;
                return sim.SaveCheckpoint(outputPath);
            }

            case "quit":
            {
                var outputPath = cmd.TryGetProperty("path", out var op) ? op.GetString() : null;
                if (!string.IsNullOrEmpty(outputPath))
                {
                    var saveResult = sim.SaveCheckpoint(outputPath);
                    bool saveOk = saveResult.TryGetValue("success", out var sObj) && sObj is bool b && b;
                    if (!saveOk)
                    {
                        // Save failed — do NOT clean up so the caller can retry with a different path.
                        return new Dictionary<string, object?>
                        {
                            ["type"] = "save_error",
                            ["save"] = saveResult,
                        };
                    }
                    sim.CleanUp();
                    return new Dictionary<string, object?>
                    {
                        ["type"] = "quit_result",
                        ["success"] = true,
                        ["save"] = saveResult,
                    };
                }
                sim.CleanUp();
                return new Dictionary<string, object?>
                {
                    ["type"] = "quit_result",
                    ["success"] = true,
                    ["save"] = null,
                };
            }

            default:
                return new Dictionary<string, object?> { ["type"] = "error", ["message"] = $"Unknown command: {cmdType}" };
        }
    }

    private static Dictionary<string, object?> EnterCombat(
        RunSimulator sim,
        string? encounter,
        IReadOnlyList<(string Action, Dictionary<string, object?>? Args)>? actionTape)
    {
        var state = sim.EnterRoom(
            "combat",
            encounter,
            null,
            detectDecision: actionTape == null);
        if (actionTape == null
            || state.GetValueOrDefault("type")?.ToString() == "error")
            return state;
        return sim.ExecuteActionTape(actionTape, allowUnexportedCombatPolicy: true);
    }

    private static Dictionary<string, object?>? ParseActionTape(
        JsonElement actionsElement,
        out List<(string Action, Dictionary<string, object?>? Args)> tape)
    {
        tape = new List<(string Action, Dictionary<string, object?>? Args)>();
        if (actionsElement.ValueKind != JsonValueKind.Array)
        {
            return new Dictionary<string, object?>
            {
                ["type"] = "error",
                ["message"] = "action_tape requires an actions array",
            };
        }
        foreach (var actionElement in actionsElement.EnumerateArray())
        {
            if (actionElement.ValueKind != JsonValueKind.Object
                || !actionElement.TryGetProperty("cmd", out var nestedCmd)
                || nestedCmd.GetString() != "action"
                || !actionElement.TryGetProperty("action", out var nestedAction))
            {
                return new Dictionary<string, object?>
                {
                    ["type"] = "error",
                    ["message"] = "action_tape accepts only action commands",
                };
            }
            Dictionary<string, object?>? actionArgs = null;
            if (actionElement.TryGetProperty("args", out var argsElement))
            {
                if (argsElement.ValueKind != JsonValueKind.Object)
                {
                    return new Dictionary<string, object?>
                    {
                        ["type"] = "error",
                        ["message"] = "action_tape action args must be an object",
                    };
                }
                actionArgs = argsElement.EnumerateObject().ToDictionary(
                    property => property.Name,
                    property => ConvertJsonValue(property.Value));
            }
            tape.Add((nestedAction.GetString() ?? "", actionArgs));
        }
        if (tape.Count == 0)
        {
            return new Dictionary<string, object?>
            {
                ["type"] = "error",
                ["message"] = "action_tape must contain at least one action",
            };
        }
        return null;
    }

    static object? ConvertJsonValue(JsonElement value)
    {
        return value.ValueKind switch
        {
            JsonValueKind.Number => value.TryGetInt32(out var intValue) ? (object)intValue : value.GetDouble(),
            JsonValueKind.String => value.GetString(),
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Null => null,
            JsonValueKind.Array => value.EnumerateArray().Select(ConvertJsonValue).ToList(),
            JsonValueKind.Object => value.EnumerateObject().ToDictionary(prop => prop.Name, prop => ConvertJsonValue(prop.Value)),
            _ => value.ToString(),
        };
    }

    static void WriteLine(Dictionary<string, object?> data)
    {
        Console.Out.WriteLine(JsonSerializer.Serialize(data, JsonOpts));
        Console.Out.Flush();
    }
}
