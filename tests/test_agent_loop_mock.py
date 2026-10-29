"""Mock LLM 驱动的 Agent 循环：仅验证步数上限与消息协议，不是真实决策证据。"""

from pathlib import Path

from content_agent.agent import ContentAgent
from content_agent.executor import ToolExecutor
from content_agent.llm import CompletePathMockLLM, MockLLM
from content_agent.state import RunState
from content_agent.tools import ToolRuntime


def _agent(tmp_path: Path, script: list[dict], data_dir: Path) -> ContentAgent:
    runtime = ToolRuntime(data_dir=data_dir, plans_dir=tmp_path / "plans")
    executor = ToolExecutor(runtime=runtime, runs_dir=tmp_path / "runs")
    return ContentAgent(
        llm=MockLLM(script),
        executor=executor,
        runtime=runtime,
        runs_dir=tmp_path / "runs",
    )


def _complete_path_agent(tmp_path: Path, data_dir: Path) -> ContentAgent:
    runtime = ToolRuntime(data_dir=data_dir, plans_dir=tmp_path / "plans")
    executor = ToolExecutor(runtime=runtime, runs_dir=tmp_path / "runs")
    return ContentAgent(
        llm=CompletePathMockLLM(),
        executor=executor,
        runtime=runtime,
        runs_dir=tmp_path / "runs",
    )


def test_max_steps_stops_without_fake_save(tmp_path, data_dir):
    script = [
        {
            "name": "update_plan",
            "arguments": {
                "reason": "plan",
                "steps": [
                    {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                ],
            },
        },
        {
            "name": "search_materials",
            "arguments": {"step_id": "s1", "source": "primary", "limit": 2, "reason": "go"},
        },
        {
            "name": "search_materials",
            "arguments": {"step_id": "s1", "source": "primary", "limit": 2, "reason": "again"},
        },
    ]
    state = RunState.create(
        topic="夏季新品发布",
        budget=15,
        deadline="2026-11-20",
        today="2026-11-01",
        max_steps=2,
        run_id="mock_max_steps",
    )
    report = _agent(tmp_path, script, data_dir).run(state)
    assert report["status"] == "incomplete"
    assert report["reason"] == "max_steps_reached"
    assert report["llm_mode"] == "mock"
    assert report["saved_plan"] is None
    assert state.steps_used == 2
    # 守卫拒绝也计步：本例两步都是有效调用
    assert (tmp_path / "runs" / "mock_max_steps" / "trace.jsonl").is_file()


def test_guard_reject_consumes_agent_step(tmp_path, data_dir):
    script = [
        {
            "name": "search_materials",
            "arguments": {"step_id": "s1", "source": "primary", "limit": 2, "reason": "no plan"},
        },
        {
            "name": "finish",
            "arguments": {"status": "incomplete", "reason": "stop", "summary": "stop"},
        },
    ]
    state = RunState.create(
        topic="夏季新品发布",
        budget=15,
        deadline="2026-11-20",
        today="2026-11-01",
        max_steps=5,
        run_id="mock_guard_step",
    )
    report = _agent(tmp_path, script, data_dir).run(state)
    assert state.steps_used >= 1
    assert state.execution_counts.get("search_materials", 0) == 0
    assert report["status"] == "incomplete"


def test_complete_path_mock_finishes_successfully(tmp_path, data_dir):
    """默认完整 Mock 路径可确定性完成；llm_mode 必须为 mock。"""
    state = RunState.create(
        topic="夏季新品发布",
        budget=15,
        deadline="2026-11-20",
        today="2026-11-01",
        max_steps=10,
        run_id="mock_complete_path",
    )
    report = _complete_path_agent(tmp_path, data_dir).run(state)
    assert report["llm_mode"] == "mock"
    assert report["model"] == "mock-llm-complete-path"
    assert report["status"] == "completed"
    assert report["saved_plan"] is not None
    assert report["total_cost"] == 8
    assert state.execution_counts.get("search_materials") == 1
    assert state.execution_counts.get("generate_script") == 1
    assert state.execution_counts.get("estimate_cost") == 1
    assert state.execution_counts.get("save_plan") == 1
    assert state.steps["s4"].status == "succeeded"
