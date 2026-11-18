"""为既有历史候选添加六项历史窗口特征，保持标签与候选不变。"""

from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

EXTRA_COLUMNS = [
    "pair_events_last24h",
    "pair_events_24to72h",
    "pair_behavior_types",
    "pair_span_hours",
    "pair_user_event_share",
    "pair_item_event_share",
]


def augment(
    connection: duckdb.DuckDBPyConnection, frame: pd.DataFrame, cutoff: datetime
) -> pd.DataFrame:
    """聚合截点前历史信息，并按候选键一对一合并。

    Args:
        connection: 含 events 视图的连接。
        frame: 原始已审计候选与特征。
        cutoff: 历史窗口右端，不包含该时刻。

    Returns:
        原候选顺序、标签和特征均不变的扩展样本。
    """
    extra = connection.execute(
        """WITH bounds AS (SELECT CAST(? AS TIMESTAMP) AS cutoff)
        SELECT user_id,item_id,
            count(*) FILTER (WHERE event_time>=cutoff-INTERVAL '24 hours')
                AS pair_events_last24h,
            count(*) FILTER (WHERE event_time>=cutoff-INTERVAL '72 hours'
                AND event_time<cutoff-INTERVAL '24 hours') AS pair_events_24to72h,
            count(DISTINCT behavior_type) AS pair_behavior_types,
            date_diff('hour',min(event_time),max(event_time)) AS pair_span_hours
        FROM events,bounds
        WHERE event_time>=cutoff-INTERVAL '7 days' AND event_time<cutoff
        GROUP BY user_id,item_id""",
        [cutoff],
    ).df()
    result = frame.merge(
        extra, on=["user_id", "item_id"], how="left", validate="one_to_one", sort=False
    )
    if len(extra) != len(frame) or not result[frame.columns].equals(
        frame.reset_index(drop=True)
    ):
        raise ValueError("候选键、顺序或既有特征发生改变")
    result["pair_user_event_share"] = result.pair_events / result.user_events
    result["pair_item_event_share"] = result.pair_events / result.item_events
    if not np.isfinite(result[EXTRA_COLUMNS].to_numpy()).all():
        raise ValueError("新增特征缺失或非有限")
    return result
