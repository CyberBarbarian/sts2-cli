import importlib.util
import sys
from pathlib import Path


def _load_play_full_run():
    root = Path(__file__).resolve().parents[1]
    python_dir = root / "python"
    sys.path.insert(0, str(python_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "play_full_run",
            python_dir / "play_full_run.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(python_dir))


def test_full_run_skips_unclaimable_potion_rewards():
    play_full_run = _load_play_full_run()

    command = play_full_run.combat_reward_command({
        "rewards": [
            {
                "index": 0,
                "kind": "potion",
                "can_claim": False,
                "can_skip": True,
                "blocked_reason": "potion_slots_full",
            },
            {"index": 1, "kind": "card_reward", "can_claim": True, "can_skip": True},
        ],
    })

    assert command == {
        "cmd": "action",
        "action": "skip_reward",
        "args": {"reward_index": 0},
    }
