"""验证新增历史特征的时间边界、重复保留与未来隔离。"""

from datetime import datetime, timedelta

import duckdb
import pandas as pd

from douyin_analysis.extra_features import EXTRA_COLUMNS, augment


def test_history_boundaries_and_future_isolation() -> None:
    """手算三个时间边界，确保未来记录不改变新增特征。"""
    cutoff = datetime(2025, 12, 2)
    rows = [
        ("u", "i", behavior, cutoff - timedelta(hours=hours))
        for hours, behavior in [(168, 1), (72, 2), (24, 3), (24, 3), (1, 1), (169, 4)]
    ]
    events = pd.DataFrame(
        rows, columns=["user_id", "item_id", "behavior_type", "event_time"]
    )
    frame = pd.DataFrame(
        {
            "user_id": ["u"],
            "item_id": ["i"],
            "pair_events": [5],
            "user_events": [10],
            "item_events": [20],
            "label": [0],
        }
    )
    with duckdb.connect() as connection:
        connection.register("input_events", events)
        connection.execute("CREATE TABLE events AS SELECT * FROM input_events")
        before = augment(connection, frame, cutoff)
        connection.execute("INSERT INTO events VALUES ('u','i',4,?)", [cutoff])
        after = augment(connection, frame, cutoff)
    pd.testing.assert_frame_equal(before, after)
    assert before[EXTRA_COLUMNS].iloc[0].tolist() == [3, 1, 3, 167, 0.5, 0.25]
    pd.testing.assert_frame_equal(before[frame.columns], frame)
