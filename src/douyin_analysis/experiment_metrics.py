"""验证集阈值选择及固定阈值的离线评价。"""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def select_threshold(labels: pd.Series, scores: np.ndarray) -> float:
    """仅在验证集最大化 F1；并列时选择较高阈值。

    Args:
        labels: 验证集二元标签。
        scores: 验证集正类分数。

    Returns:
        冻结后用于测试集的阈值。
    """
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    values = (
        2
        * precision[:-1]
        * recall[:-1]
        / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    )
    index = np.flatnonzero(values == values.max())[-1]
    return float(thresholds[index])


def evaluate(labels: pd.Series, scores: np.ndarray, threshold: float) -> dict:
    """计算自然类别比例下的指标，不调整测试阈值。

    Args:
        labels: 真实二值标签。
        scores: 模型正类分数，加权 LR 输出不解释为校准后的购买概率。
        threshold: 验证集固定的分类阈值。

    Returns:
        分类、排序与预测数量指标。
    """
    predictions = scores >= threshold
    true_positives = int(np.sum(predictions & labels.to_numpy().astype(bool)))
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
        "predicted_positive": int(predictions.sum()),
        "true_positive": true_positives,
        "false_positive": int(predictions.sum()) - true_positives,
        "false_negative": int(labels.sum()) - true_positives,
    }
