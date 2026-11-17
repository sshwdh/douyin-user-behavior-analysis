"""仅用截点前七日事件构造用户、商品与交互特征。"""

from datetime import datetime, timedelta

import duckdb
import pandas as pd

BASELINE_FEATURES = [
    "pair_events",
    "pair_pv",
    "pair_fav",
    "pair_cart",
    "pair_buy",
    "pair_recency_hours",
    "user_events",
    "user_buy",
    "item_events",
    "item_buy",
]
FEATURE_COLUMNS = BASELINE_FEATURES + [
    "pair_active_days",
    "pair_distinct_hours",
    "user_pv",
    "user_fav",
    "user_cart",
    "user_distinct_items",
    "user_active_days",
    "user_recency_hours",
    "user_buy_recency_hours",
    "user_has_buy",
    "item_users",
    "item_buyers",
    "item_active_days",
    "item_buyer_rate",
]


def validate_window(connection: duckdb.DuckDBPyConnection, cutoff: datetime) -> None:
    """拒绝非整小时截点及存在空白小时的观察或标签窗口。

    Args:
        connection: 包含小时精度 events 表的连接。
        cutoff: 无时区的预测截点，与原始数据时间表示一致。

    Raises:
        ValueError: 截点格式不匹配或窗口未覆盖全部 336 个小时。
    """
    if cutoff.tzinfo is not None or any(
        [cutoff.minute, cutoff.second, cutoff.microsecond]
    ):
        raise ValueError("截点必须为无时区的整小时")
    hours = connection.execute(
        """SELECT count(DISTINCT event_time) FROM events
        WHERE event_time>=? AND event_time<?""",
        [cutoff - timedelta(days=7), cutoff + timedelta(days=7)],
    ).fetchall()[0][0]
    if hours != 336:
        raise ValueError("观察或标签窗口存在缺失小时，不能直接生成负标签")


def build_features(
    connection: duckdb.DuckDBPyConnection, cutoff: datetime
) -> pd.DataFrame:
    """构造历史候选对的 24 项特征与未来七日观测标签。

    Args:
        connection: 含 events 表的连接，重复事件必须已按确认口径保留。
        cutoff: 观察窗口右端和标签窗口左端，两个窗口均左闭右开。

    Returns:
        用户商品键、历史特征及 label。label=0 仅表示未观测到行为码 4。
        有记录覆盖每小时不等于已证明采样或采集完整。
    """
    validate_window(connection, cutoff)
    return connection.execute(
        """WITH bounds AS (
            SELECT CAST(? AS TIMESTAMP) AS cutoff
        ), history AS (
            SELECT events.* FROM events,bounds
            WHERE event_time>=cutoff-INTERVAL '7 days' AND event_time<cutoff
        ), pairs AS (
            SELECT user_id,item_id,count(*) AS pair_events,
                count(*) FILTER (WHERE behavior_type=1) AS pair_pv,
                count(*) FILTER (WHERE behavior_type=2) AS pair_fav,
                count(*) FILTER (WHERE behavior_type=3) AS pair_cart,
                count(*) FILTER (WHERE behavior_type=4) AS pair_buy,
                count(DISTINCT CAST(event_time AS DATE)) AS pair_active_days,
                count(DISTINCT event_time) AS pair_distinct_hours,
                date_diff('hour',max(event_time),max(cutoff)) AS pair_recency_hours
            FROM history,bounds GROUP BY user_id,item_id
        ), users AS (
            SELECT user_id,count(*) AS user_events,
                count(*) FILTER (WHERE behavior_type=1) AS user_pv,
                count(*) FILTER (WHERE behavior_type=2) AS user_fav,
                count(*) FILTER (WHERE behavior_type=3) AS user_cart,
                count(*) FILTER (WHERE behavior_type=4) AS user_buy,
                count(DISTINCT item_id) AS user_distinct_items,
                count(DISTINCT CAST(event_time AS DATE)) AS user_active_days,
                date_diff('hour',max(event_time),max(cutoff)) AS user_recency_hours,
                coalesce(date_diff('hour',
                    max(event_time) FILTER (WHERE behavior_type=4),max(cutoff)),168)
                    AS user_buy_recency_hours,
                CAST(count(*) FILTER (WHERE behavior_type=4)>0 AS INTEGER)
                    AS user_has_buy
            FROM history,bounds GROUP BY user_id
        ), items AS (
            SELECT item_id,count(*) AS item_events,
                count(DISTINCT user_id) AS item_users,
                count(*) FILTER (WHERE behavior_type=4) AS item_buy,
                count(DISTINCT user_id) FILTER (WHERE behavior_type=4)
                    AS item_buyers,
                count(DISTINCT CAST(event_time AS DATE)) AS item_active_days
            FROM history GROUP BY item_id
        ), labels AS (
            SELECT DISTINCT user_id,item_id,1 AS label FROM events,bounds
            WHERE event_time>=cutoff AND event_time<cutoff+INTERVAL '7 days'
                AND behavior_type=4
        ) SELECT pairs.*,users.* EXCLUDE(user_id),items.* EXCLUDE(item_id),
            1.0*item_buyers/item_users AS item_buyer_rate,
            coalesce(label,0) AS label FROM pairs
            JOIN users USING(user_id) JOIN items USING(item_id)
            LEFT JOIN labels USING(user_id,item_id)
            ORDER BY user_id,item_id""",
        [cutoff],
    ).df()
