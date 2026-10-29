"""费用与工期由代码确定性计算，不接受外部数字。"""

from datetime import date

from content_agent.tools import calc_format_cost, finish_date_for, load_json


def test_format_cost_totals(data_dir):
    costs = load_json(data_dir / "costs.json")
    assert calc_format_cost(costs, "video_premium")["total_cost"] == 12
    assert calc_format_cost(costs, "video_basic")["total_cost"] == 10
    assert calc_format_cost(costs, "graphic")["total_cost"] == 8
    assert calc_format_cost(costs, "video_premium")["total_days"] == 5
    assert calc_format_cost(costs, "video_basic")["total_days"] == 4
    assert calc_format_cost(costs, "graphic")["total_days"] == 3


def test_finish_date_is_today_plus_days():
    assert finish_date_for("2026-11-01", 5) == date(2026, 11, 6)
    assert finish_date_for(date(2026, 11, 1), 0) == date(2026, 11, 1)
