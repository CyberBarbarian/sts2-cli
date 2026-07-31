namespace Sts2Headless;

/// <summary>
/// Bilingual localization lookup — loads eng/zhs JSON files for display names.
/// </summary>
internal class LocLookup
{
    private readonly Dictionary<string, Dictionary<string, string>> _eng = new();
    private readonly Dictionary<string, Dictionary<string, string>> _zhs = new();

    public LocLookup()
    {
        var baseDir = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..");
        Load(Path.Combine(baseDir, "localization_eng"), _eng);
        Load(Path.Combine(baseDir, "localization_zhs"), _zhs);
    }

    private static void Load(string dir, Dictionary<string, Dictionary<string, string>> target)
    {
        if (!Directory.Exists(dir))
            return;

        foreach (var file in Directory.GetFiles(dir, "*.json"))
        {
            try
            {
                var name = Path.GetFileNameWithoutExtension(file);
                var data = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, string>>(
                    File.ReadAllText(file)
                );
                if (data != null)
                    target[name] = data;
            }
            catch
            {
                // A malformed optional localization file should not prevent startup.
            }
        }
    }

    /// <summary>Get bilingual name: "English / 中文" or just the key if not found.</summary>
    public string Name(string table, string key)
    {
        var en = _eng.GetValueOrDefault(table)?.GetValueOrDefault(key);
        var zh = _zhs.GetValueOrDefault(table)?.GetValueOrDefault(key);
        if (en != null && zh != null && en != zh)
            return $"{en} / {zh}";
        return en ?? zh ?? key;
    }

    public string? En(string table, string key) =>
        _eng.GetValueOrDefault(table)?.GetValueOrDefault(key);

    public string? Zh(string table, string key) =>
        _zhs.GetValueOrDefault(table)?.GetValueOrDefault(key);

    /// <summary>Strip BBCode tags like [gold], [/blue], [b], [sine], etc.</summary>
    private static string StripBBCode(string text)
    {
        text = System.Text.RegularExpressions.Regex.Replace(
            text,
            @"\[/?[a-zA-Z_][a-zA-Z0-9_=]*\]",
            ""
        );
        return System.Text.RegularExpressions.Regex.Replace(
            text,
            @"#[A-Z](?=\{|[A-Za-z0-9])",
            ""
        );
    }

    /// <summary>Language for JSON output: "en" or "zh". Default: "en".</summary>
    public string Lang { get; set; } = "en";

    /// <summary>Return localized string for JSON output based on Lang setting.</summary>
    public string Bilingual(string table, string key)
    {
        if (Lang == "zh")
        {
            var zh = _zhs.GetValueOrDefault(table)?.GetValueOrDefault(key);
            if (zh != null)
                return StripBBCode(zh);
        }

        var en = _eng.GetValueOrDefault(table)?.GetValueOrDefault(key) ?? key;
        return StripBBCode(en);
    }

    public string Card(string entry) => Bilingual("cards", entry + ".title");

    public string Monster(string entry)
    {
        var key = entry + ".name";
        var result = Bilingual("monsters", key);
        if (result == key)
        {
            var lastUnderscore = entry.LastIndexOf('_');
            if (lastUnderscore > 0)
            {
                var baseEntry = entry[..lastUnderscore];
                var baseKey = baseEntry + ".name";
                var baseResult = Bilingual("monsters", baseKey);
                if (baseResult != baseKey)
                    return baseResult;
            }
        }
        return result;
    }

    public string Relic(string entry) => Bilingual("relics", entry + ".title");
    public string Potion(string entry) => Bilingual("potions", entry + ".title");
    public string Power(string entry) => PowerText(entry, ".title");
    public string PowerDescription(string entry) => PowerText(entry, ".description");
    public string Event(string entry) => Bilingual("events", entry + ".title");
    public string Act(string entry) => Bilingual("acts", entry + ".title");

    public string MonsterMove(string monsterEntry, string moveEntry)
    {
        foreach (var candidate in MonsterMoveKeyCandidates(moveEntry))
        {
            var titleKey = monsterEntry + ".moves." + candidate + ".title";
            var title = Bilingual("monsters", titleKey);
            if (title != titleKey)
                return title;

            var key = monsterEntry + ".moves." + candidate;
            var name = Bilingual("monsters", key);
            if (name != key)
                return name;
        }

        return HumanizeMoveEntry(moveEntry);
    }

    private static IEnumerable<string> MonsterMoveKeyCandidates(string moveEntry)
    {
        yield return moveEntry;
        if (moveEntry.EndsWith("_MOVE", StringComparison.Ordinal))
            yield return moveEntry[..^5];
    }

    private static string HumanizeMoveEntry(string moveEntry)
    {
        foreach (var candidate in MonsterMoveKeyCandidates(moveEntry).Reverse())
        {
            var words = candidate
                .Split('_', StringSplitOptions.RemoveEmptyEntries)
                .Select(word => word.Length == 0
                    ? word
                    : char.ToUpperInvariant(word[0]) + word[1..].ToLowerInvariant());
            var title = string.Join(" ", words);
            if (!string.IsNullOrWhiteSpace(title))
                return title;
        }

        return moveEntry;
    }

    private string PowerText(string entry, string suffix)
    {
        var powerKey = entry + suffix;
        var result = Bilingual("powers", powerKey);
        if (result != powerKey)
            return result;

        if (entry.EndsWith("_POTION_POWER", StringComparison.Ordinal))
        {
            var potionEntry = entry[..^"_POWER".Length];
            var potionKey = potionEntry + suffix;
            var potionResult = Bilingual("potions", potionKey);
            if (potionResult != potionKey)
                return potionResult;
        }

        if (entry.EndsWith("_POWER", StringComparison.Ordinal))
        {
            var cardEntry = entry[..^"_POWER".Length];
            var cardKey = cardEntry + (suffix == ".title" ? ".title" : ".description");
            var cardResult = Bilingual("cards", cardKey);
            if (cardResult != cardKey)
                return cardResult;
        }

        return result;
    }

    /// <summary>Resolve a full loc key like "TABLE.KEY.SUB" by searching all tables.</summary>
    public string BilingualFromKey(string locKey)
    {
        if (Lang == "zh")
        {
            foreach (var tableName in _zhs.Keys)
            {
                var zh = _zhs.GetValueOrDefault(tableName)?.GetValueOrDefault(locKey);
                if (zh != null)
                    return StripBBCode(zh);
            }
        }

        foreach (var tableName in _eng.Keys)
        {
            var en = _eng.GetValueOrDefault(tableName)?.GetValueOrDefault(locKey);
            if (en != null)
                return StripBBCode(en);
        }
        return locKey;
    }

    public IEnumerable<KeyValuePair<string, string>> Entries(string table)
    {
        var source = Lang == "zh" && _zhs.TryGetValue(table, out var zhsTable)
            ? zhsTable
            : _eng.GetValueOrDefault(table);
        if (source == null)
            yield break;

        foreach (var entry in source)
            yield return new KeyValuePair<string, string>(entry.Key, StripBBCode(entry.Value));
    }

    public bool IsLoaded => _eng.Count > 0;
}
