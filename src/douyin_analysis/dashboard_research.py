"""补齐验证曲线与 LR 类别权重对照，仅输出不含标识的汇总。"""

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import precision_recall_curve, roc_curve

from douyin_analysis.dashboard_data import model_metrics
from douyin_analysis.experiment_metrics import evaluate, select_threshold
from douyin_analysis.lr_experiment import load_sample, transform
from douyin_analysis.pipeline import file_digest

OUTPUT = "reports/dashboard/research"


def curve_tables(labels: pd.Series, scores: np.ndarray) -> dict[str, pd.DataFrame]:
    """生成抽点曲线，指标仍使用全部预测计算。

    Args:
        labels: 自然分布验证标签。
        scores: 与标签等长的有限模型分数。

    Returns:
        PR 与 ROC 的有序抽点表，保留两端。
    """
    if len(labels) != len(scores) or not np.isfinite(scores).all():
        raise ValueError("曲线输入长度不一致或分数无效")
    precision, recall, _ = precision_recall_curve(labels, scores)
    false_rate, true_rate, _ = roc_curve(labels, scores)
    result = {}
    for name, horizontal, vertical in [
        ("pr", recall, precision),
        ("roc", false_rate, true_rate),
    ]:
        indices = np.unique(np.linspace(0, len(horizontal) - 1, 400).astype(int))
        result[name] = pd.DataFrame(
            {
                "order": range(len(indices)),
                "x": horizontal[indices],
                "y": vertical[indices],
            }
        )
    return result


def threshold_table(labels: pd.Series, scores: np.ndarray, best: float) -> pd.DataFrame:
    """以排序累计计数生成固定网格阈值敏感性，不重复扫描全量数据。

    Args:
        labels: 二元验证标签。
        scores: 有限模型分数。
        best: 已保存或当前验证集选出的阈值。

    Returns:
        含阈值及三个指标的汇总，不代表业务阈值决策。
    """
    order = np.argsort(scores, kind="stable")
    sorted_scores = scores[order]
    suffix = np.r_[np.cumsum(labels.to_numpy()[order][::-1])[::-1], 0]
    grid = np.unique(
        np.r_[np.linspace(0, 1, 101), np.quantile(scores, np.linspace(0, 1, 101)), best]
    )
    position = np.searchsorted(sorted_scores, grid, side="left")
    predicted = len(scores) - position
    hits = suffix[position]
    precision = np.divide(hits, predicted, out=np.zeros(len(grid)), where=predicted > 0)
    recall = hits / labels.sum()
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros(len(grid)),
        where=precision + recall > 0,
    )
    return pd.DataFrame(
        {
            "threshold": grid,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "predicted": predicted,
            "hits": hits,
        }
    )


def run(root: Path) -> None:
    """先写实验协议，再拟合未加权 LR 并复核原模型验证结果。

    Args:
        root: 已有样本及本地模型的项目目录。
    """
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "reports/features/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    paths = {
        "lr_24": root / "data/models/lr_2026-11-17/lr_24.joblib",
        "hgb_31": root / "data/models/tree_validation_2026-11-17/hgb_31.joblib",
    }
    protocol = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_manifest_sha256": file_digest(manifest_path),
        "source_models": {key: file_digest(path) for key, path in paths.items()},
        "change": "LR24 class_weight balanced versus None; all other parameters fixed",
        "split": "train and validation only; no resampling",
        "primary_metric": "validation average precision",
        "secondary": "ROC AUC, validation-selected F1, global Top-5060 and Top-12400",
        "threshold_rule": "maximum validation F1; ties prefer higher threshold",
        "selection": "exploratory only; no baseline replacement or tuning",
        "test_accessed": False,
        "code_sha256": file_digest(Path(__file__)),
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    train = load_sample(root, "train", manifest)
    validation = load_sample(root, "validation", manifest)
    baseline = joblib.load(paths["lr_24"])
    unweighted = clone(baseline["model"])
    unweighted.set_params(logisticregression__class_weight=None)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        unweighted.fit(transform(train, baseline["features"]), train.label)
    local = root / "data/models/dashboard_research_2026-11-23"
    local.mkdir(parents=True, exist_ok=True)
    bundles = {key: joblib.load(path) for key, path in paths.items()}
    bundles["lr_24_unweighted"] = {
        "model": unweighted,
        "features": baseline["features"],
    }
    expected = model_metrics()
    metrics, budgets, curves, sensitivity = [], [], [], []
    for name, bundle in bundles.items():
        features = validation[bundle["features"]]
        if name.startswith("lr"):
            features = transform(validation, bundle["features"])
        scores = bundle["model"].predict_proba(features)[:, 1]
        threshold = bundle.get("threshold", select_threshold(validation.label, scores))
        measured = evaluate(validation.label, scores, threshold)
        if name in expected.index:
            for key, value in measured.items():
                if not np.isclose(
                    value, expected.loc[name, key], rtol=1e-10, atol=1e-12
                ):
                    raise ValueError(f"存档模型指标未复现: {name}/{key}")
        metrics.append({"model": name, **measured})
        for kind, table in curve_tables(validation.label, scores).items():
            curves.append(table.assign(model=name, kind=kind))
        sensitivity.append(
            threshold_table(validation.label, scores, threshold).assign(model=name)
        )
        order = np.lexsort((validation.item_id, validation.user_id, -scores))
        for budget in [5060, 12400]:
            hits = int(validation.label.iloc[order[:budget]].sum())
            budgets.append(
                {
                    "model": name,
                    "budget": budget,
                    "hits": hits,
                    "precision": hits / budget,
                    "recall": hits / int(validation.label.sum()),
                }
            )
        if name == "lr_24_unweighted":
            bundle["threshold"] = threshold
            joblib.dump(bundle, local / "lr_24_unweighted.joblib")
        print(f"{name}: AP={measured['pr_auc_average_precision']:.6f}", flush=True)
    tables = {
        "metrics": pd.DataFrame(metrics),
        "budgets": pd.DataFrame(budgets),
        "curves": pd.concat(curves),
        "thresholds": pd.concat(sensitivity),
    }
    files = {}
    for name, table in tables.items():
        path = output / f"{name}.csv"
        table.to_csv(path, index=False)
        files[name] = {"sha256": file_digest(path), "rows": len(table)}
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "files": files,
                "test_accessed": False,
                "new_model": "lr_24_unweighted",
                "curve_note": "400 ordered display points; full-data metrics",
                "validation_sha256": manifest["artifacts"]["validation"]["sha256"],
                "train_sha256": manifest["artifacts"]["train"]["sha256"],
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    run(Path.cwd())
