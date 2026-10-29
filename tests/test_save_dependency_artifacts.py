"""save_plan 必须使用当前依赖链上成功步骤的产物，不能偷用无关估算。"""

from helpers import apply_standard_plan, make_state


def test_save_rejects_estimate_from_non_dependency_step(executor, tmp_path):
    """复现：save 声明依赖 s6，却传入 s3 的 estimate_id —— 必须拒绝。"""
    state = make_state(tmp_path, budget=15)
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
            "format": "graphic",
            "reason": "t",
        },
    )
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    old_estimate = r3["data"]["estimate_id"]
    old_script = r2["data"]["script_id"]

    # 重规划：保留成功步骤，新增替代路径；s4 仍 pending 可被省略→superseded
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "reason": "alt path",
            "steps": [
                {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s5", "name": "新脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "新估算", "tool": "estimate_cost", "depends_on": ["s5"]},
                {"step_id": "s7", "name": "保存", "tool": "save_plan", "depends_on": ["s6"]},
            ],
        },
    )
    assert out["ok"], out

    r5 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s5",
            "material_ids": r1["data"]["material_ids"],
            "format": "video_basic",
            "reason": "t",
        },
    )
    r6 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r5["data"]["script_id"], "reason": "t"}
    )
    assert r6["ok"]

    # 错误：依赖的是 s6，却用 s3 的估算 + s2 的脚本（二者自洽，旧逻辑会放过）
    bad = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": old_script,
            "estimate_id": old_estimate,
            "reason": "wrong lineage",
        },
    )
    assert bad["ok"] is False
    assert bad["error"]["code"] == "DEPENDENCY_ARTIFACT_MISMATCH"
    assert state.steps["s7"].status != "succeeded"

    # 正确：使用依赖链上 s6 / s5 的产物
    ok = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r5["data"]["script_id"],
            "estimate_id": r6["data"]["estimate_id"],
            "reason": "correct lineage",
        },
    )
    assert ok["ok"] is True


def test_t04_style_replan_save_still_works(executor, tmp_path):
    """预算重规划路径：新 save 依赖新 estimate，使用匹配产物应成功。"""
    state = make_state(tmp_path, budget=10)
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
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    assert r3["data"]["within_budget"] is False

    executor.dispatch(
        state,
        "update_plan",
        {
            "reason": "over budget",
            "steps": [
                {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s5", "name": "基础脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "基础估算", "tool": "estimate_cost", "depends_on": ["s5"]},
                {"step_id": "s7", "name": "保存", "tool": "save_plan", "depends_on": ["s6"]},
            ],
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
    r6 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r5["data"]["script_id"], "reason": "t"}
    )
    save = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r5["data"]["script_id"],
            "estimate_id": r6["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert save["ok"] is True
    assert save["data"]["total_cost"] <= 10
