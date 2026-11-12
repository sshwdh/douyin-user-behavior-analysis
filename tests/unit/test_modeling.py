"""模型样本边界与评价指标测试。"""

from datetime import datetime

import duckdb
import numpy as np
import pandas as pd
import pytest

from douyin_analysis.modeling import build_samples, evaluate


def test_cutoff_boundary() -> None:
    """截点购买只能进入标签，未来新交互对不能反向进入候选。"""
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE events AS SELECT * FROM (VALUES
            ('1','1',1,TIMESTAMP '2025-11-18 00:00:00'),
            ('1','1',4,TIMESTAMP '2025-11-25 00:00:00'),
            ('2','2',4,TIMESTAMP '2025-11-26 00:00:00'),
            ('2','2',1,TIMESTAMP '2025-12-01 23:00:00')
            ) AS rows(user_id,item_id,behavior_type,event_time)""")
        result = build_samples(connection, datetime(2025, 11, 25))
        assert len(result) == 1
        assert result.iloc[0]["pair_buy"] == 0
        assert result.iloc[0]["label"] == 1


def test_incomplete_labels() -> None:
    """右截尾窗口必须拒绝生成负标签。"""
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE events AS SELECT
            TIMESTAMP '2025-11-25' AS event_time""")
        with pytest.raises(ValueError, match="完整观察窗"):
            build_samples(connection, datetime(2025, 11, 25))


def test_perfect_ranking() -> None:
    """完美排序和固定阈值应得到可解释的指标。"""
    labels = pd.Series([0, 0, 1, 1])
    result = evaluate(labels, np.array([0.1, 0.2, 0.8, 0.9]), 0.5)
    assert result["roc_auc"] == 1.0
    assert result["f1"] == 1.0
