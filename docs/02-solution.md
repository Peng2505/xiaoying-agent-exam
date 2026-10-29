# 解决方案

## 1. 架构

单 Agent + ToolExecutor，无多 Agent、无 LangGraph。

| 模块 | 职责 |
| --- | --- |
| `cli.py` | 参数、缺约束拒绝、`--resume`；默认中文报告，`--output json` / `--verbose` |
| `display.py` | 人类可读报告与进度文案（数据来自真实 report/state） |
| `llm.py` | OpenAI 兼容客户端；DeepSeek `thinking.disabled`；Mock 仅流程 |
| `agent.py` | 决策循环、步数/累计上限、消息协议；可选进度回调 |
| `executor.py` | 调度：守卫 → 复用/执行 → `record_attempt` → 落盘 |
| `guards.py` | 计划/依赖/save 血缘/`finish` 计划一致性/`compute_gap` |
| `tools.py` | 四个业务工具 + 失败注入计数 |
| `store.py` | 指纹幂等保存（含规范化 outline） |
| `state.py` / `trace.py` | 状态与 JSONL Trace |

## 2. 动态决策循环

1. LLM 读任务与状态摘要  
2. 返回 tool_calls（保留完整 assistant 消息）  
3. 校验参数 JSON；守卫检查依赖与计划  
4. ToolExecutor 执行并写 Trace  
5. tool message 按 `tool_call_id` 回传  
6. 模型继续或 `finish`  

**不做的事**：代码不硬编码「超预算就选图文」；不自动替模型重试业务工具。

## 3. 工具设计

统一返回 `{ok, tool, data, error}`。

| 工具 | 要点 |
| --- | --- |
| `search_materials` | primary/backup；注入 `SOURCE_UNAVAILABLE` |
| `generate_script` | format 三选一；工具描述不暴露价格 |
| `estimate_cost` | 代码算费用；`within_budget` 为观察 |
| `save_plan` | 重算后校验；指纹幂等；**script/estimate 必须来自当前依赖链成功步骤** |
| `update_plan` / `finish` | 控制工具；`finish(completed)` 要求当前有效计划全部必需步骤成功且存在有效 save；`optional`/`superseded` 不阻碍 |

## 4. 状态与恢复

- 步骤状态只经 `record_attempt` 按工具 `ok` 变更；attempts 只追加  
- 成功步骤复用：工具名 + 业务参数一致才缓存；否则 `ARGS_MISMATCH_ON_SUCCEEDED`  
- `--resume`：加载 state，生成续跑摘要，清除注入（除非再指定）；同 run_id 追加 Trace，`session` 区分  
- 单步 `MAX_ATTEMPTS_PER_STEP`；会话 `MAX_STEPS`；跨会话 `MAX_CUMULATIVE_STEPS`（防无限新建 step_id）

## 5. 预算、工期与不可行

- 费用表：`video_premium=12`、`video_basic=10`、`graphic=8`  
- 保存前按脚本重算；超限 → `CONSTRAINT_VIOLATION`（`retryable=false`）  
- `compute_gap`：综合已观察估算；若传入费用表则穷举全部 format，标记 `globally_infeasible_by_budget`  
- **边界**：全局证明仅覆盖当前模拟费用表中的支持格式集合

## 6. 幂等

指纹 = topic + budget + deadline + format + material_ids + resource_items + total_cost 的规范化哈希。同指纹返回原 `plan_id` 且 `duplicate=true`。

## 7. 技术取舍

| 选择 | 原因 |
| --- | --- |
| 原生循环而非 LangGraph | 代码量可控、决策边界清晰、便于解释 |
| DeepSeek 非思考模式 | 官方 Tool Calling 示例推荐；避免 reasoning_content 回传复杂度 |
| CLI | 考试允许三选一；评审复现成本低 |
| 工具本地 Mock + 真实模型 | 符合「工具可 Mock、模型决策需真实」 |

## 8. 异常语义

| 类型 | 特征 | 期望模型行为 |
| --- | --- | --- |
| 临时故障 | `retryable=true`（如注入 STORAGE_ERROR） | 重试 / 换源 / 停 |
| 业务约束 | `within_budget=false` 或 `CONSTRAINT_VIOLATION` | 重规划或 `infeasible` |
| 决策上限 | `max_steps_reached` / `max_cumulative_steps_reached` | 停止，不伪造成功 |
