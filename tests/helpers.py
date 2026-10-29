from __future__ import annotations

from pathlib import Path

from content_agent.executor import ToolExecutor
from content_agent.state import RunState

STANDARD_PLAN = [
    {"step_id": "s1", "name": "检索素材", "tool": "search_materials", "depends_on": []},
    {"step_id": "s2", "name": "生成脚本", "tool": "generate_script", "depends_on": ["s1"]},
    {"step_id": "s3", "name": "估算成本", "tool": "estimate_cost", "depends_on": ["s2"]},
    {"step_id": "s4", "name": "保存方案", "tool": "save_plan", "depends_on": ["s3"]},
]


def make_state(
    tmp_path: Path,
    *,
    budget: int = 15,
    deadline: str = "2026-11-20",
    today: str = "2026-11-01",
    topic: str = "夏季新品发布",
    max_attempts_per_step: int = 3,
    inject_failures: dict[str, str] | None = None,
) -> RunState:
    return RunState.create(
        topic=topic,
        budget=budget,
        deadline=deadline,
        today=today,
        max_attempts_per_step=max_attempts_per_step,
        inject_failures=inject_failures,
        run_id=f"test_{tmp_path.name}",
    )


def apply_standard_plan(executor: ToolExecutor, state: RunState) -> None:
    result = executor.dispatch(state, "update_plan", {"steps": STANDARD_PLAN, "reason": "test"})
    assert result["ok"], result
