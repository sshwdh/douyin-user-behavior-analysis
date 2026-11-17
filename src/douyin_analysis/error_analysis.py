"""固定树模型验证集误报漏报分组诊断，不调参、不访问测试集。"""

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from douyin_analysis.experiment_metrics import evaluate
from douyin_analysis.features import FEATURE_COLUMNS
from douyin_analysis.lr_experiment import load_sample
from douyin_analysis.pipeline import file_digest
from douyin_analysis.tree_experiment import verify_protocol

BINS = {
    "user_events": [-1, 100, 500, 2000, float("inf")],
    "user_buy": [-1, 0, 5, float("inf")],
    "user_distinct_items": [-1, 50, 200, float("inf")],
    "item_users": [-1, 1, 5, 20, float("inf")],
    "item_buyers": [-1, 0, 1, float("inf")],
    "pair_events": [-1, 1, 5, float("inf")],
    "pair_buy": [-1, 0, float("inf")],
    "pair_recency_hours": [-1, 24, 72, float("inf")],
}


def segment_errors(
    frame: pd.DataFrame, scores: np.ndarray, threshold: float
) -> pd.DataFrame:
    """按固定历史特征区间统计混淆计数与明确分母的错误率。

    Args:
        frame: 含二元 label 与分组特征的验证样本。
        scores: 固定模型的正类分数。
        threshold: 已存档的验证阈值。

    Returns:
        每个维度每个区间的统计，零分母比率留空。
    """
    if len(frame) != len(scores) or not np.isfinite(scores).all():
        raise ValueError("预测长度不符或分数非有限")
    if not frame.label.isin([0, 1]).all():
        raise ValueError("标签必须为二元值")
    actual = frame.label.to_numpy().astype(bool)
    predicted = scores >= threshold
    counts = pd.DataFrame(
        {
            "rows": np.ones(len(frame), dtype=int),
            "tp": actual & predicted,
            "fp": ~actual & predicted,
            "fn": actual & ~predicted,
            "tn": ~actual & ~predicted,
        }
    )
    tables = []
    for feature, edges in BINS.items():
        groups = pd.cut(frame[feature].reset_index(drop=True), edges, right=True)
        if groups.isna().any():
            raise ValueError("分组特征缺失或超出允许范围")
        table = counts.groupby(groups, observed=False).sum().reset_index()
        table = table.rename(columns={feature: "segment"})
        table["feature"] = feature
        table["positives"] = table.tp + table.fn
        table["negatives"] = table.fp + table.tn
        table["predicted_positive"] = table.tp + table.fp
        denominators = {
            "false_positive_rate": (table.fp, table.negatives),
            "false_negative_rate": (table.fn, table.positives),
            "precision": (table.tp, table.predicted_positive),
            "positive_rate": (table.positives, table.rows),
            "fp_share": (table.fp, pd.Series(int(counts.fp.sum()), index=table.index)),
            "fn_share": (table.fn, pd.Series(int(counts.fn.sum()), index=table.index)),
        }
        for name, (numerator, denominator) in denominators.items():
            table[name] = numerator / denominator.replace(0, np.nan)
        table["low_positive_support"] = table.positives < 30
        if int(table.rows.sum()) != len(frame):
            raise ValueError("分组计数不守恒")
        tables.append(table)
    return pd.concat(tables, ignore_index=True)


def plot_errors(table: pd.DataFrame, output: Path) -> None:
    """绘制各特征分组错误率，数量另见汇总表。

    Args:
        table: 分组统计。
        output: 公开输出目录。
    """
    plt.switch_backend("Agg")
    figure, axes = plt.subplots(4, 2, figsize=(13, 16))
    for axis, (feature, groups) in zip(axes.flat, table.groupby("feature", sort=False)):
        groups.set_index("segment")[
            ["false_positive_rate", "false_negative_rate"]
        ].plot.bar(ax=axis)
        axis.set(
            title=feature,
            ylabel="Rate",
            ylim=(0, 1.2),
            xlabel="Historical feature interval",
        )
        axis.tick_params(axis="x", rotation=20)
        axis.legend(["FP / actual negatives", "FN / actual positives"], fontsize=8)
    figure.tight_layout()
    figure.savefig(output / "segment_error_rates.png", dpi=150)
    plt.close(figure)


def run(root: Path) -> None:
    """重算验证预测并对账已存档指标，输出无个人标识的分组汇总。

    Args:
        root: 项目目录。
    """
    _, manifest = verify_protocol(root)
    experiment = root / "reports/experiments/tree_validation_2026-11-17"
    metrics_path = experiment / "metrics.json"
    summary = json.loads(metrics_path.read_text())
    name = summary["selected_tree"]
    model_path = root / "data/models/tree_validation_2026-11-17" / f"{name}.joblib"
    bundle = joblib.load(model_path)
    expected = summary["models"][name]["validation"]
    if (
        bundle["features"] != FEATURE_COLUMNS
        or bundle["threshold"] != expected["threshold"]
    ):
        raise ValueError("本地模型特征或阈值与存档不符")
    frame = load_sample(root, "validation", manifest)
    scores = bundle["model"].predict_proba(frame[FEATURE_COLUMNS])[:, 1]
    measured = evaluate(frame.label, scores, bundle["threshold"])
    for key, value in expected.items():
        if not np.isclose(measured[key], value, rtol=1e-12, atol=1e-12):
            raise ValueError(f"验证预测未复现存档指标: {key}")
    table = segment_errors(frame, scores, bundle["threshold"])
    output = root / "reports/errors/tree_validation_2026-11-17"
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(output / "segments.csv", index=False)
    metadata = {
        "status": "descriptive_validation_error_audit",
        "selected_model": name,
        "threshold": bundle["threshold"],
        "model_sha256": file_digest(model_path),
        "metrics_sha256": file_digest(metrics_path),
        "sample_sha256": manifest["artifacts"]["validation"]["sha256"],
        "code_sha256": file_digest(Path(__file__)),
        "metrics_reproduced": measured,
        "test_accessed": False,
        "model_retrained": False,
        "threshold_changed": False,
        "bins": {key: [str(edge) for edge in edges] for key, edges in BINS.items()},
        "bin_rule": "fixed descriptive intervals, right closed; "
        + "no outcome-based search",
        "semantics": manifest["semantic_confirmations"],
    }
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    plot_errors(table, output)


if __name__ == "__main__":
    run(Path.cwd())
