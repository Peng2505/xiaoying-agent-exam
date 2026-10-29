"""失败注入按真实执行次数触发；守卫拒绝与复用不计次。不自动重试。"""

from helpers import apply_standard_plan, make_state


def test_inject_nth_execution(executor, tmp_path):
    state = make_state(tmp_path, inject_failures={"search_materials": "1"})
    apply_standard_plan(executor, state)

    first = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert first["ok"] is False
    assert first["error"]["code"] == "SOURCE_UNAVAILABLE"
    assert first["error"]["injected"] is True
    assert first["error"]["retryable"] is True
    assert state.execution_counts["search_materials"] == 1
    assert state.steps["s1"].status == "failed"
    assert len(state.steps["s1"].attempts) == 1

    # 本层不会自动重试；调用方（将来是 LLM）再次调用才会执行第 2 次
    second = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "retry"}
    )
    assert second["ok"] is True
    assert state.execution_counts["search_materials"] == 2
    assert state.steps["s1"].status == "succeeded"
    assert len(state.steps["s1"].attempts) == 2
    assert state.steps["s1"].attempts[0].result["ok"] is False
    assert state.steps["s1"].attempts[1].result["ok"] is True


def test_guard_reject_does_not_count_as_execution(executor, tmp_path):
    state = make_state(tmp_path, inject_failures={"generate_script": "1"})
    apply_standard_plan(executor, state)
    blocked = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": ["M001"], "format": "graphic", "reason": "t"},
    )
    assert blocked["error"]["guard_rejected"] is True
    assert state.execution_counts.get("generate_script", 0) == 0

    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    first_real = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": state.steps["s1"].attempts[-1].result["data"]["material_ids"],
            "format": "graphic",
            "reason": "t",
        },
    )
    assert first_real["ok"] is False
    assert first_real["error"]["injected"] is True
    assert state.execution_counts["generate_script"] == 1


def test_reuse_does_not_count_as_execution(executor, tmp_path):
    state = make_state(tmp_path, inject_failures={"search_materials": "2"})
    apply_standard_plan(executor, state)
    first = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert first["ok"] is True
    reused = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "again"}
    )
    assert reused["data"]["reused"] is True
    assert state.execution_counts["search_materials"] == 1


def test_estimate_must_match_current_script_after_replan(executor, tmp_path):
    """新脚本必须重新估算；拿旧 estimate_id 保存新脚本会被拒绝。"""
    state = make_state(tmp_path, budget=20)
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
    old_estimate = r3["data"]["estimate_id"]
    executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "生成脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算成本", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s4", "name": "保存方案", "tool": "save_plan", "depends_on": ["s3"]},
                {"step_id": "s5", "name": "基础视频", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "估算新脚本", "tool": "estimate_cost", "depends_on": ["s5"]},
                {"step_id": "s7", "name": "保存新方案", "tool": "save_plan", "depends_on": ["s6"]},
            ],
            "reason": "replan",
        },
    )
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
    # 先让依赖满足，再故意提交旧 estimate_id
    executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r5["data"]["script_id"], "reason": "t"}
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
    assert stale["ok"] is False
    # 旧估算不在 s7 依赖链 → 血缘校验优先；否则工具层 STALE_ESTIMATE
    assert stale["error"]["code"] in ("DEPENDENCY_ARTIFACT_MISMATCH", "STALE_ESTIMATE")


def test_always_inject_and_retry_exhausted(executor, tmp_path):
    state = make_state(
        tmp_path,
        inject_failures={"save_plan": "always"},
        max_attempts_per_step=2,
        budget=15,
    )
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
    args = {
        "step_id": "s4",
        "script_id": r2["data"]["script_id"],
        "estimate_id": r3["data"]["estimate_id"],
        "reason": "t",
    }
    a1 = executor.dispatch(state, "save_plan", args)
    a2 = executor.dispatch(state, "save_plan", args)
    a3 = executor.dispatch(state, "save_plan", args)
    assert a1["ok"] is False and a1["error"]["injected"] is True
    assert a2["ok"] is False and a2["error"]["injected"] is True
    assert a3["ok"] is False and a3["error"]["code"] == "RETRY_EXHAUSTED"
    # 第 3 次未真实执行工具
    assert state.execution_counts["save_plan"] == 2
    assert len(state.steps["s4"].attempts) == 3
    assert state.steps["s1"].status == "succeeded"
    assert state.steps["s2"].status == "succeeded"
    assert state.steps["s3"].status == "succeeded"
