"""验证并读取轻量看板聚合；筛选仅作用于可相加的事件数。"""

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import REPORTS

DATA = REPORTS / "dashboard/aggregates"
TABLE_NAMES = {"hourly_behavior", "daily_categories", "user_activity", "daily_users"}


@st.cache_data(show_spinner=False, max_entries=6)
def _load_verified(path: str, digest: str, modified: int) -> pd.DataFrame:
    """按内容指纹和修改时间缓存公开聚合表，不缓存用户明细。"""
    del modified
    source = Path(path)
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError(f"{source.name} 文件指纹不一致，请重新导出看板数据")
    return pd.read_csv(source)


def load_aggregate(name: str) -> pd.DataFrame:
    """读取白名单中的聚合并检查版本，原数据不需要上传。

    Args:
        name: 已知聚合表名。

    Returns:
        经指纹验证的独立数据副本。
    """
    if name not in TABLE_NAMES:
        raise ValueError("未知看板聚合表")
    manifest = json.loads((DATA / "manifest.json").read_text("utf-8"))
    quality_digest = hashlib.sha256((REPORTS / "quality.json").read_bytes()).hexdigest()
    if quality_digest != manifest["quality_sha256"]:
        raise ValueError("质量报告已更新，请重新导出看板聚合")
    path = DATA / f"{name}.csv.gz"
    frame = _load_verified(
        str(path), manifest["files"][name]["sha256"], path.stat().st_mtime_ns
    )
    if len(frame) != manifest["files"][name]["rows"]:
        raise ValueError("聚合行数不一致")
    return frame


def filter_events(
    frame: pd.DataFrame, start: date, end: date, behavior: int
) -> pd.DataFrame:
    """按自然日首尾及单个行为码筛选，0代表所有行为。

    Args:
        frame: 小时或日聚合，含 events 和 behavior_type。
        start: 包含的起始日。
        end: 包含的结束日。
        behavior: 0、1、2、3或4。

    Returns:
        独立筛选结果，空集合保留为空。
    """
    if start > end or behavior not in range(5):
        raise ValueError("日期范围或行为码无效")
    column = "event_time" if "event_time" in frame else "day"
    days = pd.to_datetime(frame[column]).dt.date
    mask = days.between(start, end)
    if behavior:
        mask &= frame.behavior_type == behavior
    return frame.loc[mask].copy()


def weekday_heatmap(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """补齐小时网格并以所选区间内同星期的天数归一化。

    Args:
        frame: 已按日期和行为筛选的小时计数。
        start: 区间首日。
        end: 区间末日。

    Returns:
        星期、小时、事件数、天数和日均事件数；区间未包含的星期均值为空。
    """
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    times = pd.to_datetime(frame.event_time)
    values = frame.assign(weekday=times.dt.day_of_week, hour=times.dt.hour)
    grouped = values.groupby(["weekday", "hour"]).events.sum()
    index = pd.MultiIndex.from_product([range(7), range(24)], names=["weekday", "hour"])
    result = grouped.reindex(index, fill_value=0).reset_index()
    days = pd.Series(pd.date_range(start, end).day_of_week).value_counts()
    result["days"] = result.weekday.map(days).fillna(0).astype(int)
    result["mean_events"] = result.events / result.days.replace(0, float("nan"))
    return result


def category_counts(frame: pd.DataFrame) -> pd.DataFrame:
    """按类目汇总可加事件数并给出累计占比。

    Args:
        frame: 已筛选的日类目行为聚合。

    Returns:
        按事件数降序排列的类目和累计份额；同次数按类目编号排序。
    """
    result = frame.groupby("category_id")["events"].sum().reset_index()
    result = result.sort_values(["events", "category_id"], ascending=[False, True])
    result["rank"] = range(1, len(result) + 1)
    total = result.events.sum()
    result["cumulative_share"] = result.events.cumsum() / total if total else 0.0
    return result
