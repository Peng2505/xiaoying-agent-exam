"""四个业务工具。

费用与工期只由本模块根据 data/costs.json 计算，不接受调用方传入的数字。
失败注入按「通过守卫后的真实执行次数」触发；工具层只返回观察结果，
不会自动重试——重试与否由阶段 C 的 LLM 决定。
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from content_agent import results
from content_agent.state import RunState, record_attempt
from content_agent.store import PlanStore

INJECT_ERRORS = {
    "search_materials": ("SOURCE_UNAVAILABLE", "素材源暂时不可用（测试注入）。"),
    "generate_script": ("GENERATION_FAILED", "脚本生成服务暂时失败（测试注入）。"),
    "estimate_cost": ("COST_SERVICE_ERROR", "成本估算服务暂时失败（测试注入）。"),
    "save_plan": ("STORAGE_ERROR", "方案存储服务暂时失败（测试注入）。"),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def global_min_cost(costs: dict[str, Any]) -> dict[str, Any]:
    """穷举费用表中全部 format，返回全局最低成本（确定性，不依赖模型）。"""
    per_format = {
        name: calc_format_cost(costs, name)["total_cost"] for name in costs["formats"]
    }
    min_cost = min(per_format.values())
    return {
        "per_format": per_format,
        "global_min_cost": min_cost,
        "cheapest_formats": [name for name, cost in per_format.items() if cost == min_cost],
    }


def calc_format_cost(costs: dict[str, Any], format_name: str) -> dict[str, Any]:
    """确定性费用/工期计算。"""
    if format_name not in costs["formats"]:
        raise KeyError(format_name)
    resource_ids = list(costs["formats"][format_name]["resources"])
    items = []
    total_cost = 0
    total_days = 0
    for rid in resource_ids:
        resource = costs["resources"][rid]
        items.append(
            {
                "resource_id": rid,
                "name": resource["name"],
                "cost": int(resource["cost"]),
                "days": int(resource["days"]),
            }
        )
        total_cost += int(resource["cost"])
        total_days += int(resource["days"])
    return {
        "format": format_name,
        "items": items,
        "resource_items": resource_ids,
        "total_cost": total_cost,
        "total_days": total_days,
    }


def finish_date_for(today: str | date, total_days: int) -> date:
    base = today if isinstance(today, date) else datetime.strptime(today, "%Y-%m-%d").date()
    return base + timedelta(days=total_days)


def _match_materials(topic: str, catalog: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    tokens = [t for t in topic.replace("，", " ").replace(",", " ").split() if t]
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in catalog:
        haystack = " ".join([item["title"], *item.get("tags", [])])
        score = sum(1 for token in tokens if token in haystack)
        # 主题整串包含也计分，便于「夏季新品发布」命中 tags
        if topic in haystack or any(tag in topic for tag in item.get("tags", [])):
            score += 2
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [
        {"id": m["id"], "title": m["title"], "tags": list(m.get("tags", [])), "type": m["type"]}
        for _, m in scored[:limit]
    ]


class ToolRuntime:
    """工具执行入口。守卫通过后才进入这里；本层不决定是否重试。"""

    def __init__(self, data_dir: Path, plans_dir: Path):
        self.data_dir = Path(data_dir)
        self.plans_dir = Path(plans_dir)
        self.materials = load_json(self.data_dir / "materials.json")
        self.costs = load_json(self.data_dir / "costs.json")
        self.store = PlanStore(self.plans_dir)
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "search_materials": self.search_materials,
            "generate_script": self.generate_script,
            "estimate_cost": self.estimate_cost,
            "save_plan": self.save_plan,
        }

    def available_formats(self) -> dict[str, str]:
        # 只暴露名称与内容描述，不暴露价格，避免诱导固定决策路径。
        return {name: spec["description"] for name, spec in self.costs["formats"].items()}

    def should_inject(self, state: RunState, tool: str, next_count: int) -> bool:
        spec = state.inject_failures.get(tool)
        if spec is None:
            return False
        if spec == "always":
            return True
        return str(next_count) == str(spec)

    def execute(self, state: RunState, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool not in self._handlers:
            return results.fail(tool, "UNKNOWN_TOOL", f"未知工具：{tool}")

        validation = self._validate_args(tool, args)
        if validation is not None:
            return validation

        next_count = int(state.execution_counts.get(tool, 0)) + 1
        state.execution_counts[tool] = next_count
        injected = self.should_inject(state, tool, next_count)
        if injected:
            code, message = INJECT_ERRORS[tool]
            return results.fail(tool, code, message, retryable=True, injected=True)

        try:
            return self._handlers[tool](state, **{k: v for k, v in args.items() if k != "reason"})
        except Exception as exc:  # noqa: BLE001 - 结构化错误交回 Agent，禁止进程崩溃
            return results.fail(
                tool,
                "TOOL_EXCEPTION",
                f"工具内部未预期异常：{type(exc).__name__}: {exc}",
                retryable=True,
            )

    def _validate_args(self, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """业务参数严格校验。非法时返回结构化错误，不产生产物。"""
        if tool == "search_materials":
            source = args.get("source", "primary")
            if not isinstance(source, str) or not source.strip():
                return results.fail(tool, "INVALID_ARGUMENTS", "source 必须是非空字符串")
            if "limit" in args and args["limit"] is not None:
                try:
                    limit_n = int(args["limit"])
                except (TypeError, ValueError):
                    return results.fail(
                        tool, "INVALID_LIMIT", f"limit 必须是正整数，当前值：{args['limit']!r}"
                    )
                if limit_n <= 0:
                    return results.fail(
                        tool, "INVALID_LIMIT", f"limit 必须大于 0，当前值：{limit_n}"
                    )
            if "topic" in args and args["topic"] is not None and not isinstance(args["topic"], str):
                return results.fail(tool, "INVALID_ARGUMENTS", "topic 必须是字符串")
            return None

        if tool == "generate_script":
            fmt = args.get("format")
            if not isinstance(fmt, str) or not fmt.strip():
                return results.fail(tool, "INVALID_ARGUMENTS", "format 必须是非空字符串")
            material_ids = args.get("material_ids")
            if not isinstance(material_ids, list) or not material_ids:
                return results.fail(tool, "INVALID_MATERIAL", "material_ids 必须是非空列表")
            bad_types = [
                i
                for i, mid in enumerate(material_ids)
                if not isinstance(mid, str) or not mid.strip()
            ]
            if bad_types:
                return results.fail(
                    tool,
                    "INVALID_ARGUMENTS",
                    "material_ids 的每个元素必须是非空字符串；"
                    f"非法下标：{bad_types}（收到类型非字符串或空串，例如 dict）",
                    bad_indexes=bad_types,
                )
            return None

        if tool == "estimate_cost":
            script_id = args.get("script_id")
            if not isinstance(script_id, str) or not script_id.strip():
                return results.fail(tool, "INVALID_ARGUMENTS", "script_id 必须是非空字符串")
            return None

        if tool == "save_plan":
            for key in ("script_id", "estimate_id"):
                val = args.get(key)
                if not isinstance(val, str) or not val.strip():
                    return results.fail(tool, "INVALID_ARGUMENTS", f"{key} 必须是非空字符串")
            return None

        return None

    def search_materials(
        self,
        state: RunState,
        *,
        step_id: str,
        topic: str | None = None,
        source: str = "primary",
        limit: int = 5,
        **_: Any,
    ) -> dict[str, Any]:
        tool = "search_materials"
        topic = topic or state.topic
        if source not in self.materials["sources"]:
            return results.fail(tool, "INVALID_SOURCE", f"未知素材源：{source}")
        try:
            limit_n = int(limit)
        except (TypeError, ValueError):
            return results.fail(tool, "INVALID_LIMIT", f"limit 必须是正整数，当前值：{limit!r}")
        if limit_n <= 0:
            return results.fail(tool, "INVALID_LIMIT", f"limit 必须大于 0，当前值：{limit_n}")

        matched = _match_materials(topic, self.materials["sources"][source], limit_n)
        if not matched:
            return results.fail(tool, "NO_MATCH", f"主题 {topic!r} 在源 {source} 中没有匹配素材")

        artifact_id = f"matset_{uuid.uuid4().hex[:10]}"
        data = {
            "artifact_id": artifact_id,
            "topic": topic,
            "source": source,
            "materials": matched,
            "material_ids": [m["id"] for m in matched],
        }
        state.artifacts["materials"][artifact_id] = data
        for material in matched:
            state.artifacts["materials"][material["id"]] = {
                **material,
                "from_set": artifact_id,
                "source": source,
            }
        return results.ok(tool, data)

    def generate_script(
        self,
        state: RunState,
        *,
        step_id: str,
        material_ids: list[str],
        format: str,
        **_: Any,
    ) -> dict[str, Any]:
        tool = "generate_script"
        if format not in self.costs["formats"]:
            return results.fail(
                tool,
                "INVALID_FORMAT",
                f"未知格式：{format}。可选：{', '.join(self.costs['formats'])}",
            )
        # 元素类型已在 _validate_args 校验；此处再防防御性拷贝为纯字符串列表
        ids = [str(mid).strip() for mid in material_ids]

        known = state.artifacts.get("materials", {})
        missing = [mid for mid in ids if mid not in known or "title" not in known[mid]]
        if missing:
            return results.fail(
                tool,
                "INVALID_MATERIAL",
                f"素材不存在或不来自已成功的检索：{', '.join(missing)}",
            )

        resources = list(self.costs["formats"][format]["resources"])
        script_id = f"script_{uuid.uuid4().hex[:10]}"
        titles = [known[mid]["title"] for mid in ids]
        outline = [
            f"主题：{state.topic}",
            f"形式：{self.costs['formats'][format]['description']}",
            "开场：引出活动主题与目标受众",
            f"主体：结合素材展示卖点 —— {', '.join(titles)}",
            "结尾：行动号召与活动截止提醒",
        ]
        data = {
            "script_id": script_id,
            "artifact_id": script_id,
            "format": format,
            "material_ids": list(ids),
            "outline": outline,
            "required_resources": resources,
        }
        state.artifacts["scripts"][script_id] = data
        return results.ok(tool, data)

    def estimate_cost(
        self,
        state: RunState,
        *,
        step_id: str,
        script_id: str,
        **_: Any,
    ) -> dict[str, Any]:
        tool = "estimate_cost"
        script = state.artifacts.get("scripts", {}).get(script_id)
        if not script:
            return results.fail(tool, "UNKNOWN_SCRIPT", f"未知脚本：{script_id}")

        calc = calc_format_cost(self.costs, script["format"])
        finish = finish_date_for(state.today, calc["total_days"])
        deadline = datetime.strptime(state.deadline, "%Y-%m-%d").date()
        within_budget = calc["total_cost"] <= state.budget
        meets_deadline = finish <= deadline
        estimate_id = f"est_{uuid.uuid4().hex[:10]}"
        data = {
            "estimate_id": estimate_id,
            "artifact_id": estimate_id,
            "script_id": script_id,
            "format": script["format"],
            "items": calc["items"],
            "resource_items": calc["resource_items"],
            "total_cost": calc["total_cost"],
            "total_days": calc["total_days"],
            "budget": state.budget,
            "within_budget": within_budget,
            "over_by": max(0, calc["total_cost"] - state.budget),
            "finish_date": finish.isoformat(),
            "deadline": state.deadline,
            "meets_deadline": meets_deadline,
            "days_over": max(0, (finish - deadline).days),
        }
        state.artifacts["estimates"][estimate_id] = data
        return results.ok(tool, data)

    def save_plan(
        self,
        state: RunState,
        *,
        step_id: str,
        script_id: str,
        estimate_id: str,
        **_: Any,
    ) -> dict[str, Any]:
        tool = "save_plan"
        script = state.artifacts.get("scripts", {}).get(script_id)
        estimate = state.artifacts.get("estimates", {}).get(estimate_id)
        if not script:
            return results.fail(tool, "UNKNOWN_SCRIPT", f"未知脚本：{script_id}")
        if not estimate:
            return results.fail(tool, "STALE_ESTIMATE", f"未知估算：{estimate_id}")
        if estimate.get("script_id") != script_id:
            return results.fail(
                tool,
                "STALE_ESTIMATE",
                f"估算 {estimate_id} 对应脚本 {estimate.get('script_id')}，与请求的 {script_id} 不一致",
            )
        if estimate.get("format") != script.get("format"):
            return results.fail(
                tool,
                "STALE_ESTIMATE",
                f"估算格式 {estimate.get('format')} 与脚本格式 {script.get('format')} 不一致，请重新估算",
            )

        # 保存前按 script 重新计算，不信任缓存数字。
        recalc = calc_format_cost(self.costs, script["format"])
        finish = finish_date_for(state.today, recalc["total_days"])
        deadline = datetime.strptime(state.deadline, "%Y-%m-%d").date()
        violations: list[str] = []
        if recalc["total_cost"] > state.budget:
            violations.append(
                f"预算超限：费用 {recalc['total_cost']} > 预算 {state.budget}"
            )
        if finish > deadline:
            violations.append(
                f"截止时间不满足：完成日 {finish.isoformat()} > 截止日 {state.deadline}"
            )
        if recalc["total_cost"] != int(estimate["total_cost"]) or recalc["format"] != estimate["format"]:
            violations.append("估算结果与按脚本重新计算结果不一致")
        if violations:
            return results.fail(
                tool,
                "CONSTRAINT_VIOLATION",
                "；".join(violations),
                retryable=False,
                violations=violations,
                recomputed={
                    "total_cost": recalc["total_cost"],
                    "total_days": recalc["total_days"],
                    "finish_date": finish.isoformat(),
                },
            )

        document = {
            "topic": state.topic,
            "budget": state.budget,
            "deadline": state.deadline,
            "today": state.today,
            "format": script["format"],
            "material_ids": list(script["material_ids"]),
            "resource_items": list(recalc["resource_items"]),
            "total_cost": recalc["total_cost"],
            "total_days": recalc["total_days"],
            "finish_date": finish.isoformat(),
            "script_id": script_id,
            "estimate_id": estimate_id,
            "outline": list(script["outline"]),
            "run_id": state.run_id,
        }
        saved = self.store.save(document)
        data = {
            **saved,
            "artifact_id": saved["plan_id"],
            "total_cost": recalc["total_cost"],
            "total_days": recalc["total_days"],
            "finish_date": finish.isoformat(),
            "script_id": script_id,
            "estimate_id": estimate_id,
        }
        state.artifacts["plans"][saved["plan_id"]] = data
        return results.ok(tool, data)
