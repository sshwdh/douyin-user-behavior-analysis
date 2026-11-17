"""执行预先固定的树模型验证集对照，不访问测试样本。"""

import json
import platform
import time
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import precision_recall_curve

from douyin_analysis.experiment_metrics import evaluate, select_threshold
from douyin_analysis.features import FEATURE_COLUMNS
from douyin_analysis.lr_experiment import load_sample
from douyin_analysis.pipeline import file_digest
from douyin_analysis.tree_preparation import build_estimators


def verify_protocol(root: Path) -> tuple[dict, dict]:
    """确认配置、特征及事件快照与事先准备版本一致。

    Args:
        root: 项目目录。

    Returns:
        固定协议与特征清单。
    """
    protocol = json.loads((root / "reports/trees/preparation.json").read_text())
    manifest_path = root / "reports/features/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    actual = {name: model.get_params() for name, model in build_estimators().items()}
    if protocol["variants"] != actual or protocol["features"] != FEATURE_COLUMNS:
        raise ValueError("树模型配置或特征已偏离预先协议")
    if file_digest(manifest_path) != protocol["feature_manifest_sha256"]:
        raise ValueError("特征清单变化")
    if file_digest(root / "data/processed/events.parquet") != manifest["events_sha256"]:
        raise ValueError("事件数据变化")
    return protocol, manifest


def run(root: Path) -> None:
    """训练两组固定树，在验证集选择方案和阈值并保存本地模型。

    Args:
        root: 项目目录。
    """
    protocol, manifest = verify_protocol(root)
    output = root / "reports/experiments/tree_validation_2026-11-17"
    local = root / "data/models/tree_validation_2026-11-17"
    output.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    execution = {
        "preparation_sha256": file_digest(root / "reports/trees/preparation.json"),
        "code_sha256": {
            name: file_digest(Path(__file__).with_name(name))
            for name in [
                "tree_experiment.py",
                "tree_preparation.py",
                "experiment_metrics.py",
            ]
        },
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "protocol": protocol,
        "test_accessed": False,
    }
    (output / "execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    train = load_sample(root, "train", manifest)
    validation = load_sample(root, "validation", manifest)
    for frame in [train, validation]:
        if not np.isfinite(frame[FEATURE_COLUMNS].to_numpy()).all():
            raise ValueError("特征含非有限值")
    results: dict[str, dict] = {}
    plt.switch_backend("Agg")
    figure, axis = plt.subplots(figsize=(8, 5))
    for name, model in build_estimators().items():
        started = time.perf_counter()
        model.fit(train[FEATURE_COLUMNS], train["label"])
        duration = time.perf_counter() - started
        scores = model.predict_proba(validation[FEATURE_COLUMNS])[:, 1]
        threshold = select_threshold(validation["label"], scores)
        results[name] = {
            "fit_seconds": duration,
            "iterations": int(model.n_iter_),
            "validation": evaluate(validation["label"], scores, threshold),
        }
        joblib.dump(
            {"model": model, "features": FEATURE_COLUMNS, "threshold": threshold},
            local / f"{name}.joblib",
        )
        precision, recall, _ = precision_recall_curve(validation["label"], scores)
        axis.plot(recall, precision, label=name)
        print(json.dumps({name: results[name]}), flush=True)
    selected = max(
        results,
        key=lambda name: results[name]["validation"]["pr_auc_average_precision"],
    )
    axis.axhline(
        validation.label.mean(), color="grey", linestyle="--", label="Prevalence"
    )
    axis.set(
        xlim=(0, 1),
        ylim=(0, 1),
        xlabel="Recall",
        ylabel="Precision",
        title="Validation: fixed tree models",
    )
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "precision_recall.png", dpi=150)
    plt.close(figure)
    summary = {
        "status": "validation_only_semantics_pending",
        "selected_tree": selected,
        "test_accessed": False,
        "models": results,
    }
    (output / "metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(
        {name: value["validation"] for name, value in results.items()}
    ).T.to_csv(output / "validation.csv")


if __name__ == "__main__":
    run(Path.cwd())
