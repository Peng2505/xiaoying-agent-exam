"""方案保存与指纹幂等。

指纹基于方案内容，不只看活动主题：topic、预算、截止时间、格式、
素材 id、资源条目、合计费用、规范化后的脚本大纲（outline）。
不纳入 script_id / estimate_id / run_id / plan_id 等运行期随机标识，
避免同内容不同运行被误判为新方案。
相同指纹返回原 plan_id，不写新文件。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def normalize_outline(outline: Any) -> list[str]:
    """规范化脚本大纲：仅保留字符串行并 strip，忽略运行期噪声。"""
    if outline is None:
        return []
    if isinstance(outline, str):
        text = outline.strip()
        return [text] if text else []
    if not isinstance(outline, list):
        text = str(outline).strip()
        return [text] if text else []
    return [str(line).strip() for line in outline if str(line).strip()]


def compute_fingerprint(payload: dict[str, Any]) -> str:
    canonical = {
        "topic": payload["topic"],
        "budget": int(payload["budget"]),
        "deadline": payload["deadline"],
        "format": payload["format"],
        "material_ids": sorted(payload["material_ids"]),
        "resource_items": list(payload["resource_items"]),
        "total_cost": int(payload["total_cost"]),
        "outline": normalize_outline(payload.get("outline")),
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PlanStore:
    def __init__(self, plans_dir: Path):
        self.plans_dir = Path(plans_dir)
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.plans_dir / "index.json"

    def _load_index(self) -> dict[str, str]:
        if not self.index_path.is_file():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict[str, str]) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    def plan_count(self) -> int:
        return len(list(self.plans_dir.glob("plan_*.json")))

    def save(self, document: dict[str, Any]) -> dict[str, Any]:
        fingerprint = compute_fingerprint(document)
        index = self._load_index()
        if fingerprint in index:
            plan_id = index[fingerprint]
            path = self.plans_dir / f"{plan_id}.json"
            return {
                "plan_id": plan_id,
                "path": str(path),
                "fingerprint": fingerprint,
                "duplicate": True,
            }

        plan_id = f"plan_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        path = self.plans_dir / f"{plan_id}.json"
        stored = {
            **document,
            "plan_id": plan_id,
            "fingerprint": fingerprint,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        index[fingerprint] = plan_id
        self._save_index(index)
        return {
            "plan_id": plan_id,
            "path": str(path),
            "fingerprint": fingerprint,
            "duplicate": False,
        }
