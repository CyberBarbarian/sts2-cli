# Self-Improving Experience Memory Plan

本文记录一个新的长期研究方向：让模型在 benchmark 游玩过程中维护一个可检索、可更新的经验库，并在后续决策中利用这些经验优化策略。这个方向类似 text gradient / textual feedback 的思想：模型不仅输出动作，还从结果中提炼文字形式的策略改进，持续更新一个外部知识库。

这个方案与 `turn_chat`、`memory_enabled` 的关系不同：

- `turn_chat`: 当前玩家出牌回合内的短 chat history，解决同一回合多步操作的局部连续性。
- `memory_enabled`: 单局 episode 内的短期事实记忆，解决最近若干动作和状态变化的可见性。
- `experience_memory`: 跨局、跨 seed、可冻结评估的长期经验库，解决“这个角色/敌人/遗物/卡牌组合应该怎么打”的策略知识积累。

因此 `experience_memory` 可以与 `single_turn` 或 `turn_chat` 同时存在。它不是 prompt 组织方法，而是一个检索增强的长期策略层。

## Research Questions

| Question | Why it matters |
|---|---|
| 经验库能否改善同一角色、同一难度的后续 run？ | 验证自我反思和策略积累是否有正向效果。 |
| Ironclad A0 学到的知识能否泛化到 Ironclad 更高 ascension？ | 验证同角色跨难度迁移。 |
| Ironclad 学到的通用战斗原则能否迁移到 Silent / Defect / Regent / Necrobinder？ | 验证角色无关的全局策略知识与角色专属知识的边界。 |
| 在线更新会不会污染评估？ | 如果边玩边学，必须区分 training mode 和 frozen evaluation mode。 |
| 模型自写经验会不会积累错误？ | 需要证据、置信度、反例和淘汰机制。 |

## Method Naming

建议把这个方向暂时命名为 `experience_memory`，也可以作为后续实验矩阵中的 M3：

| Name | Meaning |
|---|---|
| `M0 no_memory` | 原始 single-turn baseline。 |
| `M1 episode_memory` | 单局内 factual/action memory。 |
| `M2 turn_chat` | 玩家回合内 chat history。 |
| `M3 experience_memory` | 跨局经验库和自我改进。 |

`M3` 可以叠加在 `M0/M1/M2` 上，例如：

- `single_turn + experience_memory`
- `turn_chat + experience_memory`
- `turn_chat + experience_memory + frozen_eval`

但严肃对比时应一次只打开一个主要变量。

## Core Design

### Runtime Loop

```text
state + legal actions
      |
      v
build retrieval query
      |
      v
retrieve relevant experience entries
      |
      v
agent prompt = rules + state + legal actions + retrieved experience notes
      |
      v
model chooses one atomic action
      |
      v
environment transition
      |
      v
optional reflection/update pass writes candidate experience entries
```

关键原则：

- 经验库只提供建议，不是事实来源；当前 state 永远优先。
- 经验库不能包含当前 evaluation seed 的未来信息。
- evaluation 时经验库应冻结，不能边评估边更新。
- 更新经验库时必须记录 evidence，例如 source log、floor、encounter、death cause、action result。

### Experience Entry Schema

第一版建议用 JSONL 存储，便于程序读取；同时可以生成 Markdown 视图供人审阅。

```json
{
  "id": "exp_ironclad_lagavulin_0001",
  "status": "active",
  "scope": {
    "level": "character",
    "character": "Ironclad",
    "ascension_min": 0,
    "ascension_max": 20,
    "encounter": "Lagavulin Matriarch",
    "boss": null,
    "cards": ["Rampage", "Shrug It Off"],
    "relics": []
  },
  "trigger": "Act 1 boss Lagavulin Matriarch with Strength/Dexterity debuffs active",
  "lesson": "Do not wait until heavy debuffs stack before switching to defense or scaling damage.",
  "recommendation": "Prioritize early damage setup and preserve potions for the boss. If debuffs already reduce block/damage to near zero, recognize the fight is likely lost.",
  "anti_pattern": "Continuing low-impact attacks while ignoring that future turns will be debuffed below survival thresholds.",
  "evidence": [
    {
      "run_id": "bench_20260529_194446",
      "seed": "bench_0000",
      "act": 1,
      "floor": 17,
      "outcome": "death"
    }
  ],
  "confidence": 0.4,
  "updated_at": "2026-05-30"
}
```

字段说明：

| Field | Purpose |
|---|---|
| `scope.level` | `global`, `character`, `encounter`, `card`, `relic`, `archetype` 等。 |
| `trigger` | 检索时匹配当前状态的短描述。 |
| `lesson` | 从历史结果中学到的核心经验。 |
| `recommendation` | 决策时可执行的建议。 |
| `anti_pattern` | 应避免的错误模式。 |
| `evidence` | 经验的来源，防止无根据经验无限累积。 |
| `confidence` | 根据重复证据、胜负结果、人审或反例调整。 |
| `status` | `active`, `candidate`, `deprecated`, `contradicted`。 |

## Knowledge Scopes

经验库应分层，避免 Ironclad 专属知识错误污染其他角色。

| Scope | Example | Retrieval rule |
|---|---|---|
| Global | “不要对 engine preview damage/block 二次应用 Strength/Dexterity。” | 所有角色都可检索。 |
| Character | “Ironclad 可以更积极利用 Burning Blood 的战后回复。” | 只给对应角色，或迁移实验中显式允许。 |
| Ascension band | “高 ascension 下低 HP 事件风险更高。” | 按难度区间检索。 |
| Encounter | “Tunneler burrowed block 不清除，破 block 可 stun。” | 当前敌人匹配时检索。 |
| Boss | “Lagavulin Matriarch 的 debuff 会让后期 block/damage 失效。” | 当前 boss 或 boss path planning 时检索。 |
| Card/relic | “Pael's Eye extra-turn 条件是未出牌 end turn，不是普通存能。” | 当前 deck/relic 或手牌匹配时检索。 |
| Archetype | “高 deck size 时优先高影响卡，避免继续膨胀。” | deck/relic/card pattern 匹配时检索。 |

## Retrieval Design

第一版不需要复杂向量库。建议从可解释的检索开始：

1. 从当前 state 构造 query terms：
   - character, ascension, act, floor, room type
   - enemies, boss, elite/event/shop/rest context
   - current HP band, deck size band
   - visible hand cards, relics, potions
   - current decision type
2. 对 JSONL entry 做 keyword/BM25-like scoring：
   - exact enemy/boss match 权重最高
   - character match 次之
   - card/relic match 次之
   - global entries 作为低权重常驻候选
3. 取 top K 条，按 token budget 压缩成 prompt section。

Prompt section 示例：

```text
Experience notes, advisory only. Current game state overrides these notes.
- [global/conf=0.8] Card damage/block values are engine previews; do not apply visible Strength/Dexterity/Frail/Weak again.
- [encounter/conf=0.5] Tunneler keeps Burrowed block between turns; if you cannot remove block to stun, prioritize survival over small damage.
- [character/conf=0.4] Ironclad can trade some HP in hallway fights because Burning Blood heals after combat, but do not enter boss fights below a safe HP threshold.
```

控制项：

| Config | Default | Meaning |
|---|---:|---|
| `experience_memory.enabled` | `false` | 是否启用经验库检索。 |
| `experience_memory.store_path` | `sts2_bench/experience_memory/` | 经验库路径。 |
| `experience_memory.top_k` | `5` | 每次最多注入几条经验。 |
| `experience_memory.token_budget` | `800` | 经验库 prompt 最大预算。 |
| `experience_memory.include_global` | `true` | 是否总是允许 global 条目。 |
| `experience_memory.allow_cross_character` | `false` | 是否允许跨角色检索。 |
| `experience_memory.allow_cross_ascension` | `true` | 是否允许同角色跨难度检索。 |

## Update Design

经验库更新应分两种模式。

### Offline Reflection

先从 offline reflection 开始，风险最低。

```text
completed run log
      |
      v
reflection prompt
      |
      v
candidate experience entries
      |
      v
dedupe / merge / confidence update
      |
      v
human-readable diff for review
```

优点：

- 不影响当前 run。
- 可以用完整 log 做更准确的总结。
- 方便人审查候选经验，避免错误知识直接进入库。

触发点：

- 每局结束后。
- 每次死亡后。
- 每个 boss/elite 结束后。
- 出现 fallback、invalid action、明显 tactical blunder 后。

### Online Update

在线更新是后续阶段，不建议第一版直接用于严肃评估。

适用场景：

- training runs。
- agent 自我改进演示。
- 观察是否能快速修正重复错误。

限制：

- evaluation mode 必须冻结经验库。
- 在线写入的 entry 初始状态应为 `candidate`，不能默认 `active`。
- 只有重复证据或人审后才提升 confidence。

## Text-Gradient Style Reflection Prompt

反思 prompt 不应泛泛而谈，而应要求模型输出可检索、可验证、可执行的经验。

示例输入：

```text
You are updating an experience library for future STS2 benchmark decisions.
Extract only lessons that are likely to help future runs.
Do not invent hidden mechanics.
Each lesson must cite evidence from the run.
Separate global lessons from character-specific lessons.
Mark uncertain lessons as low confidence.
```

示例输出 schema：

```json
{
  "new_entries": [
    {
      "scope": {"level": "encounter", "encounter": "Tunneler"},
      "trigger": "Tunneler is Burrowed with high block and attacking",
      "lesson": "Removing all block can stun Tunneler, but if the current hand cannot remove the block, survival should be prioritized.",
      "recommendation": "Compare total available block-break damage to enemy block before spending attacks. Use redraw or block if break is impossible.",
      "anti_pattern": "Spending all energy on small attacks that leave block intact while taking full attack damage.",
      "confidence": 0.3,
      "evidence_refs": ["run=bench_20260529_183627 step=178"]
    }
  ],
  "updates": [
    {
      "id": "exp_preview_values_0001",
      "confidence_delta": 0.1,
      "reason": "Another run showed the model double-counted visible modifiers."
    }
  ],
  "deprecated_entries": []
}
```

## Generalization Experiments

不需要立刻跑大规模实验，但计划上要把 train/eval 拆清楚。

### Stage A: Same Character, Same Difficulty

| Train | Eval | Purpose |
|---|---|---|
| Ironclad A0 seeds 0-4 | Ironclad A0 seeds 5-9 | 验证经验库能否改善同分布表现。 |

比较：

- baseline: no experience memory
- frozen library: train 后冻结经验库再 eval
- online: 边 eval 边更新，单独记录但不作为严肃结论

### Stage B: Same Character, Higher Difficulty

| Train | Eval | Purpose |
|---|---|---|
| Ironclad A0 | Ironclad A5/A10 | 验证同角色跨 ascension 迁移。 |

注意：

- A0 学到的高风险路线策略可能在高 ascension 下过于激进。
- 需要记录哪些 entry 在高难度下失效，并降低 confidence 或加 ascension scope。

### Stage C: Cross Character Transfer

| Train | Eval | Purpose |
|---|---|---|
| Ironclad A0 global-only entries | Silent/Defect/Regent/Necrobinder A0 | 验证全局机制知识能否迁移。 |
| Ironclad full library | Other characters A0 | 故意测试污染风险，不作为默认设置。 |

默认只允许 `global` 和明确角色无关的 encounter/mechanic entries 迁移。角色专属卡牌、遗物、HP tradeoff 经验默认不迁移。

## Evaluation Metrics

Run-level:

- act / floor reached
- win rate
- death floor
- wall time
- total prompt/completion tokens
- fallback count
- invalid state count
- view action rate

Experience-specific:

- retrieved entry count per decision
- prompt token overhead from experience notes
- entries used in model reason
- entries contradicted by final result
- new candidate entries per run
- active/deprecated/confidence distribution

Generalization:

- source-trained vs target-eval delta
- same-character high-ascension delta
- cross-character delta
- negative transfer cases

## Implementation Plan

### Phase 1: Read-only Experience Retrieval

- Add structured store loader for JSONL entries.
- Add query builder from compact state.
- Add deterministic keyword scorer.
- Inject top K experience notes into prompt.
- Log retrieved entry ids and token count.
- No writing yet.

### Phase 2: Offline Reflection Writer

- Add script that reads benchmark logs and proposes candidate entries.
- Write candidates to a review file, not directly into active store.
- Add dedupe/merge by normalized trigger + scope.
- Add human-readable Markdown report.

### Phase 3: Frozen Evaluation Mode

- Add config:

```yaml
experience_memory:
  enabled: true
  mode: frozen
  store_path: sts2_bench/experience_memory/active.jsonl
  top_k: 5
  token_budget: 800
  allow_cross_character: false
  allow_cross_ascension: true
```

- Refuse to write updates in `frozen` mode.
- Store `experience_memory.store_digest` in `run_config` for reproducibility.

### Phase 4: Online Training Mode

- Add config:

```yaml
experience_memory:
  enabled: true
  mode: online_train
  candidate_path: sts2_bench/experience_memory/candidates.jsonl
  update_on: ["run_end", "death", "boss_end", "fallback"]
```

- Write candidate entries with source run id.
- Keep them inactive until promoted.

### Phase 5: Promotion / Deprecation

- Promote entries after:
  - repeated evidence across seeds, or
  - manual review, or
  - positive eval correlation.
- Deprecate entries after:
  - repeated contradictions, or
  - scoped failure on higher ascension / other characters.

## Tests

Unit tests:

- JSONL entry parsing and validation.
- Scope matching for character / ascension / encounter.
- Retrieval scoring order.
- Token budget truncation.
- Prompt injection includes “advisory only”.
- `frozen` mode never writes.
- `online_train` writes only candidates.
- Store digest changes when active store changes.

Integration tests:

- Run benchmark with a tiny fake experience store and assert retrieved ids appear in action meta/logs.
- Verify `run_config` records experience memory settings and store digest.
- Verify `allow_cross_character=false` excludes character-specific entries.

## Risks

| Risk | Mitigation |
|---|---|
| 错误经验被反复检索，放大坏策略。 | 记录 evidence/confidence/status；默认 candidate 需审核或重复证据后激活。 |
| evaluation 污染。 | 严格区分 `online_train` 和 `frozen`；eval 时记录 store digest。 |
| 经验库 token 过大。 | top K + token budget + compact notes。 |
| 跨角色负迁移。 | 默认只迁移 global entries；角色专属经验需显式开启。 |
| 模型把经验当成当前事实。 | prompt 中明确 “current state overrides experience notes”。 |
| 难以归因提升来源。 | 单独做 read-only retrieval / online update / turn_chat 组合消融。 |

## First Small Experiment

不需要先跑大规模实验。可以先做一个小验证：

1. 从已有三条 log 手工或 offline reflection 生成 5-10 条 candidate experience entries。
2. 只启用 read-only retrieval，不启用更新。
3. 使用同一个 seed 做 smoke rerun，观察：
   - prompt 是否正确注入经验；
   - 模型 reason 是否引用经验；
   - fallback/JSON 格式是否变差；
   - token overhead 是否可接受。
4. 再换一个未见 seed 做一次 sanity check，避免只记住 `bench_0000`。

第一批高价值经验候选：

- 当前 state 中展示的 card damage/block 和 enemy intent 是 engine preview，不要二次应用可见 modifiers。
- 一次只执行一个 atomic action；不要依赖后续计划，除非当前 action 本身创造出必要状态。
- Tunneler 的 Burrowed block 不会自动清除；若无法破 block stun，应优先生存或使用 redraw。
- Lagavulin Matriarch 的 Strength/Dexterity debuff 会让后期防御和输出急剧变差；需要更早建立输出/防御路线。
- view actions 不推进游戏；只有在信息能改变当前决策时才使用。
