"""Policy agents used by benchmark runners."""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .actions import LegalAction
from .context import compact_state, render_state_text


PromptStyle = Literal["default", "analysis"]


class Agent(Protocol):
    def build_prompt(self, state: dict[str, Any], legal_actions: list[LegalAction]) -> str:
        """Return the prompt this agent would use for this decision."""

    def choose(
        self,
        state: dict[str, Any],
        legal_actions: list[LegalAction],
        *,
        prompt: str | None = None,
    ) -> tuple[LegalAction, dict[str, Any]]:
        """Return a legal action and metadata for logging."""


@dataclass
class ShortTermMemory:
    """Small per-episode memory owned by an agent, not by state rendering."""

    max_entries: int = 8
    entries: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.entries.clear()

    def remember(self, state: dict[str, Any], action: LegalAction, meta: dict[str, Any]) -> None:
        if self.max_entries <= 0:
            return

        context = state.get("context") or {}
        player = state.get("player") or {}
        parsed = meta.get("parsed") if isinstance(meta.get("parsed"), dict) else {}
        reason = _one_line(parsed.get("reason") or meta.get("reason") or "")
        parts = [
            f"decision={state.get('decision', '?')}",
            f"act={state.get('act') or context.get('act', '?')}",
            f"floor={state.get('floor') or context.get('floor', '?')}",
            f"room={context.get('room_type', '?')}",
        ]
        if player:
            parts.append(f"hp={player.get('hp', '?')}/{player.get('max_hp', '?')}")
            parts.append(f"gold={player.get('gold', '?')}")
            parts.append(f"deck_size={player.get('deck_size', '?')}")
        parts.append(f"action={action.label}")
        if reason:
            parts.append(f"reason={reason}")

        self.entries.append(" | ".join(parts))
        if len(self.entries) > self.max_entries:
            del self.entries[: len(self.entries) - self.max_entries]

    def render(self) -> str:
        if not self.entries:
            return ""
        return "\n".join(f"- {entry}" for entry in self.entries)


def build_llm_prompt(
    state: dict[str, Any],
    legal_actions: list[LegalAction],
    *,
    include_json: bool = True,
    prompt_style: PromptStyle = "default",
    memory_text: str = "",
) -> str:
    """Build the action-selection prompt used by LLM policies.

    ``context.py`` owns only state rendering.  The policy-facing task
    instruction, response schema, and legal-action wrapper live with agents so
    different agents can define different prompting methods over the same
    state text.
    """

    if prompt_style not in {"default", "analysis"}:
        raise ValueError(f"Unknown prompt style: {prompt_style}")

    parts = _prompt_header(prompt_style)
    if memory_text:
        parts.extend(["", "Episode memory:", memory_text])
    parts.extend(
        [
            "",
            "Game state:",
            render_state_text(state),
            "",
            "Legal actions:",
            json.dumps([action.to_prompt_dict() for action in legal_actions], ensure_ascii=False, separators=(",", ":")),
        ]
    )
    if include_json:
        parts.extend(
            [
                "",
                "Compact state JSON:",
                json.dumps(compact_state(state), ensure_ascii=False, separators=(",", ":")),
            ]
        )
    return "\n".join(parts)


def _one_line(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _prompt_header(prompt_style: PromptStyle) -> list[str]:
    shared = [
        "Each legal action is one atomic command, not a full-turn plan. After playing a card, using a potion, choosing a reward, or viewing information, you will receive a fresh state and may act again if the game still allows actions.",
        "In combat, end turn is the action that intentionally finishes the current turn; do not choose it while useful playable cards or potions remain unless passing is strategically better.",
        "Enemy intent damage shown in the state is the engine-displayed damage after currently visible modifiers; do not add enemy Strength or other visible modifiers to that intent damage a second time.",
        "View deck/map/pile actions do not advance the game state. They are information requests logged separately; use them when deck composition, pile contents, path context, or current position could affect the decision.",
    ]

    if prompt_style == "analysis":
        return [
            "You are playing Slay the Spire 2 through a headless benchmark environment.",
            "Choose exactly one legal action. Use only an action_id from the legal action list.",
            *shared,
            "Before choosing, write a compact public analysis in JSON. Analyze the current situation, do any needed arithmetic, compare a few plausible legal actions, then choose.",
            "Return only valid JSON with this schema:",
            (
                '{"situation":"<current objective and main risk>",'
                '"calculations":["<damage/block/energy/path/reward calculation if relevant>"],'
                '"candidates":[{"action_id":<integer>,"label":"<legal action label>",'
                '"pros":"<why it helps>","cons":"<main risk or cost>"}],'
                '"action_id":<integer>,"reason":"<final concise reason>"}'
            ),
            "For combat, compute enemy attacks from intents yourself and compare playable damage, block, energy, and lethal lines.",
            "For map choices, compare path rewards and risks. For rewards, compare deck impact.",
        ]

    return [
        "You are playing Slay the Spire 2 through a headless benchmark environment.",
        "Choose exactly one legal action. Return only JSON with this schema:",
        *shared,
        '{"action_id": <integer>, "reason": "<short reason>"}',
    ]


class RandomAgent:
    """Simple non-LLM baseline."""

    def __init__(
        self,
        seed: int | None = None,
        *,
        include_json_state: bool = False,
        prompt_style: PromptStyle = "default",
        memory_enabled: bool = False,
        memory_window: int = 8,
    ) -> None:
        self.rng = random.Random(seed)
        self.include_json_state = include_json_state
        self.prompt_style = prompt_style
        self.memory = ShortTermMemory(memory_window) if memory_enabled else None

    def build_prompt(self, state: dict[str, Any], legal_actions: list[LegalAction]) -> str:
        return build_llm_prompt(
            state,
            legal_actions,
            include_json=self.include_json_state,
            prompt_style=self.prompt_style,
            memory_text=self.memory.render() if self.memory else "",
        )

    def choose(
        self,
        state: dict[str, Any],
        legal_actions: list[LegalAction],
        *,
        prompt: str | None = None,
    ) -> tuple[LegalAction, dict[str, Any]]:
        action = self.rng.choice(legal_actions)
        return action, {"agent": "random"}

    def reset_episode(self) -> None:
        if self.memory:
            self.memory.reset()

    def record_transition(self, state: dict[str, Any], action: LegalAction, meta: dict[str, Any]) -> None:
        if self.memory:
            self.memory.remember(state, action, meta)


@dataclass
class OpenAICompatAgent:
    """Local LLM agent for OpenAI-compatible servers.

    Works with Ollama, LM Studio, vLLM, llama.cpp server, and similar local
    servers that expose ``/v1/chat/completions``.
    """

    base_url: str
    model: str
    api_key: str = "local"
    temperature: float = 0.0
    timeout: float = 120.0
    include_json_state: bool = False
    max_retries: int = 2
    prompt_style: PromptStyle = "default"
    memory_enabled: bool = False
    memory_window: int = 8

    def __post_init__(self) -> None:
        self.memory = ShortTermMemory(self.memory_window) if self.memory_enabled else None

    def build_prompt(self, state: dict[str, Any], legal_actions: list[LegalAction]) -> str:
        return build_llm_prompt(
            state,
            legal_actions,
            include_json=self.include_json_state,
            prompt_style=self.prompt_style,
            memory_text=self.memory.render() if self.memory else "",
        )

    def choose(
        self,
        state: dict[str, Any],
        legal_actions: list[LegalAction],
        *,
        prompt: str | None = None,
    ) -> tuple[LegalAction, dict[str, Any]]:
        if not legal_actions:
            raise ValueError("No legal actions available")

        prompt = prompt if prompt is not None else self.build_prompt(state, legal_actions)
        messages = [
            {
                "role": "system",
                "content": "You are a careful game-playing policy. Return only valid JSON. Never invent actions.",
            },
            {"role": "user", "content": prompt},
        ]

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            started = time.time()
            try:
                response = self._chat(messages)
                elapsed = time.time() - started
                text = response["choices"][0]["message"]["content"]
                parsed = parse_json_object(text)
                action_id = int(parsed.get("action_id"))
                if action_id < 0 or action_id >= len(legal_actions):
                    raise ValueError(f"action_id out of range: {action_id}")
                return legal_actions[action_id], {
                    "agent": "openai_compat",
                    "model": self.model,
                    "attempt": attempt,
                    "elapsed_sec": elapsed,
                    "raw_response": text,
                    "parsed": parsed,
                    "usage": response.get("usage"),
                    "prompt_chars": len(prompt),
                }
            except Exception as exc:  # noqa: BLE001 - log and retry with stricter correction
                last_error = str(exc)
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous response was invalid: {last_error}. "
                            f"Return only JSON with action_id between 0 and {len(legal_actions) - 1}."
                        ),
                    }
                )

        # Deterministic fallback keeps long benchmark batches moving while
        # still recording the invalid model behavior.  Prefer a real game
        # action so parse failures do not degenerate into repeated view actions.
        fallback = first_non_view_action(legal_actions)
        return fallback, {
            "agent": "openai_compat",
            "model": self.model,
            "fallback": True,
            "error": last_error,
            "fallback_action_id": fallback.action_id,
            "prompt_chars": len(prompt),
        }

    def reset_episode(self) -> None:
        if self.memory:
            self.memory.reset()

    def record_transition(self, state: dict[str, Any], action: LegalAction, meta: dict[str, Any]) -> None:
        if self.memory:
            self.memory.remember(state, action, meta)

    def _chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        base = self.base_url.rstrip("/")
        url = base + "/chat/completions"
        if not base.endswith("/v1"):
            url = base + "/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {body[:500]}") from exc


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object even if the model wrapped it in fences."""

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object, got {type(value).__name__}")
    return value


def first_non_view_action(legal_actions: list[LegalAction]) -> LegalAction:
    return next(
        (action for action in legal_actions if action.command.get("cmd") != "bench_view"),
        legal_actions[0],
    )
