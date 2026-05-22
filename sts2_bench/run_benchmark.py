"""Command-line runner for STS2 benchmark policies."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .runner import JsonlLogger, agent_from_args, run_one, summarize


ROOT = Path(__file__).resolve().parents[1]


def load_seeds(path: str | None, count: int) -> list[str]:
    if not path:
        return [f"bench_{i:04d}" for i in range(count)]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        seeds = []
        for item in data:
            if isinstance(item, str):
                seeds.append(item)
            elif isinstance(item, dict) and item.get("seed"):
                seeds.append(str(item["seed"]))
            else:
                raise ValueError(f"Unsupported seed entry: {item!r}")
        return seeds
    raise ValueError("Seed file must be a JSON list of strings or objects with a seed field")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Load a simple .env file without adding a runtime dependency.

    Existing shell environment variables win over .env values. CLI arguments
    then win over both because argparse uses these values only as defaults.
    """

    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()

        os.environ.setdefault(key, value)


def env_str(name: str, default: str | None = None, *, fallbacks: tuple[str, ...] = ()) -> str | None:
    for key in (name, *fallbacks):
        value = os.environ.get(key)
        if value:
            return value
    return default


def env_int(name: str, default: int) -> int:
    value = env_str(name)
    return int(value) if value is not None else default


def env_bool(name: str, default: bool = False) -> bool:
    value = env_str(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value, got {value!r}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run STS2 headless benchmark policies.")
    parser.add_argument("--agent", choices=["random", "llm"], default=env_str("STS2_BENCH_AGENT", "random"))
    parser.add_argument(
        "--base-url",
        default=env_str("STS2_BENCH_BASE_URL"),
        help="OpenAI-compatible base URL, e.g. http://127.0.0.1:11434/v1",
    )
    parser.add_argument("--model", default=env_str("STS2_BENCH_MODEL"), help="Model name for --agent llm")
    parser.add_argument(
        "--api-key",
        default=env_str("DEEPSEEK_API_KEY", "local", fallbacks=("OPENAI_API_KEY",)),
    )
    parser.add_argument(
        "--prompt-style",
        choices=["default", "analysis"],
        default=env_str("STS2_BENCH_PROMPT_STYLE", "default"),
        help="LLM prompt style. 'analysis' asks for structured situation analysis and calculations.",
    )
    parser.add_argument(
        "--character",
        default=env_str("STS2_BENCH_CHARACTER", "Ironclad"),
        choices=["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"],
    )
    parser.add_argument("--ascension", type=int, default=env_int("STS2_BENCH_ASCENSION", 0))
    parser.add_argument("--lang", default=env_str("STS2_BENCH_LANG", "en"), choices=["en", "zh"])
    parser.add_argument("--seeds", default=env_str("STS2_BENCH_SEEDS"), help="JSON seed file")
    parser.add_argument("--count", type=int, default=env_int("STS2_BENCH_COUNT", 1))
    parser.add_argument("--max-steps", type=int, default=env_int("STS2_BENCH_MAX_STEPS", 2000))
    parser.add_argument("--out", default=env_str("STS2_BENCH_OUT"), help="JSONL trace output path")
    parser.add_argument(
        "--print-prompts",
        action=argparse.BooleanOptionalAction,
        default=env_bool("STS2_BENCH_PRINT_PROMPTS", False),
        help="Print the LLM prompt for every decision before acting",
    )
    parser.add_argument(
        "--print-model-output",
        action=argparse.BooleanOptionalAction,
        default=env_bool("STS2_BENCH_PRINT_MODEL_OUTPUT", False),
        help="Print the raw agent/model output and selected action for every decision",
    )
    parser.add_argument(
        "--include-full-map",
        action=argparse.BooleanOptionalAction,
        default=env_bool("STS2_BENCH_INCLUDE_FULL_MAP", False),
        help="Always fetch and render the full map at map_select decisions",
    )
    args = parser.parse_args(argv)

    agent = agent_from_args(
        args.agent,
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        prompt_style=args.prompt_style,
    )
    seeds = load_seeds(args.seeds, args.count)
    logger = JsonlLogger(args.out)
    results = []
    try:
        for seed in seeds:
            result = run_one(
                agent=agent,
                seed=seed,
                character=args.character,
                ascension=args.ascension,
                lang=args.lang,
                max_steps=args.max_steps,
                logger=logger,
                print_prompts=args.print_prompts,
                print_model_output=args.print_model_output,
                include_full_map=args.include_full_map,
            )
            results.append(result)
            print(json.dumps({"seed": seed, "result": result.to_dict()}, ensure_ascii=False), flush=True)
        print(json.dumps({"summary": summarize(results)}, ensure_ascii=False, indent=2))
        return 0 if all(result.error is None for result in results) else 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
