# 评估报告

本文只记录**实际执行过**的结果。单元测试为确定性 Mock/无模型；正式真实场景均为 DeepSeek（`llm_mode=real`），除非 meta 标明探索性或模拟。

## 1. 证据分层：历史运行 vs 修复后验证

| 类别 | 含义 | 主要路径 |
| --- | --- | --- |
| 历史正式证据 | 独立审查修复**之前**真实 DeepSeek 跑通并归档；**未改写 Trace** | `examples/T01_normal/` … `T08_max_steps/`、`T04_budget_overrun/` |
| 修复后验证 | 独立审查缺陷修复后的确定性回归 + 真实模型复跑 | `examples/unit_tests/pytest_final_pre_commit.txt`；`examples/T04_budget_overrun_post_fix/`；`examples/T02_missing_constraints/` |
| 集中优化后验证 | save 血缘 / finish 一致性 / CLI 展示之后 | `examples/unit_tests/pytest_post_opt.txt`；`examples/T01_normal_post_opt/`；`examples/T04_budget_overrun_post_opt/` |
| Mock / 探索性 | 仅流程或非正式 | `--llm mock`；`examples/T04_exploratory/`（`formal_acceptance=false`） |

评审时：动态决策主证据仍看历史 T01/T03/T04/T05 等 Trace；修复后以 post_fix 与单元测试证明守卫/指纹/参数校验未破坏真实重规划能力。

## 2. 测试分层

| 层 | 命令 / 位置 | 证明什么 |
| --- | --- | --- |
| 单元测试 | `python -m pytest -q` | 硬约束、幂等、守卫、续跑；**不证明**模型决策 |
| 真实场景（历史） | `examples/T0x_*/` | 真实 Tool Calling 与动态路径 |
| 真实场景（修复后） | `examples/T04_budget_overrun_post_fix/` | 修复后仍能超限重规划 |
| Mock CLI | `--llm mock` | 仅流程；不得当决策证据 |

提交前全量单元测试（集中优化后）：`examples/unit_tests/pytest_post_opt.txt`（**84 passed**）。

## 3. 场景总表

| ID | 场景 | LLM | 最终状态 | 费用 | 保存 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | 正常完成 | real | completed | 10 | 是 | `examples/T01_normal/`（历史） |
| T02 | 缺预算/截止 | 无 | incomplete/`missing_constraints` | — | 否 | `examples/T02_missing_constraints/` + pytest |
| T03 | 工具失败 | real | completed | 10 | 是 | `examples/T03_tool_failure/`（历史） |
| T04 | 预算超限重规划 | real | completed | 10 | 是 | 历史：`T04_budget_overrun/`；修复后复跑：`T04_budget_overrun_post_fix/` |
| T05 | 无可行方案 | real | incomplete/infeasible | 未保存 | 否 | `examples/T05_infeasible/`（历史） |
| T06 | 幂等重复保存 | real | completed×2 | 8 | 第二次 duplicate | `examples/T06_idempotent/`（历史） |
| T07 | 失败续跑 | real | s1 incomplete → s2 completed | 8 | 是 | `examples/T07_resume/`（历史） |
| T08 | 执行上限 | real | incomplete/`max_steps_reached` | — | 否 | `examples/T08_max_steps/`（历史） |

另：`examples/T04_exploratory/` 为阶段 C 探索性运行（`formal_acceptance=false`）。

## 4. 分场景说明

### T01 正常完成（历史）

- 输入：主题「夏季新品发布」，预算 15，截止 2026-11-20  
- 行为：update_plan → search → generate(`video_basic`) → estimate(10) → save → finish  
- 结果：completed；方案已保存  

### T02 缺少约束（修复后补齐落盘）

- 预期：不调用 LLM，不擅自补全  
- 实际：缺 `budget` / 缺 `deadline` 均退出码 2，`reason=missing_constraints`，`llm_calls=0`，`tool_calls=0`  
- 证据：`examples/T02_missing_constraints/`；`tests/test_cli_validation.py`  

### T03 工具失败（历史）

- 注入：`search_materials:1` → `SOURCE_UNAVAILABLE`  
- 模型改用 `backup` 源后完成（非程序自动重试）  
- 失败 attempts 保留  

### T04 预算超限

**历史正式证据**（`examples/T04_budget_overrun/`）：

- 输入含「高质量视频」，预算 10  
- 关键：`video_premium` 估 12 / `within_budget=false` → 重规划 → `video_basic` 估 10 → 保存  
- 当时指纹算法尚未纳入 outline；该次保存相对探索性运行曾出现 `duplicate=true`（见 `idempotency_note.json`）  

**修复后真实复跑**（`examples/T04_budget_overrun_post_fix/`，**不覆盖**历史目录）：

- 命令同历史 T04；`run_id=20261029T105429Z_ea82aee8`  
- 再次观察到 premium=12 超限后改 basic=10；`search_materials` 仅执行 1 次；`status=completed`，`total_cost=10`，`duplicate=false`（新指纹含 outline）  
- `llm_mode=real`，`model=deepseek-flash`  

### T05 无可行方案（历史）

- 预算 5；观察均超限；未成功保存  
- `gap.budget_gap=3`；全局最低成本 8 > 5 → `globally_infeasible_by_budget`  

### T06 幂等（历史 + 修复后单元测试）

- 历史真实双跑：同内容第二次 `duplicate=true`  
- 修复后：指纹含规范化 outline；同内容复用、outline 变化新建——`tests/test_store_idempotency.py`；提交前手工核对 `FINGERPRINT_OK`  

### T07 / T08（历史）

- T07：失败注入后续跑；成功步骤复用；`MAX_CUMULATIVE_STEPS`  
- T08：`--max-steps 2` → `max_steps_reached`  

## 5. 两条以上真实决策路径（对比）

| 路径 | 证据 | 差异点 |
| --- | --- | --- |
| 直接完成 | T01 | 未触发超限 |
| 超限后重规划 | T04（历史）+ T04_post_fix | 先 12 后 10 |
| 失败换源 | T03 | 注入失败后 backup |
| 不可行停止 | T05 | incomplete + gap |

## 6. 修复后专项核对

| 项 | 结果 |
| --- | --- |
| 非法参数（如 `material_ids` 含 dict） | 结构化 `INVALID_ARGUMENTS`；成功步骤不变；无虚假脚本产物；可 JSON 回传模型 |
| superseded 步骤 | 拒绝执行，不得改回 succeeded |
| 幂等指纹 | 同内容（含 outline）复用；outline 变化新建；随机 script/estimate/run id 不进指纹 |
| 全量 pytest | 74 passed |

## 7. 偏差与限制

1. 模型路径非确定性：同输入可能选不同 format；断言约束与不变量，不要求固定调用顺序  
2. T05 的 `reason` 可为模型长文本；结构化以 `gap` 与全局费用表为准  
3. Mock 不得作为真实决策证据  
4. 指纹含 outline 后，与审查前旧 `saved_plans/index.json` 混用可能无法命中旧指纹；新证据目录已分开保留  
5. 本仓库不提交 `.env`；评审需自备 Key 复现真实场景  

## 8. 单元测试与辅助脚本

覆盖：费用/工期、守卫、幂等、失败注入、状态持久化、续跑、累计上限、CLI 缺约束、superseded、非法参数、完整 Mock 路径等。详见 `tests/`。

| 脚本 | 用途 |
| --- | --- |
| `scripts/probe_tool_calling.py` | 最小真实 Tool Calling 探测 |
| `scripts/archive_run.py` | 归档 `runs/<run_id>` → `examples/`，不改写 Trace |
