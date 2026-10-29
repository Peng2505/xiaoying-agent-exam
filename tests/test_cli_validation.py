"""CLI 约束校验（T02 的确定性部分）。不调用任何模型。"""

import json
from datetime import date

import pytest

from content_agent.cli import (
    EXIT_INVALID_INPUT,
    build_parser,
    main,
    validate_constraints,
)


def _run(capsys, *argv):
    # 测试依赖机器可读 JSON；默认 CLI 已改为 text
    argv = list(argv)
    if "--output" not in argv:
        argv.extend(["--output", "json"])
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_missing_budget_is_rejected_without_llm(capsys):
    code, out = _run(capsys, "run", "--topic", "夏季新品发布", "--deadline", "2026-11-20", "--today", "2026-11-01")
    assert code == EXIT_INVALID_INPUT
    assert out["status"] == "incomplete"
    assert out["reason"] == "missing_constraints"
    assert out["missing"] == ["budget"]
    assert out["llm_calls"] == 0 and out["tool_calls"] == 0


def test_missing_deadline_is_rejected_without_llm(capsys):
    code, out = _run(capsys, "run", "--topic", "夏季新品发布", "--budget", "15", "--today", "2026-11-01")
    assert code == EXIT_INVALID_INPUT
    assert out["reason"] == "missing_constraints"
    assert out["missing"] == ["deadline"]
    assert out["llm_calls"] == 0


def test_missing_both_lists_both_and_does_not_fill_defaults(capsys):
    code, out = _run(capsys, "run", "--topic", "夏季新品发布")
    assert code == EXIT_INVALID_INPUT
    assert out["missing"] == ["budget", "deadline"]
    assert "constraints" not in out


def test_missing_budget_default_text_output_is_human_readable(capsys):
    code = main(
        [
            "run",
            "--topic",
            "夏季新品发布",
            "--deadline",
            "2026-11-20",
            "--today",
            "2026-11-01",
            "--output",
            "text",
        ]
    )
    out = capsys.readouterr().out
    assert code == EXIT_INVALID_INPUT
    assert "missing_constraints" in out or "缺少" in out
    assert "未调用 LLM" in out
    # 默认 text 不应整段是 JSON 对象
    assert not out.strip().startswith("{")


def test_blank_budget_counts_as_missing():
    constraints, rejection = validate_constraints("主题", "  ", "2026-11-20", "2026-11-01")
    assert constraints is None
    assert rejection["missing"] == ["budget"]


@pytest.mark.parametrize("budget", ["abc", "10.5", "0", "-3"])
def test_invalid_budget(budget):
    _, rejection = validate_constraints("主题", budget, "2026-11-20", "2026-11-01")
    assert rejection["reason"] == "invalid_constraints"


def test_invalid_deadline_format():
    _, rejection = validate_constraints("主题", "10", "2026/11/20", "2026-11-01")
    assert rejection["reason"] == "invalid_constraints"


def test_deadline_in_past_is_rejected():
    _, rejection = validate_constraints("主题", "10", "2026-10-01", "2026-11-01")
    assert rejection["reason"] == "invalid_constraints"
    assert "早于" in rejection["message"]


def test_valid_constraints_are_parsed():
    constraints, rejection = validate_constraints(" 夏季新品发布 ", "10", "2026-11-20", "2026-11-01")
    assert rejection is None
    assert constraints.topic == "夏季新品发布"
    assert constraints.budget == 10
    assert constraints.deadline == date(2026, 11, 20)
    assert constraints.today == date(2026, 11, 1)


@pytest.mark.parametrize("spec", ["search_materials:1", "save_plan:always", "generate_script:3"])
def test_failure_spec_accepted(spec):
    args = build_parser().parse_args(["run", "--inject-failure", spec])
    assert args.inject_failure[0][0] == spec.split(":")[0]


@pytest.mark.parametrize("spec", ["unknown_tool:1", "save_plan", "save_plan:0", "save_plan:x"])
def test_failure_spec_rejected(spec):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--inject-failure", spec])
