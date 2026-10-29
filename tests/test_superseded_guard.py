"""废弃步骤（superseded）不得再执行、不得恢复为成功、不得参与完成判断。"""

from helpers import apply_standard_plan, make_state


def _search_and_supersede_pending_script(executor, state):
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert r1["ok"]
    # 用新步骤替代尚未执行的 s2/s3/s4，使其变为 superseded
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "reason": "replace pending path",
            "steps": [
                {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2b", "name": "新脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3b", "name": "新估算", "tool": "estimate_cost", "depends_on": ["s2b"]},
                {"step_id": "s4b", "name": "新保存", "tool": "save_plan", "depends_on": ["s3b"]},
            ],
        },
    )
    assert out["ok"], out
    assert state.steps["s2"].status == "superseded"
    assert state.steps["s3"].status == "superseded"
    assert state.steps["s4"].status == "superseded"
    return r1


def test_superseded_step_cannot_execute(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    r1 = _search_and_supersede_pending_script(executor, state)

    rejected = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": r1["data"]["material_ids"],
            "format": "graphic",
            "reason": "try old step",
        },
    )
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "STEP_SUPERSEDED"
    assert state.steps["s2"].status == "superseded"
    # 不得写入成功 attempts，也不得产生产物
    assert not any(a.result.get("ok") for a in state.steps["s2"].attempts)
    assert state.artifacts.get("scripts") in (None, {})


def test_superseded_cannot_become_succeeded(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    r1 = _search_and_supersede_pending_script(executor, state)
    before_status = state.steps["s2"].status

    executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": r1["data"]["material_ids"],
            "format": "graphic",
            "reason": "again",
        },
    )
    assert state.steps["s2"].status == before_status == "superseded"
    assert state.steps["s2"].status != "succeeded"


def test_superseded_save_does_not_count_for_finish(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    _search_and_supersede_pending_script(executor, state)
    # 仅有 superseded 的 save 步骤，不允许 completed
    finish = executor.dispatch(
        state,
        "finish",
        {"status": "completed", "summary": "should fail"},
    )
    assert finish["ok"] is False
    assert finish["error"]["code"] == "FINISH_NOT_READY"
    assert state.status != "completed"


def test_current_path_after_supersede_still_works(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    r1 = _search_and_supersede_pending_script(executor, state)
    r2 = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2b",
            "material_ids": r1["data"]["material_ids"],
            "format": "graphic",
            "reason": "new path",
        },
    )
    assert r2["ok"]
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3b", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    assert r3["ok"]
    r4 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4b",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert r4["ok"]
    # 废弃旧步骤仍保持 superseded
    assert state.steps["s2"].status == "superseded"
    assert state.steps["s4"].status == "superseded"
    finish = executor.dispatch(
        state, "finish", {"status": "completed", "summary": "done via new path"}
    )
    assert finish["ok"]
    assert state.status == "completed"
