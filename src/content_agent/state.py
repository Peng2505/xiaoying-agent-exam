"""运行状态与步骤状态。

步骤状态只能通过 record_attempt 根据工具实际返回结果改变。
attempts 只追加不删除：重试成功也不会抹掉之前的失败历史。
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


STEP_PENDING = "pending"
STEP_SUCCEEDED = "succeeded"
STEP_FAILED = "failed"
STEP_SUPERSEDED = "superseded"

RUN_INCOMPLETE = "incomplete"
RUN_COMPLETED = "completed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


@dataclass
class Attempt:
    attempt_no: int
    tool: str
    args: dict[str, Any]
    result: dict[str, Any]
    reused: bool = False
    injected: bool = False
    timestamp: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attempt:
        return cls(**data)


@dataclass
class Step:
    step_id: str
    name: str
    tool: str
    depends_on: list[str] = field(default_factory=list)
    status: str = STEP_PENDING
    attempts: list[Attempt] = field(default_factory=list)
    artifact_id: str | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "tool": self.tool,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "attempts": [a.to_dict() for a in self.attempts],
            "artifact_id": self.artifact_id,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        return cls(
            step_id=data["step_id"],
            name=data["name"],
            tool=data["tool"],
            depends_on=list(data.get("depends_on") or []),
            status=data.get("status", STEP_PENDING),
            attempts=[Attempt.from_dict(a) for a in data.get("attempts") or []],
            artifact_id=data.get("artifact_id"),
            error=data.get("error"),
        )


@dataclass
class RunState:
    run_id: str
    topic: str
    budget: int
    deadline: str  # YYYY-MM-DD
    today: str  # YYYY-MM-DD
    steps: dict[str, Step] = field(default_factory=dict)
    step_order: list[str] = field(default_factory=list)
    artifacts: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "materials": {},
            "scripts": {},
            "estimates": {},
            "plans": {},
        }
    )
    status: str = RUN_INCOMPLETE
    reason: str | None = None
    message: str | None = None
    gap: dict[str, Any] | None = None
    steps_used: int = 0
    cumulative_steps: int = 0
    session: int = 1
    max_steps: int = 12
    max_attempts_per_step: int = 3
    max_cumulative_steps: int = 36
    inject_failures: dict[str, str] = field(default_factory=dict)
    execution_counts: dict[str, int] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        topic: str,
        budget: int,
        deadline: date | str,
        today: date | str,
        max_steps: int = 12,
        max_attempts_per_step: int = 3,
        max_cumulative_steps: int = 36,
        inject_failures: dict[str, str] | None = None,
        run_id: str | None = None,
    ) -> RunState:
        return cls(
            run_id=run_id or new_run_id(),
            topic=topic,
            budget=int(budget),
            deadline=str(deadline),
            today=str(today),
            max_steps=max_steps,
            max_attempts_per_step=max_attempts_per_step,
            max_cumulative_steps=max_cumulative_steps,
            inject_failures=dict(inject_failures or {}),
        )

    def get_step(self, step_id: str) -> Step | None:
        return self.steps.get(step_id)

    def succeeded_steps(self) -> list[Step]:
        return [s for s in self.steps.values() if s.status == STEP_SUCCEEDED]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "topic": self.topic,
            "budget": self.budget,
            "deadline": self.deadline,
            "today": self.today,
            "steps": {sid: step.to_dict() for sid, step in self.steps.items()},
            "step_order": list(self.step_order),
            "artifacts": deepcopy(self.artifacts),
            "status": self.status,
            "reason": self.reason,
            "message": self.message,
            "gap": deepcopy(self.gap),
            "steps_used": self.steps_used,
            "cumulative_steps": self.cumulative_steps,
            "session": self.session,
            "max_steps": self.max_steps,
            "max_attempts_per_step": self.max_attempts_per_step,
            "max_cumulative_steps": self.max_cumulative_steps,
            "inject_failures": dict(self.inject_failures),
            "execution_counts": dict(self.execution_counts),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        steps = {sid: Step.from_dict(raw) for sid, raw in (data.get("steps") or {}).items()}
        return cls(
            run_id=data["run_id"],
            topic=data["topic"],
            budget=int(data["budget"]),
            deadline=data["deadline"],
            today=data["today"],
            steps=steps,
            step_order=list(data.get("step_order") or []),
            artifacts=deepcopy(
                data.get("artifacts")
                or {"materials": {}, "scripts": {}, "estimates": {}, "plans": {}}
            ),
            status=data.get("status", RUN_INCOMPLETE),
            reason=data.get("reason"),
            message=data.get("message"),
            gap=deepcopy(data.get("gap")),
            steps_used=int(data.get("steps_used") or 0),
            cumulative_steps=int(data.get("cumulative_steps") or 0),
            session=int(data.get("session") or 1),
            max_steps=int(data.get("max_steps") or 12),
            max_attempts_per_step=int(data.get("max_attempts_per_step") or 3),
            max_cumulative_steps=int(data.get("max_cumulative_steps") or 36),
            inject_failures=dict(data.get("inject_failures") or {}),
            execution_counts=dict(data.get("execution_counts") or {}),
            created_at=data.get("created_at") or _utcnow(),
            updated_at=data.get("updated_at") or _utcnow(),
        )


def record_attempt(
    step: Step,
    *,
    tool: str,
    args: dict[str, Any],
    result: dict[str, Any],
    reused: bool = False,
    injected: bool = False,
) -> Attempt:
    """根据工具结果更新步骤状态。这是改变步骤状态的唯一入口。"""
    attempt = Attempt(
        attempt_no=len(step.attempts) + 1,
        tool=tool,
        args=deepcopy(args),
        result=deepcopy(result),
        reused=reused,
        injected=injected,
    )
    step.attempts.append(attempt)

    if reused:
        # 复用已成功产物：状态保持 succeeded，不覆盖 artifact。
        step.status = STEP_SUCCEEDED
        return attempt

    if result.get("ok"):
        step.status = STEP_SUCCEEDED
        data = result.get("data") or {}
        step.artifact_id = (
            data.get("artifact_id")
            or data.get("script_id")
            or data.get("estimate_id")
            or data.get("plan_id")
            or step.artifact_id
        )
        step.error = None
    else:
        step.status = STEP_FAILED
        step.error = deepcopy(result.get("error"))
    return attempt


def save_state(state: RunState, runs_dir: Path) -> Path:
    """原子写入 runs/<run_id>/state.json。"""
    run_dir = Path(runs_dir) / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "state.json"
    tmp = run_dir / "state.json.tmp"
    state.updated_at = _utcnow()
    payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)
    return target


def load_state(run_id: str, runs_dir: Path) -> RunState:
    path = Path(runs_dir) / run_id / "state.json"
    if not path.is_file():
        raise FileNotFoundError(f"找不到运行状态：{path}")
    return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def resume_summary(state: RunState) -> dict[str, Any]:
    """续跑时交给模型的完整上下文摘要（不回放原始 messages）。"""
    scripts = {
        sid: {
            "script_id": sid,
            "format": data.get("format"),
            "material_ids": data.get("material_ids"),
        }
        for sid, data in state.artifacts.get("scripts", {}).items()
    }
    estimates = {
        eid: {
            "estimate_id": eid,
            "script_id": data.get("script_id"),
            "format": data.get("format"),
            "total_cost": data.get("total_cost"),
            "within_budget": data.get("within_budget"),
            "meets_deadline": data.get("meets_deadline"),
        }
        for eid, data in state.artifacts.get("estimates", {}).items()
    }
    material_ids = [
        mid
        for mid, data in state.artifacts.get("materials", {}).items()
        if isinstance(data, dict) and "title" in data
    ]
    return {
        "run_id": state.run_id,
        "session": state.session,
        "topic": state.topic,
        "budget": state.budget,
        "deadline": state.deadline,
        "today": state.today,
        "previous_status": state.status,
        "previous_reason": state.reason,
        "cumulative_steps": state.cumulative_steps,
        "execution_counts": dict(state.execution_counts),
        "steps": [
            {
                "step_id": sid,
                "name": state.steps[sid].name,
                "tool": state.steps[sid].tool,
                "depends_on": state.steps[sid].depends_on,
                "status": state.steps[sid].status,
                "artifact_id": state.steps[sid].artifact_id,
                "attempt_count": len(state.steps[sid].attempts),
                "failed_attempt_count": sum(
                    1 for a in state.steps[sid].attempts if not a.result.get("ok") and not a.reused
                ),
                "last_error": state.steps[sid].error,
            }
            for sid in state.step_order
            if sid in state.steps
        ],
        "artifacts": {
            "material_ids": material_ids,
            "scripts": scripts,
            "estimates": estimates,
            "plans": list(state.artifacts.get("plans", {})),
        },
        "instruction": (
            "这是续跑。请复用已成功步骤的产物，不要重复执行参数未变的成功业务步骤；"
            "根据失败历史决定重试、换方案或保存；不得使用与当前脚本不匹配的旧 estimate_id。"
        ),
    }


def prepare_resume(
    state: RunState,
    *,
    max_steps: int | None = None,
    max_cumulative_steps: int | None = None,
    inject_failures: dict[str, str] | None = None,
    clear_inject: bool = True,
) -> RunState:
    """准备续跑会话：重置本会话步数，保留成功产物与失败历史。

    安全边界：若累计决策步已达 max_cumulative_steps，拒绝续跑，
    防止通过反复新建 step_id 绕过单步重试上限。
    """
    if state.status == RUN_COMPLETED:
        raise ValueError(f"运行 {state.run_id} 已完成，不能续跑")
    if max_cumulative_steps is not None:
        state.max_cumulative_steps = max_cumulative_steps
    if state.cumulative_steps >= state.max_cumulative_steps:
        raise ValueError(
            f"运行 {state.run_id} 累计决策步 {state.cumulative_steps} "
            f"已达全局上限 {state.max_cumulative_steps}，拒绝续跑"
        )
    state.session += 1
    state.steps_used = 0
    if max_steps is not None:
        state.max_steps = max_steps
    if inject_failures is not None:
        state.inject_failures = dict(inject_failures)
    elif clear_inject:
        state.inject_failures = {}
    state.status = RUN_INCOMPLETE
    state.reason = None
    state.message = None
    state.gap = None
    return state
