"""LLM-facing state compaction and prompt rendering."""

from __future__ import annotations

import json
from typing import Any

from .actions import LegalAction


DROP_KEYS = {
    "enchantment_description",
    "affliction_description",
    "instance_id",
    "draw_pile",
    "discard_pile",
    "exhaust_pile",
    "inactive_enemies",
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
                "cost": card.get("cost"),
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

    return _compact_obj(state)


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


def card_line(card: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    stats = card.get("stats") or {}
    bits = [
        f"[{card.get('index', '?')}]",
        name(card.get("name")),
        f"cost={card.get('cost', '?')}",
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
        if after.get("cost") is not None and after.get("cost") != card.get("cost"):
            upgrade_parts.append(f"cost {card.get('cost')} -> {after.get('cost')}")
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
            lines.append(
                f"  [{enemy.get('index')}] {name(enemy.get('name'))} hp={enemy.get('hp')}/{enemy.get('max_hp')} block={enemy.get('block', 0)} intent={','.join(intents) or 'none'} move={enemy.get('move_name', enemy.get('move_id', '?'))}{power_text}"
            )

        hand = state.get("hand", []) or []
        lines.append(f"Hand ({len(hand)}):")
        for card in hand:
            append_card_lines(lines, card)

    elif decision == "map_select":
        choices = state.get("choices", []) or []
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
            option_id = option.get("option_id") or option.get("id")
            id_text = f" id={option_id}" if option_id else ""
            vars_text = vars_line(option) or "{}"
            lines.append(f"  [{option.get('index')}] {name(option.get('title') or option.get('name'))}{id_text}{disabled} vars={vars_text}")
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

    return "\n".join(lines)


def build_llm_prompt(state: dict[str, Any], legal_actions: list[LegalAction], *, include_json: bool = True) -> str:
    """Build a strict action-selection prompt for local LLMs."""

    action_payload = [action.to_prompt_dict() for action in legal_actions]
    parts = [
        "You are playing Slay the Spire 2 through a headless benchmark environment.",
        "Choose exactly one legal action. Return only JSON with this schema:",
        '{"action_id": <integer>, "reason": "<short reason>"}',
        "",
        "Game state:",
        render_state_text(state),
        "",
        "Legal actions:",
        json.dumps(action_payload, ensure_ascii=False, separators=(",", ":")),
    ]
    if include_json:
        parts.extend(
            [
                "",
                "Compact state JSON:",
                json.dumps(compact_state(state), ensure_ascii=False, separators=(",", ":")),
            ]
        )
    return "\n".join(parts)
