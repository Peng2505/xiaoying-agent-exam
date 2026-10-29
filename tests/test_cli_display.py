"""CLI 默认中文报告、--output json、--verbose 兼容性。"""

import json

from content_agent.cli import EXIT_COMPLETED, EXIT_INCOMPLETE, main
from content_agent.display import format_text_report
from content_agent.state import RunState


def test_mock_default_text_report(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENT_AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("CONTENT_AGENT_PLANS_DIR", str(tmp_path / "plans"))
    # 重新加载 settings 会在 main 内 load_settings，环境变量需在调用前生效
    from content_agent import config

    monkeypatch.setattr(
        config,
        "load_settings",
        lambda: config.Settings(
            llm_api_key="",
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            llm_thinking="disabled",
            max_steps=12,
            max_attempts_per_step=3,
            max_cumulative_steps=36,
            data_dir=config._REPO_ROOT / "data",
            runs_dir=tmp_path / "runs",
            plans_dir=tmp_path / "plans",
        ),
    )
    code = main(
        [
            "run",
            "--topic",
            "夏季新品发布",
            "--budget",
            "15",
            "--deadline",
            "2026-11-20",
            "--today",
            "2026-11-01",
            "--llm",
            "mock",
            "--output",
            "text",
        ]
    )
    out = capsys.readouterr().out
    assert code == EXIT_COMPLETED
    assert "最终状态：completed" in out
    assert "模拟单位" in out
    assert "脚本大纲" in out
    assert "plan_id=" in out
    assert not out.strip().startswith("{")


def test_mock_json_output_is_parseable_and_pure(capsys, tmp_path, monkeypatch):
    from content_agent import config

    monkeypatch.setattr(
        config,
        "load_settings",
        lambda: config.Settings(
            llm_api_key="",
            llm_base_url="https://api.deepseek.com",
            llm_model="deepseek-flash",
            llm_thinking="disabled",
            max_steps=12,
            max_attempts_per_step=3,
            max_cumulative_steps=36,
            data_dir=config._REPO_ROOT / "data",
            runs_dir=tmp_path / "runs",
            plans_dir=tmp_path / "plans",
        ),
    )
    code = main(
        [
            "run",
            "--topic",
            "夏季新品发布",
            "--budget",
            "15",
            "--deadline",
            "2026-11-20",
            "--today",
            "2026-11-01",
            "--llm",
            "mock",
            "--output",
            "json",
            "--verbose",
        ]
    )
    captured = capsys.readouterr()
    assert code == EXIT_COMPLETED
    report = json.loads(captured.out)
    assert report["status"] == "completed"
    assert report["llm_mode"] == "mock"
    assert report["saved_plan"] is not None
    # verbose 进度应在 stderr，不污染 stdout JSON
    assert "[进度]" in captured.err
    assert "[进度]" not in captured.out


def test_format_text_marks_incomplete_not_success():
    report = {
        "run_id": "r1",
        "status": "incomplete",
        "reason": "infeasible",
        "message": "无可行方案",
        "llm_mode": "real",
        "model": "deepseek-flash",
        "constraints": {"topic": "x", "budget": 5, "deadline": "2026-11-20", "today": "2026-11-01"},
        "plan": [],
        "gap": {"budget_gap": 3},
        "saved_plan": None,
        "trace_path": "runs/r1/trace.jsonl",
        "state_path": "runs/r1/state.json",
    }
    text = format_text_report(report, state=None)
    assert "incomplete（未完成）" in text
    assert "未保存方案" in text
