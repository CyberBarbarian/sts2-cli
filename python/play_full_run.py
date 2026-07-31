#!/usr/bin/env python3
"""
Play a full STS2 run using the headless simulator with a random agent.

Usage:
  python3 play_full_run.py <num_runs> [character]

Arguments:
  num_runs    Positive integer: number of runs to play
  character   One of: Ironclad, Silent, Defect, Regent, Necrobinder (default: Ironclad)

Examples:
  python3 play_full_run.py 5
  python3 play_full_run.py 3 Silent
"""

import argparse
import json
import subprocess
import sys
import random
import os
from game_log import GameLogger

VALID_CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]


def card_energy_cost(card, default=99):
    cost = card.get("energy_cost", card.get("cost", default))
    if isinstance(cost, (int, float)):
        return cost
    if isinstance(cost, str) and cost.upper() == "X":
        x_value = card.get("x_value", card.get("x_cost", 0))
        if isinstance(x_value, (int, float)):
            return x_value
        return 0
    return default


def minimum_card_selection_indices(state: dict) -> str:
    """Return distinct exported indices satisfying the required minimum."""

    cards = state.get("cards", []) or []
    required = int(state.get("min_select", 1) or 0)
    if required < 0:
        raise RuntimeError(f"invalid card_select min_select={required}")
    if len(cards) < required:
        raise RuntimeError(
            f"card_select requires {required} card(s), but only {len(cards)} option(s) were exported"
        )
    indices = [int(card.get("index", position)) for position, card in enumerate(cards[:required])]
    if len(indices) != len(set(indices)):
        raise RuntimeError("card_select exported duplicate candidate indices")
    return ",".join(str(index) for index in indices)


def combat_reward_command(state: dict) -> dict:
    rewards = state.get("rewards", [])
    if not rewards:
        raise RuntimeError("combat_reward exported no rewards")

    claimable_non_card = next(
        (
            reward for reward in rewards
            if reward.get("kind") != "card_reward" and reward.get("can_claim") is True
        ),
        None,
    )
    if claimable_non_card:
        return {
            "cmd": "action",
            "action": "claim_reward",
            "args": {"reward_index": claimable_non_card["index"]},
        }

    skippable_blocked = next(
        (
            reward for reward in rewards
            if reward.get("can_claim") is False and reward.get("can_skip") is True
        ),
        None,
    )
    if skippable_blocked:
        return {
            "cmd": "action",
            "action": "skip_reward",
            "args": {"reward_index": skippable_blocked["index"]},
        }

    card_reward = next((reward for reward in rewards if reward.get("kind") == "card_reward"), None)
    if card_reward:
        return {
            "cmd": "action",
            "action": "skip_reward",
            "args": {"reward_index": card_reward["index"]},
        }

    return {
        "cmd": "action",
        "action": "claim_reward",
        "args": {"reward_index": rewards[0]["index"]},
    }


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(ROOT, "lib")
LOCAL_DOTNET_DIR = os.path.join(ROOT, ".tools", "dotnet")
LOCAL_DOTNET = os.path.join(LOCAL_DOTNET_DIR, "dotnet.exe" if os.name == "nt" else "dotnet")
HEADLESS_DLL = os.path.join(ROOT, "src", "Sts2Headless", "bin", "Debug", "net9.0", "Sts2Headless.dll")


def _runtime_binding():
    required = [LOCAL_DOTNET, HEADLESS_DLL, os.path.join(LIB_DIR, "sts2.dll")]
    missing = [path for path in required if not os.path.isfile(path)]
    if missing:
        raise RuntimeError(
            "play_full_run requires the repository-local prebuilt runtime; missing: " + ", ".join(missing)
        )
    env = os.environ.copy()
    env["DOTNET_ROOT"] = LOCAL_DOTNET_DIR
    env["PATH"] = LOCAL_DOTNET_DIR + os.pathsep + env.get("PATH", "")
    env["STS2_LIB"] = LIB_DIR
    env["STS2_GAME_DIR"] = LIB_DIR
    return [LOCAL_DOTNET, HEADLESS_DLL], env


def play_run(seed: str, character: str = "Ironclad", verbose: bool = True, log: bool = True):
    """Play a complete run and return the result."""
    command, env = _runtime_binding()
    logger = GameLogger(character, seed, enabled=log)
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if not verbose else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
    except BaseException:
        logger.close()
        raise

    def read_json_line() -> dict:
        """Read a line from stdout, skipping non-JSON lines (build warnings etc.)"""
        while True:
            resp_line = proc.stdout.readline().strip()
            if not resp_line:
                raise RuntimeError("No response from simulator (EOF)")
            if resp_line.startswith("{"):
                return json.loads(resp_line)
            # Skip non-JSON lines (build warnings, etc.)
            if verbose:
                print(f"  [skip] {resp_line[:120]}")

    def send(cmd: dict) -> dict:
        line = json.dumps(cmd)
        if verbose:
            print(f"  > {line[:200]}")
        logger.log_action(cmd)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        resp = read_json_line()
        logger.log_state(resp)
        if verbose:
            rtype = resp.get("type", "?")
            decision = resp.get("decision", "")
            if rtype == "decision":
                player = resp.get("player", {})
                hp = player.get("hp", "?")
                max_hp = player.get("max_hp", "?")
                gold = player.get("gold", "?")
                act = resp.get("act", "?")
                floor = resp.get("floor", "?")
                print(f"  < {rtype}/{decision} act={act} floor={floor} hp={hp}/{max_hp} gold={gold}")
            else:
                print(f"  < {json.dumps(resp)[:200]}")
        return resp

    step = 0
    try:
        # Read ready message (may need to skip build warnings)
        ready = read_json_line()
        if ready.get("type") != "ready":
            print(f"  Unexpected initial response: {ready}")
            return {"victory": False, "seed": seed, "error": "bad_init"}
        if verbose:
            print(f"Connected: {ready}")

        # Start run
        state = send({"cmd": "start_run", "character": character, "seed": seed})

        step = 0
        max_steps = 500  # Safety limit
        stuck_count = 0
        last_state_key = None

        while step < max_steps:
            step += 1

            if not isinstance(state, dict):
                raise RuntimeError(f"invalid simulator state payload: {type(state).__name__}")
            if state.get("type") == "error":
                raise RuntimeError(str(state.get("message") or state.get("error") or "simulator error"))
            if state.get("engine_error") is True or state.get("error") == "engine_error":
                raise RuntimeError(
                    str(state.get("engine_error_reason") or state.get("message") or "engine error")
                )
            if state.get("type") != "decision":
                raise RuntimeError(f"unsupported simulator state type: {state.get('type')!r}")

            decision = state.get("decision", "")

            # Stuck detection — use comprehensive state key
            hand_len = len(state.get("hand", []))
            enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
            energy = state.get("energy", 0)
            state_key = f"{decision}:{state.get('round')}:{state.get('player',{}).get('hp')}:{hand_len}:{enemy_hp}:{energy}"
            if state_key == last_state_key:
                stuck_count += 1
                if stuck_count > 20:
                    raise RuntimeError(f"decision state did not change for {stuck_count} consecutive steps")
            else:
                stuck_count = 0
                last_state_key = state_key

            if decision == "game_over":
                victory = state.get("victory", False)
                player = state.get("player", {})
                print(f"\n{'VICTORY' if victory else 'DEFEAT'} at act {state.get('act')}, "
                      f"floor {state.get('floor')} "
                      f"(HP: {player.get('hp')}/{player.get('max_hp')}, "
                      f"Gold: {player.get('gold')}, "
                      f"Deck: {player.get('deck_size')} cards)")
                return {
                    "victory": victory,
                    "seed": seed,
                    "steps": step,
                    "act": state.get("act"),
                    "floor": state.get("floor"),
                    "hp": player.get("hp"),
                    "max_hp": player.get("max_hp"),
                }

            elif decision == "map_select":
                choices = state.get("choices", [])
                if not choices:
                    raise RuntimeError("map_select exported no legal choices")
                # Random selection
                choice = random.choice(choices)
                state = send({
                    "cmd": "action",
                    "action": "select_map_node",
                    "args": {"col": choice["col"], "row": choice["row"]}
                })

            elif decision == "combat_play":
                hand = state.get("hand", [])
                energy = state.get("energy", 0)
                enemies = state.get("enemies", [])

                # Simple strategy: play playable cards until out of energy
                playable = [c for c in hand if c.get("can_play") is True
                           and (card_energy_cost(c, 0) <= energy)]

                if playable:
                    card = playable[0]
                    args = {"card_index": card["index"]}
                    # If card needs a target, pick first enemy
                    if card.get("target_type") == "AnyEnemy" and enemies:
                        args["target_index"] = 0
                    state = send({
                        "cmd": "action",
                        "action": "play_card",
                        "args": args
                    })
                else:
                    state = send({
                        "cmd": "action",
                        "action": "end_turn"
                    })

            elif decision == "event_choice":
                options = state.get("options", [])
                choice = next((option for option in options if option.get("is_locked") is False), None)
                if choice is None:
                    raise RuntimeError("event_choice exported no unlocked option")
                state = send({
                    "cmd": "action",
                    "action": "choose_option",
                    "args": {"option_index": choice["index"]}
                })

            elif decision == "crystal_sphere":
                if state.get("can_proceed") is True:
                    state = send({"cmd": "action", "action": "crystal_sphere_proceed"})
                else:
                    clickable = state.get("clickable_cells", [])
                    if clickable:
                        cell = clickable[0]
                        state = send({
                            "cmd": "action",
                            "action": "crystal_sphere_click_cell",
                            "args": {"x": cell["x"], "y": cell["y"]}
                        })
                    else:
                        raise RuntimeError("crystal_sphere exported neither a legal cell nor proceed")

            elif decision == "rest_site":
                options = state.get("options", [])
                # Prefer heal (HEAL), then smith
                enabled = [o for o in options if o.get("is_enabled") is True]
                heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
                choice = heal or (enabled[0] if enabled else None)
                if choice:
                    state = send({
                        "cmd": "action",
                        "action": "choose_option",
                        "args": {"option_index": choice["index"]}
                    })
                else:
                    raise RuntimeError("rest_site exported no enabled option")

            elif decision == "combat_reward":
                state = send(combat_reward_command(state))

            elif decision == "card_reward":
                # Pick the first card offered
                cards = state.get("cards", [])
                if cards:
                    state = send({
                        "cmd": "action",
                        "action": "select_card_reward",
                        "args": {"card_index": 0}
                    })
                elif state.get("can_skip") is True:
                    state = send({"cmd": "action", "action": "skip_card_reward"})
                else:
                    raise RuntimeError("card_reward exported neither cards nor explicit skip")

            elif decision == "treasure":
                relics = state.get("relics", [])
                if relics:
                    state = send({
                        "cmd": "action",
                        "action": "claim_relic",
                        "args": {"relic_index": relics[0]["index"]}
                    })
                elif state.get("can_proceed") is True:
                    state = send({"cmd": "action", "action": "proceed"})
                else:
                    raise RuntimeError("treasure exported neither relics nor explicit proceed")

            elif decision == "bundle_select":
                bundles = state.get("bundles", [])
                if not bundles:
                    raise RuntimeError("bundle_select exported no bundles")
                state = send({"cmd": "action", "action": "select_bundle",
                             "args": {"bundle_index": bundles[0]["index"]}})

            elif decision == "card_select":
                indices = minimum_card_selection_indices(state)
                if indices:
                    state = send({"cmd": "action", "action": "select_cards",
                                 "args": {"indices": indices}})
                elif state.get("can_skip") is True:
                    state = send({"cmd": "action", "action": "skip_select"})
                else:
                    raise RuntimeError("card_select requires a card but no options were exported")

            elif decision == "shop":
                state = send({"cmd": "action", "action": "leave_room"})

            elif decision == "fake_merchant_shop":
                if state.get("can_leave") is not True:
                    raise RuntimeError("fake_merchant_shop did not explicitly allow leave")
                state = send({"cmd": "action", "action": "leave_room"})

            elif decision == "event_result":
                if state.get("can_proceed") is not True:
                    raise RuntimeError("event_result did not explicitly allow proceed")
                state = send({"cmd": "action", "action": "proceed"})

            elif decision in {"unrecognized_state", "unknown", "event_blocked"}:
                raise RuntimeError(
                    f"Runtime exposed unsupported decision state {decision!r}: "
                    f"{state.get('message') or 'no diagnostic message'}"
                )

            else:
                raise RuntimeError(f"Unhandled decision {decision!r}; refusing implicit proceed")

        print(f"  Reached max steps ({max_steps})")
        return {"victory": False, "seed": seed, "steps": step, "timeout": True}

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {"victory": False, "seed": seed, "steps": step, "error": str(e)}

    finally:
        logger.close()
        if logger.path:
            print(f"  [log] Saved to {logger.path}")
        try:
            proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass


def main():
    parser = argparse.ArgumentParser(
        description="Play full STS2 runs using the headless simulator with a random agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Valid characters: " + ", ".join(VALID_CHARACTERS),
    )
    parser.add_argument("num_runs", type=int, help="Number of runs to play (must be positive)")
    parser.add_argument("character", nargs="?", default="Ironclad",
                        choices=VALID_CHARACTERS, metavar="character",
                        help=f"Character to play as (default: Ironclad). Choices: {', '.join(VALID_CHARACTERS)}")
    args = parser.parse_args()

    if args.num_runs <= 0:
        parser.error(f"num_runs must be a positive integer, got {args.num_runs}")

    num_runs = args.num_runs
    character = args.character

    print(f"Playing {num_runs} runs as {character}")
    print("=" * 60)

    results = []
    for i in range(num_runs):
        seed = f"run_{i+1}"
        print(f"\n--- Run {i+1}/{num_runs} (seed: {seed}) ---")
        result = play_run(seed, character, verbose=True)
        results.append(result)
        print()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    wins = sum(1 for r in results if r and r.get("victory"))
    completed = sum(1 for r in results if r and not r.get("timeout"))
    for i, r in enumerate(results):
        if r:
            status = "WIN" if r.get("victory") else ("TIMEOUT" if r.get("timeout") else "LOSS")
            print(f"  Run {i+1}: {status} | seed={r.get('seed')} steps={r.get('steps')} "
                  f"act={r.get('act')} floor={r.get('floor')}")
    print(f"\nWins: {wins}/{num_runs}, Completed: {completed}/{num_runs}")


if __name__ == "__main__":
    main()
