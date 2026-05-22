"""LLM-facing state compaction and prompt rendering."""

from __future__ import annotations

import json
from typing import Any


DROP_KEYS = {
    "enchantment_description",
    "affliction_description",
    "id",
    "option_id",
    "instance_id",
    "move_id",
    "draw_pile",
    "discard_pile",
    "exhaust_pile",
    "inactive_enemies",
    "full_map",
}

MAP_ICONS = {
    "Monster": "M",
    "Elite": "E",
    "Boss": "B",
    "RestSite": "R",
    "Shop": "$",
    "Treasure": "T",
    "Event": "?",
    "Unknown": "?",
    "Ancient": "A",
}


def name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("en", "name", "title", "id"):
            if value.get(key):
                return str(value[key])
        return "?"
    return str(value) if value is not None else "?"


def _compact_obj(obj: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    if depth > max_depth:
        return "..."
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key in DROP_KEYS:
                continue
            if key == "deck" and isinstance(value, list):
                out[key] = compact_deck(value)
                continue
            out[key] = _compact_obj(value, depth=depth + 1, max_depth=max_depth)
        return out
    if isinstance(obj, list):
        return [_compact_obj(item, depth=depth + 1, max_depth=max_depth) for item in obj]
    return obj


def compact_deck(deck: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, int], int] = {}
    examples: dict[tuple[str, int], dict[str, Any]] = {}
    for card in deck:
        card_name = name(card.get("name"))
        upgraded = int(card.get("upgrade_level", card.get("upgraded", 0)) or 0)
        key = (card_name, upgraded)
        counts[key] = counts.get(key, 0) + 1
        examples.setdefault(
            key,
            {
                "name": card_name,
                "upgraded": upgraded,
                "type": card.get("type"),
                "cost": card_cost_label(card),
            },
        )
    result = []
    for key, count in sorted(counts.items(), key=lambda item: (item[0][0], item[0][1])):
        item = dict(examples[key])
        item["count"] = count
        result.append(item)
    return result


def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-friendly state for logs and LLM prompts."""

    data = _compact_obj(state)
    viewed = []

    if state.get("view_deck"):
        player = state.get("player") or {}
        viewed.append("deck")
        data["viewed_deck"] = {
            "deck_size": player.get("deck_size"),
            "deck": compact_deck(player.get("deck") or []),
        }

    if state.get("view_map"):
        viewed.append("map")
        full_map = state.get("full_map")
        if isinstance(full_map, dict) and full_map.get("type") == "map":
            data["viewed_map"] = render_full_map(full_map, state.get("choices", []) or [])
        else:
            data["viewed_map_error"] = _compact_obj(state.get("view_map_error") or "Map view unavailable.")

    if viewed:
        data["viewed"] = viewed

    return data


def incoming_damage(state: dict[str, Any]) -> int:
    total = 0
    for enemy in state.get("enemies", []) or []:
        for intent in enemy.get("intents") or []:
            if intent.get("type") not in {"Attack", "DeathBlow"}:
                continue
            damage = intent.get("damage") or 0
            hits = intent.get("hits") or 1
            if isinstance(damage, (int, float)) and isinstance(hits, (int, float)):
                total += int(damage) * int(hits)
    return total


def card_cost_label(card: dict[str, Any]) -> Any:
    """Return the CLI-facing card cost, matching python/play.py fallback order."""

    return card.get("cost", card.get("energy_cost", "?"))


def card_line(card: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    stats = card.get("stats") or {}
    bits = [
        f"[{card.get('index', '?')}]",
        name(card.get("name")),
        f"cost={card_cost_label(card)}",
        str(card.get("type", "?")),
    ]
    if card.get("rarity"):
        bits.append(f"rarity={card.get('rarity')}")
    if card.get("upgraded") is not None:
        bits.append(f"upgraded={card.get('upgraded')}")
    if card.get("can_play") is not None:
        bits.append(f"can_play={card.get('can_play')}")
    for key in ("damage", "calculateddamage", "block", "magic", "draw"):
        value = stats.get(key)
        if value is not None:
            label = "damage" if key == "calculateddamage" else key
            bits.append(f"{label}={value}")
    for key in ("cards", "vulnerablepower", "weakpower", "strengthpower", "dexteritypower"):
        value = stats.get(key)
        if value is not None:
            bits.append(f"{key}={value}")
    if card.get("target_type"):
        bits.append(f"target={card.get('target_type')}")
    if card.get("star_cost"):
        bits.append(f"star_cost={card.get('star_cost')}")
    if card.get("enchantment"):
        bits.append(f"enchantment={name(card.get('enchantment'))}")
    if card.get("affliction"):
        bits.append(f"affliction={name(card.get('affliction'))}")
    keywords = card.get("keywords") or []
    if keywords:
        bits.append("keywords=" + ",".join(str(k) for k in keywords))
    return " ".join(bits)


def deck_card_line(card: dict[str, Any]) -> str:
    stats = card.get("stats") or {}
    bits = [
        name(card.get("name")),
        f"cost={card_cost_label(card)}",
        str(card.get("type", "?")),
    ]
    if card.get("rarity"):
        bits.append(f"rarity={card.get('rarity')}")
    if card.get("upgraded") is not None:
        bits.append(f"upgraded={card.get('upgraded')}")
    for key in ("damage", "calculateddamage", "block", "magic", "draw"):
        value = stats.get(key)
        if value is not None:
            label = "damage" if key == "calculateddamage" else key
            bits.append(f"{label}={value}")
    for key in ("cards", "vulnerablepower", "weakpower", "strengthpower", "dexteritypower"):
        value = stats.get(key)
        if value is not None:
            bits.append(f"{key}={value}")
    if card.get("target_type"):
        bits.append(f"target={card.get('target_type')}")
    if card.get("star_cost"):
        bits.append(f"star_cost={card.get('star_cost')}")
    keywords = card.get("keywords") or []
    if keywords:
        bits.append("keywords=" + ",".join(str(k) for k in keywords))
    return " ".join(bits)


def one_line(value: Any) -> str:
    if not value:
        return ""
    text = name(value) if isinstance(value, dict) else str(value)
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def description_of(obj: dict[str, Any]) -> str:
    """Return a one-line description if the simulator exported one."""

    description = obj.get("description")
    if not description:
        return ""
    return one_line(description)


def card_description(card: dict[str, Any]) -> str:
    return description_of(card)


def vars_line(obj: dict[str, Any]) -> str:
    vars_obj = obj.get("vars")
    if not vars_obj:
        return ""
    try:
        return json.dumps(vars_obj, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return str(vars_obj)


def append_hover_tip_lines(lines: list[str], obj: dict[str, Any], *, prefix: str = "  ") -> None:
    for tip in obj.get("hover_tips") or []:
        title = name(tip.get("name") or tip.get("title") or tip.get("id") or tip.get("kind"))
        desc = description_of(tip)
        if desc:
            lines.append(prefix + f"tip: {title}: {desc}")
        elif title and title != "?":
            lines.append(prefix + f"tip: {title}")


def _draw_conn(buf: list[str], from_col: int, to_col: int, width: int) -> None:
    """Draw a simple TUI-style connection between two map columns."""

    from_pos = from_col * width + width // 2
    to_pos = to_col * width + width // 2
    if from_pos == to_pos:
        if 0 <= from_pos < len(buf):
            buf[from_pos] = "|"
        return
    lo, hi = sorted((from_pos, to_pos))
    char = "/" if to_pos < from_pos else "\\"
    for pos in range(lo, hi + 1):
        if 0 <= pos < len(buf):
            buf[pos] = char


def map_display_choices(choices: list[dict[str, Any]], map_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Match ``python/play.py`` filtering of choices to visible map coords."""

    visible_coords: set[tuple[Any, Any]] = set()
    for row in (map_data or {}).get("rows", []):
        for node in row:
            visible_coords.add((node.get("col"), node.get("row")))

    boss = (map_data or {}).get("boss") or {}
    if "col" in boss and "row" in boss:
        visible_coords.add((boss.get("col"), boss.get("row")))

    if not visible_coords:
        return choices

    filtered = [
        choice
        for choice in choices
        if (choice.get("col"), choice.get("row")) in visible_coords
        or choice.get("type") == "Ancient"
    ]
    return filtered or choices


def render_full_map(map_data: dict[str, Any], choices: list[dict[str, Any]]) -> list[str]:
    """Render map as a text grid close to ``python/play.py``'s TUI map."""

    rows = map_data.get("rows") or []
    if not rows:
        return []

    visible_choices = map_display_choices(choices, map_data)
    choice_indices = {
        (choice.get("col"), choice.get("row")): idx
        for idx, choice in enumerate(visible_choices)
    }
    choice_nodes = {
        (choice.get("col"), choice.get("row")): choice
        for choice in visible_choices
    }

    node_map: dict[tuple[int, int], dict[str, Any]] = {}
    max_col = 0
    row_numbers: set[int] = set()
    for row in rows:
        for node in row:
            col = int(node.get("col", 0))
            row_number = int(node.get("row", 0))
            node_map[(col, row_number)] = node
            max_col = max(max_col, col)
            row_numbers.add(row_number)

    boss = map_data.get("boss") or {}
    if "col" in boss:
        max_col = max(max_col, int(boss.get("col", 0)))
    for col, _row in choice_indices:
        if isinstance(col, int):
            max_col = max(max_col, col)

    row_numbers_sorted = sorted(row_numbers)
    total_cols = max_col + 1
    cell_width = 4
    grid_width = cell_width * total_cols
    current = map_data.get("current_coord")
    out = ["Full map:"]

    if current and current.get("row", -1) not in row_numbers:
        out.append("  You are at the start")

    off_grid_choices = []
    for coord, choice_idx in choice_indices.items():
        col, row = coord
        boss_coord = (boss.get("col"), boss.get("row"))
        if coord not in node_map and coord != boss_coord:
            node = choice_nodes.get(coord, {"col": col, "row": row, "type": "?"})
            off_grid_choices.append((choice_idx, node))
    for choice_idx, node in sorted(off_grid_choices):
        out.append(f"  [{choice_idx}] {node.get('type', '?')}")

    boss_col = int(boss.get("col", 0))
    boss_row = boss.get("row", -1)
    boss_choice_idx = choice_indices.get((boss_col, boss_row))
    boss_buf = list(" " * grid_width)
    boss_center = boss_col * cell_width + cell_width // 2
    if 0 <= boss_center < len(boss_buf):
        boss_buf[boss_center] = "B"
    out.append(f"  B | {''.join(boss_buf)}")
    if boss_choice_idx is not None:
        ann = list(" " * grid_width)
        label = f"[{boss_choice_idx}]"
        start = boss_center - 1
        for offset, ch in enumerate(label):
            if 0 <= start + offset < len(ann):
                ann[start + offset] = ch
        out.append(f"    | {''.join(ann)}")

    if row_numbers_sorted:
        top_row = row_numbers_sorted[-1]
        conn = list(" " * grid_width)
        for row in rows:
            for node in row:
                if node.get("row") != top_row:
                    continue
                for child in node.get("children") or []:
                    if child.get("row") == boss_row:
                        _draw_conn(conn, int(node.get("col", 0)), int(child.get("col", 0)), cell_width)
        out.append(f"    | {''.join(conn)}")

    for idx in range(len(row_numbers_sorted) - 1, -1, -1):
        row_number = row_numbers_sorted[idx]
        node_buf = list(" " * grid_width)
        for col in range(total_cols):
            node = node_map.get((col, row_number))
            if not node:
                continue
            icon = MAP_ICONS.get(node.get("type", "?"), ".")
            center = col * cell_width + cell_width // 2
            is_current = bool(current and current.get("col") == col and current.get("row") == row_number)
            if is_current and center - 1 >= 0 and center + 1 < len(node_buf):
                node_buf[center - 1] = "["
                node_buf[center] = icon
                node_buf[center + 1] = "]"
            else:
                node_buf[center] = icon
        out.append(f"  {row_number:>2}| {''.join(node_buf)}")

        row_choices = {
            col: choice_indices[(col, row_number)]
            for col in range(total_cols)
            if (col, row_number) in choice_indices
        }
        if row_choices:
            ann = list(" " * grid_width)
            for col, choice_idx in row_choices.items():
                label = f"[{choice_idx}]"
                start = col * cell_width + cell_width // 2 - 1
                for offset, ch in enumerate(label):
                    if 0 <= start + offset < len(ann):
                        ann[start + offset] = ch
            out.append(f"    | {''.join(ann)}")

        if idx > 0:
            below_row = row_numbers_sorted[idx - 1]
            conn = list(" " * grid_width)
            for row in rows:
                for node in row:
                    if node.get("row") != below_row:
                        continue
                    for child in node.get("children") or []:
                        if child.get("row") == row_number:
                            _draw_conn(conn, int(node.get("col", 0)), int(child.get("col", 0)), cell_width)
            out.append(f"    | {''.join(conn)}")

    out.append("  Legend: M=Monster E=Elite R=Rest $=Shop T=Treasure ?=Event A=Ancient [x]=Current [n]=Choice")
    if choice_indices:
        parts = []
        inverse = {value: key for key, value in choice_indices.items()}
        for choice_idx in sorted(inverse):
            col, row = inverse[choice_idx]
            node = node_map.get((col, row))
            if not node and col == boss_col and row == boss_row:
                node = boss
            if not node:
                node = choice_nodes.get((col, row))
            if node:
                parts.append(f"{choice_idx}={node.get('type', '?')}")
        if parts:
            out.append("  Choices: " + " ".join(parts))
    return out


def append_card_lines(lines: list[str], card: dict[str, Any], *, prefix: str = "  ") -> None:
    lines.append(prefix + card_line(card))
    description = card_description(card)
    if description:
        lines.append(prefix + f"  description: {description}")
    for key in ("enchantment_description", "affliction_description"):
        value = one_line(card.get(key))
        if value:
            lines.append(prefix + f"  {key}: {value}")
    after = card.get("after_upgrade")
    if isinstance(after, dict):
        upgrade_parts = []
        old_cost = card_cost_label(card)
        new_cost = card_cost_label(after)
        if new_cost != "?" and new_cost != old_cost:
            upgrade_parts.append(f"cost {old_cost} -> {new_cost}")
        stats = card.get("stats") or {}
        after_stats = after.get("stats") or {}
        for key in sorted(set(stats) | set(after_stats)):
            if key.endswith("_by_target"):
                continue
            old = stats.get(key)
            new = after_stats.get(key, old)
            if old != new and not isinstance(old, (dict, list)) and not isinstance(new, (dict, list)):
                upgrade_parts.append(f"{key} {old} -> {new}")
        after_desc = card_description(after)
        if upgrade_parts:
            lines.append(prefix + "  upgrade: " + "; ".join(upgrade_parts))
        if after_desc:
            lines.append(prefix + f"  upgrade_description: {after_desc}")
    append_hover_tip_lines(lines, card, prefix=prefix + "  ")


def append_deck_view(lines: list[str], player: dict[str, Any]) -> None:
    deck = player.get("deck") or []
    lines.append(f"Deck view ({len(deck)} entries, deck_size={player.get('deck_size', '?')}):")
    if not deck:
        lines.append("  No deck details available in this state.")
        return
    for card in deck:
        count = card.get("count")
        suffix = f" x{count}" if count else ""
        lines.append(f"  {deck_card_line(card)}{suffix}")
        desc = card_description(card)
        if desc:
            lines.append(f"    description: {desc}")


def append_viewed_information(lines: list[str], state: dict[str, Any], player: dict[str, Any]) -> None:
    if not (state.get("view_deck") or state.get("view_map")):
        return

    lines.append("")
    lines.append("Viewed information:")
    if state.get("view_deck"):
        lines.append("Viewed deck:")
        append_deck_view(lines, player)

    if state.get("view_map"):
        lines.append("Viewed map:")
        full_map = state.get("full_map")
        if isinstance(full_map, dict) and full_map.get("type") == "map":
            lines.extend(render_full_map(full_map, state.get("choices", []) or []))
        elif state.get("view_map_error"):
            lines.append(f"  Map view unavailable: {state.get('view_map_error')}")
        else:
            lines.append("  Map view unavailable.")


def player_summary(player: dict[str, Any]) -> str:
    if not player:
        return "unknown player"
    parts = [
        f"hp={player.get('hp', '?')}/{player.get('max_hp', '?')}",
        f"block={player.get('block', 0)}",
        f"gold={player.get('gold', '?')}",
        f"deck_size={player.get('deck_size', '?')}",
    ]
    relics = [name(relic.get("name")) for relic in player.get("relics", []) or [] if relic]
    potions = [f"{pot.get('index', pot.get('slot_index', '?'))}:{name(pot.get('name'))}" for pot in player.get("potions", []) or [] if pot]
    if relics:
        parts.append("relics=" + ", ".join(relics[:12]) + (f" (+{len(relics) - 12})" if len(relics) > 12 else ""))
    if potions:
        parts.append("potions=" + ", ".join(potions))
    return " | ".join(parts)


def append_player_details(lines: list[str], player: dict[str, Any]) -> None:
    """Render player details like the TUI's ``show_player``.

    Keep this intentionally close to ``python/play.py``: show relics and
    potions, but do not expand the full deck in ordinary decision prompts.
    Full deck expansion is available from the raw/compact JSON, but putting it
    in the human-readable section makes it too easy to confuse deck cards with
    the current hand.
    """

    relics = [relic for relic in player.get("relics", []) or [] if relic]
    if relics:
        lines.append(f"Relics ({len(relics)}):")
        for relic in relics:
            bits = [name(relic.get("name"))]
            vars_text = vars_line(relic)
            if vars_text:
                bits.append(f"vars={vars_text}")
            if relic.get("show_counter") is not None:
                bits.append(f"show_counter={relic.get('show_counter')}")
            lines.append("  " + " ".join(bits))
            desc = description_of(relic)
            if desc:
                lines.append(f"    description: {desc}")

    potions = [potion for potion in player.get("potions", []) or [] if potion]
    if potions or player.get("potion_slots") is not None:
        slots = player.get("potion_slots", "?")
        empty = player.get("potion_empty_slots", "?")
        lines.append(f"Potions ({len(potions)}/{slots}, empty={empty}):")
        for potion in potions:
            idx = potion.get("index", potion.get("slot_index", "?"))
            bits = [f"[{idx}]", name(potion.get("name"))]
            if potion.get("target_type"):
                bits.append(f"target={potion.get('target_type')}")
            vars_text = vars_line(potion)
            if vars_text:
                bits.append(f"vars={vars_text}")
            lines.append("  " + " ".join(bits))
            desc = description_of(potion)
            if desc:
                lines.append(f"    description: {desc}")


def render_state_text(state: dict[str, Any]) -> str:
    """Render a concise, stable text view inspired by ``python/play.py``."""

    decision = state.get("decision", state.get("type", "?"))
    context = state.get("context") or {}
    player = state.get("player") or {}

    lines = [
        f"Decision: {decision}",
        f"Context: act={context.get('act', state.get('act', '?'))} floor={context.get('floor', state.get('floor', '?'))} room={context.get('room_type', '?')} boss={name((context.get('boss') or {}).get('name'))}",
        f"Player: {player_summary(player)}",
    ]
    append_player_details(lines, player)

    if decision == "combat_play":
        lines.append(
            f"Combat: round={state.get('round', '?')} energy={state.get('energy', '?')}/{state.get('max_energy', '?')} "
            f"draw_pile={state.get('draw_pile_count', '?')} discard_pile={state.get('discard_pile_count', '?')}"
        )
        powers = state.get("player_powers") or []
        if powers:
            lines.append("Player powers: " + "; ".join(f"{name(p.get('name'))}({p.get('amount', '')})" for p in powers))
        if state.get("orbs"):
            lines.append("Orbs: " + "; ".join(f"{name(o.get('name'))} passive={o.get('passive')} evoke={o.get('evoke')}" for o in state.get("orbs", [])))
        if state.get("stars") is not None:
            lines.append(f"Stars: {state.get('stars')}")

        enemies = state.get("enemies", []) or []
        lines.append(f"Enemies ({len(enemies)}):")
        for enemy in enemies:
            intents = []
            for intent in enemy.get("intents") or []:
                if intent.get("type") == "Attack":
                    if intent.get("hits", 1) and intent.get("hits", 1) > 1:
                        intents.append(f"Attack {intent.get('damage')}x{intent.get('hits')}")
                    else:
                        intents.append(f"Attack {intent.get('damage')}")
                else:
                    intents.append(str(intent.get("type")))
            powers = enemy.get("powers") or []
            power_text = ""
            if powers:
                power_text = " powers=" + ",".join(f"{name(p.get('name'))}({p.get('amount', '')})" for p in powers)
            move = enemy.get("move_name") or "?"
            lines.append(
                f"  [{enemy.get('index')}] {name(enemy.get('name'))} hp={enemy.get('hp')}/{enemy.get('max_hp')} block={enemy.get('block', 0)} intent={','.join(intents) or 'none'} move={move}{power_text}"
            )

        hand = state.get("hand", []) or []
        lines.append(f"Hand ({len(hand)}):")
        for card in hand:
            append_card_lines(lines, card)

    elif decision == "map_select":
        choices = state.get("choices", []) or []
        full_map = state.get("full_map")
        if not state.get("view_map") and isinstance(full_map, dict) and full_map.get("type") == "map":
            lines.extend(render_full_map(full_map, choices))
        lines.append(f"Map choices ({len(choices)}):")
        for choice in choices:
            lines.append(f"  col={choice.get('col')} row={choice.get('row')} type={choice.get('type')}")

    elif decision == "card_reward":
        cards = state.get("cards", []) or []
        lines.append(f"Card rewards ({len(cards)}):")
        for card in cards:
            append_card_lines(lines, card)
        lines.append(f"Can skip: {state.get('can_skip', True)}")

    elif decision == "combat_reward":
        rewards = state.get("rewards", []) or []
        lines.append(f"Combat rewards ({len(rewards)}):")
        for reward in rewards:
            bits = [
                f"[{reward.get('index')}]",
                f"kind={reward.get('kind')}",
                f"type_name={reward.get('type_name', '?')}",
                f"name={name(reward.get('name'))}",
            ]
            if reward.get("amount") is not None:
                bits.append(f"amount={reward.get('amount')}")
            if reward.get("can_claim") is not None:
                bits.append(f"can_claim={reward.get('can_claim')}")
            if reward.get("can_skip") is not None:
                bits.append(f"can_skip={reward.get('can_skip')}")
            lines.append("  " + " ".join(bits))
            desc = description_of(reward)
            if desc:
                lines.append(f"    description: {desc}")
            append_hover_tip_lines(lines, reward, prefix="    ")

    elif decision == "event_choice":
        lines.append(f"Event: {name(state.get('event_name'))}")
        if state.get("description"):
            lines.append(f"Description: {state.get('description')}")
        options = state.get("options", []) or []
        lines.append(f"Options ({len(options)}):")
        for option in options:
            locked = " locked" if option.get("is_locked") else ""
            enabled = "" if option.get("is_enabled", True) else " disabled"
            vars_text = vars_line(option) or "{}"
            lines.append(f"  [{option.get('index')}] {name(option.get('title') or option.get('name'))}{locked}{enabled} vars={vars_text}")
            desc = description_of(option)
            if desc:
                lines.append(f"    description: {desc}")
            append_hover_tip_lines(lines, option, prefix="    ")

    elif decision == "rest_site":
        options = state.get("options", []) or []
        lines.append(f"Rest options ({len(options)}):")
        for option in options:
            disabled = " disabled" if option.get("is_enabled") is False else ""
            vars_text = vars_line(option) or "{}"
            lines.append(f"  [{option.get('index')}] {name(option.get('title') or option.get('name'))}{disabled} vars={vars_text}")
            desc = description_of(option)
            if desc:
                lines.append(f"    description: {desc}")
            append_hover_tip_lines(lines, option, prefix="    ")

    elif decision == "shop":
        shop_cards = state.get("cards", []) or []
        lines.append(f"Shop cards ({len(shop_cards)}):")
        for card in shop_cards:
            stocked = "" if card.get("is_stocked") else " sold"
            lines.append(f"  [{card.get('index')}] {name(card.get('name'))} price={card.get('price', card.get('gold_cost', '?'))}{stocked}")
            append_card_lines(lines, card, prefix="    ")
        shop_relics = state.get("relics", []) or []
        lines.append(f"Shop relics ({len(shop_relics)}):")
        for relic in shop_relics:
            stocked = "" if relic.get("is_stocked") else " sold"
            lines.append(f"  [{relic.get('index')}] {name(relic.get('name'))} cost={relic.get('cost')}{stocked}")
            desc = description_of(relic)
            if desc:
                lines.append(f"    description: {desc}")
            append_hover_tip_lines(lines, relic, prefix="    ")
        shop_potions = state.get("potions", []) or []
        lines.append(f"Shop potions ({len(shop_potions)}):")
        for potion in shop_potions:
            stocked = "" if potion.get("is_stocked") else " sold"
            lines.append(f"  [{potion.get('index')}] {name(potion.get('name'))} cost={potion.get('cost')}{stocked} target={potion.get('target_type', '?')}")
            desc = description_of(potion)
            if desc:
                lines.append(f"    description: {desc}")
            append_hover_tip_lines(lines, potion, prefix="    ")
        if state.get("card_removal_cost") is not None:
            lines.append(f"Card removal cost: {state.get('card_removal_cost')}")

    elif decision == "treasure":
        relics = state.get("relics", []) or []
        lines.append(f"Treasure relics ({len(relics)}):")
        for relic in relics:
            lines.append(f"  [{relic.get('index')}] {name(relic.get('name'))}")
            desc = description_of(relic)
            if desc:
                lines.append(f"    description: {desc}")
            append_hover_tip_lines(lines, relic, prefix="    ")
        if not state.get("relics"):
            lines.append(state.get("message", "No relic choices"))

    elif decision == "card_select":
        lines.append(f"Card select: min={state.get('min_select')} max={state.get('max_select')} prompt={name(state.get('prompt'))}")
        for source_key in ("source_event_option", "source_room_option", "source_potion", "source_card", "source_power"):
            source = state.get(source_key)
            if isinstance(source, dict) and source:
                lines.append(f"{source_key}: {name(source.get('title') or source.get('name') or source.get('id'))}")
                desc = description_of(source)
                if desc:
                    lines.append(f"  description: {desc}")
                append_hover_tip_lines(lines, source, prefix="  ")
        combat = state.get("combat")
        if isinstance(combat, dict) and combat:
            lines.append(
                f"Combat context: round={combat.get('round', '?')} energy={combat.get('energy', '?')}/{combat.get('max_energy', '?')} draw={combat.get('draw_pile_count', '?')} discard={combat.get('discard_pile_count', '?')} exhaust={combat.get('exhaust_pile_count', '?')}"
            )
            for enemy in combat.get("enemies") or []:
                intents = ",".join(str(intent.get("type")) for intent in enemy.get("intents") or []) or "none"
                lines.append(f"  enemy [{enemy.get('index')}] {name(enemy.get('name'))} hp={enemy.get('hp')}/{enemy.get('max_hp')} block={enemy.get('block', 0)} intents={intents}")
        cards = state.get("cards", []) or []
        lines.append(f"Selectable cards ({len(cards)}):")
        for card in cards:
            append_card_lines(lines, card)

    elif decision == "game_over":
        lines.append(f"Game over: victory={state.get('victory')} act={state.get('act')} floor={state.get('floor')}")

    append_viewed_information(lines, state, player)
    return "\n".join(lines)
