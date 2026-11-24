"""核验新增研究的标签边界、截尾规则和真实曲线计数。"""

import duckdb
import numpy as np
import pandas as pd
import pytest

from douyin_analysis.dashboard_categories import category_structure
from douyin_analysis.dashboard_cohorts import cohort_table
from douyin_analysis.dashboard_model_charts import research_table
from douyin_analysis.dashboard_research import curve_tables, threshold_table
from douyin_analysis.experiment_metrics import evaluate


def test_cohort_exact_day_and_immature_null() -> None:
    """重复交互只计一个回访用户，未成熟队列留空，非累计回访。"""
    with duckdb.connect() as connection:
        connection.execute("""CREATE TABLE events AS SELECT * FROM (VALUES
            (1,TIMESTAMP '2025-01-01 00:00:00'),
            (1,TIMESTAMP '2025-01-01 00:00:00'),
            (1,TIMESTAMP '2025-01-03 00:00:00'),
            (2,TIMESTAMP '2025-01-02 00:00:00')) t(user_id,event_time)""")
        table = cohort_table(connection)
    first = table.loc[table.cohort == pd.Timestamp("2025-01-01")].set_index("elapsed")
    assert first.loc[0, "cohort_users"] == 1
    assert first.loc[1, "return_rate"] == 0
    assert first.loc[2, "return_rate"] == 1
    assert pd.isna(first.loc[3, "return_rate"])
    assert not first.loc[3, "mature"]


def test_threshold_ties_and_metrics_match_reference() -> None:
    """阈值使用大于等于，分数并列和零预测边界均与独立计算一致。"""
    labels = pd.Series([0, 1, 1, 0, 0])
    scores = np.array([0.1, 0.4, 0.4, 0.8, 0.1])
    table = threshold_table(labels, scores, 0.4)
    for threshold in [0.0, 0.4, 1.0]:
        row = table.loc[np.isclose(table.threshold, threshold)].iloc[0]
        expected = evaluate(labels, scores, threshold)
        assert row.precision == pytest.approx(expected["precision"])
        assert row.recall == pytest.approx(expected["recall"])
        assert row.hits == expected["true_positive"]
    curves = curve_tables(labels, scores)
    assert curves["roc"].iloc[0].x == 0
    assert curves["roc"].iloc[-1].x == 1


def test_research_budgets_reconcile_and_paths_reject() -> None:
    """固定预算的原基线复现旧结果，公开研究表不含用户和商品标识。"""
    table = research_table("budgets").set_index(["model", "budget"])
    assert table.loc[("lr_24", 5060), "hits"] == 241
    assert table.loc[("hgb_31", 12400), "hits"] == 654
    for name in ["curves", "metrics", "thresholds", "budgets"]:
        frame = research_table(name)
        assert not {"user_id", "item_id"}.intersection(frame.columns)
    with pytest.raises(ValueError, match="未知"):
        research_table("../../raw")


def test_category_share_is_event_based() -> None:
    """行为码 4 占全部事件的份额，不能错误地除以行为码 1。"""
    frame = pd.DataFrame(
        {"category_id": [1, 1, 2], "behavior_type": [1, 4, 2], "events": [8, 2, 5]}
    )
    table = category_structure(frame).set_index("category_id")
    assert table.loc[1, "share"] == 0.2
    assert table.loc[2, "share"] == 0
