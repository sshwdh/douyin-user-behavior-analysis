"""固定树参数，对照 24 与 30 项特征，仅使用训练及验证窗口。"""

import json
from datetime import datetime
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

from douyin_analysis.error_comparison import BUDGETS, groups, top_k
from douyin_analysis.experiment_metrics import evaluate, select_threshold
from douyin_analysis.extra_features import EXTRA_COLUMNS, augment
from douyin_analysis.features import FEATURE_COLUMNS
from douyin_analysis.lr_experiment import load_sample
from douyin_analysis.pipeline import file_digest
from douyin_analysis.tree_experiment import verify_protocol
from douyin_analysis.tree_preparation import build_estimators

EXPERIMENT = "temporal_features_2026-11-18"


def build_samples(root: Path, manifest: dict) -> dict[str, pd.DataFrame]:
    """分别生成开发样本，原样本和测试样本保持不动。

    Args:
        root: 项目目录。
        manifest: 已验证特征清单。

    Returns:
        训练、验证扩展样本。
    """
    samples = {}
    with duckdb.connect() as connection:
        connection.execute("SET threads=4")
        connection.execute("SET memory_limit='2GB'")
        connection.from_parquet(
            str(root / "data/processed/events.parquet")
        ).create_view("events")
        for split, day in [("train", "2025-11-25"), ("validation", "2025-12-02")]:
            frame = load_sample(root, split, manifest)
            samples[split] = augment(connection, frame, datetime.fromisoformat(day))
    return samples


def summarize(frame: pd.DataFrame, scores: dict[str, np.ndarray]) -> pd.DataFrame:
    """统计固定全局预算下的总体和重点分组命中。

    Args:
        frame: 验证样本。
        scores: 两方案分数。

    Returns:
        等预算命中、精确率和召回率。
    """
    rows = []
    positive = frame.label.to_numpy() == 1
    for name, values in scores.items():
        for budget in BUDGETS:
            selected = top_k(values, budget)
            for group, mask in groups(frame).items():
                hits = int((selected & positive & mask).sum())
                predicted = int((selected & mask).sum())
                total = int((positive & mask).sum())
                rows.append(
                    {
                        "variant": name,
                        "budget": budget,
                        "group": group,
                        "positives": total,
                        "predicted": predicted,
                        "hits": hits,
                        "precision": hits / predicted if predicted else None,
                        "recall": hits / total if total else None,
                    }
                )
    return pd.DataFrame(rows)


def fit_compare(root: Path, samples: dict[str, pd.DataFrame], output: Path) -> None:
    """复现旧模型并训练一次新增特征方案，不搜索模型参数。

    Args:
        root: 项目目录。
        samples: 扩展后的训练与验证样本。
        output: 公开实验目录。
    """
    validation = samples["validation"]
    old_path = root / "data/models/tree_validation_2026-11-17/hgb_31.joblib"
    old = joblib.load(old_path)
    scores = {
        "baseline24": old["model"].predict_proba(validation[FEATURE_COLUMNS])[:, 1]
    }
    results = {
        "baseline24": evaluate(validation.label, scores["baseline24"], old["threshold"])
    }
    archived = json.loads(
        (
            root / "reports/experiments/tree_validation_2026-11-17/metrics.json"
        ).read_text()
    )
    expected = archived["models"]["hgb_31"]["validation"]
    if any(
        not np.isclose(results["baseline24"][key], value, rtol=1e-12, atol=1e-12)
        for key, value in expected.items()
    ):
        raise ValueError("原模型未复现")
    model = build_estimators()["hgb_31"]
    columns = FEATURE_COLUMNS + EXTRA_COLUMNS
    model.fit(samples["train"][columns], samples["train"].label)
    scores["extended30"] = model.predict_proba(validation[columns])[:, 1]
    threshold = select_threshold(validation.label, scores["extended30"])
    results["extended30"] = evaluate(validation.label, scores["extended30"], threshold)
    local = root / "data/models" / EXPERIMENT
    local.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "features": columns, "threshold": threshold},
        local / "extended30.joblib",
    )
    (output / "metrics.json").write_text(
        json.dumps(
            {
                "status": "exploratory_validation_only",
                "models": results,
                "baseline_model_sha256": file_digest(old_path),
                "extended_model_sha256": file_digest(local / "extended30.joblib"),
                "test_accessed": False,
                "business_threshold_decided": False,
            },
            indent=2,
        )
        + "\n"
    )
    summarize(validation, scores).to_csv(output / "budget_comparison.csv", index=False)
    print(json.dumps(results), flush=True)


def run(root: Path) -> None:
    """训练前冻结协议，生成仅历史特征并执行一次对照。

    Args:
        root: 项目目录。
    """
    _, manifest = verify_protocol(root)
    output = root / "reports/experiments" / EXPERIMENT
    output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "features": FEATURE_COLUMNS + EXTRA_COLUMNS,
        "parameters": build_estimators()["hgb_31"].get_params(),
        "budgets": BUDGETS,
        "test_accessed": False,
        "samples": {key: manifest["artifacts"][key] for key in ["train", "validation"]},
        "events_sha256": manifest["events_sha256"],
        "semantics": manifest["semantic_confirmations"],
        "code_sha256": {
            name: file_digest(Path(__file__).with_name(name))
            for name in ["extra_features.py", "feature_ablation.py"]
        },
        "selection": "Report AP and fixed-budget subgroup hits; "
        + "no automatic replacement",
        "threshold": "New variant validation maximum F1, "
        + "ties prefer higher; development only",
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    samples = build_samples(root, manifest)
    quality = []
    for split, frame in samples.items():
        for name in EXTRA_COLUMNS:
            quality.append(
                {
                    "split": split,
                    "feature": name,
                    "minimum": float(frame[name].min()),
                    "maximum": float(frame[name].max()),
                    "missing": int(frame[name].isna().sum()),
                }
            )
    pd.DataFrame(quality).to_csv(output / "feature_quality.csv", index=False)
    fit_compare(root, samples, output)


if __name__ == "__main__":
    run(Path.cwd())
