"""Benchmark and RL helpers for the STS2 headless JSON protocol."""

__all__ = [
    "LegalAction",
    "Sts2Process",
    "build_legal_actions",
    "build_llm_prompt",
    "compact_state",
]


def __getattr__(name):
    if name == "Sts2Process":
        from .process import Sts2Process

        return Sts2Process
    if name in {"LegalAction", "build_legal_actions"}:
        from .actions import LegalAction, build_legal_actions

        return {"LegalAction": LegalAction, "build_legal_actions": build_legal_actions}[name]
    if name in {"build_llm_prompt", "compact_state"}:
        from .context import build_llm_prompt, compact_state

        return {"build_llm_prompt": build_llm_prompt, "compact_state": compact_state}[name]
    raise AttributeError(name)
