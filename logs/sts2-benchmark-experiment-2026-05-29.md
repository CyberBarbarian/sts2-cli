# STS2 Benchmark Experiment 2026-05-29

## Purpose

Compare three agent-side context variants on the same benchmark setup:

- `no_memory`: single-turn prompt, no episode memory.
- `memory`: single-turn prompt plus factual-diff episode memory.
- `turn_chat`: short chat history within the current player combat turn, no episode memory.
- `plan_flag_single_turn`: follow-up smoke run with `turn_chat.plan.enabled=true`, but `context_management.mode=single_turn`.

This is a single-seed smoke experiment, not a statistically meaningful benchmark. Treat the result as a debugging and qualitative comparison record.

## Common Setup

| Field | Value |
|---|---|
| Model | `deepseek-chat` |
| API style | OpenAI-compatible, `https://api.deepseek.com` |
| Character / ascension | `Ironclad`, A0 |
| Seed | `bench_0000` |
| Count | `1` |
| Max steps | `500` |
| Prompt style | `analysis` |
| Include compact JSON state | `false` |
| Run summary | `false` |
| LLM timeout / retries | `30s`, `0` retries |
| LLM temperature | `0.0` |
| Include full map | `true` |
| Allow repeat views | `false` |
| Terminal logging | `print_prompts=true`, `print_model_output=true` |
| JSONL log level | `metrics` |

Important reproducibility note: all three runs recorded the same `logging.out` path:
`./results/deepseek-chat-analysis-2026-05-29-10-00-00.jsonl`.
That structured JSONL file may have been overwritten by later runs. The preserved source of truth for this record is the terminal logs under `logs/`.

## Run Index

| Variant | Log file | Run config source | Result source | Distinguishing configuration |
|---|---|---:|---:|---|
| `turn_chat` | `logs/bench_20260529_183627.log` | line 1 | line 34300 | `context_management.mode=turn_chat`, `turn_chat.window=10`, `assistant_history=compact`, `memory_enabled=false` |
| `memory` | `logs/bench_20260529_191001.log` | line 1 | line 39885 | `context_management.mode=single_turn`, `memory_enabled=true`, `memory_mode=factual_diff`, `memory_window=8` |
| `no_memory` | `logs/bench_20260529_194446.log` | line 1 | line 24999 | `context_management.mode=single_turn`, `memory_enabled=false` |
| `plan_flag_single_turn` | `logs/bench_20260531_172852.log` | line 1 | line 42192 | `context_management.mode=single_turn`, `turn_chat.plan.enabled=true`, `memory_enabled=false`; actual printed prompts do not contain `turn_plan` because `turn_chat` was not enabled |

Important caveat for the 2026-05-31 run: this log is useful as a follow-up single-turn smoke result, but it is not a clean `turn_chat + plan` experiment. The run config sets `turn_chat.plan.enabled=true`, yet `context_management.mode` remains `single_turn`, and the printed prompt schema remains the normal `analysis` schema without `turn_plan`.

## Detailed Result Table

| Variant | Final progress | Outcome | Final state | Step/action stats | View usage | Model reliability | Runtime | Token usage from printed `usage` records | Qualitative end-state analysis |
|---|---|---|---|---|---|---|---:|---:|---|
| `memory` | Act 2, floor 7 | Death, no truncation, no runner error | `hp=0/80`, `gold=159`, `deck_size=30` | `steps=300`, `game_action_count=297` | 3 view actions, all `view_deck`; view action rate `1.00%` | `model_fallback_count=0`, `invalid_states=0` | `2049.4s` / `34.16m` | 300 usage records; prompt `712,092`; completion `227,401`; total `939,493`; avg prompt `2,373.6`; avg completion `758.0` | Best progress of the three. Died on Act 2 floor 7 against Slumbering Beetle. The final lethal state was already forced: `8 HP`, `8 block`, `0 energy`, no potions, enemy attack would kill. The important earlier issue was strategic/arithmetic: the model chose `Shining Strike` expecting it to enable later Defends, but after the atomic action the state had `0 energy`, so the planned multi-card survival line was impossible. It also still sometimes double-counted enemy Strength despite the prompt warning, though the final death remained lethal either way. |
| `plan_flag_single_turn` | Act 2, floor 8 | Death, no truncation, no runner error | `hp=0/80`, `gold=394`, `deck_size=30` | `steps=343`, `game_action_count=341` | 2 view actions, all `view_deck`; view action rate `0.58%` | `model_fallback_count=0`, `invalid_states=0` | `2014.2s` / `33.57m` | 343 usage records; prompt `578,333`; completion `238,251`; total `816,584`; avg prompt `1,686.1`; avg completion `694.6` | Reached the deepest floor in this smoke set, but this should not be attributed to `turn_plan`: the run was still `single_turn`, and no `turn_plan` instructions appeared in the printed prompts. Died on Act 2 floor 8 elite fight against Entomancer. Final state had `5 HP`, `0 block`, `5/3 energy`, no potions, enemy at `41/145` with `Attack 19`, and only `21` total playable damage plus `5` block available, so every line was lethal. Near the end, step 340 briefly double-counted Strength on a `4x7` intent, then step 341 corrected that displayed intent already included Strength. |
| `turn_chat` | Act 2, floor 6 | Death, no truncation, no runner error | `hp=0/80`, `gold=158`, `deck_size=33` | `steps=236`, `game_action_count=235` | 1 view action, `view_deck`; view action rate `0.42%` | `model_fallback_count=1`, `invalid_states=0` | `1252.6s` / `20.88m` | 235 usage records for 236 model-output sections; prompt `639,530`; completion `125,712`; total `765,242`; avg prompt `2,721.4`; avg completion `534.9` | Second-best progress by act/floor. Died on Act 2 floor 6 against Exoskeletons. Final state had `15 HP`, `0 block`, `0 energy`, one `Liquid Bronze`, and remaining enemy attacks exceeded survival. The final decision to end turn was reasonable because the potion could not prevent death. The transcript shows one fallback in the run, and the final combat history suggests the chat context kept recent action continuity, but it still did not prevent entering a low-HP, no-defense forced-death state. |
| `no_memory` | Act 1, floor 17 | Death, no truncation, no runner error | `hp=0/80`, `gold=193`, `deck_size=24` | `steps=209`, `game_action_count=209` | 0 view actions; view action rate `0.00%` | `model_fallback_count=0`, `invalid_states=0` | `1272.9s` / `21.21m` | 209 usage records; prompt `334,272`; completion `136,954`; total `471,226`; avg prompt `1,599.4`; avg completion `655.3` | Worst progress. Died on Act 1 floor 17 boss fight against Lagavulin Matriarch. Final state was `10 HP`, boss at `73/222`, player had `Strength(-4)` and `Dexterity(-4)`, and available block/damage was effectively too weak. The final decision was locally sensible: no action could prevent lethal damage. Compared with the other variants, it used the fewest tokens and no view actions, but reached a substantially worse endpoint. |

## Metric Summary

| Variant | Rank by reached progress | Reached boss/encounter at death | Steps | Total tokens | Avg prompt tokens | Avg completion tokens | Fallbacks | Notes |
|---|---:|---|---:|---:|---:|---:|---:|---|
| `plan_flag_single_turn` | 1 | Act 2 floor 8, Entomancer | 343 | 816,584 | 1,686.1 | 694.6 | 0 | Deepest progress in this log set, but not evidence for `turn_plan` because `context_management.mode=single_turn` prevented plan prompt injection. |
| `memory` | 2 | Act 2 floor 7, Slumbering Beetle | 300 | 939,493 | 2,373.6 | 758.0 | 0 | Longest original run; highest wall time and total token use. |
| `turn_chat` | 3 | Act 2 floor 6, Exoskeletons | 236 | 765,242 | 2,721.4 | 534.9 | 1 | More prompt tokens per call than memory because chat transcript is carried within turns; fewer completion tokens per call. |
| `no_memory` | 4 | Act 1 floor 17, Lagavulin Matriarch | 209 | 471,226 | 1,599.4 | 655.3 | 0 | Cheapest run by tokens, but stopped before Act 2. |

## Prompt / Strategy Observations

| Variant | Strengths observed | Weaknesses observed | Likely action item |
|---|---|---|---|
| `memory` | Factual-diff memory helped preserve recent combat facts and produced the deepest run. It made more information requests than other variants, especially deck inspection. | The model still planned multi-action turns even though the environment only executes one atomic action at a time. It misread at least one card/resource interaction in a lethal turn. | Add stronger prompt pressure around "choose one atomic action only" and "do not rely on planned later actions unless this action itself creates the needed state." Consider adding card-result examples to memory or prompt. |
| `turn_chat` | Compact assistant history preserved local turn context and reduced repeated full-state re-analysis within a turn. Final decisions were coherent in immediate lethal states. | Prompt size per call was highest. One fallback occurred. Local history did not guarantee better strategic pathing or HP preservation. | Investigate the fallback entry and compare turn-level transcripts around the forced-death fight. Consider lowering `turn_chat.window` or adding stricter compact history fields. |
| `no_memory` | Cheapest and simplest baseline. No parsing fallbacks or invalid states. | Lost before Act 2. The prompt lacks persistent strategic context, so long-run decisions may be less coherent. It also made no view requests, which may indicate underuse of available information. | Keep as baseline, but do not use it as the main M2 candidate unless future multi-seed runs contradict this single-seed result. |
| `plan_flag_single_turn` | Reached Act 2 floor 8 with no fallback and relatively low average prompt tokens compared with the original `memory` and `turn_chat` runs. Final forced-death analysis was mostly coherent. | This was not an active plan-prompt run: `turn_chat.plan.enabled=true` was recorded, but `context_management.mode=single_turn` meant the actual prompt stayed normal analysis format. The model still showed tactical arithmetic instability near the end, including a temporary double-count of enemy Strength. | Rerun with `context_management.mode=turn_chat` and `turn_chat.plan.enabled=true` before drawing any conclusion about the plan mechanism. Also record whether `turn_plan` appears in the first combat prompt. |

## Initial Conclusion

For the original 2026-05-29 single-seed set, `memory` reached the best endpoint, followed by `turn_chat`, then `no_memory`.
The later 2026-05-31 `plan_flag_single_turn` run reached Act 2 floor 8, but it should be treated separately because the plan flag was enabled without enabling `turn_chat`, so the plan prompt was not actually active.
The result does not prove the memory variant is generally superior; it only shows that on `bench_0000`, the factual-diff memory run survived one floor deeper than turn-chat and reached Act 2 while the original no-memory baseline died to the Act 1 boss.

The most important correctness issue across variants is still local tactical reasoning under the atomic-action API. The model often analyzes full-turn plans, but the runner executes exactly one action and then re-prompts. This can make a locally plausible plan fail if the first action does not itself preserve survival or resources.

## Follow-up Recommendations

| Priority | Recommendation | Reason |
|---|---|---|
| High | Use unique `out` paths per run, e.g. include variant and timestamp. | Prevent JSONL trace overwrite and make later automated analysis reliable. |
| High | Run at least 5-10 fixed seeds per variant. | Single-seed variance is too high for method selection. |
| Medium | Add a prompt rule or validator note for cards that create energy/resources. | The memory run's final mistake came from relying on an expected multi-action continuation after an atomic action. |
| Medium | Parse and compare fallback locations. | `turn_chat` had one fallback; knowing whether it happened near a critical decision matters. |
| Medium | Track per-run final encounter and death cause in structured JSONL. | Reduces manual log inspection for future benchmark summaries. |
