"""方案指纹幂等：同内容不重复落盘，不同内容可再次保存。"""

from helpers import apply_standard_plan, make_state
from content_agent.store import compute_fingerprint


def _save_once(executor, state, fmt="graphic"):
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
            "format": fmt,
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
    return r1, r2, r3, r4


def test_fingerprint_ignores_topic_alone():
    base = {
        "topic": "夏季新品发布",
        "budget": 15,
        "deadline": "2026-11-20",
        "format": "graphic",
        "material_ids": ["M002", "M001"],
        "resource_items": ["copywriting", "visual_design", "layout"],
        "total_cost": 8,
        "outline": ["主题：夏季新品发布", "开场", "结尾"],
    }
    same_content_diff_order = dict(base, material_ids=["M001", "M002"])
    different_format = dict(base, format="video_basic", total_cost=10, resource_items=["a"])
    assert compute_fingerprint(base) == compute_fingerprint(same_content_diff_order)
    assert compute_fingerprint(base) != compute_fingerprint(different_format)
    # 同主题不同费用必须不同
    assert compute_fingerprint(base) != compute_fingerprint(dict(base, total_cost=9))


def test_fingerprint_includes_outline_content():
    base = {
        "topic": "夏季新品发布",
        "budget": 15,
        "deadline": "2026-11-20",
        "format": "graphic",
        "material_ids": ["M001", "M002"],
        "resource_items": ["copywriting", "visual_design", "layout"],
        "total_cost": 8,
        "outline": ["A", "B"],
    }
    same_outline_whitespace = dict(base, outline=["  A  ", "B"])
    different_outline = dict(base, outline=["A", "B-changed"])
    # 运行期随机 id 不得影响指纹
    with_noise = dict(base, script_id="script_aaa", estimate_id="est_bbb", run_id="run_ccc")
    assert compute_fingerprint(base) == compute_fingerprint(same_outline_whitespace)
    assert compute_fingerprint(base) != compute_fingerprint(different_outline)
    assert compute_fingerprint(base) == compute_fingerprint(with_noise)


def test_duplicate_save_same_run(executor, tmp_path, runtime):
    state = make_state(tmp_path, budget=15)
    _, _, _, first = _save_once(executor, state)
    assert first["ok"] and first["data"]["duplicate"] is False
    count_after_first = runtime.store.plan_count()

    # 同一次运行再次 save：步骤已成功，应复用而不是再写
    reused = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": first["data"]["script_id"],
            "estimate_id": first["data"]["estimate_id"],
            "reason": "again",
        },
    )
    assert reused["ok"]
    assert reused["data"].get("reused") is True
    assert runtime.store.plan_count() == count_after_first

    # 绕过复用，直接打 store：仍应 duplicate（含规范化 outline，不含随机 id）
    script = state.artifacts["scripts"][first["data"]["script_id"]]
    doc = {
        "topic": state.topic,
        "budget": state.budget,
        "deadline": state.deadline,
        "format": "graphic",
        "material_ids": script["material_ids"],
        "resource_items": ["copywriting", "visual_design", "layout"],
        "total_cost": 8,
        "outline": list(script["outline"]),
        "script_id": "script_should_be_ignored",
        "estimate_id": "est_should_be_ignored",
        "run_id": "run_should_be_ignored",
    }
    second = runtime.store.save(doc)
    assert second["duplicate"] is True
    assert second["plan_id"] == first["data"]["plan_id"]
    assert runtime.store.plan_count() == count_after_first


def test_duplicate_across_runs_same_store(executor, runtime, tmp_path):
    state1 = make_state(tmp_path, budget=15)
    state1.run_id = "run_a"
    _, _, _, first = _save_once(executor, state1)

    state2 = make_state(tmp_path, budget=15)
    state2.run_id = "run_b"
    # 使用同一 plans_dir / runtime.store
    _, _, _, second = _save_once(executor, state2)
    assert second["data"]["duplicate"] is True
    assert second["data"]["plan_id"] == first["data"]["plan_id"]
    assert runtime.store.plan_count() == 1


def test_different_plan_content_saves_again(executor, runtime, tmp_path):
    state = make_state(tmp_path, budget=20)
    apply_standard_plan(executor, state)
    r1 = executor.dispatch(
        state, "search_materials", {"step_id": "s1", "source": "primary", "limit": 2, "reason": "t"}
    )
    # 先保存 graphic
    r2 = executor.dispatch(
        state,
        "generate_script",
        {"step_id": "s2", "material_ids": r1["data"]["material_ids"], "format": "graphic", "reason": "t"},
    )
    r3 = executor.dispatch(
        state, "estimate_cost", {"step_id": "s3", "script_id": r2["data"]["script_id"], "reason": "t"}
    )
    s1 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert s1["ok"] and s1["data"]["duplicate"] is False

    # 重规划：必须保留全部已成功步骤，再追加替代路径
    out = executor.dispatch(
        state,
        "update_plan",
        {
            "steps": [
                {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
                {"step_id": "s2", "name": "生成脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s3", "name": "估算成本", "tool": "estimate_cost", "depends_on": ["s2"]},
                {"step_id": "s4", "name": "保存方案", "tool": "save_plan", "depends_on": ["s3"]},
                {"step_id": "s5", "name": "基础视频脚本", "tool": "generate_script", "depends_on": ["s1"]},
                {"step_id": "s6", "name": "估算", "tool": "estimate_cost", "depends_on": ["s5"]},
                {"step_id": "s7", "name": "保存", "tool": "save_plan", "depends_on": ["s6"]},
            ],
            "reason": "change format",
        },
    )
    assert out["ok"], out
    assert state.steps["s2"].status == "succeeded"
    assert state.steps["s4"].status == "succeeded"
    r2b = executor.dispatch(
        state,
        "generate_script",
        {
            "step_id": "s5",
            "material_ids": r1["data"]["material_ids"],
            "format": "video_basic",
            "reason": "t",
        },
    )
    r3b = executor.dispatch(
        state, "estimate_cost", {"step_id": "s6", "script_id": r2b["data"]["script_id"], "reason": "t"}
    )
    s2 = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s7",
            "script_id": r2b["data"]["script_id"],
            "estimate_id": r3b["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert s2["ok"]
    assert s2["data"]["duplicate"] is False
    assert s2["data"]["plan_id"] != s1["data"]["plan_id"]
    assert runtime.store.plan_count() == 2


def test_same_outline_reused_across_runs_different_script_ids(executor, runtime, tmp_path):
    """跨运行：脚本内容相同（含 outline）应复用；仅 script_id 不同不算新方案。"""
    state1 = make_state(tmp_path, budget=15)
    state1.run_id = "run_outline_a"
    _, r2a, _, first = _save_once(executor, state1)
    outline = list(r2a["data"]["outline"])

    state2 = make_state(tmp_path, budget=15)
    state2.run_id = "run_outline_b"
    _, r2b, _, second = _save_once(executor, state2)
    assert r2b["data"]["script_id"] != r2a["data"]["script_id"]
    assert list(r2b["data"]["outline"]) == outline
    assert second["data"]["duplicate"] is True
    assert second["data"]["plan_id"] == first["data"]["plan_id"]


def test_outline_change_creates_new_plan(executor, runtime, tmp_path):
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
    first = executor.dispatch(
        state,
        "save_plan",
        {
            "step_id": "s4",
            "script_id": r2["data"]["script_id"],
            "estimate_id": r3["data"]["estimate_id"],
            "reason": "t",
        },
    )
    assert first["ok"] and first["data"]["duplicate"] is False

    # 直接向 store 提交「同字段但 outline 不同」的方案 → 必须新建
    script = state.artifacts["scripts"][r2["data"]["script_id"]]
    altered = {
        "topic": state.topic,
        "budget": state.budget,
        "deadline": state.deadline,
        "format": "graphic",
        "material_ids": list(script["material_ids"]),
        "resource_items": ["copywriting", "visual_design", "layout"],
        "total_cost": 8,
        "outline": list(script["outline"]) + ["额外改动行"],
    }
    second = runtime.store.save(altered)
    assert second["duplicate"] is False
    assert second["plan_id"] != first["data"]["plan_id"]
    assert runtime.store.plan_count() == 2
