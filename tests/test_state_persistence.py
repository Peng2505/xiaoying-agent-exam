"""状态持久化、失败历史保留、成功步骤复用。"""

from helpers import apply_standard_plan, make_state
from content_agent.state import load_state, resume_summary, save_state


def test_failure_history_kept_after_success(executor, tmp_path):
    state = make_state(tmp_path, inject_failures={"search_materials": "1"})
    apply_standard_plan(executor, state)
    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "retry"}
    )
    step = state.steps["s1"]
    assert step.status == "succeeded"
    assert len(step.attempts) == 2
    assert step.attempts[0].result["ok"] is False
    assert step.attempts[1].result["ok"] is True
    assert step.attempts[0].args["reason"] == "t"


def test_persist_and_reload(executor, tmp_path):
    state = make_state(tmp_path, inject_failures={"search_materials": "1"})
    apply_standard_plan(executor, state)
    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "retry"}
    )
    path = save_state(state, tmp_path / "runs")
    assert path.is_file()

    loaded = load_state(state.run_id, tmp_path / "runs")
    assert loaded.topic == state.topic
    assert loaded.steps["s1"].status == "succeeded"
    assert len(loaded.steps["s1"].attempts) == 2
    assert loaded.steps["s1"].attempts[0].result["ok"] is False
    assert loaded.execution_counts["search_materials"] == 2
    assert loaded.artifacts["materials"]
    summary = resume_summary(loaded)
    assert summary["steps"][0]["status"] == "succeeded"
    assert summary["artifacts"]["material_ids"]


def test_succeeded_step_reused_without_reexecution(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    first = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    artifact = first["data"]["artifact_id"]
    count = state.execution_counts["search_materials"]
    # reason 不同不影响复用；业务参数必须一致
    second = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "again"}
    )
    assert second["ok"]
    assert second["data"]["reused"] is True
    assert second["data"]["artifact_id"] == artifact
    assert state.execution_counts["search_materials"] == count
    assert state.steps["s1"].attempts[-1].reused is True


def test_succeeded_step_rejects_different_args(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    first = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert first["ok"]
    mismatched = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "backup", "limit": 9, "reason": "t"}
    )
    assert mismatched["ok"] is False
    assert mismatched["error"]["code"] == "ARGS_MISMATCH_ON_SUCCEEDED"
    assert state.execution_counts["search_materials"] == 1
    assert state.steps["s1"].status == "succeeded"
    assert all(not a.reused for a in state.steps["s1"].attempts)
