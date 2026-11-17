"""兼容旧样本检查接口；命令行转入固定样本的 LR 对照实验。"""

from datetime import datetime, timedelta

import duckdb
import pandas as pd

from douyin_analysis.experiment_metrics import evaluate
from douyin_analysis.lr_experiment import main, run

__all__ = ["build_samples", "evaluate", "run"]


def build_samples(
    connection: duckdb.DuckDBPyConnection,
    cutoff: datetime,
) -> pd.DataFrame:
    """以过去七日发生交互的用户商品对构建样本。

    Args:
        connection: 含 events 表的数据库连接。
        cutoff: 观察窗终点和标签窗起点。

    Returns:
        历史候选对的数值特征与未来七日标签。
        窗口边界检查不证明采集完整性；调用前须确认数据覆盖无遗漏。

    Raises:
        ValueError: 数据无法覆盖观察或标签窗口。
    """
    start, end = connection.execute(
        "SELECT min(event_time), max(event_time) FROM events"
    ).fetchall()[0]
    if start > cutoff - timedelta(days=7) or end < cutoff + timedelta(days=7, hours=-1):
        raise ValueError("数据未覆盖完整观察窗及标签窗，不能填充负标签")
    return connection.execute(
        """
        WITH history AS (
            SELECT * FROM events WHERE event_time>=? AND event_time<?
        ), pairs AS (
            SELECT user_id,item_id,count(*) AS pair_events,
            count(*) FILTER (WHERE behavior_type=1) AS pair_pv,
            count(*) FILTER (WHERE behavior_type=2) AS pair_fav,
            count(*) FILTER (WHERE behavior_type=3) AS pair_cart,
            count(*) FILTER (WHERE behavior_type=4) AS pair_buy,
            date_diff('hour',max(event_time),?) AS pair_recency_hours
            FROM history GROUP BY 1,2
        ), users AS (
            SELECT user_id,count(*) AS user_events,
            count(*) FILTER (WHERE behavior_type=4) AS user_buy
            FROM history GROUP BY 1
        ), items AS (
            SELECT item_id,count(*) AS item_events,
            count(*) FILTER (WHERE behavior_type=4) AS item_buy
            FROM history GROUP BY 1
        ), labels AS (
            SELECT DISTINCT user_id,item_id,1 AS label
            FROM events WHERE event_time>=? AND event_time<? AND behavior_type=4
        )
        SELECT pairs.*,user_events,user_buy,item_events,item_buy,
        coalesce(labels.label,0) AS label FROM pairs
        JOIN users USING(user_id) JOIN items USING(item_id)
        LEFT JOIN labels USING(user_id,item_id)
        """,
        [
            cutoff - timedelta(days=7),
            cutoff,
            cutoff,
            cutoff,
            cutoff + timedelta(days=7),
        ],
    ).df()


if __name__ == "__main__":
    main()
