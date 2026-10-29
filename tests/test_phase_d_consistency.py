"""阶段 D 一致性回归：重规划保留成功检索、拒绝旧估算；临时失败与不可行语义分离。"""

from helpers import apply_standard_plan, make_state
from content_agent.guards import compute_gap


def test_replan_keeps_search_requires_new_estimate(executor, tmp_path):
    state = make_state(tmp_path, budget=10)
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    search_artifact = r1["data"]["artifact_id"]
    r2 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": r1["data"]["material_ids"],
            "format": "video_premium",
            "reason": "t",
        },
    )
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    assert r3["data"]["within_budget"] is False
    old_estimate = r3["data"]["estimate_id"]
    save_fail = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": old_estimate,
            "reason": "t",
        },
    )
    assert save_fail["error"]["code"] == "CONSTRAINT_VIOLATION"
    assert save_fail["error"]["retryable"] is False

    out = executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "生成脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算成本", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s5", "name": "替代脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "替代估算", "tool": "estimate_cost", "depends_on": ["s5"]},
                {"step_id": "s7", "name": "保存", "tool": "save_plan", "depends_on": ["s6"]},
            ],
            "reason": "over budget",
        },
    )
    assert out["ok"]
    assert state.steps["s1"].status == "succeeded"
    assert state.steps["s1"].artifact_id == search_artifact
    assert state.steps["s4"].status == "superseded"

    # 复用检索，不增加真实执行次数
    count = state.execution_counts["search_materials"]
    reused = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "reuse"}
    )
    assert reused["data"]["reused"] is True
    assert state.execution_counts["search_materials"] == count

    r5 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s5",
            "material_ids": r1["data"]["material_ids"],
            "format": "graphic",
            "reason": "t",
        },
    )
    stale = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r5["data"]["script_id"],
            "estimate_id": old_estimate,
            "reason": "t",
        },
    )
    # 依赖未满足或 STALE；先估再测 stale
    assert stale["ok"] is False
    executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r5["data"]["script_id"], "reason": "t"}
    )
    stale2 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r5["data"]["script_id"],
            "estimate_id": old_estimate,
            "reason": "t",
        },
    )
    # 旧 estimate 不在当前 save 依赖链上 → DEPENDENCY_ARTIFACT_MISMATCH；
    # 若绕过血缘仍会因 script/format 不一致得到 STALE_ESTIMATE。
    assert stale2["error"]["code"] in ("DEPENDENCY_ARTIFACT_MISMATCH", "STALE_ESTIMATE")

    r6 = state.steps["s6"].attempts[-1].result
    ok_save = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r5["data"]["script_id"],
            "estimate_id": r6["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert ok_save["ok"] is True
    assert ok_save["data"]["total_cost"] <= 10


def test_temporary_failure_retryable_unlike_constraint(executor, tmp_path):
    state = make_state(tmp_path, budget=10, inject_failures={"search_materials": "1"})
    apply_standard_plan(executor, state)
    fail = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert fail["error"]["code"] == "SOURCE_UNAVAILABLE"
    assert fail["error"]["retryable"] is True
    assert fail["error"]["injected"] is True

    state2 = make_state(tmp_path, budget=10)
    state2.run_id = "constraint_case"
    apply_standard_plan(executor, state2)
    r1 = executor.dispatch(
        state2, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    r2 = executor.dispatch(
        state2,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": r1["data"]["material_ids"],
            "format": "video_premium",
            "reason": "t",
        },
    )
    r3 = executor.dispatch(
        state2, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    assert r3["ok"] is True and r3["data"]["within_budget"] is False
    save = executor.dispatch(
        state2,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert save["error"]["code"] == "CONSTRAINT_VIOLATION"
    assert save["error"]["retryable"] is False


def test_compute_gap_uses_best_observed_overrun(executor, tmp_path):
    state = make_state(tmp_path, budget=5)
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    r2 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": r1["data"]["material_ids"],
            "format": "video_premium",
            "reason": "t",
        },
    )
    executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "生成脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算成本", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s4", "name": "保存方案", "tool": "save_plan", "depends_on": ["s3"]},
                {"step_id": "s5", "name": "图文", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "估图文", "tool": "estimate_cost", "depends_on": ["s5"]},
            ],
            "reason": "try cheaper",
        },
    )
    r5 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s5",
            "material_ids": r1["data"]["material_ids"],
            "format": "graphic",
            "reason": "t",
        },
    )
    executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r5["data"]["script_id"], "reason": "t"}
    )
    gap = compute_gap(state)
    assert gap is not None
    assert gap["min_observed_cost"] == 8
    assert gap["budget_gap"] == 3
    assert gap["budget"] == 5
    assert gap.get("budget_gap_scope") == "observed_estimates_only"

    gap_global = compute_gap(state, cost_table=executor.runtime.costs)
    assert gap_global["globally_infeasible_by_budget"] is True
    assert gap_global["global_min_cost"] == 8
    assert gap_global["budget_gap"] == 3
    assert gap_global["budget_gap_scope"] == "all_supported_formats"
