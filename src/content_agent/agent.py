"""真实 LLM 动态决策循环。

下一步动作由模型选择；硬约束与状态由 ToolExecutor / guards 执行。
本模块不含「超预算就换某种格式」等业务分支。

计数约定：
- steps_used / MAX_STEPS：Agent 决策步（每次 LLM 响应计 1）。守卫拒绝、非法参数、无 tool_call 均计入。
- step.attempts（非 reused）：该步骤的调用尝试（含 RETRY_EXHAUSTED）。
- execution_counts：通过守卫后真实执行工具的次数（失败注入按此计数）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_agent.executor import ToolExecutor
from content_agent.llm import LLMClient, LLMResponse
from content_agent.prompts import SYSTEM_PROMPT, state_summary, tool_schemas, user_task_message
from content_agent.state import (
    RUN_COMPLETED,
    RUN_INCOMPLETE,
    RunState,
    resume_summary,
    save_state,
)
from content_agent.tools import ToolRuntime
from content_agent.trace import TraceWriter

# 连续无效响应（无 tool_call / 全部解析失败）上限，防止空转
MAX_INVALID_STREAK = 3


class ContentAgent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        executor: ToolExecutor,
        runtime: ToolRuntime,
        runs_dir: Path,
    ):
        self.llm = llm
        self.executor = executor
        self.runtime = runtime
        self.runs_dir = Path(runs_dir)

    def run(self, state: RunState, *, is_resume: bool = False) -> dict[str, Any]:
        run_dir = self.runs_dir / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trace = TraceWriter(
            run_dir / "trace.jsonl",
            run_id=state.run_id,
            llm_mode=self.llm.mode,
            model=self.llm.model_name,
        )
        formats = self.runtime.available_formats()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _formats_block(formats)},
        ]
        if is_resume:
            messages.append(
                {
                    "role": "user",
                    "content": "续跑任务上下文（由程序根据 state.json 生成）：\n"
                    + json.dumps(resume_summary(state), ensure_ascii=False, indent=2),
                }
            )
            trace.emit(
                "session_resume",
                session=state.session,
                constraints=_constraints(state),
                llm_mode=self.llm.mode,
                cumulative_steps=state.cumulative_steps,
                succeeded_steps=[
                    sid for sid, step in state.steps.items() if step.status == "succeeded"
                ],
            )
        else:
            messages.append({"role": "user", "content": user_task_message(state, formats)})
            trace.emit(
                "run_start",
                session=state.session,
                constraints=_constraints(state),
                llm_mode=self.llm.mode,
            )
        save_state(state, self.runs_dir)

        invalid_streak = 0
        finished = False

        if state.cumulative_steps >= state.max_cumulative_steps:
            state.status = RUN_INCOMPLETE
            state.reason = "max_cumulative_steps_reached"
            state.message = (
                f"累计决策步已达全局上限 {state.max_cumulative_steps}，拒绝继续执行"
            )
            trace.emit(
                "run_end",
                session=state.session,
                status=state.status,
                reason=state.reason,
                message=state.message,
                steps_used=state.steps_used,
                cumulative_steps=state.cumulative_steps,
            )
            save_state(state, self.runs_dir)
            report = build_report(state, llm_mode=self.llm.mode, model=trace.model)
            (run_dir / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            return report

        while (
            state.steps_used < state.max_steps
            and state.cumulative_steps < state.max_cumulative_steps
            and not finished
        ):
            # 每轮附带最新状态摘要，帮助模型在长对话中对齐事实
            turn_messages = list(messages) + [
                {
                    "role": "user",
                    "content": "当前状态摘要（由程序生成，以工具观察为准）：\n"
                    + json.dumps(state_summary(state), ensure_ascii=False),
                }
            ]

            try:
                response = self.llm.complete(turn_messages, tool_schemas())
            except Exception as exc:  # noqa: BLE001 - 需要把网络/API 错误交回运行报告
                state.steps_used += 1
                state.cumulative_steps += 1
                state.status = RUN_INCOMPLETE
                state.reason = "llm_error"
                state.message = f"LLM 调用失败：{exc}"
                trace.emit(
                    "llm_error",
                    step_index=state.steps_used,
                    error=str(exc),
                    status=state.status,
                    reason=state.reason,
                )
                save_state(state, self.runs_dir)
                break

            state.steps_used += 1
            state.cumulative_steps += 1
            step_index = state.steps_used
            trace.model = response.model or self.llm.model_name

            if not response.tool_calls:
                invalid_streak += 1
                messages.append(response.raw_assistant_message)
                messages.append(
                    {
                        "role": "user",
                        "content": "你必须调用恰好一个工具。请不要只回复文本。",
                    }
                )
                trace.emit(
                    "llm_no_tool",
                    step_index=step_index,
                    content=response.content,
                    finish_reason=response.finish_reason,
                    invalid_streak=invalid_streak,
                )
                if invalid_streak >= MAX_INVALID_STREAK:
                    state.status = RUN_INCOMPLETE
                    state.reason = "llm_error"
                    state.message = "模型连续未调用工具"
                    break
                save_state(state, self.runs_dir)
                continue

            # 协议：完整保留 assistant tool_calls；若返回多个，逐一执行并各自回传 tool message
            messages.append(response.raw_assistant_message)
            if len(response.tool_calls) > 1:
                trace.emit(
                    "multiple_tool_calls",
                    step_index=step_index,
                    count=len(response.tool_calls),
                    names=[tc.name for tc in response.tool_calls],
                )

            for tc in response.tool_calls:
                if tc.parse_error or tc.arguments is None:
                    observation = {
                        "ok": False,
                        "tool": tc.name,
                        "data": None,
                        "error": {
                            "code": "INVALID_TOOL_ARGUMENTS",
                            "message": tc.parse_error or "参数无效",
                            "retryable": True,
                            "arguments_raw": tc.arguments_raw[:500],
                        },
                    }
                    invalid_streak += 1
                else:
                    invalid_streak = 0
                    before = _step_snapshot(state)
                    try:
                        observation = self.executor.dispatch(state, tc.name, tc.arguments)
                    except Exception as exc:  # noqa: BLE001 - 兜底为观察，交回模型/报告
                        observation = {
                            "ok": False,
                            "tool": tc.name,
                            "data": None,
                            "error": {
                                "code": "EXECUTOR_EXCEPTION",
                                "message": f"调度未预期异常：{type(exc).__name__}: {exc}",
                                "retryable": True,
                            },
                        }
                    after = _step_snapshot(state)
                    trace.emit(
                        "tool_result",
                        session=state.session,
                        step_index=step_index,
                        tool=tc.name,
                        tool_call_id=tc.id,
                        arguments=tc.arguments,
                        reason=(tc.arguments or {}).get("reason"),
                        observation=_compact_observation(observation),
                        state_before=before,
                        state_after=after,
                        source="llm",
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(observation, ensure_ascii=False, default=str),
                    }
                )

                if observation.get("ok") and (observation.get("data") or {}).get("finished"):
                    finished = True
                    break

            if not any(tc.arguments is not None and not tc.parse_error for tc in response.tool_calls):
                if invalid_streak >= MAX_INVALID_STREAK:
                    state.status = RUN_INCOMPLETE
                    state.reason = "llm_error"
                    state.message = "模型连续返回无法解析的工具参数"
                    break

            save_state(state, self.runs_dir)

            if state.steps_used >= state.max_steps and not finished and state.status != RUN_COMPLETED:
                break

        if not finished and state.status != RUN_COMPLETED:
            if state.reason is None:
                if state.cumulative_steps >= state.max_cumulative_steps:
                    state.status = RUN_INCOMPLETE
                    state.reason = "max_cumulative_steps_reached"
                    state.message = (
                        f"已达到跨会话累计决策步上限 {state.max_cumulative_steps}，任务未完成"
                    )
                elif state.steps_used >= state.max_steps:
                    state.status = RUN_INCOMPLETE
                    state.reason = "max_steps_reached"
                    state.message = f"已达到最大执行步数 {state.max_steps}，任务未完成"
                else:
                    state.status = RUN_INCOMPLETE
                    state.reason = "incomplete"
            trace.emit(
                "run_end",
                session=state.session,
                status=state.status,
                reason=state.reason,
                message=state.message,
                steps_used=state.steps_used,
                cumulative_steps=state.cumulative_steps,
            )
        else:
            trace.emit(
                "run_end",
                session=state.session,
                status=state.status,
                reason=state.reason,
                message=state.message,
                steps_used=state.steps_used,
                cumulative_steps=state.cumulative_steps,
            )

        save_state(state, self.runs_dir)
        report = build_report(state, llm_mode=self.llm.mode, model=trace.model)
        (run_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return report


def build_report(state: RunState, *, llm_mode: str, model: str | None) -> dict[str, Any]:
    estimates = list(state.artifacts.get("estimates", {}).values())
    plans = list(state.artifacts.get("plans", {}).values())
    latest_estimate = estimates[-1] if estimates else None
    saved = plans[-1] if plans else None
    total_cost = None
    cost_note = None
    if saved:
        total_cost = saved.get("total_cost")
        cost_note = "已保存方案复核费用"
    elif latest_estimate:
        total_cost = latest_estimate.get("total_cost")
        cost_note = "未保存；取最近一次成功估算"

    return {
        "run_id": state.run_id,
        "session": state.session,
        "status": state.status,
        "reason": state.reason,
        "message": state.message,
        "gap": state.gap,
        "llm_mode": llm_mode,
        "model": model,
        "constraints": _constraints(state),
        "plan": [state.steps[sid].to_dict() for sid in state.step_order if sid in state.steps],
        "tool_execution_counts": dict(state.execution_counts),
        "steps_used": state.steps_used,
        "cumulative_steps": state.cumulative_steps,
        "max_steps": state.max_steps,
        "max_cumulative_steps": state.max_cumulative_steps,
        "total_cost": total_cost,
        "cost_note": cost_note,
        "saved_plan": saved,
        "trace_path": str(Path("runs") / state.run_id / "trace.jsonl"),
        "state_path": str(Path("runs") / state.run_id / "state.json"),
    }


def _constraints(state: RunState) -> dict[str, Any]:
    return {
        "topic": state.topic,
        "budget": state.budget,
        "deadline": state.deadline,
        "today": state.today,
    }


def _formats_block(formats: dict[str, str]) -> str:
    lines = ["可选内容形式（仅描述，不含价格）："]
    for name, desc in formats.items():
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def _step_snapshot(state: RunState) -> dict[str, str]:
    return {sid: step.status for sid, step in state.steps.items()}


def _compact_observation(observation: dict[str, Any]) -> dict[str, Any]:
    """Trace 中保留关键字段，避免过大 outline 刷屏。"""
    data = observation.get("data")
    if isinstance(data, dict):
        slim = {k: v for k, v in data.items() if k != "outline"}
        if "outline" in data:
            slim["outline_preview"] = list(data["outline"])[:3]
        return {**observation, "data": slim}
    return observation
