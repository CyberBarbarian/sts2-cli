# sts2_bench

Python benchmark and RL scaffolding for the STS2 headless JSON protocol.

This package deliberately avoids the HTTP bridge under `agent/`.  It starts
`src/Sts2Headless` directly as a subprocess and communicates through
stdin/stdout JSON.  That keeps benchmark runs reproducible, easier to parallelize,
and closer to an RL environment.

## Layout

- `process.py` - owns one `Sts2Headless` subprocess.
- `actions.py` - converts each decision point into a dynamic legal-action list.
- `context.py` - renders compact LLM-facing state inspired by `python/play.py`.
- `agents.py` - random baseline and OpenAI-compatible local LLM agent.
- `runner.py` - programmatic benchmark loop.
- `run_benchmark.py` - command-line benchmark runner.
- `env.py` - dependency-free RL-style environment with action masks.

## Quick Smoke Test

Show CLI options without starting the game:

```bash
python3 -m sts2_bench.run_benchmark --help
```

Start the headless process and read the ready message:

```bash
python3 -m sts2_bench.process
```

## Random Baseline

Run one random-policy game:

```bash
python3 -m sts2_bench.run_benchmark \
  --agent random \
  --character Ironclad \
  --ascension 0 \
  --count 1 \
  --out results/random_ironclad_a0.jsonl
```

The output JSONL contains every compact state, legal action list, selected
action, and final result.

## Local LLM Benchmark

The LLM agent expects an OpenAI-compatible chat completions endpoint.  Examples:
Ollama, LM Studio, vLLM, llama.cpp server.

Ollama example:

```bash
ollama serve
ollama pull qwen2.5:14b
```

Run benchmark:

```bash
python3 -m sts2_bench.run_benchmark \
  --agent llm \
  --base-url http://127.0.0.1:11434/v1 \
  --model qwen2.5:14b \
  --character Ironclad \
  --ascension 0 \
  --seeds sts2_bench/seeds_ironclad_a0.json \
  --out results/qwen25_14b_ironclad_a0.jsonl
```

The prompt asks the model to return only:

```json
{"action_id": 0, "reason": "short reason"}
```

The model never needs to invent raw game commands.  `actions.py` generates all
legal commands from the current state, and the model picks one by id.

## RL Environment

`env.py` exposes a minimal dependency-free interface:

```python
from sts2_bench.env import Sts2Env

env = Sts2Env(character="Ironclad", ascension=0)
obs, info = env.reset(seed="rl_seed_0001")
mask = info["action_mask"]
legal = info["legal_actions"]

obs, reward, terminated, truncated, info = env.step(0)
env.close()
```

For Gymnasium/SB3 integration, wrap `Sts2Env` and use:

- `obs` from `compact_state()`, or your own numeric encoder.
- `info["action_mask"]` for dynamic valid actions.
- `info["legal_actions"][idx]["cmd"]` as the raw command mapping.

## Design Notes

The current LLM context keeps the important human-facing information from
`python/play.py`, but formats it for models:

- act, floor, room, boss
- player HP, block, gold, deck size, relics, potions
- combat energy, incoming damage, draw/discard counts
- enemy HP, block, intents, moves, powers
- hand cards with cost, type, playability, target type, and exposed stats
- map, card reward, event, shop, rest, treasure, and selection options

This is intentionally a benchmark scaffold, not a solved policy.  Serious RL
work should add a numeric encoder and tune rewards separately from the
terminal win/floor metrics used for benchmark comparison.
