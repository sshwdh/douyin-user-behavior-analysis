"""用可手算样本验证候选覆盖和树模型配置。"""

from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from douyin_analysis.candidate_audit import build_candidates, evaluate_coverage
from douyin_analysis.tree_preparation import build_estimators


def test_candidate_coverage_and_future_isolation() -> None:
    """验证五类互斥分组及未来事件不改变候选集合。"""
    cutoff = datetime(2025, 11, 25)
    rows = [
        ("99", "99", "9", 1, cutoff + timedelta(hours=hour))
        for hour in range(-168, 168)
    ]
    rows.extend(
        [
            ("1", "a", "1", 1, cutoff - timedelta(hours=1)),
            ("2", "b", "1", 1, cutoff - timedelta(hours=1)),
        ]
    )
    columns = ["user_id", "item_id", "category_id", "behavior_type", "event_time"]
    with duckdb.connect() as connection:
        connection.register("input_frame", pd.DataFrame(rows, columns=columns))
        connection.execute("CREATE TABLE events AS SELECT * FROM input_frame")
        build_candidates(connection, cutoff)
        before = connection.execute("SELECT * FROM candidates ORDER BY ALL").fetchall()
        for user, item in [
            ("1", "a"),
            ("1", "a"),
            ("1", "b"),
            ("1", "c"),
            ("3", "a"),
            ("3", "c"),
        ]:
            connection.execute(
                "INSERT INTO events VALUES (?,?, '1',4,?)", [user, item, cutoff]
            )
        build_candidates(connection, cutoff)
        assert (
            before
            == connection.execute("SELECT * FROM candidates ORDER BY ALL").fetchall()
        )
        coverage, strata = evaluate_coverage(connection, cutoff)
    assert strata.pairs.tolist() == [1] * 5
    values = coverage.set_index("rule")
    assert values.loc["history_7d", "covered"] == 1
    assert values.loc["global_20", "candidates"] == 9
    assert values.loc["category_3x10", "candidates"] == 5
    assert values.loc["category_3x10", "covered"] == 2
    assert (values.future_pairs == 5).all()


def test_tree_synthetic_smoke() -> None:
    """验证固定配置可拟合合成样本且输出有效分数。"""
    generator = np.random.default_rng(42)
    values = generator.normal(size=(240, 24))
    labels = (values[:, 0] > 0.5).astype(int)
    for model in build_estimators().values():
        assert model.early_stopping is False
        model.fit(values, labels)
        scores = model.predict_proba(values)[:, 1]
        assert np.isfinite(scores).all()
        assert ((scores >= 0) & (scores <= 1)).all()
