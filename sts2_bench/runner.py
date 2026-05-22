"""Benchmark runner for STS2 policies."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .actions import LegalAction, build_legal_actions
from .agents import Agent, OpenAICompatAgent, PromptStyle, RandomAgent
from .context import compact_state
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
    print_model_output: bool = False,
    include_full_map: bool = False,
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

            if include_full_map and decision == "map_select" and "full_map" not in state:
                map_state = proc.send({"cmd": "get_map"})
                if map_state.get("type") == "map":
                    state = {**state, "full_map": map_state}

            legal_actions = build_legal_actions(state)
            prompt = agent.build_prompt(state, legal_actions) if print_prompts else None
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

            action, meta = agent.choose(state, legal_actions, prompt=prompt)
            if not isinstance(action, LegalAction):
                raise TypeError("Agent returned a non-LegalAction")

            if print_model_output:
                _print_model_output(step=step, decision=decision, action=action, meta=meta)

            logger and logger.write(
                {
                    "type": "action",
                    "step": step,
                    "action": action.to_prompt_dict(),
                    "agent_meta": meta,
                }
            )

            if action.command.get("cmd") == "bench_view":
                state = _apply_view_action(proc, state, action.command)
                continue

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


def _apply_view_action(proc: Sts2Process, state: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    view = command.get("view")
    if view == "deck":
        return {**state, "view_deck": True}
    if view == "map":
        map_state = proc.send({"cmd": "get_map"})
        if map_state.get("type") == "map":
            return {**state, "view_map": True, "full_map": map_state}
        return {**state, "view_map": True, "view_map_error": map_state}
    return state


def _print_model_output(*, step: int, decision: Any, action: LegalAction, meta: dict[str, Any]) -> None:
    print(f"\n===== MODEL OUTPUT step={step} decision={decision} =====")
    raw_response = meta.get("raw_response")
    if raw_response is not None:
        print("raw_response:")
        print(raw_response)
    parsed = meta.get("parsed")
    if parsed is not None:
        print("parsed:")
        print(json.dumps(parsed, ensure_ascii=False, separators=(",", ":")))
    if meta.get("fallback"):
        print("fallback: true")
    if meta.get("error"):
        print(f"error: {meta.get('error')}")
    usage = meta.get("usage")
    if usage is not None:
        print("usage:")
        print(json.dumps(usage, ensure_ascii=False, separators=(",", ":")))
    print("selected_action:")
    print(json.dumps(action.to_prompt_dict(), ensure_ascii=False, separators=(",", ":")))
    print(f"===== END MODEL OUTPUT step={step} =====\n", flush=True)


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


def agent_from_args(
    kind: str,
    *,
    base_url: str | None,
    model: str | None,
    api_key: str,
    prompt_style: PromptStyle = "default",
) -> Agent:
    if kind == "random":
        return RandomAgent(seed=0, prompt_style=prompt_style)
    if kind == "llm":
        if not base_url or not model:
            raise ValueError("--base-url and --model, or STS2_BENCH_BASE_URL and STS2_BENCH_MODEL, are required for --agent llm")
        if api_key == "local" and not _is_local_url(base_url):
            raise ValueError(
                "Set --api-key, DEEPSEEK_API_KEY, or OPENAI_API_KEY for non-local LLM endpoints"
            )
        return OpenAICompatAgent(base_url=base_url, model=model, api_key=api_key, prompt_style=prompt_style)
    raise ValueError(f"Unknown agent kind: {kind}")


def _is_local_url(url: str) -> bool:
    lowered = url.lower()
    return "localhost" in lowered or "127.0.0.1" in lowered or "0.0.0.0" in lowered
