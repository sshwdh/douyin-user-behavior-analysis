"""基于固定窗口样本比较 10 项与 24 项特征的 LR，不调测试阈值。"""

import argparse
import json
import platform
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from douyin_analysis.experiment_metrics import evaluate, select_threshold
from douyin_analysis.features import BASELINE_FEATURES, FEATURE_COLUMNS
from douyin_analysis.pipeline import file_digest

EXPERIMENT = "lr_2026-11-17"
VARIANTS = {"lr_10": BASELINE_FEATURES, "lr_24": FEATURE_COLUMNS}


def transform(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """对计数与间隔做 log1p，比例及二元标记保留原值。

    Args:
        frame: 原始窗口样本。
        columns: 当前方案预先指定的特征顺序。

    Returns:
        未拟合任何全样本统计量的变换特征。
    """
    values = frame[columns].astype(float).copy()
    for column in columns:
        if column not in {"user_has_buy", "item_buyer_rate"}:
            values[column] = np.log1p(values[column])
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError("模型输入包含非有限值")
    return values


def load_sample(root: Path, split: str, manifest: dict) -> pd.DataFrame:
    """在读取每个样本前核对指纹、行数和标签。

    Args:
        root: 项目根目录。
        split: train、validation 或 test。
        manifest: 特征生成清单。

    Returns:
        指纹一致且含两类标签的样本。
    """
    path = root / "data/features" / f"{split}.parquet"
    expected = manifest["artifacts"][split]
    if file_digest(path) != expected["sha256"]:
        raise ValueError("样本指纹变化，拒绝混用数据版本")
    frame = pd.read_parquet(path)
    if len(frame) != expected["rows"] or set(frame["label"].unique()) != {0, 1}:
        raise ValueError("样本行数或二元标签不符合清单")
    return frame


def plot_curves(curves: dict, output: Path) -> None:
    """绘制两组 PR 曲线，保留验证与测试的独立视图。

    Args:
        curves: 每个 split 含方案曲线及自然正例率。
        output: 公开实验目录。
    """
    plt.switch_backend("Agg")
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for axis, split in zip(axes, ["validation", "test"]):
        for name, values in curves[split]["models"].items():
            axis.plot(values["recall"], values["precision"], label=name)
        axis.axhline(
            curves[split]["prevalence"],
            color="grey",
            linestyle="--",
            label="Random ranking reference",
        )
        axis.set(
            title=f"{split}: candidate-only PR", xlabel="Recall", ylabel="Precision"
        )
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.grid(alpha=0.2)
        axis.legend()
    figure.tight_layout()
    figure.savefig(output / "precision_recall.png", dpi=150)
    plt.close(figure)


def save_results(
    output: Path, summary: dict, coefficients: list[dict], curves: dict
) -> None:
    """保存指标、标准化系数和结果图。

    Args:
        output: 公开实验目录。
        summary: 评价指标与冻结的方案选择。
        coefficients: 两组模型的系数记录。
        curves: 验证与测试 PR 曲线。
    """
    (output / "metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(coefficients).to_csv(output / "coefficients.csv", index=False)
    plot_curves(curves, output)


def run(root: Path) -> None:
    """冻结实验协议，训练两种 LR，验证决策后加载测试集评价。

    Args:
        root: 含已审计特征样本的项目目录。
    """
    output = root / "reports/experiments" / EXPERIMENT
    local = root / "data/models" / EXPERIMENT
    output.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "reports/features/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if file_digest(root / "data/processed/events.parquet") != manifest["events_sha256"]:
        raise ValueError("清洗数据已改变，请重新生成窗口样本")
    protocol = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_manifest_sha256": file_digest(manifest_path),
        "data_snapshot_id": manifest["data_snapshot_id"],
        "sample_fingerprints": manifest["artifacts"],
        "semantic_confirmations": manifest["semantic_confirmations"],
        "variants": VARIANTS,
        "class_weight": "balanced",
        "C": 1.0,
        "solver": "lbfgs",
        "max_iter": 500,
        "random_state": 42,
        "selection": "highest validation AP; ties prefer lr_10",
        "threshold": "maximum validation F1; ties prefer higher threshold",
        "test_use": "evaluate both prespecified variants after validation decision",
        "transform": "log1p counts and recencies; binary and rate unchanged; "
        + "train-only scaler",
        "resampling": "none",
        "runtime": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
        },
        "code_sha256": {
            name: file_digest(Path(__file__).with_name(name))
            for name in ["lr_experiment.py", "experiment_metrics.py"]
        },
    }
    (output / "protocol.json").write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    train = load_sample(root, "train", manifest)
    validation = load_sample(root, "validation", manifest)
    models: dict[str, Pipeline] = {}
    results: dict[str, dict] = {}
    coefficients: list[dict] = []
    curves: dict = {
        "validation": {"models": {}, "prevalence": float(validation.label.mean())}
    }
    for name, columns in VARIANTS.items():
        classifier = LogisticRegression(
            class_weight="balanced",
            C=1.0,
            solver="lbfgs",
            max_iter=500,
            random_state=42,
        )
        model = make_pipeline(StandardScaler(), classifier)
        started = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(transform(train, columns), train["label"])
        duration = time.perf_counter() - started
        scores = model.predict_proba(transform(validation, columns))[:, 1]
        threshold = select_threshold(validation["label"], scores)
        results[name] = {
            "features": len(columns),
            "fit_seconds": duration,
            "iterations": int(classifier.n_iter_[0]),
            "validation": evaluate(validation["label"], scores, threshold),
        }
        precision, recall, _ = precision_recall_curve(validation["label"], scores)
        curves["validation"]["models"][name] = {
            "precision": precision,
            "recall": recall,
        }
        coefficients.extend(
            {"variant": name, "feature": column, "coefficient": float(weight)}
            for column, weight in zip(columns, classifier.coef_[0])
        )
        joblib.dump(
            {"model": model, "features": columns, "threshold": threshold},
            local / f"{name}.joblib",
        )
        models[name] = model
        validation_ap = results[name]["validation"]["pr_auc_average_precision"]
        print(f"{name}: validation AP={validation_ap:.6f}", flush=True)
    selected = max(
        results,
        key=lambda name: results[name]["validation"]["pr_auc_average_precision"],
    )
    decision = {
        "decided_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_variant": selected,
        "validation_results": results,
        "test_loaded": False,
    }
    (output / "validation_decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    del train, validation
    test = load_sample(root, "test", manifest)
    curves["test"] = {"models": {}, "prevalence": float(test.label.mean())}
    coverage = pd.read_csv(root / "reports/features/sample_summary.csv")
    future_pairs = int(
        coverage.loc[coverage["split"] == "test", "future_code4_pairs"].iloc[0]
    )
    for name, model in models.items():
        scores = model.predict_proba(transform(test, VARIANTS[name]))[:, 1]
        threshold = results[name]["validation"]["threshold"]
        results[name]["test"] = evaluate(test["label"], scores, threshold)
        results[name]["test"]["recall_all_future_pairs"] = (
            results[name]["test"]["true_positive"] / future_pairs
        )
        precision, recall, _ = precision_recall_curve(test["label"], scores)
        curves["test"]["models"][name] = {"precision": precision, "recall": recall}
    summary = {
        "status": "offline_experiment_semantics_pending",
        "selected_by_validation": selected,
        "test_evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "test_candidate_coverage": float(test.label.sum() / future_pairs),
        "test_future_code4_pairs": future_pairs,
        "models": results,
    }
    save_results(output, summary, coefficients, curves)


def main() -> None:
    """从固定的本地样本运行 LR 对照。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    run(parser.parse_args().root)


if __name__ == "__main__":
    main()
