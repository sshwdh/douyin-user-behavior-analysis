"""聚合看板的重复事件、筛选边界、热力图分母与全量对账测试。"""

from datetime import date

import duckdb
import pandas as pd
import pytest

from douyin_analysis.dashboard_aggregates import (
    category_counts,
    filter_events,
    load_aggregate,
    weekday_heatmap,
)
from douyin_analysis.dashboard_data import read_report
from douyin_analysis.dashboard_export import aggregate_events


def test_aggregation_preserves_repeated_events_and_user_counts() -> None:
    """同一用户重复交互计为多个事件，但全期用户只计一次。"""
    events = pd.DataFrame(
        {
            "user_id": [1, 1, 1, 2],
            "category_id": [10, 10, 10, 20],
            "behavior_type": [1, 1, 4, 1],
            "event_time": pd.to_datetime(
                ["2025-11-18 00:00"] * 3 + ["2025-11-19 00:00"]
            ),
        }
    )
    with duckdb.connect() as connection:
        connection.register("events", events)
        tables = aggregate_events(connection)
    assert tables["hourly_behavior"].events.sum() == 4
    assert tables["daily_categories"].events.sum() == 4
    users = tables["user_activity"].query("behavior_type == 0")
    assert users.users.sum() == 2
    assert users.events.sum() == 4
    assert all("user_id" not in table for table in tables.values())
    daily_users = tables["daily_users"].query("behavior_type == 0")
    assert daily_users.users.tolist() == [1, 1]


def test_filter_includes_whole_end_day_and_behavior_only() -> None:
    """所选末日23点保留，次日零点及其他行为排除。"""
    frame = pd.DataFrame(
        {
            "event_time": ["2025-11-18 23:00", "2025-11-19 00:00", "2025-11-18 23:00"],
            "behavior_type": [1, 1, 4],
            "events": [2, 7, 5],
        }
    )
    selected = filter_events(frame, date(2025, 11, 18), date(2025, 11, 18), 1)
    assert selected.events.sum() == 2
    with pytest.raises(ValueError):
        filter_events(frame, date(2025, 11, 18), date(2025, 11, 18), 8)


def test_heatmap_normalizes_by_calendar_days_including_zero_events() -> None:
    """八天包含两个周一，仅首个周一有事件也须除以2。"""
    frame = pd.DataFrame({"event_time": ["2025-11-17 08:00"], "events": [10]})
    heat = weekday_heatmap(frame, date(2025, 11, 17), date(2025, 11, 24))
    cell = heat.query("weekday == 0 and hour == 8").iloc[0]
    assert cell.days == 2
    assert cell.mean_events == 5
    single = weekday_heatmap(frame, date(2025, 11, 17), date(2025, 11, 17))
    assert single.loc[single.weekday == 1, "mean_events"].isna().all()


def test_category_curve_includes_all_events_and_handles_empty() -> None:
    """相同次数按ID稳定排序，累计占比终点为1，空集合不造数据。"""
    frame = pd.DataFrame({"category_id": [2, 1, 1], "events": [5, 2, 3]})
    counts = category_counts(frame)
    assert counts.category_id.tolist() == [1, 2]
    assert counts.cumulative_share.tolist() == [0.5, 1.0]
    assert category_counts(frame.iloc[:0]).empty


def test_exported_aggregates_reconcile_all_days_and_behaviors() -> None:
    """逐日逐行为核对两个聚合粒度，并与旧全期报告交叉核对。"""
    hourly = load_aggregate("hourly_behavior")
    categories = load_aggregate("daily_categories")
    activity = load_aggregate("user_activity")
    hourly["day"] = pd.to_datetime(hourly.event_time).dt.strftime("%Y-%m-%d")
    left = hourly.groupby(["day", "behavior_type"]).events.sum().sort_index()
    right = categories.groupby(["day", "behavior_type"]).events.sum().sort_index()
    pd.testing.assert_series_equal(left, right)
    old = read_report("daily.csv").set_index("day").events
    pd.testing.assert_series_equal(hourly.groupby("day").events.sum(), old)
    daily_users = load_aggregate("daily_users")
    previous = read_report("daily.csv").set_index("day")
    for code, column in [(0, "dau"), (4, "buyers")]:
        users = daily_users.loc[daily_users.behavior_type == code].set_index("day")
        pd.testing.assert_series_equal(users.users, previous[column], check_names=False)
    old_behavior = read_report("behavior.csv").set_index("behavior_type")
    for code in range(1, 5):
        selected = activity.loc[activity.behavior_type == code]
        assert selected.users.sum() == old_behavior.loc[code, "users"]
        assert selected.events.sum() == old_behavior.loc[code, "events"]
