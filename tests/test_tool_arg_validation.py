"""非法工具参数返回结构化错误，不崩溃、不伪造成功产物。"""

from helpers import apply_standard_plan, make_state


def test_generate_script_rejects_dict_in_material_ids(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    apply_standard_plan(executor, state)
    search = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert search["ok"]
    scripts_before = dict(state.artifacts.get("scripts") or {})

    bad = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s2",
            "material_ids": [{"id": "M001"}],  # 曾触发 TypeError: unhashable type: 'dict'
            "format": "graphic",
            "reason": "bad args",
        },
    )
    assert bad["ok"] is False
    assert bad["error"]["code"] == "INVALID_ARGUMENTS"
    assert state.steps["s1"].status == "succeeded"
    assert state.artifacts.get("scripts") == scripts_before
    # 非法参数在真实执行计数之前拒绝，不增加 generate 执行次数
    assert state.execution_counts.get("generate_script", 0) == 0


def test_generate_script_rejects_non_list_material_ids(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    apply_standard_plan(executor, state)
    executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    bad = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": "M001", "format": "graphic", "reason": "t"},
    )
    assert bad["ok"] is False
    assert bad["error"]["code"] == "INVALID_MATERIAL"


def test_estimate_rejects_non_string_script_id(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    apply_standard_plan(executor, state)
    # 直接测工具层校验（dispatch 会先被依赖守卫拦住）
    bad = executor.runtime.execute(
        state, "estimate_cost", {"step_id": "s3", "script_id": {"x": 1}}
    )
    assert bad["ok"] is False
    assert bad["error"]["code"] == "INVALID_ARGUMENTS"
    assert state.execution_counts.get("estimate_cost", 0) == 0


def test_tool_exception_is_caught_as_structured_error(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    apply_standard_plan(executor, state)

    def boom(_state, **_kwargs):
        raise RuntimeError("simulated internal failure")

    executor.runtime._handlers["search_materials"] = boom
    obs = executor.runtime.execute(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2}
    )
    assert obs["ok"] is False
    assert obs["error"]["code"] == "TOOL_EXCEPTION"
    assert "RuntimeError" in obs["error"]["message"]


def test_invalid_args_do_not_mark_succeeded_search_failed(executor, tmp_path):
    state = make_state(tmp_path, budget=15)
    apply_standard_plan(executor, state)
    ok = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    assert ok["ok"]
    # 已成功步骤参数变化：ARGS_MISMATCH，不得破坏成功状态
    bad = executor.dispatch(
        state,
        "search_materials",
        {"step_id": "s1", "source": "backup", "limit": 2, "reason": "t"},
    )
    assert bad["ok"] is False
    assert bad["error"]["code"] == "ARGS_MISMATCH_ON_SUCCEEDED"
    assert state.steps["s1"].status == "succeeded"
