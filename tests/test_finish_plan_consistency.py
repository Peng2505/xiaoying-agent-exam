"""finish(completed) 必须与当前有效计划必需步骤一致。"""

from helpers import apply_standard_plan, make_state


def _complete_standard_save(executor, state):
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
    r4 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert r4["ok"]
    return r1, r2, r3, r4


def test_finish_completed_blocked_when_required_step_pending(executor, tmp_path):
    """复现：已有成功 save，但当前计划仍有未完成必需步骤时，不得 completed。"""
    state = make_state(tmp_path, budget=15)
    _complete_standard_save(executor, state)

    out = executor.dispatch(
        state,
        "update_plan",
        {
            "reason": "add unfinished required work",
            "steps": [
                {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s4", "name": "保存", "tool": "save_plan", "depends_on": ["s3"]},
                {"step_id": "s5", "name": "额外脚本", "tool": "generate_script", "depends_on": ["s1"]},
            ],
        },
    )
    assert out["ok"]
    assert state.steps["s5"].status == "pending"

    finish = executor.dispatch(
        state, "finish", {"status": "completed", "summary": "should fail", "reason": "done"}
    )
    assert finish["ok"] is False
    assert finish["error"]["code"] == "FINISH_NOT_READY"
    assert state.status != "completed"
    assert "s5" in str(finish["error"])


def test_finish_completed_ok_when_all_required_succeeded(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    _complete_standard_save(executor, state)
    finish = executor.dispatch(
        state, "finish", {"status": "completed", "summary": "ok", "reason": "done"}
    )
    assert finish["ok"] is True
    assert state.status == "completed"


def test_superseded_does_not_block_finish(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    # 省略未执行的 s2/s3/s4 → superseded，改走新路径
    executor.dispatch(
        state,
        "update_plan",
        {
            "reason": "replace pending",
            "steps": [
                {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2b", "name": "脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3b", "name": "估算", "tool": "estimate_cost", "depends_on": ["s2b"]},
                {"step_id": "s4b", "name": "保存", "tool": "save_plan", "depends_on": ["s3b"]},
            ],
        },
    )
    assert state.steps["s2"].status == "superseded"
    r2 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2b",
            "material_ids": r1["data"]["material_ids"],
            "format": "graphic",
            "reason": "t",
        },
    )
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3b", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4b",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    finish = executor.dispatch(
        state, "finish", {"status": "completed", "summary": "ok", "reason": "done"}
    )
    assert finish["ok"] is True


def test_optional_pending_does_not_block_finish(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    _complete_standard_save(executor, state)
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "reason": "optional extra",
            "steps": [
                {"step_id": "s1", "name": "检索", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s4", "name": "保存", "tool": "save_plan", "depends_on": ["s3"]},
                {
                    "step_id": "s_opt",
                    "name": "可选补充脚本",
                    "tool": "generate_script",
                    "depends_on": ["s1"],
                    "optional": True,
                },
            ],
        },
    )
    assert out["ok"], out
    assert state.steps["s_opt"].optional is True
    assert state.steps["s_opt"].status == "pending"
    finish = executor.dispatch(
        state, "finish", {"status": "completed", "summary": "ok", "reason": "done"}
    )
    assert finish["ok"] is True
    assert state.status == "completed"
