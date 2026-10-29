"""合成数据的一致性检查：费用表与素材库可被加载，三种格式的合计与设计一致。"""

import json

from content_agent.config import load_settings


def _load(name):
    return json.loads((load_settings().data_dir / name).read_text(encoding="utf-8"))


def test_every_format_resource_exists_in_cost_table():
    costs = _load("costs.json")
    for fmt, spec in costs["formats"].items():
        for rid in spec["resources"]:
            assert rid in costs["resources"], f"{fmt} 引用了不存在的资源 {rid}"


def test_format_totals_match_design():
    costs = _load("costs.json")
    totals = {
        fmt: (
            sum(costs["resources"][r]["cost"] for r in spec["resources"]),
            sum(costs["resources"][r]["days"] for r in spec["resources"]),
        )
        for fmt, spec in costs["formats"].items()
    }
    assert totals == {"video_premium": (12, 5), "video_basic": (10, 4), "graphic": (8, 3)}


def test_material_ids_are_unique_across_sources():
    sources = _load("materials.json")["sources"]
    ids = [m["id"] for items in sources.values() for m in items]
    assert len(ids) == len(set(ids))
    assert set(sources) == {"primary", "backup"}
