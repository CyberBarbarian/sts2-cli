"""Legal-action generation for benchmark and RL policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LegalAction:
    """One action exposed to a model or policy.

    ``command`` is either the exact JSON command sent to ``Sts2Headless`` or a
    benchmark-local ``bench_view`` command. ``label`` is intentionally plain
    text because it is shown to LLMs and log readers.
    """

    action_id: int
    label: str
    command: dict[str, Any]
    kind: str

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "label": self.label,
            "cmd": self.command,
        }


def _action(label: str, action: str, kind: str, **args: Any) -> dict[str, Any]:
    command: dict[str, Any] = {"cmd": "action", "action": action}
    if args:
        command["args"] = args
    return {"label": label, "command": command, "kind": kind}


def _view_action(label: str, view: str, kind: str) -> dict[str, Any]:
    return {
        "label": label,
        "command": {"cmd": "bench_view", "view": view},
        "kind": kind,
    }


def _name(obj: Any) -> str:
    if isinstance(obj, dict):
        for key in ("en", "name", "title", "id"):
            value = obj.get(key)
            if value:
                return str(value)
        return "?"
    return str(obj) if obj is not None else "?"


def _price(item: dict[str, Any]) -> int:
    for key in ("price", "gold_cost", "cost"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 10**9


def _card_cost_value(card: dict[str, Any]) -> int:
    cost = card.get("energy_cost", card.get("cost", 99))
    if isinstance(cost, (int, float)):
        return int(cost)
    if isinstance(cost, str) and cost.upper() == "X":
        return 0
    return 99


def _targeted_card_actions(state: dict[str, Any], card: dict[str, Any]) -> list[dict[str, Any]]:
    card_index = card.get("index")
    card_name = _name(card.get("name"))
    target_type = str(card.get("target_type") or "")
    enemies = [enemy for enemy in state.get("enemies", []) if enemy.get("hp", 0) > 0]

    if target_type == "AnyEnemy":
        return [
            _action(
                f"play card {card_index}: {card_name} on enemy {enemy.get('index')}: {_name(enemy.get('name'))}",
                "play_card",
                "combat_play_card",
                card_index=card_index,
                target_index=enemy.get("index"),
            )
            for enemy in enemies
        ]

    return [
        _action(
            f"play card {card_index}: {card_name}",
            "play_card",
            "combat_play_card",
            card_index=card_index,
        )
    ]


def build_legal_actions(state: dict[str, Any]) -> list[LegalAction]:
    """Build legal actions from the current decision point.

    The resulting action ids are stable only for this one state.  Store the
    selected full command in logs, not just the id.
    """

    decision = state.get("decision")
    raw: list[dict[str, Any]] = []

    if decision != "game_over":
        raw.extend(
            [
                _view_action("view deck", "deck", "view_deck"),
                _view_action("view map and current position", "map", "view_map"),
            ]
        )

    if decision == "map_select":
        for choice in state.get("choices", []):
            raw.append(
                _action(
                    f"go to {choice.get('type', '?')} at col={choice.get('col')} row={choice.get('row')}",
                    "select_map_node",
                    "map",
                    col=choice.get("col"),
                    row=choice.get("row"),
                )
            )

    elif decision == "combat_play":
        energy = state.get("energy", 0)
        for card in state.get("hand", []):
            if not card.get("can_play"):
                continue
            if _card_cost_value(card) > energy:
                continue
            raw.extend(_targeted_card_actions(state, card))

        player = state.get("player") or {}
        for potion in player.get("potions", []) or state.get("potions", []) or []:
            if not potion:
                continue
            potion_index = potion.get("index", potion.get("slot_index"))
            if potion_index is None:
                continue
            potion_name = _name(potion.get("name"))
            target_type = str(potion.get("target_type") or "")
            if target_type == "AnyEnemy":
                for enemy in state.get("enemies", []):
                    if enemy.get("hp", 0) > 0:
                        raw.append(
                            _action(
                                f"use potion {potion_index}: {potion_name} on enemy {enemy.get('index')}: {_name(enemy.get('name'))}",
                                "use_potion",
                                "combat_use_potion",
                                potion_index=potion_index,
                                target_index=enemy.get("index"),
                            )
                        )
            else:
                raw.append(
                    _action(
                        f"use potion {potion_index}: {potion_name}",
                        "use_potion",
                        "combat_use_potion",
                        potion_index=potion_index,
                    )
                )

        raw.append(_action("end turn", "end_turn", "combat_end_turn"))

    elif decision == "combat_reward":
        rewards = state.get("rewards") or []
        for reward in rewards:
            raw.append(
                _action(
                    f"claim reward {reward.get('index')}: {reward.get('kind', reward.get('type_name', '?'))}",
                    "claim_reward",
                    "combat_reward",
                    reward_index=reward.get("index"),
                )
            )
        if not rewards:
            raw.append(_action("proceed", "proceed", "proceed"))

    elif decision == "card_reward":
        for card in state.get("cards", []):
            raw.append(
                _action(
                    f"pick card {card.get('index')}: {_name(card.get('name'))}",
                    "select_card_reward",
                    "card_reward",
                    card_index=card.get("index"),
                )
            )
        if state.get("can_skip", True):
            raw.append(_action("skip card reward", "skip_card_reward", "card_reward_skip"))

    elif decision == "treasure":
        relics = state.get("relics") or []
        for relic in relics:
            raw.append(
                _action(
                    f"claim relic {relic.get('index')}: {_name(relic.get('name'))}",
                    "claim_relic",
                    "treasure",
                    relic_index=relic.get("index"),
                )
            )
        if not relics and state.get("can_proceed"):
            raw.append(_action("proceed", "proceed", "proceed"))

    elif decision in {"rest_site", "event_choice"}:
        action_name = "choose_option"
        kind = "rest_site" if decision == "rest_site" else "event"
        for option in state.get("options", []):
            if option.get("is_locked"):
                continue
            if option.get("is_enabled") is False:
                continue
            title = _name(option.get("title") or option.get("name") or option.get("description"))
            raw.append(
                _action(
                    f"choose option {option.get('index')}: {title}",
                    action_name,
                    kind,
                    option_index=option.get("index"),
                )
            )

    elif decision == "shop":
        player_gold = int((state.get("player") or {}).get("gold", 0) or 0)
        for card in state.get("cards", []) or []:
            if card.get("is_stocked") and _price(card) <= player_gold:
                raw.append(
                    _action(
                        f"buy card {card.get('index')}: {_name(card.get('name'))} for {_price(card)} gold",
                        "buy_card",
                        "shop_buy_card",
                        card_index=card.get("index"),
                    )
                )
        for relic in state.get("relics", []) or []:
            if relic.get("is_stocked") and _price(relic) <= player_gold:
                raw.append(
                    _action(
                        f"buy relic {relic.get('index')}: {_name(relic.get('name'))} for {_price(relic)} gold",
                        "buy_relic",
                        "shop_buy_relic",
                        relic_index=relic.get("index"),
                    )
                )
        for potion in state.get("potions", []) or []:
            if potion.get("is_stocked") and _price(potion) <= player_gold:
                raw.append(
                    _action(
                        f"buy potion {potion.get('index')}: {_name(potion.get('name'))} for {_price(potion)} gold",
                        "buy_potion",
                        "shop_buy_potion",
                        potion_index=potion.get("index"),
                    )
                )
        removal_cost = state.get("card_removal_cost")
        if isinstance(removal_cost, (int, float)) and removal_cost <= player_gold:
            raw.append(_action(f"remove a card for {int(removal_cost)} gold", "remove_card", "shop_remove_card"))
        raw.append(_action("leave shop", "leave_room", "shop_leave"))

    elif decision == "card_select":
        cards = state.get("cards") or []
        min_select = int(state.get("min_select", 1) or 0)
        max_select = int(state.get("max_select", min_select) or min_select)
        if min_select == 0:
            raw.append(_action("skip selection", "skip_select", "card_select_skip"))
        if cards:
            # Conservative generic action set: individual cards and first-k selection.
            for card in cards:
                raw.append(
                    _action(
                        f"select card {card.get('index')}: {_name(card.get('name'))}",
                        "select_cards",
                        "card_select",
                        indices=str(card.get("index")),
                    )
                )
            if min_select > 1:
                indices = ",".join(str(card.get("index")) for card in cards[: min(max_select, len(cards))])
                raw.append(_action(f"select first {min_select} cards", "select_cards", "card_select", indices=indices))

    elif decision == "bundle_select":
        for bundle in state.get("bundles", []) or state.get("options", []) or []:
            raw.append(
                _action(
                    f"select bundle {bundle.get('index')}: {_name(bundle.get('name') or bundle.get('title'))}",
                    "select_bundle",
                    "bundle_select",
                    bundle_index=bundle.get("index"),
                )
            )

    elif decision == "crystal_sphere":
        raw.append(_action("proceed from crystal sphere", "crystal_sphere_proceed", "crystal_sphere"))

    elif decision == "game_over":
        raw = []

    else:
        raw.append(_action("proceed", "proceed", "proceed"))

    return [
        LegalAction(action_id=i, label=item["label"], command=item["command"], kind=item["kind"])
        for i, item in enumerate(raw)
    ]
