"""续跑：保留成功产物与失败历史，不重复真实执行成功步骤。Mock 仅验证流程。"""

from pathlib import Path

from content_agent.agent import ContentAgent
from content_agent.executor import ToolExecutor
from content_agent.llm import MockLLM
from content_agent.state import load_state, prepare_resume, save_state  # noqa: F401 — save_state used below
from content_agent.tools import ToolRuntime
from helpers import apply_standard_plan, make_state


def test_resume_reuses_succeeded_and_completes(tmp_path, data_dir):
    runtime = ToolRuntime(data_dir=data_dir, plans_dir=tmp_path / "plans")
    executor = ToolExecutor(runtime=runtime, runs_dir=tmp_path / "runs")
    state = make_state(tmp_path, budget=15, inject_failures={"save_plan": "always"})
    state.run_id = "resume_demo"
    state.max_attempts_per_step = 2
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    r2 = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": r1["data"]["material_ids"], "format": "graphic", "reason": "t"},
    )
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    fail = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert fail["ok"] is False and fail["error"]["injected"] is True
    state.status = "incomplete"
    state.reason = "tool_failure"
    save_state(state, tmp_path / "runs")

    loaded = load_state("resume_demo", tmp_path / "runs")
    fail_attempts = len(loaded.steps["s4"].attempts)
    search_exec = loaded.execution_counts["search_materials"]
    prepare_resume(loaded, max_steps=5, clear_inject=True)

    script = [
        {
            "name": "save_plan",
            "arguments": {
                "step_id": "s4",
                "script_id": r2["data"]["script_id"],
                "estimate_id": r3["data"]["estimate_id"],
                "reason": "resume save",
            },
        },
        {
            "name": "finish",
            "arguments": {"status": "completed", "reason": "done", "summary": "saved"},
        },
    ]
    agent = ContentAgent(
        llm=MockLLM(script),
        executor=ToolExecutor(runtime=runtime, runs_dir=tmp_path / "runs"),
        runtime=runtime,
        runs_dir=tmp_path / "runs",
    )
    report = agent.run(loaded, is_resume=True)
    assert report["status"] == "completed"
    assert report["llm_mode"] == "mock"
    assert loaded.session == 2
    assert loaded.execution_counts["search_materials"] == search_exec
    assert loaded.execution_counts["generate_script"] == 1
    assert loaded.execution_counts["estimate_cost"] == 1
    assert len(loaded.steps["s4"].attempts) > fail_attempts
    assert any(not a.result.get("ok") for a in loaded.steps["s4"].attempts)
    assert loaded.steps["s1"].status == "succeeded"
    # 若模型误调成功检索，应复用
    reused = executor.dispatch(
        loaded, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "x"}
    )
    assert reused["data"]["reused"] is True


def test_global_min_cost_proves_budget5_infeasible(data_dir):
    from content_agent.tools import global_min_cost, load_json

    catalog = global_min_cost(load_json(data_dir / "costs.json"))
    assert catalog["global_min_cost"] == 8
    assert catalog["per_format"]["graphic"] == 8
    assert 5 < catalog["global_min_cost"]


def test_global_min_cost_covers_all_supported_formats(data_dir):
    """不可行证明必须覆盖费用表与工具 schema 中的全部 format。"""
    from content_agent.prompts import tool_schemas
    from content_agent.tools import global_min_cost, load_json

    costs = load_json(data_dir / "costs.json")
    catalog = global_min_cost(costs)
    table_formats = set(costs["formats"])
    assert set(catalog["per_format"]) == table_formats

    gen = next(t for t in tool_schemas() if t["function"]["name"] == "generate_script")
    schema_formats = set(gen["function"]["parameters"]["properties"]["format"]["enum"])
    assert table_formats == schema_formats


def test_cumulative_steps_block_infinite_resume_new_steps(tmp_path, data_dir):
    """新建 step_id 不能无限绕过单步重试：跨会话累计上限生效。"""
    runtime = ToolRuntime(data_dir=data_dir, plans_dir=tmp_path / "plans")
    state = make_state(tmp_path, budget=15)
    state.run_id = "cum_limit"
    state.max_steps = 5
    state.max_cumulative_steps = 4
    state.cumulative_steps = 4
    state.status = "incomplete"
    save_state(state, tmp_path / "runs")

    loaded = load_state("cum_limit", tmp_path / "runs")
    try:
        prepare_resume(loaded, max_steps=5, clear_inject=True)
        assert False, "应拒绝续跑"
    except ValueError as exc:
        assert "全局上限" in str(exc)

    # Agent 入口同样停止
    loaded2 = load_state("cum_limit", tmp_path / "runs")
    agent = ContentAgent(
        llm=MockLLM([]),
        executor=ToolExecutor(runtime=runtime, runs_dir=tmp_path / "runs"),
        runtime=runtime,
        runs_dir=tmp_path / "runs",
    )
    report = agent.run(loaded2, is_resume=False)
    assert report["status"] == "incomplete"
    assert report["reason"] == "max_cumulative_steps_reached"
