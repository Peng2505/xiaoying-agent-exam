"""命令行入口：解析参数、确定性校验关键约束，再交给 Agent 循环。

缺少预算或截止时间属于硬约束问题，在这里直接拒绝，不调用 LLM，也不填默认值。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from content_agent.agent import ContentAgent
from content_agent.config import BUSINESS_TOOLS, load_settings
from content_agent.executor import ToolExecutor
from content_agent.llm import build_llm
from content_agent.state import RUN_COMPLETED, RunState, load_state, prepare_resume
from content_agent.tools import ToolRuntime

EXIT_COMPLETED = 0
EXIT_INCOMPLETE = 1
EXIT_INVALID_INPUT = 2
EXIT_CONFIG_ERROR = 3

DATE_FORMAT = "%Y-%m-%d"


@dataclass(frozen=True)
class Constraints:
    topic: str
    budget: int
    deadline: date
    today: date


def _parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), DATE_FORMAT).date()
    except ValueError:
        return None


def validate_constraints(
    topic: str | None,
    budget: str | None,
    deadline: str | None,
    today: str | None,
) -> tuple[Constraints | None, dict[str, Any] | None]:
    """返回 (约束, None) 或 (None, 拒绝报告)。"""
    missing = [
        name
        for name, value in (("topic", topic), ("budget", budget), ("deadline", deadline))
        if value is None or not str(value).strip()
    ]
    if missing:
        return None, _rejection(
            "missing_constraints",
            f"缺少关键约束：{', '.join(missing)}。不会自动补全，请补充后重新运行。",
            missing=missing,
        )

    errors: list[str] = []

    budget_value: int | None = None
    try:
        budget_value = int(str(budget).strip())
    except ValueError:
        errors.append(f"budget 必须是正整数（模拟单位），当前值：{budget!r}")
    else:
        if budget_value <= 0:
            errors.append(f"budget 必须大于 0，当前值：{budget_value}")

    deadline_value = _parse_date(str(deadline))
    if deadline_value is None:
        errors.append(f"deadline 必须是 YYYY-MM-DD 格式，当前值：{deadline!r}")

    if today is None or not today.strip():
        today_value: date | None = date.today()
    else:
        today_value = _parse_date(today)
        if today_value is None:
            errors.append(f"today 必须是 YYYY-MM-DD 格式，当前值：{today!r}")

    if deadline_value and today_value and deadline_value < today_value:
        errors.append(f"deadline {deadline_value} 早于当前日期 {today_value}")

    if errors:
        return None, _rejection("invalid_constraints", "；".join(errors), errors=errors)

    return Constraints(str(topic).strip(), budget_value, deadline_value, today_value), None


def _rejection(reason: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "status": "incomplete",
        "reason": reason,
        "message": message,
        **details,
        "llm_calls": 0,
        "tool_calls": 0,
    }


def parse_failure_spec(spec: str) -> tuple[str, str]:
    """解析 `TOOL:N` 或 `TOOL:always`。"""
    tool, sep, when = spec.partition(":")
    if not sep or tool not in BUSINESS_TOOLS:
        raise argparse.ArgumentTypeError(
            f"格式应为 TOOL:N 或 TOOL:always，TOOL 取值 {', '.join(BUSINESS_TOOLS)}；当前值：{spec!r}"
        )
    if when != "always" and not (when.isdigit() and int(when) >= 1):
        raise argparse.ArgumentTypeError(f"N 必须是不小于 1 的整数或 always；当前值：{spec!r}")
    return tool, when


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-agent",
        description="内容任务规划 Agent：在预算与截止时间内规划并生成内容活动方案。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="运行一次任务，或用 --resume 续跑未完成的任务")
    run.add_argument("--topic", help="活动主题")
    run.add_argument("--budget", help="预算，正整数模拟单位")
    run.add_argument("--deadline", help="截止日期，YYYY-MM-DD")
    run.add_argument("--today", help="起算日期，YYYY-MM-DD；默认取系统日期，测试时固定以便复现")
    run.add_argument("--max-steps", type=int, help="覆盖环境变量 MAX_STEPS")
    run.add_argument(
        "--inject-failure",
        action="append",
        default=[],
        type=parse_failure_spec,
        metavar="TOOL:N|TOOL:always",
        help="让某个工具的第 N 次真实执行失败，或每次都失败；可重复使用",
    )
    run.add_argument("--resume", metavar="RUN_ID", help="续跑一个未完成的运行，约束从其 state.json 读取")
    run.add_argument(
        "--llm",
        choices=("real", "mock"),
        default="real",
        help="real 使用真实模型；mock 仅验证流程，不能作为模型决策证据",
    )
    return parser


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _use_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _build_stack(settings, llm_mode: str):
    runtime = ToolRuntime(data_dir=settings.data_dir, plans_dir=settings.plans_dir)
    executor = ToolExecutor(runtime=runtime, runs_dir=settings.runs_dir)
    # mock 默认 CompletePathMockLLM（完整确定性成功路径）；仍标记 llm_mode=mock，非真实决策证据
    llm = build_llm(settings, mode=llm_mode, mock_script=None)
    agent = ContentAgent(llm=llm, executor=executor, runtime=runtime, runs_dir=settings.runs_dir)
    return agent


def main(argv: list[str] | None = None) -> int:
    _use_utf8_output()
    args = build_parser().parse_args(argv)
    settings = load_settings()

    inject = {tool: when for tool, when in args.inject_failure}
    max_steps = args.max_steps if args.max_steps is not None else settings.max_steps

    if args.resume:
        try:
            state = load_state(args.resume, settings.runs_dir)
        except FileNotFoundError as exc:
            _print_json({"status": "error", "message": str(exc)})
            return EXIT_INVALID_INPUT
        if state.status == RUN_COMPLETED:
            _print_json(
                {
                    "status": "error",
                    "message": f"运行 {args.resume} 已完成，不能续跑。",
                    "run_id": args.resume,
                }
            )
            return EXIT_INVALID_INPUT
        # 续跑不允许改约束；若用户误传 topic/budget/deadline，直接拒绝以免静默忽略
        overrides = [
            name
            for name, value in (
                ("topic", args.topic),
                ("budget", args.budget),
                ("deadline", args.deadline),
                ("today", args.today),
            )
            if value is not None and str(value).strip()
        ]
        if overrides:
            _print_json(
                {
                    "status": "error",
                    "message": "续跑时约束必须来自原 state.json，请勿同时传入 "
                    + ", ".join(overrides),
                }
            )
            return EXIT_INVALID_INPUT

        if args.llm == "real" and not settings.llm_configured:
            _print_json(
                {
                    "status": "error",
                    "message": "未配置 LLM_API_KEY 或 LLM_MODEL。请复制 .env.example 为 .env 并填写。",
                }
            )
            return EXIT_CONFIG_ERROR
        try:
            prepare_resume(
                state,
                max_steps=max_steps,
                max_cumulative_steps=settings.max_cumulative_steps,
                inject_failures=inject if inject else None,
                clear_inject=not bool(inject),
            )
        except ValueError as exc:
            _print_json({"status": "incomplete", "reason": "max_cumulative_steps_reached", "message": str(exc)})
            return EXIT_INCOMPLETE
        agent = _build_stack(settings, args.llm)
        report = agent.run(state, is_resume=True)
        _print_json(report)
        return EXIT_COMPLETED if report.get("status") == RUN_COMPLETED else EXIT_INCOMPLETE

    # 约束校验优先于 LLM 配置检查，避免缺预算时被误报成「未配置密钥」
    constraints, rejection = validate_constraints(args.topic, args.budget, args.deadline, args.today)
    if rejection:
        _print_json(rejection)
        return EXIT_INVALID_INPUT

    if args.llm == "real" and not settings.llm_configured:
        _print_json(
            {
                "status": "error",
                "message": "未配置 LLM_API_KEY 或 LLM_MODEL。请复制 .env.example 为 .env 并填写。",
            }
        )
        return EXIT_CONFIG_ERROR

    state = RunState.create(
        topic=constraints.topic,
        budget=constraints.budget,
        deadline=constraints.deadline,
        today=constraints.today,
        max_steps=max_steps,
        max_attempts_per_step=settings.max_attempts_per_step,
        max_cumulative_steps=settings.max_cumulative_steps,
        inject_failures=inject,
    )

    agent = _build_stack(settings, args.llm)
    report = agent.run(state)
    _print_json(report)
    return EXIT_COMPLETED if report.get("status") == RUN_COMPLETED else EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
