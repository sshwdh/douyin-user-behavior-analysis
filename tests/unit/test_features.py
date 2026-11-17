"""通过手工计数与未来扰动验证窗口特征和标签边界。"""

import json
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from douyin_analysis.feature_audit import feature_quality, run
from douyin_analysis.features import FEATURE_COLUMNS, build_features, validate_window


def seed_events(connection: duckdb.DuckDBPyConnection) -> None:
    """建立完整小时覆盖及可手工计算的交互样本。

    Args:
        connection: 独立测试数据库连接。
    """
    connection.execute("""CREATE TABLE events AS
        SELECT '99' AS user_id,'99' AS item_id,1 AS behavior_type,hour AS event_time
        FROM generate_series(TIMESTAMP '2025-11-18 00:00:00',
            TIMESTAMP '2025-12-01 23:00:00',INTERVAL '1 hour') AS t(hour)""")
    connection.execute("""INSERT INTO events VALUES
        ('1','a',1,'2025-11-18 00:00:00'),
        ('1','a',1,'2025-11-18 00:00:00'),
        ('1','a',1,'2025-11-18 00:00:00'),
        ('1','a',3,'2025-11-24 23:00:00'),
        ('1','b',4,'2025-11-24 22:00:00'),
        ('2','a',4,'2025-11-24 20:00:00'),
        ('1','a',4,'2025-11-25 00:00:00'),
        ('1','b',4,'2025-12-02 00:00:00'),
        ('3','c',4,'2025-11-26 00:00:00')""")


def test_features_match_manual_counts() -> None:
    """重复计数、独立买家比例和窗口两侧边界符合手算结果。"""
    with duckdb.connect() as connection:
        seed_events(connection)
        frame = build_features(connection, datetime(2025, 11, 25))
    pair = frame.set_index(["user_id", "item_id"]).loc[("1", "a")]
    expected = {
        "pair_events": 4,
        "pair_pv": 3,
        "pair_cart": 1,
        "pair_buy": 0,
        "pair_active_days": 2,
        "pair_distinct_hours": 2,
        "pair_recency_hours": 1,
        "user_events": 5,
        "user_buy": 1,
        "user_distinct_items": 2,
        "user_buy_recency_hours": 2,
        "user_has_buy": 1,
        "item_events": 5,
        "item_users": 2,
        "item_buyers": 1,
        "item_buyer_rate": 0.5,
        "label": 1,
    }
    for feature, value in expected.items():
        assert pair[feature] == value
    assert (
        frame.loc[(frame.user_id == "1") & (frame.item_id == "b"), "label"].item() == 0
    )
    assert "3" not in set(frame.user_id)
    no_buy = frame.loc[frame.user_id == "99"].iloc[0]
    assert no_buy.user_buy_recency_hours == 168
    assert no_buy.user_has_buy == 0
    assert feature_quality(frame, "train").missing_rate.eq(0).all()


def test_future_events_cannot_change_features() -> None:
    """修改截点之后的数据可以改变标签，但不能改变候选与任何特征。"""
    with duckdb.connect() as connection:
        seed_events(connection)
        before = build_features(connection, datetime(2025, 11, 25))
        connection.execute("""INSERT INTO events VALUES
            ('1','b',4,'2025-11-26 00:00:00'),
            ('88','new',4,'2025-11-26 00:00:00')""")
        after = build_features(connection, datetime(2025, 11, 25))
    columns = ["user_id", "item_id", *FEATURE_COLUMNS]
    pd.testing.assert_frame_equal(before[columns], after[columns])
    assert after.label.sum() == before.label.sum() + 1


def test_internal_missing_hour_rejected() -> None:
    """起止时间完整但中间缺失一小时也必须拒绝。"""
    with duckdb.connect() as connection:
        seed_events(connection)
        connection.execute("DELETE FROM events WHERE event_time='2025-11-22 03:00:00'")
        with pytest.raises(ValueError, match="缺失小时"):
            validate_window(connection, datetime(2025, 11, 25))


def test_non_hour_cutoff_rejected() -> None:
    """小时精度数据不接受半小时截点。"""
    with duckdb.connect() as connection:
        with pytest.raises(ValueError, match="整小时"):
            validate_window(connection, datetime(2025, 11, 25, 0, 30))


def test_stale_snapshot_rejected(tmp_path: Path) -> None:
    """输入指纹不匹配时不得发布新的特征产物。"""
    source = tmp_path / "data/processed/events.parquet"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"changed")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"artifacts": {"data/processed/events.parquet": {"sha256": "old"}}})
    )
    with pytest.raises(ValueError, match="指纹"):
        run(tmp_path, snapshot)
    assert not (tmp_path / "reports/features").exists()
