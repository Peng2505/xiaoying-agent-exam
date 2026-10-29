"""CLI 人类可读报告与进度输出。数据一律来自实际 report/state，不硬编码演示内容。"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from content_agent.state import RunState


def format_text_report(report: dict[str, Any], state: RunState | None = None) -> str:
    lines: list[str] = []
    status = report.get("status")
    constraints = report.get("constraints") or {}
    saved = report.get("saved_plan")
    gap = report.get("gap")

    lines.append("=" * 56)
    lines.append("内容任务规划 Agent · 运行报告")
    lines.append("=" * 56)
    lines.append(f"主题：{constraints.get('topic') or report.get('message') or '（无）'}")
    lines.append(
        f"模型：{report.get('model') or '（未知）'}　模式：{report.get('llm_mode') or '（未知）'}"
    )
    lines.append(f"运行 ID：{report.get('run_id')}")
    lines.append(f"最终状态：{_status_label(status)}")
    if report.get("reason"):
        lines.append(f"原因码：{report.get('reason')}")
    if report.get("message"):
        lines.append(f"说明：{report.get('message')}")
    lines.append("")

    # 约束
    if constraints.get("budget") is not None:
        lines.append("【约束】")
        lines.append(f"  预算：{constraints.get('budget')} 模拟单位")
        lines.append(f"  截止日期：{constraints.get('deadline')}")
        lines.append(f"  起算日期：{constraints.get('today')}")
        lines.append("")

    # 步骤
    plan = report.get("plan") or []
    if plan:
        lines.append("【Agent 步骤】")
        for step in plan:
            opt = "（可选）" if step.get("optional") else ""
            lines.append(
                f"  - {step.get('step_id')}: {step.get('name')} "
                f"[{step.get('tool')}] → {_step_status_label(step.get('status'))}{opt}"
            )
        lines.append("")

    # 素材 / 脚本 / 成本（优先用 state 真实产物）
    materials_summary = _materials_summary(state, report)
    if materials_summary:
        lines.append("【检索素材摘要】")
        for row in materials_summary:
            lines.append(f"  - {row}")
        lines.append("")

    script_summary = _script_summary(state, report, saved)
    if script_summary:
        lines.append("【内容形式与脚本大纲】")
        lines.append(f"  形式：{script_summary.get('format')}")
        lines.append("  说明：当前工具生成的是脚本大纲，不是完整成品脚本。")
        for i, line in enumerate(script_summary.get("outline") or [], 1):
            lines.append(f"  {i}. {line}")
        lines.append("")

    cost_block = _cost_block(state, report, saved, constraints)
    if cost_block:
        lines.extend(cost_block)
        lines.append("")

    # 保存
    lines.append("【保存结果】")
    if saved:
        dup = bool(saved.get("duplicate"))
        if dup:
            lines.append(
                f"  复用已有方案（幂等），plan_id={saved.get('plan_id')}；未新建文件。"
            )
        else:
            lines.append(f"  已新建保存，plan_id={saved.get('plan_id')}")
        if saved.get("path"):
            lines.append(f"  路径：{saved.get('path')}")
        if saved.get("total_cost") is not None:
            lines.append(f"  复核费用：{saved.get('total_cost')} 模拟单位")
    else:
        lines.append("  未保存方案。")
    lines.append("")

    # 失败 / 缺口
    if status != "completed":
        lines.append("【未完成说明】")
        lines.append(f"  状态不是成功完成（当前：{_status_label(status)}）。")
        if gap:
            lines.append(f"  缺口摘要：{json.dumps(gap, ensure_ascii=False)}")
        err_notes = _failure_notes(state)
        for note in err_notes:
            lines.append(f"  - {note}")
        lines.append("")

    # 文件位置
    lines.append("【产物位置】")
    lines.append(f"  Trace：{report.get('trace_path')}")
    lines.append(f"  完整报告：{report.get('state_path') and str(report.get('state_path')).replace('state.json', 'report.json')}")
    lines.append(f"  状态：{report.get('state_path')}")
    if saved and saved.get("path"):
        lines.append(f"  方案：{saved.get('path')}")
    lines.append("=" * 56)
    return "\n".join(lines)


def emit_progress(message: str, *, stream: TextIO | None = None) -> None:
    """进度信息默认写 stderr，避免污染 --output json 的 stdout。"""
    out = stream or sys.stderr
    print(message, file=out, flush=True)


def format_tool_progress(
    *,
    tool: str,
    ok: bool | None,
    observation: dict[str, Any] | None,
    arguments: dict[str, Any] | None = None,
) -> str:
    status = "成功" if ok else "失败" if ok is False else "执行"
    parts = [f"[进度] 工具={tool} → {status}"]
    if arguments and arguments.get("reason"):
        parts.append(f"原因={arguments.get('reason')}")
    if observation:
        err = observation.get("error") or {}
        data = observation.get("data") or {}
        if err:
            parts.append(f"错误={err.get('code')}: {err.get('message')}")
        if data.get("within_budget") is False:
            parts.append(
                f"预算超限：费用 {data.get('total_cost')}，差额 {data.get('over_by')} 模拟单位"
            )
        if data.get("duplicate") is True:
            parts.append(f"幂等复用 plan_id={data.get('plan_id')}")
        if data.get("finished"):
            parts.append(f"结束 status={data.get('status')}")
        if tool == "update_plan" and data.get("step_order"):
            parts.append(f"计划步骤={','.join(data.get('step_order') or [])}")
    return " | ".join(parts)


def _status_label(status: str | None) -> str:
    mapping = {
        "completed": "completed（已完成）",
        "incomplete": "incomplete（未完成）",
        "error": "error（错误）",
    }
    return mapping.get(status or "", str(status))


def _step_status_label(status: str | None) -> str:
    mapping = {
        "succeeded": "成功",
        "failed": "失败",
        "pending": "待执行",
        "superseded": "已废弃",
    }
    return mapping.get(status or "", str(status))


def _materials_summary(state: RunState | None, report: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    if state is None:
        return rows
    mats = state.artifacts.get("materials") or {}
    # 优先展示集合产物
    for _aid, data in mats.items():
        if isinstance(data, dict) and "materials" in data:
            for m in data.get("materials") or []:
                rows.append(f"{m.get('id')}: {m.get('title')} ({m.get('type')})")
            break
    if not rows:
        for mid, data in mats.items():
            if isinstance(data, dict) and data.get("title"):
                rows.append(f"{mid}: {data.get('title')} ({data.get('type')})")
    return rows[:12]


def _script_summary(
    state: RunState | None,
    report: dict[str, Any],
    saved: dict[str, Any] | None,
) -> dict[str, Any] | None:
    script_id = None
    if saved:
        script_id = saved.get("script_id")
    if state is None:
        return None
    scripts = state.artifacts.get("scripts") or {}
    script = scripts.get(script_id) if script_id else None
    if script is None and scripts:
        # 取最近一次成功脚本
        script = list(scripts.values())[-1]
    if not script:
        return None
    return {
        "format": script.get("format"),
        "outline": list(script.get("outline") or []),
        "script_id": script.get("script_id"),
    }


def _cost_block(
    state: RunState | None,
    report: dict[str, Any],
    saved: dict[str, Any] | None,
    constraints: dict[str, Any],
) -> list[str]:
    lines: list[str] = ["【成本与工期】", "  （费用单位：模拟单位，非真实货币）"]
    estimate = None
    if state is not None:
        estimates = state.artifacts.get("estimates") or {}
        if saved and saved.get("estimate_id") in estimates:
            estimate = estimates[saved["estimate_id"]]
        elif estimates:
            estimate = list(estimates.values())[-1]
    if estimate:
        for item in estimate.get("items") or []:
            lines.append(
                f"  - {item.get('name')}: {item.get('cost')} 模拟单位 / {item.get('days')} 天"
            )
        total = estimate.get("total_cost")
        budget = constraints.get("budget")
        lines.append(f"  合计费用：{total} 模拟单位")
        if budget is not None and total is not None:
            remain = int(budget) - int(total)
            lines.append(f"  预算：{budget} 模拟单位；余额：{remain} 模拟单位")
            if not estimate.get("within_budget"):
                lines.append(
                    f"  ⚠ 预算超限：超出 {estimate.get('over_by')} 模拟单位"
                )
        lines.append(f"  预计工期：{estimate.get('total_days')} 天")
        lines.append(f"  预计完成日：{estimate.get('finish_date')}")
        lines.append(f"  截止日期：{estimate.get('deadline')}")
        if estimate.get("meets_deadline") is False:
            lines.append(f"  ⚠ 无法在截止日前完成（超出 {estimate.get('days_over')} 天）")
        return lines
    if report.get("total_cost") is not None:
        lines.append(f"  合计费用：{report.get('total_cost')} 模拟单位（{report.get('cost_note')}）")
        return lines
    lines.append("  （尚无成功的成本估算）")
    return lines


def _failure_notes(state: RunState | None) -> list[str]:
    if state is None:
        return []
    notes: list[str] = []
    for sid in state.step_order:
        step = state.steps.get(sid)
        if step is None or step.status == "superseded":
            continue
        if step.error:
            notes.append(
                f"步骤 {sid}: {step.error.get('code')} — {step.error.get('message')}"
            )
        for att in step.attempts:
            if att.result.get("ok"):
                continue
            err = (att.result.get("error") or {})
            if err.get("injected"):
                notes.append(f"步骤 {sid} 注入失败: {err.get('code')} — {err.get('message')}")
    return notes[:8]
