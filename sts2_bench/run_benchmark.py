"""Command-line runner for STS2 benchmark policies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import JsonlLogger, agent_from_args, run_one, summarize


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run STS2 headless benchmark policies.")
    parser.add_argument("--agent", choices=["random", "llm"], default="random")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:11434/v1")
    parser.add_argument("--model", default=None, help="Local model name for --agent llm")
    parser.add_argument("--api-key", default="local")
    parser.add_argument("--character", default="Ironclad", choices=["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"])
    parser.add_argument("--ascension", type=int, default=0)
    parser.add_argument("--lang", default="en", choices=["en", "zh"])
    parser.add_argument("--seeds", default=None, help="JSON seed file")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--out", default=None, help="JSONL trace output path")
    parser.add_argument("--print-prompts", action="store_true", help="Print the LLM prompt for every decision before acting")
    parser.add_argument("--include-full-map", action="store_true", help="Always fetch and render the full map at map_select decisions")
    args = parser.parse_args(argv)

    agent = agent_from_args(args.agent, base_url=args.base_url, model=args.model, api_key=args.api_key)
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
