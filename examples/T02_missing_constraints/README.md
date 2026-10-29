# T02 缺少关键约束（无 LLM）

证明：缺少 `budget` 或 `deadline` 时，CLI 在进入 Agent / LLM 之前确定性拒绝，**不会**调用模型，也**不会**擅自补全约束。

| 用例 | 命令要点 | 退出码 | 输出 | 说明 |
| --- | --- | --- | --- | --- |
| 缺 budget | `--topic` + `--deadline` + `--today`，无 `--budget` | 2 | `missing_budget_output.json` | `llm_calls=0`，`tool_calls=0`，`missing=["budget"]` |
| 缺 deadline | `--topic` + `--budget` + `--today`，无 `--deadline` | 2 | `missing_deadline_output.json` | `llm_calls=0`，`tool_calls=0`，`missing=["deadline"]` |

本场景**不是**真实模型决策证据；对应验收点为硬约束拒识。单元测试见 `tests/test_cli_validation.py`。
