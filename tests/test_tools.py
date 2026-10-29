"""四个业务工具的正常路径与错误输入。不调用 LLM。"""

from helpers import apply_standard_plan, make_state


def _happy_path(executor, state, fmt="graphic"):
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state,
        "search_materials",
        {"step_id": "s1", "topic": state.topic, "source": "primary", "limit": 3, "reason": "test"},
    )
    assert r1["ok"], r1
    material_ids = r1["data"]["material_ids"]
    r2 = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": material_ids, "format": fmt, "reason": "test"},
    )
    assert r2["ok"], r2
    r3 = executor.dispatch(
        state,
        "estimate_cost",
        {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "test"},
    )
    assert r3["ok"], r3
    return r1, r2, r3


def test_normal_tool_chain_and_save(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    r1, r2, r3 = _happy_path(executor, state, "graphic")
    assert r3["data"]["total_cost"] == 8
    assert r3["data"]["within_budget"] is True
    assert r3["data"]["meets_deadline"] is True

    r4 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "test",
        },
    )
    assert r4["ok"], r4
    assert r4["data"]["duplicate"] is False
    assert state.steps["s1"].status == "succeeded"
    assert state.steps["s4"].status == "succeeded"
    assert state.steps["s4"].artifact_id == r4["data"]["plan_id"]


def test_search_no_match(executor, tmp_path):
    state = make_state(tmp_path, topic="火星殖民冷启动")
    apply_standard_plan(executor, state)
    out = executor.dispatch(
        state,
        "search_materials",
        {"step_id": "s1", "topic": state.topic, "source": "primary", "limit": 5, "reason": "test"},
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "NO_MATCH"
    assert state.steps["s1"].status == "failed"
    assert len(state.steps["s1"].attempts) == 1


def test_generate_script_rejects_unknown_material(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    executor.dispatch(
        state,
        "search_materials",
        {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"},
    )
    out = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": ["NOT_EXIST"], "format": "graphic", "reason": "t"},
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_MATERIAL"


def test_estimate_unknown_script(executor, tmp_path):
    state = make_state(tmp_path)
    apply_standard_plan(executor, state)
    # 跳过依赖会先被守卫拦住；这里直接测工具层
    out = executor.runtime.estimate_cost(state, step_id="s3", script_id="script_missing")
    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_SCRIPT"


def test_estimate_reports_budget_overrun_but_still_returns_ok(executor, tmp_path):
    """超预算是观察结果，不是工具失败；是否重规划由 LLM 决定。"""
    state = make_state(tmp_path, budget=10)
    _, r2, r3 = _happy_path(executor, state, "video_premium")
    assert r3["ok"] is True
    assert r3["data"]["total_cost"] == 12
    assert r3["data"]["within_budget"] is False
    assert r3["data"]["over_by"] == 2


def test_save_rejects_budget_overrun(executor, tmp_path):
    state = make_state(tmp_path, budget=10)
    _, r2, r3 = _happy_path(executor, state, "video_premium")
    out = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "CONSTRAINT_VIOLATION"
    assert "预算超限" in out["error"]["message"]
    assert state.steps["s4"].status == "failed"


def test_save_rejects_deadline_miss(executor, tmp_path):
    # premium 需要 5 天，today+5 = 11-06 > 11-03
    state = make_state(tmp_path, budget=20, deadline="2026-11-03", today="2026-11-01")
    _, r2, r3 = _happy_path(executor, state, "video_premium")
    assert r3["data"]["meets_deadline"] is False
    out = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "CONSTRAINT_VIOLATION"
    assert "截止时间" in out["error"]["message"]


def test_save_rejects_mismatched_estimate(executor, tmp_path):
    state = make_state(tmp_path, budget=20)
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    r2a = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": r1["data"]["material_ids"], "format": "graphic", "reason": "t"},
    )
    # 再生成另一个脚本，估算挂在旧脚本上再拿去保存新脚本
    # 先让 s2 成功后不能改 tool；另起状态更直接：手工塞一个错配估算
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2a["data"]["script_id"], "reason": "t"}
    )
    fake_script = {
        "script_id": "script_other",
        "format": "graphic",
        "material_ids": r1["data"]["material_ids"],
        "outline": ["x"],
        "required_resources": ["copywriting", "visual_design", "layout"],
    }
    state.artifacts["scripts"]["script_other"] = fake_script
    out = executor.runtime.save_plan(
        state,
        step_id="s4",
        script_id="script_other",
        estimate_id=r3["data"]["estimate_id"],
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "STALE_ESTIMATE"
