"""确定性硬约束：计划校验、依赖检查、产物来源、成功步骤复用、finish 校验。

本模块不决定业务下一步——不通过时返回观察结果，交给 LLM。
"""

from __future__ import annotations

from typing import Any

from content_agent import results
from content_agent.config import BUSINESS_TOOLS
from content_agent.state import (
    STEP_FAILED,
    STEP_PENDING,
    STEP_SUCCEEDED,
    STEP_SUPERSEDED,
    RunState,
    Step,
)

CONTROL_TOOLS = ("update_plan", "finish")
ALL_PLAN_TOOLS = BUSINESS_TOOLS  # 计划步骤只能引用业务工具


def guard_rejected(code: str, message: str, **details: Any) -> dict[str, Any]:
    return results.fail("guard", code, message, retryable=False, guard_rejected=True, **details)


def validate_plan_steps(proposed: list[dict[str, Any]], state: RunState) -> dict[str, Any] | None:
    if not isinstance(proposed, list) or not proposed:
        return guard_rejected("INVALID_PLAN", "计划必须是非空步骤列表")

    ids: list[str] = []
    for raw in proposed:
        if not isinstance(raw, dict):
            return guard_rejected("INVALID_PLAN", "每个步骤必须是对象")
        for key in ("step_id", "name", "tool"):
            if not raw.get(key):
                return guard_rejected("INVALID_PLAN", f"步骤缺少字段：{key}")
        sid = str(raw["step_id"])
        if sid in ids:
            return guard_rejected("INVALID_PLAN", f"重复的 step_id：{sid}")
        ids.append(sid)
        if raw["tool"] not in ALL_PLAN_TOOLS:
            return guard_rejected("INVALID_PLAN", f"未知工具：{raw['tool']}")

    by_id = {str(s["step_id"]): s for s in proposed}

    # 禁止修改或删除已成功步骤
    for sid, step in state.steps.items():
        if step.status != STEP_SUCCEEDED:
            continue
        if sid not in by_id:
            return guard_rejected(
                "PROTECT_SUCCEEDED",
                f"不能删除已成功步骤 {sid}",
                protected_step=sid,
            )
        new = by_id[sid]
        if new["tool"] != step.tool:
            return guard_rejected(
                "PROTECT_SUCCEEDED",
                f"不能修改已成功步骤 {sid} 的工具",
                protected_step=sid,
            )
        if list(new.get("depends_on") or []) != list(step.depends_on):
            return guard_rejected(
                "PROTECT_SUCCEEDED",
                f"不能修改已成功步骤 {sid} 的依赖",
                protected_step=sid,
            )

    # 依赖存在、无自依赖、无环；save_plan 必须直接或间接依赖 estimate_cost
    for sid, raw in by_id.items():
        deps = list(raw.get("depends_on") or [])
        for dep in deps:
            if dep == sid:
                return guard_rejected("INVALID_DEPENDENCY", f"步骤 {sid} 不能依赖自己")
            if dep not in by_id and dep not in state.steps:
                return guard_rejected("INVALID_DEPENDENCY", f"步骤 {sid} 依赖了未知步骤 {dep}")

    if _has_cycle(by_id, state):
        return guard_rejected("INVALID_DEPENDENCY", "计划存在循环依赖")

    save_steps = [s for s in proposed if s["tool"] == "save_plan"]
    for save in save_steps:
        if not _depends_on_tool(str(save["step_id"]), "estimate_cost", by_id, state):
            return guard_rejected(
                "INVALID_PLAN",
                f"save_plan 步骤 {save['step_id']} 必须依赖 estimate_cost（直接或间接）",
            )
    return None


def _has_cycle(by_id: dict[str, dict[str, Any]], state: RunState) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def deps_of(sid: str) -> list[str]:
        if sid in by_id:
            return list(by_id[sid].get("depends_on") or [])
        step = state.steps.get(sid)
        return list(step.depends_on) if step else []

    def dfs(sid: str) -> bool:
        if sid in visiting:
            return True
        if sid in visited:
            return False
        visiting.add(sid)
        for dep in deps_of(sid):
            if dfs(dep):
                return True
        visiting.remove(sid)
        visited.add(sid)
        return False

    return any(dfs(sid) for sid in by_id)


def _depends_on_tool(
    step_id: str,
    tool: str,
    by_id: dict[str, dict[str, Any]],
    state: RunState,
) -> bool:
    seen: set[str] = set()

    def walk(sid: str) -> bool:
        if sid in seen:
            return False
        seen.add(sid)
        raw = by_id.get(sid)
        deps = list(raw.get("depends_on") or []) if raw else list(state.steps.get(sid).depends_on if state.steps.get(sid) else [])
        for dep in deps:
            dep_tool = None
            if dep in by_id:
                dep_tool = by_id[dep]["tool"]
            elif dep in state.steps:
                dep_tool = state.steps[dep].tool
            if dep_tool == tool or walk(dep):
                return True
        return False

    return walk(step_id)


def apply_plan_update(state: RunState, proposed: list[dict[str, Any]]) -> dict[str, Any]:
    rejection = validate_plan_steps(proposed, state)
    if rejection:
        return rejection

    new_ids = {str(s["step_id"]) for s in proposed}
    for sid, step in list(state.steps.items()):
        # 已成功步骤不可删除；pending/failed 可被替代方案取代
        if sid not in new_ids and step.status != STEP_SUCCEEDED:
            if step.status in (STEP_PENDING, STEP_FAILED):
                step.status = STEP_SUPERSEDED

    for raw in proposed:
        sid = str(raw["step_id"])
        existing = state.steps.get(sid)
        if existing and existing.status == STEP_SUCCEEDED:
            continue
        state.steps[sid] = Step(
            step_id=sid,
            name=str(raw["name"]),
            tool=str(raw["tool"]),
            depends_on=list(raw.get("depends_on") or []),
            status=existing.status if existing and existing.status == STEP_FAILED else STEP_PENDING,
            attempts=list(existing.attempts) if existing else [],
            artifact_id=existing.artifact_id if existing else None,
            error=existing.error if existing else None,
        )

    # 保持原成功步骤顺序，再追加新步骤
    ordered: list[str] = []
    for sid in state.step_order:
        if sid in state.steps and sid not in ordered:
            ordered.append(sid)
    for raw in proposed:
        sid = str(raw["step_id"])
        if sid not in ordered:
            ordered.append(sid)
    state.step_order = ordered
    return results.ok(
        "update_plan",
        {
            "step_order": list(state.step_order),
            "steps": [state.steps[sid].to_dict() for sid in state.step_order],
        },
    )


def check_dependencies(state: RunState, step: Step) -> dict[str, Any] | None:
    for dep in step.depends_on:
        dep_step = state.steps.get(dep)
        if dep_step is None:
            return guard_rejected("DEPENDENCY_MISSING", f"依赖步骤不存在：{dep}", step_id=step.step_id)
        if dep_step.status != STEP_SUCCEEDED:
            return guard_rejected(
                "DEPENDENCY_NOT_READY",
                f"依赖步骤 {dep} 状态为 {dep_step.status}，尚未成功",
                step_id=step.step_id,
                dependency=dep,
                dependency_status=dep_step.status,
            )
    return None


def check_attempt_limit(state: RunState, step: Step) -> dict[str, Any] | None:
    real_attempts = sum(1 for a in step.attempts if not a.reused)
    if real_attempts >= state.max_attempts_per_step:
        return results.fail(
            step.tool,
            "RETRY_EXHAUSTED",
            f"步骤 {step.step_id} 已达到单步真实执行上限 {state.max_attempts_per_step}，"
            "请改用替代方案或停止。本层不会自动重试。",
            retryable=False,
            step_id=step.step_id,
            attempts=real_attempts,
        )
    return None


# 参与复用比对的业务参数。忽略 reason（仅供 Trace）等非业务字段。
_REUSE_COMPARE_KEYS = {
    "search_materials": ("topic", "source", "limit"),
    "generate_script": ("material_ids", "format"),
    "estimate_cost": ("script_id",),
    "save_plan": ("script_id", "estimate_id"),
}


def _normalize_reuse_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_reuse_value(v) for v in value]
    return value


def business_args_for_reuse(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    keys = _REUSE_COMPARE_KEYS.get(tool, ())
    return {k: _normalize_reuse_value(args.get(k)) for k in keys}


def try_reuse_succeeded(
    state: RunState,
    step: Step,
    tool: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """成功步骤复用：工具名相同且业务参数一致才返回缓存。

    参数变化时不返回复用结果，由调用方拒绝并要求新建步骤，避免用旧产物冒充新请求。
    """
    if step.status != STEP_SUCCEEDED or step.tool != tool:
        return None
    if not step.attempts:
        return None
    last = next((a for a in reversed(step.attempts) if a.result.get("ok") and not a.reused), None)
    if last is None:
        last = next((a for a in reversed(step.attempts) if a.result.get("ok")), None)
    if last is None or not last.result.get("ok"):
        return None

    if args is not None:
        requested = business_args_for_reuse(tool, args)
        previous = business_args_for_reuse(tool, last.args)
        if requested != previous:
            return None  # 调用方应转为 ARGS_MISMATCH 拒绝，不得静默复用旧结果

    reused = results.ok(
        tool,
        {
            **(last.result.get("data") or {}),
            "reused": True,
            "from_step": step.step_id,
            "from_attempt": last.attempt_no,
        },
    )
    return reused


def reuse_or_reject_args_mismatch(
    state: RunState,
    step: Step,
    tool: str,
    args: dict[str, Any],
) -> dict[str, Any] | None:
    """若步骤已成功：参数一致则复用；不一致则拒绝（不得覆盖成功产物）。"""
    if step.status != STEP_SUCCEEDED or step.tool != tool:
        return None
    reused = try_reuse_succeeded(state, step, tool, args)
    if reused is not None:
        return reused
    if not step.attempts:
        return None
    last_ok = next((a for a in reversed(step.attempts) if a.result.get("ok")), None)
    if last_ok is None:
        return None
    return guard_rejected(
        "ARGS_MISMATCH_ON_SUCCEEDED",
        f"步骤 {step.step_id} 已成功。当前参数与成功时不一致，不能复用旧产物，"
        "也不能覆盖该步骤。请 update_plan 新增步骤并使用新的 step_id。",
        step_id=step.step_id,
        previous_args=business_args_for_reuse(tool, last_ok.args),
        requested_args=business_args_for_reuse(tool, args),
    )


def validate_finish(state: RunState, status: str) -> dict[str, Any] | None:
    if status == "incomplete":
        return None
    if status != "completed":
        return guard_rejected("INVALID_FINISH", f"finish.status 只能是 completed 或 incomplete，当前：{status}")

    # 仅当前有效且成功的 save_plan；superseded 不得参与完成判断
    saved = [
        s
        for s in state.steps.values()
        if s.tool == "save_plan" and s.status == STEP_SUCCEEDED
    ]
    if not saved:
        return guard_rejected(
            "FINISH_NOT_READY",
            "不能声明 completed：尚无成功的 save_plan 步骤",
        )
    return None


def compute_gap(state: RunState, cost_table: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """根据全部估算观察计算缺口。

    若已有同时满足预算与截止时间的估算，返回 None（不是「无可行方案」）。
    若传入完整费用表，额外给出全局最低成本证明（穷举全部 format），
    仅当全局最低成本仍超预算时标记 globally_infeasible_by_budget。
    """
    from content_agent.tools import global_min_cost

    estimates = list(state.artifacts.get("estimates", {}).values())
    if not estimates and cost_table is None:
        return None

    feasible = [
        e
        for e in estimates
        if e.get("within_budget") and e.get("meets_deadline")
    ]
    if feasible:
        return None

    observed_costs = [int(e["total_cost"]) for e in estimates if "total_cost" in e]
    budget_overs = [int(e.get("over_by") or 0) for e in estimates if e.get("over_by")]
    day_overs = [int(e.get("days_over") or 0) for e in estimates if e.get("days_over")]

    gap: dict[str, Any] = {
        "budget": state.budget,
        "deadline": state.deadline,
        "observed_costs": observed_costs,
        "observed_formats": [e.get("format") for e in estimates],
    }
    if observed_costs:
        gap["min_observed_cost"] = min(observed_costs)
    if budget_overs:
        gap["budget_gap"] = min(budget_overs)
        gap["budget_gap_scope"] = "observed_estimates_only"
    if day_overs:
        gap["deadline_gap_days"] = min(day_overs)

    if cost_table is not None:
        catalog = global_min_cost(cost_table)
        gap["global_min_cost"] = catalog["global_min_cost"]
        gap["global_costs_per_format"] = catalog["per_format"]
        gap["cheapest_formats"] = catalog["cheapest_formats"]
        if catalog["global_min_cost"] > state.budget:
            gap["globally_infeasible_by_budget"] = True
            gap["budget_gap"] = catalog["global_min_cost"] - state.budget
            gap["budget_gap_scope"] = "all_supported_formats"
        else:
            gap["globally_infeasible_by_budget"] = False
            if "budget_gap" in gap:
                gap["budget_gap_scope"] = "observed_estimates_only"

    if "budget_gap" not in gap and "deadline_gap_days" not in gap and not gap.get("globally_infeasible_by_budget"):
        return None if not estimates else gap
    return gap
