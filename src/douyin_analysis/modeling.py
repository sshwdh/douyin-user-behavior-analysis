"""历史候选用户商品对的七日购买预测基线，按时间外推评估。"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
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


def build_samples(
    connection: duckdb.DuckDBPyConnection,
    cutoff: datetime,
) -> pd.DataFrame:
    """以过去七日发生交互的用户商品对构建样本。

    Args:
        connection: 含 events 表的数据库连接。
        cutoff: 观察窗终点和标签窗起点。

    Returns:
        历史候选对的数值特征与完整未来七日标签。

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


def evaluate(labels: pd.Series, scores: np.ndarray, threshold: float) -> dict:
    """计算自然类别比例下的指标，不调整测试阈值。

    Args:
        labels: 真实二值标签。
        scores: 模型正类概率。
        threshold: 验证集固定的分类阈值。

    Returns:
        分类与排序指标。
    """
    predictions = scores >= threshold
    return {
        "rows": len(labels),
        "positives": int(labels.sum()),
        "positive_rate": float(labels.mean()),
        "roc_auc": float(roc_auc_score(labels, scores)),
        "pr_auc_average_precision": float(average_precision_score(labels, scores)),
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "threshold": threshold,
    }


def run(root: Path) -> None:
    """训练 LR 并在后续日期评价，输出指标及标准化系数。

    Args:
        root: 项目目录，需先运行清洗流水线。
    """
    with duckdb.connect(str(root / "data/work.duckdb"), read_only=True) as connection:
        cutoffs = [
            datetime.fromisoformat(day)
            for day in ["2025-11-25", "2025-12-02", "2025-12-09"]
        ]
        samples = [build_samples(connection, cutoff) for cutoff in cutoffs]
        coverage = []
        for cutoff, frame in zip(cutoffs, samples):
            future_pairs = connection.execute(
                """SELECT count(*) FROM (
                SELECT DISTINCT user_id,item_id FROM events
                WHERE event_time>=? AND event_time<? AND behavior_type=4)""",
                [cutoff, cutoff + timedelta(days=7)],
            ).fetchall()[0][0]
            coverage.append(
                {
                    "cutoff": cutoff.isoformat(),
                    "future_purchased_pairs": future_pairs,
                    "covered_purchased_pairs": int(frame["label"].sum()),
                    "coverage": float(frame["label"].sum() / future_pairs),
                }
            )
    train, validation, test = samples
    for frame in samples:
        if frame["label"].nunique() != 2:
            raise ValueError("训练或评价集只有一种标签，不能进行二分类评价")
    classifier = LogisticRegression(
        class_weight="balanced", max_iter=500, random_state=42
    )
    model = make_pipeline(StandardScaler(), classifier)
    model.fit(np.log1p(train[FEATURES]), train["label"])
    validation_scores = model.predict_proba(np.log1p(validation[FEATURES]))[:, 1]
    precision, recall, thresholds = precision_recall_curve(
        validation["label"], validation_scores
    )
    f1_values = (
        2
        * precision[:-1]
        * recall[:-1]
        / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    )
    threshold = float(thresholds[int(np.argmax(f1_values))])
    scores = model.predict_proba(np.log1p(test[FEATURES]))[:, 1]
    results = {
        "task": "historically interacted user-item pairs; next 7 days purchase",
        "cutoffs": ["2025-11-25", "2025-12-02", "2025-12-09"],
        "train_rows": len(train),
        "train_positive_rate": float(train["label"].mean()),
        "candidate_coverage": coverage,
        "validation": evaluate(validation["label"], validation_scores, threshold),
        "test": evaluate(test["label"], scores, threshold),
    }
    (root / "reports/lr_metrics.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    pd.DataFrame({"feature": FEATURES, "coefficient": classifier.coef_[0]}).to_csv(
        root / "reports/lr_coefficients.csv", index=False
    )


def main() -> None:
    """解析项目目录并执行基线。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    run(parser.parse_args().root)


if __name__ == "__main__":
    main()
