"""依赖、计划保护、finish 守卫。不调用 LLM，也不自动重试。"""

from helpers import apply_standard_plan, make_state


def test_dependency_blocks_early_tool(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    out = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": ["M001"], "format": "graphic", "reason": "t"},
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "DEPENDENCY_NOT_READY"
    assert out["error"].get("guard_rejected") is True
    # 守卫拒绝不计入真实执行次数
    assert state.execution_counts.get("generate_script", 0) == 0
    assert state.steps["s2"].status == "pending"
    assert state.steps["s2"].attempts == []


def test_step_must_be_in_plan(executor, tmp_path):
    state = make_state(tmp_path)
    out = executor.dispatch(
        state,
        "search_materials",
        {"step_id": "s1", "source": "primary", "reason": "t"},
    )
    assert out["error"]["code"] == "STEP_NOT_IN_PLAN"


def test_cannot_delete_succeeded_step(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert state.steps["s1"].status == "succeeded"
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "s2", "name": "脚本", "tool": "generate_script", "depends_on": []},
                {"step_id": "s3", "name": "估算", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s4", "name": "保存", "tool": "save_plan", "depends_on": ["s3"]},
            ],
            "reason": "bad",
        },
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "PROTECT_SUCCEEDED"
    assert state.steps["s1"].status == "succeeded"


def test_save_plan_must_depend_on_estimate(executor, tmp_path):
    state = make_state(tmp_path)
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                {"step_id": "s4", "name": "保存", "tool": "save_plan", "depends_on": ["s1"]},
            ],
            "reason": "bad",
        },
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PLAN"


def test_cycle_rejected(executor, tmp_path):
    state = make_state(tmp_path)
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "a", "name": "a", "tool": "search_materials", "depends_on": ["b"]},
                {"step_id": "b", "name": "b", "tool": "estimate_cost", "depends_on": ["a"]},
                {"step_id": "c", "name": "c", "tool": "save_plan", "depends_on": ["b"]},
            ],
            "reason": "cycle",
        },
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_DEPENDENCY"


def test_finish_completed_requires_successful_save(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    out = executor.dispatch(state, "finish", {"status": "completed", "summary": "done", "reason": "t"})
    assert out["ok"] is False
    assert out["error"]["code"] == "FINISH_NOT_READY"
    assert state.status == "incomplete"


def test_finish_incomplete_always_accepted(executor, tmp_path):
    state = make_state(tmp_path)
    out = executor.dispatch(
        state, "finish", {"status": "incomplete", "reason": "infeasible", "summary": "预算不够"}
    )
    assert out["ok"] is True
    assert state.status == "incomplete"
    assert state.reason == "infeasible"


def test_replan_can_replace_failed_or_pending_but_keeps_succeeded(executor, tmp_path):
    """预算超限后的重规划：保留已成功检索，替换后续未成功步骤。"""
    state = make_state(tmp_path, budget=10)
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    executor.dispatch(
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
        state,
        "estimate_cost",
        {"step_id": "s3", "script_id": state.steps["s2"].artifact_id, "reason": "t"},
    )
    assert r3["data"]["within_budget"] is False
    # 保存失败
    save = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": state.steps["s2"].artifact_id,
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert save["ok"] is False

    out = executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                # 已成功的 s1/s2/s3 必须保留；失败的 s4 可被替代
                {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "生成脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算成本", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s5", "name": "图文脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "估算", "tool": "estimate_cost", "depends_on": ["s5"]},
                {"step_id": "s7", "name": "保存", "tool": "save_plan", "depends_on": ["s6"]},
            ],
            "reason": "over budget, try graphic",
        },
    )
    assert out["ok"], out
    assert state.steps["s1"].status == "succeeded"
    assert state.steps["s2"].status == "succeeded"
    assert state.steps["s3"].status == "succeeded"
    assert state.steps["s4"].status == "superseded"

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
    r6 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r5["data"]["script_id"], "reason": "t"}
    )
    assert r6["data"]["within_budget"] is True
    r7 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r5["data"]["script_id"],
            "estimate_id": r6["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert r7["ok"] is True
    assert r7["data"]["total_cost"] == 8
