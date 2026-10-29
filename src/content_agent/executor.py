"""工具调度：守卫 →（复用或真实执行）→ record_attempt → 持久化。

本模块不会在工具失败后自动重试。失败观察原样返回，供 LLM 决策。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from content_agent import results
from content_agent.config import BUSINESS_TOOLS
from content_agent.guards import (
    apply_plan_update,
    check_attempt_limit,
    check_dependencies,
    check_save_plan_artifacts,
    compute_gap,
    guard_rejected,
    reuse_or_reject_args_mismatch,
    validate_finish,
)
from content_agent.state import (
    RUN_COMPLETED,
    RUN_INCOMPLETE,
    STEP_FAILED,
    STEP_SUPERSEDED,
    STEP_SUCCEEDED,
    RunState,
    record_attempt,
    save_state,
)
from content_agent.tools import ToolRuntime


class ToolExecutor:
    def __init__(self, runtime: ToolRuntime, runs_dir: Path):
        self.runtime = runtime
        self.runs_dir = Path(runs_dir)

    def dispatch(self, state: RunState, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        args = dict(args or {})
        if tool == "update_plan":
            observation = self._update_plan(state, args)
        elif tool == "finish":
            observation = self._finish(state, args)
        elif tool in BUSINESS_TOOLS:
            observation = self._run_business(state, tool, args)
        else:
            observation = results.fail(tool, "UNKNOWN_TOOL", f"未知工具：{tool}")

        save_state(state, self.runs_dir)
        return observation

    def _update_plan(self, state: RunState, args: dict[str, Any]) -> dict[str, Any]:
        steps = args.get("steps")
        if steps is None:
            return guard_rejected("INVALID_PLAN", "update_plan 需要 steps 参数")
        return apply_plan_update(state, steps)

    def _finish(self, state: RunState, args: dict[str, Any]) -> dict[str, Any]:
        status = args.get("status")
        rejection = validate_finish(state, str(status) if status is not None else "")
        if rejection:
            return rejection

        if status == "completed":
            state.status = RUN_COMPLETED
            state.reason = None
            state.message = args.get("summary") or "方案已保存"
            state.gap = None
        else:
            state.status = RUN_INCOMPLETE
            state.reason = args.get("reason") or "incomplete"
            state.message = args.get("summary") or args.get("reason") or "任务未完成"
            state.gap = compute_gap(state, cost_table=self.runtime.costs)

        return results.ok(
            "finish",
            {
                "status": state.status,
                "reason": state.reason,
                "message": state.message,
                "gap": state.gap,
                "finished": True,
            },
        )

    def _run_business(self, state: RunState, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        step_id = args.get("step_id")
        if not step_id:
            return guard_rejected("MISSING_STEP_ID", "业务工具必须提供 step_id")

        step = state.get_step(str(step_id))
        if step is None:
            return guard_rejected(
                "STEP_NOT_IN_PLAN",
                f"步骤 {step_id} 不在当前计划中，请先调用 update_plan",
                step_id=step_id,
            )
        if step.status == STEP_SUPERSEDED:
            # 废弃步骤不得再执行，也不得被 record_attempt 改回 succeeded
            return guard_rejected(
                "STEP_SUPERSEDED",
                f"步骤 {step_id} 已被废弃（superseded），不能再执行。"
                "请使用当前计划中有效的 step_id。",
                step_id=step_id,
            )
        if step.tool != tool:
            return guard_rejected(
                "TOOL_MISMATCH",
                f"步骤 {step_id} 计划工具是 {step.tool}，不能执行 {tool}",
                step_id=step_id,
            )

        reuse_decision = reuse_or_reject_args_mismatch(state, step, tool, args)
        if reuse_decision is not None:
            if reuse_decision.get("ok"):
                record_attempt(step, tool=tool, args=args, result=reuse_decision, reused=True)
            # 参数不一致的拒绝不写入 attempts，避免污染成功步骤历史
            return reuse_decision

        dep_err = check_dependencies(state, step)
        if dep_err:
            return dep_err

        lineage_err = check_save_plan_artifacts(state, step, args)
        if lineage_err:
            return lineage_err

        limit_err = check_attempt_limit(state, step)
        if limit_err:
            # 达到上限也记入 attempts，状态保持/设为 failed，但不增加 execution_counts
            record_attempt(step, tool=tool, args=args, result=limit_err)
            return limit_err

        try:
            observation = self.runtime.execute(state, tool, args)
        except Exception as exc:  # noqa: BLE001 - 工具层兜底，避免进程无报告退出
            observation = results.fail(
                tool,
                "TOOL_EXCEPTION",
                f"工具执行未预期异常：{exc}",
                retryable=True,
            )
        injected = bool((observation.get("error") or {}).get("injected"))
        record_attempt(step, tool=tool, args=args, result=observation, injected=injected)

        if observation.get("ok") and tool == "save_plan":
            # 成功保存不等于运行完成；是否 finish 由 LLM 决定。
            # 但硬约束已在 save_plan 内复核。
            pass
        if not observation.get("ok") and step.status != STEP_FAILED:
            step.status = STEP_FAILED
        return observation
