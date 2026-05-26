from sts2_bench.context import render_state_text


def test_view_deck_uses_full_card_rendering():
    state = {
        "decision": "combat_play",
        "context": {"act": 1, "floor": 1, "room_type": "Monster"},
        "player": {
            "hp": 80,
            "max_hp": 80,
            "gold": 99,
            "deck_size": 2,
            "deck": [
                {
                    "name": "Strike",
                    "cost": 1,
                    "type": "Attack",
                    "rarity": "Basic",
                    "upgraded": False,
                    "stats": {"damage": 6},
                    "target_type": "AnyEnemy",
                    "description": "Deal 6 damage.",
                    "after_upgrade": {
                        "cost": 1,
                        "stats": {"damage": 9},
                        "description": "Deal 9 damage.",
                    },
                    "hover_tips": [
                        {
                            "name": "Attack",
                            "description": "Attacks are played against enemies.",
                        }
                    ],
                    "count": 2,
                }
            ],
        },
        "round": 1,
        "energy": 3,
        "max_energy": 3,
        "draw_pile_count": 0,
        "discard_pile_count": 0,
        "enemies": [],
        "hand": [],
        "view_deck": True,
    }

    text = render_state_text(state)

    assert "Deck view (1 entries, deck_size=2):" in text
    assert "[0] Strike cost=1 Attack rarity=Basic upgraded=False damage=6 target=AnyEnemy x2" in text
    assert "description: Deal 6 damage." in text
    assert "upgrade: damage 6 -> 9" in text
    assert "upgrade_description: Deal 9 damage." in text
    assert "tip: Attack: Attacks are played against enemies." in text


def test_combat_power_descriptions_are_rendered_without_target_damage_preview():
    state = {
        "decision": "combat_play",
        "context": {"act": 1, "floor": 17, "room_type": "Boss"},
        "player": {"hp": 28, "max_hp": 80, "gold": 203, "deck_size": 21},
        "round": 6,
        "energy": 3,
        "max_energy": 3,
        "draw_pile_count": 1,
        "discard_pile_count": 7,
        "player_powers": [
            {
                "name": "Weak",
                "amount": 2,
                "type": "Debuff",
                "description": "Attacks deal 25% less damage.",
            }
        ],
        "enemies": [
            {
                "index": 0,
                "name": "Vantom",
                "hp": 35,
                "max_hp": 140,
                "block": 0,
                "move_name": "Attack",
                "intents": [{"type": "Attack", "damage": 27, "hits": 1}],
                "powers": [
                    {
                        "name": "Slippery",
                        "amount": 6,
                        "type": "Buff",
                        "description": "The next 6 times Vantom loses HP, it only loses 1 HP instead.",
                    }
                ],
            }
        ],
        "hand": [
            {
                "index": 0,
                "name": "Bash",
                "cost": 2,
                "type": "Attack",
                "can_play": True,
                "target_type": "AnyEnemy",
                "stats": {"damage": 12, "damage_by_target": {"0": 1}},
                "description": "Deal 12 damage. Apply 2 Vulnerable.",
            }
        ],
    }

    text = render_state_text(state)

    assert "Player powers (1):" in text
    assert "Debuff Weak(2): Attacks deal 25% less damage." in text
    assert "powers=Slippery(6)" in text
    assert "Buff Slippery(6): The next 6 times Vantom loses HP, it only loses 1 HP instead." in text
    assert "damage_by_target" not in text
    assert "target_damage" not in text
