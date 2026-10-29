"""系统提示与状态摘要。

不写入任何固定业务答案（例如「超预算就选图文」），只说明目标、约束与工具用途。
费用数字只能通过 estimate_cost 观察。
"""

from __future__ import annotations

import json
from typing import Any

from content_agent.state import RunState


SYSTEM_PROMPT = """你是内容活动方案规划 Agent。目标：在用户给定的预算与截止时间内，规划并完成一份内容活动方案。

你必须通过工具完成工作，不要只输出自然语言。每一轮请调用恰好一个工具。

可用业务工具：
1. search_materials：按主题检索合成素材库（source 可选 primary 或 backup）。
2. generate_script：基于素材生成脚本。format 可选 video_premium、video_basic、graphic（描述侧重内容形式，价格只能通过估算工具获知）。
3. estimate_cost：由程序按费用表计算成本与工期，并对照预算与截止时间；你不得自行编造费用数字。
4. save_plan：在预算与截止时间复核通过后保存方案；相同方案不会重复落盘。

可用控制工具：
5. update_plan：提交或调整任务计划（含 step_id、依赖）。已成功步骤不得删除或改工具。
6. finish：结束任务。status=completed 仅在 save_plan 已成功时允许；否则用 incomplete 并说明原因。

硬约束由程序执行：
- 缺少预算或截止时间不会进入本对话（已在入口拒绝）。
- 预算不得超限；截止时间必须满足。
- 失败步骤不得标记为成功；保存前会重新验证。
- 工具失败时你会收到错误观察，由你决定重试、换方案或停止；程序不会自动替你重试。

请区分两类观察，不要混用结束原因：
- 临时工具故障：error.retryable=true（如 SOURCE_UNAVAILABLE）。可重试、换 backup 源或换步骤；若最终无法恢复，finish(incomplete, reason=tool_failure)。
- 业务约束不满足：estimate_cost 返回 within_budget=false / meets_deadline=false，或 save_plan 返回 CONSTRAINT_VIOLATION（retryable=false）。应 update_plan 换方案并重新估算，或 finish(incomplete, reason=infeasible)。不得用旧脚本的 estimate_id 保存新脚本。

每个工具调用请在参数里提供简短 reason，说明为何选择该动作（写入 Trace，不是隐藏思维）。
先 update_plan，再按依赖执行业务工具；全部完成后调用 finish。
"""


def format_catalog(formats: dict[str, str]) -> str:
    lines = ["可选内容形式（仅描述，不含价格）："]
    for name, desc in formats.items():
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def state_summary(state: RunState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "topic": state.topic,
        "budget": state.budget,
        "deadline": state.deadline,
        "today": state.today,
        "status": state.status,
        "steps_used": state.steps_used,
        "max_steps": state.max_steps,
        "plan": [
            {
                "step_id": sid,
                "name": state.steps[sid].name,
                "tool": state.steps[sid].tool,
                "depends_on": state.steps[sid].depends_on,
                "status": state.steps[sid].status,
                "artifact_id": state.steps[sid].artifact_id,
                "last_error": state.steps[sid].error,
                "attempt_count": len(state.steps[sid].attempts),
            }
            for sid in state.step_order
            if sid in state.steps
        ],
        "artifacts": {
            "material_ids": [
                k
                for k, v in state.artifacts.get("materials", {}).items()
                if isinstance(v, dict) and "title" in v
            ],
            "script_ids": list(state.artifacts.get("scripts", {})),
            "estimate_ids": list(state.artifacts.get("estimates", {})),
            "plan_ids": list(state.artifacts.get("plans", {})),
        },
    }


def user_task_message(state: RunState, formats: dict[str, str]) -> str:
    payload = {
        "task": {
            "topic": state.topic,
            "budget": state.budget,
            "deadline": state.deadline,
            "today": state.today,
            "budget_unit": "模拟单位（整数）",
        },
        "formats": formats,
        "instruction": "请开始规划并执行，直到保存方案或明确无法完成。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_schemas() -> list[dict[str, Any]]:
    return [
        _fn(
            "update_plan",
            "提交或调整任务计划。已成功步骤必须原样保留。",
            {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {"type": "string"},
                            "name": {"type": "string"},
                            "tool": {
                                "type": "string",
                                "enum": [
                                    "search_materials",
                                    "generate_script",
                                    "estimate_cost",
                                    "save_plan",
                                ],
                            },
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["step_id", "name", "tool"],
                    },
                },
                "reason": {"type": "string"},
            },
            ["steps", "reason"],
        ),
        _fn(
            "search_materials",
            "检索与主题相关的素材。",
            {
                "step_id": {"type": "string"},
                "topic": {"type": "string"},
                "source": {"type": "string", "enum": ["primary", "backup"]},
                "limit": {"type": "integer"},
                "reason": {"type": "string"},
            },
            ["step_id", "reason"],
        ),
        _fn(
            "generate_script",
            "基于素材生成脚本。价格不可在此工具获知。",
            {
                "step_id": {"type": "string"},
                "material_ids": {"type": "array", "items": {"type": "string"}},
                "format": {
                    "type": "string",
                    "enum": ["video_premium", "video_basic", "graphic"],
                },
                "reason": {"type": "string"},
            },
            ["step_id", "material_ids", "format", "reason"],
        ),
        _fn(
            "estimate_cost",
            "由程序计算成本与工期，并对照预算与截止时间。",
            {
                "step_id": {"type": "string"},
                "script_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            ["step_id", "script_id", "reason"],
        ),
        _fn(
            "save_plan",
            "复核约束后保存方案；相同方案幂等。",
            {
                "step_id": {"type": "string"},
                "script_id": {"type": "string"},
                "estimate_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            ["step_id", "script_id", "estimate_id", "reason"],
        ),
        _fn(
            "finish",
            "结束任务。completed 仅在保存成功后允许。",
            {
                "status": {"type": "string", "enum": ["completed", "incomplete"]},
                "summary": {"type": "string"},
                "reason": {"type": "string"},
            },
            ["status", "reason"],
        ),
    ]


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
