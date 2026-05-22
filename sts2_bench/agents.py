"""Policy agents used by benchmark runners."""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
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


def build_llm_prompt(
    state: dict[str, Any],
    legal_actions: list[LegalAction],
    *,
    include_json: bool = True,
    prompt_style: PromptStyle = "default",
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


def _prompt_header(prompt_style: PromptStyle) -> list[str]:
    if prompt_style == "analysis":
        return [
            "You are playing Slay the Spire 2 through a headless benchmark environment.",
            "Choose exactly one legal action. Use only an action_id from the legal action list.",
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
            "For map choices, compare path rewards and risks. For rewards, compare deck impact. For view actions, choose them only when the missing information is worth spending a decision step.",
        ]

    return [
        "You are playing Slay the Spire 2 through a headless benchmark environment.",
        "Choose exactly one legal action. Return only JSON with this schema:",
        '{"action_id": <integer>, "reason": "<short reason>"}',
    ]


class RandomAgent:
    """Simple non-LLM baseline."""

    def __init__(self, seed: int | None = None, *, prompt_style: PromptStyle = "default") -> None:
        self.rng = random.Random(seed)
        self.prompt_style = prompt_style

    def build_prompt(self, state: dict[str, Any], legal_actions: list[LegalAction]) -> str:
        return build_llm_prompt(state, legal_actions, prompt_style=self.prompt_style)

    def choose(
        self,
        state: dict[str, Any],
        legal_actions: list[LegalAction],
        *,
        prompt: str | None = None,
    ) -> tuple[LegalAction, dict[str, Any]]:
        action = self.rng.choice(legal_actions)
        return action, {"agent": "random"}


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
    include_json_state: bool = True
    max_retries: int = 2
    prompt_style: PromptStyle = "default"

    def build_prompt(self, state: dict[str, Any], legal_actions: list[LegalAction]) -> str:
        return build_llm_prompt(
            state,
            legal_actions,
            include_json=self.include_json_state,
            prompt_style=self.prompt_style,
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
        # still recording the invalid model behavior.
        fallback = legal_actions[0]
        return fallback, {
            "agent": "openai_compat",
            "model": self.model,
            "fallback": True,
            "error": last_error,
            "prompt_chars": len(prompt),
        }

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
