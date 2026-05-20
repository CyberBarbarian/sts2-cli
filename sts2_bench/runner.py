"""Benchmark runner for STS2 policies."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .actions import LegalAction, build_legal_actions
from .agents import Agent, OpenAICompatAgent, RandomAgent
from .context import build_llm_prompt, compact_state
from .process import Sts2Process


@dataclass
class RunResult:
    seed: str
    character: str
    ascension: int
    victory: bool = False
    act: int | None = None
    floor: int | None = None
    hp: int | None = None
    max_hp: int | None = None
    gold: int | None = None
    deck_size: int | None = None
    steps: int = 0
    invalid_states: int = 0
    truncated: bool = False
    wall_time_sec: float = 0.0
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["extra"] = dict(self.extra)
        return data


class JsonlLogger:
    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path) if path else None
        self.handle = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open("w", encoding="utf-8")

    def write(self, entry: dict[str, Any]) -> None:
        if not self.handle:
            return
        self.handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.handle.flush()

    def close(self) -> None:
        if self.handle:
            self.handle.close()
            self.handle = None


def run_one(
    *,
    agent: Agent,
    seed: str,
    character: str = "Ironclad",
    ascension: int = 0,
    lang: str = "en",
    max_steps: int = 2000,
    process: Sts2Process | None = None,
    logger: JsonlLogger | None = None,
    print_prompts: bool = False,
) -> RunResult:
    """Run one game and return summary metrics."""

    owns_process = process is None
    proc = process or Sts2Process()
    started = time.time()
    result = RunResult(seed=seed, character=character, ascension=ascension)

    try:
        proc.start()
        state = proc.start_run(character=character, seed=seed, ascension=ascension, lang=lang)
        logger and logger.write({"type": "start", "seed": seed, "character": character, "ascension": ascension})

        for step in range(max_steps):
            result.steps = step
            decision = state.get("decision")
            if decision == "game_over":
                _fill_result(result, state)
                return result

            legal_actions = build_legal_actions(state)
            prompt = build_llm_prompt(state, legal_actions) if print_prompts else None
            logger and logger.write(
                {
                    "type": "decision",
                    "step": step,
                    "state": compact_state(state),
                    "legal_actions": [action.to_prompt_dict() for action in legal_actions],
                    **({"prompt": prompt} if prompt is not None else {}),
                }
            )

            if not legal_actions:
                result.invalid_states += 1
                state = proc.action("proceed")
                continue

            if print_prompts:
                print(f"\n===== PROMPT step={step} decision={decision} =====")
                print(prompt)
                print(f"===== END PROMPT step={step} =====\n", flush=True)

            action, meta = agent.choose(state, legal_actions)
            if not isinstance(action, LegalAction):
                raise TypeError("Agent returned a non-LegalAction")

            logger and logger.write(
                {
                    "type": "action",
                    "step": step,
                    "action": action.to_prompt_dict(),
                    "agent_meta": meta,
                }
            )

            state = proc.send(action.command)
            if state.get("type") == "error":
                result.invalid_states += 1
                logger and logger.write({"type": "error", "step": step, "state": state})
                # Let the engine advance if possible.  Some pending screens need a
                # specific action, so this is only a recovery path for model errors.
                state = proc.action("proceed")

        result.truncated = True
        result.extra["truncation_reason"] = f"max_steps exceeded ({max_steps})"
        _fill_result(result, state)
        return result
    except Exception as exc:  # noqa: BLE001 - benchmark should report failures per seed
        result.error = str(exc)
        return result
    finally:
        result.wall_time_sec = time.time() - started
        logger and logger.write({"type": "result", "result": result.to_dict()})
        if owns_process:
            proc.close()


def _fill_result(result: RunResult, state: dict[str, Any]) -> None:
    player = state.get("player") or {}
    context = state.get("context") or {}
    result.victory = bool(state.get("victory", False))
    result.act = state.get("act") or context.get("act")
    result.floor = state.get("floor") or context.get("floor")
    result.hp = player.get("hp")
    result.max_hp = player.get("max_hp")
    result.gold = player.get("gold")
    result.deck_size = player.get("deck_size")


def summarize(results: Iterable[RunResult]) -> dict[str, Any]:
    rows = list(results)
    if not rows:
        return {"runs": 0}
    complete = [row for row in rows if row.error is None and not row.truncated]
    return {
        "runs": len(rows),
        "completed": len(complete),
        "truncated": sum(1 for row in rows if row.truncated),
        "errors": sum(1 for row in rows if row.error is not None),
        "win_rate": sum(1 for row in rows if row.victory) / len(rows),
        "avg_floor": sum((row.floor or 0) for row in rows) / len(rows),
        "avg_steps": sum(row.steps for row in rows) / len(rows),
        "avg_invalid_states": sum(row.invalid_states for row in rows) / len(rows),
        "avg_wall_time_sec": sum(row.wall_time_sec for row in rows) / len(rows),
    }


def agent_from_args(kind: str, *, base_url: str | None, model: str | None, api_key: str) -> Agent:
    if kind == "random":
        return RandomAgent(seed=0)
    if kind == "llm":
        if not base_url or not model:
            raise ValueError("--base-url and --model are required for --agent llm")
        return OpenAICompatAgent(base_url=base_url, model=model, api_key=api_key)
    raise ValueError(f"Unknown agent kind: {kind}")
