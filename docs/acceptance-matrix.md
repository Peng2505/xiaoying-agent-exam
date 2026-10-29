# 官方验收证据矩阵

图例：✅ 已真实验证 | ⚠ 有限制说明 | ❌ 未验证（本表无此项）

| 官方要求 | 实现位置 | 测试 | 实际结果 | 证据路径 |
| --- | --- | --- | --- | --- |
| 真实模型选择工具 | `agent.py` + `llm.py` | T01/T03/T04 真实运行 | ✅ DeepSeek 返回 tool_calls | `examples/T01_normal/trace.jsonl` 等 |
| 工具结果反馈后再决策 | `agent.py` 消息回传 | T03/T04 | ✅ 失败/超限观察后下一步不同 | T03/T04 trace |
| ≥2 条不同真实路径 | 同上 | T01 vs T04（及 T03/T05） | ✅ | `docs/03-evaluation.md` §4 |
| 正常完成 | 全链路 | T01 | ✅ completed，已保存 | `examples/T01_normal/` |
| 缺预算或截止时间 | `cli.validate_constraints` | `test_cli_validation.py` + T02 落盘 | ✅ 不调用 LLM；不擅自补全 | `examples/T02_missing_constraints/` |
| 工具失败恢复 | 注入 + 模型决策 | T03 | ✅ 换 backup 后完成 | `examples/T03_tool_failure/` |
| 预算超限重规划 | 无硬编码分支 | T04 + 修复后复跑 | ✅ 12→重规划→10 | 历史 `T04_budget_overrun/`；修复后 `T04_budget_overrun_post_fix/` |
| 保留成功步骤 | `guards` PROTECT + reuse | T04/T07 | ✅ 检索未重跑 | T04/T07 state |
| 无可行方案停止 | `finish` + `compute_gap` | T05 | ✅ incomplete；未保存；全局最低成本 8>5 | `examples/T05_infeasible/` |
| 重复执行/幂等 | `store.compute_fingerprint`（含规范化 outline） | T06 + 单元测试 | ✅ duplicate=true 同 plan_id；outline 变化新建 | `examples/T06_idempotent/`；`tests/test_store_idempotency.py` |
| 废弃步骤不可再执行 | `executor` STEP_SUPERSEDED | 回归测试 | ✅ 不得恢复为 succeeded | `tests/test_superseded_guard.py` |
| 非法工具参数不崩溃 | `tools._validate_args` + 异常兜底 | 回归测试 | ✅ 结构化错误；无虚假产物 | `tests/test_tool_arg_validation.py` |
| 执行上限 | `MAX_STEPS` | T08 + mock 上限测试 | ✅ max_steps_reached | `examples/T08_max_steps/` |
| 保存前复核预算时间 | `tools.save_plan` | 单元测试超限拒绝 | ✅ CONSTRAINT_VIOLATION | `tests/test_tools.py` |
| save 产物须来自依赖链 | `check_save_plan_artifacts` | 回归测试 | ✅ 无关 estimate 拒绝 | `tests/test_save_dependency_artifacts.py` |
| finish 与当前计划一致 | `validate_finish` | 回归测试 | ✅ 未完成必需步骤不可 completed | `tests/test_finish_plan_consistency.py` |
| CLI 可读报告 / JSON | `display.py` + `--output` | CLI 测试 | ✅ 默认 text；json 可解析 | `tests/test_cli_display.py` |
| 失败不标成功 | `record_attempt` | T03/T07 | ✅ failed attempts 保留 | state.json |
| 步数上限未完成状态 | `agent.py` | T08 | ✅ | T08 report |
| 运行记录含步骤/参数/摘要 | `trace.py` | 各 T0x | ✅ | `*/trace.jsonl` |
| 可复制运行命令 | README | 复现检查 | ✅ | `README.md` |
| 不提交真实密钥 | `.gitignore` + `.env.example` | 仓库检查 | ✅ `.env` 被忽略 | `.gitignore` |
| 续跑（加分） | `--resume` | T07 | ✅ | `examples/T07_resume/` |
| 跨会话防绕过单步上限（增强） | `MAX_CUMULATIVE_STEPS` | `test_resume.py` | ✅ 单元验证 | tests |

## 特别强调

1. **真实自主选工具**：T01/T03/T04/T05 的 `meta.json` 均为 `llm_mode=real`、`model=deepseek-flash`  
2. **观察后再决策**：T04 在 `within_budget=false` 之后才出现第二次 generate/estimate  
3. **两条路径**：T01（直接完成）与 T04（超限重规划）对比即可  
4. **T04 duplicate**：幂等复用，见 `idempotency_note.json`，不改原 Trace  
5. **T05 全局不可行**：基于当前 `costs.json` 全部 format，见 `feasibility_note.json`  

未配置 API Key 时不得将真实场景标为通过；本仓库证据为已配置环境下真实跑出并归档。
