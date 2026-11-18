"""比较固定 LR 与树模型的验证分数、命中和等预算排序表现。"""

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from douyin_analysis.experiment_metrics import evaluate
from douyin_analysis.features import FEATURE_COLUMNS
from douyin_analysis.lr_experiment import load_sample, transform
from douyin_analysis.pipeline import file_digest
from douyin_analysis.tree_experiment import verify_protocol

BUDGETS = [5060, 12400]


def top_k(scores: np.ndarray, budget: int) -> np.ndarray:
    """按分数降序选定数量，同分沿用固定样本顺序。

    Args:
        scores: 有限模型分数。
        budget: 全局候选预算。

    Returns:
        与输入顺序一致的选中标记。
    """
    if not np.isfinite(scores).all() or not 0 < budget <= len(scores):
        raise ValueError("非法分数或候选预算")
    selected = np.zeros(len(scores), dtype=bool)
    selected[np.argsort(-scores, kind="stable")[:budget]] = True
    return selected


def groups(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """构造与上一轮诊断一致的历史特征分组。

    Args:
        frame: 固定验证样本。

    Returns:
        包含总体、较早、低频及其交集的布尔掩码。
    """
    older = frame.pair_recency_hours.to_numpy() > 24
    low = frame.pair_events.to_numpy() <= 5
    return {
        "all": np.ones(len(frame), dtype=bool),
        "recent_le24h": ~older,
        "older_gt24h": older,
        "low_frequency_le5": low,
        "single_event": frame.pair_events.to_numpy() == 1,
        "high_frequency_gt5": ~low,
        "older_and_low": older & low,
    }


def compare(
    frame: pd.DataFrame, scores: dict[str, np.ndarray], thresholds: dict[str, float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """计算固定阈值及全局等预算命中，分组不单独选阈值。

    Args:
        frame: 同一验证样本。
        scores: 两个固定模型的分数。
        thresholds: 已存档阈值。

    Returns:
        各模型分组指标和目标命中交集。
    """
    labels = frame.label.to_numpy().astype(bool)
    selections = {
        name: {
            "fixed": values >= thresholds[name],
            **{f"top_{budget}": top_k(values, budget) for budget in BUDGETS},
        }
        for name, values in scores.items()
    }
    rows, overlaps = [], []
    for group, mask in groups(frame).items():
        positive = mask & labels
        for name, values in scores.items():
            subset = values[positive]
            ranking = (
                float(average_precision_score(labels[mask], values[mask]))
                if positive.any()
                else None
            )
            for policy, selected in selections[name].items():
                hits = int((positive & selected).sum())
                predicted = int((mask & selected).sum())
                rows.append(
                    {
                        "group": group,
                        "model": name,
                        "policy": policy,
                        "rows": int(mask.sum()),
                        "positives": int(positive.sum()),
                        "predicted": predicted,
                        "hits": hits,
                        "recall": hits / positive.sum() if positive.any() else None,
                        "precision": hits / predicted if predicted else None,
                        "within_group_ap": ranking,
                        "positive_score_p10": (
                            float(np.quantile(subset, 0.1)) if len(subset) else None
                        ),
                        "positive_score_median": (
                            float(np.median(subset)) if len(subset) else None
                        ),
                        "positive_score_p90": (
                            float(np.quantile(subset, 0.9)) if len(subset) else None
                        ),
                    }
                )
        for policy, first in selections["lr_24"].items():
            second = selections["hgb_31"][policy]
            overlaps.append(
                {
                    "group": group,
                    "policy": policy,
                    "both": int((positive & first & second).sum()),
                    "lr_only": int((positive & first & ~second).sum()),
                    "tree_only": int((positive & ~first & second).sum()),
                    "neither": int((positive & ~first & ~second).sum()),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(overlaps)


def verified_scores(root: Path, frame: pd.DataFrame) -> tuple[dict, dict, dict]:
    """读取本地两组模型并复现各自存档验证指标。

    Args:
        root: 项目目录。
        frame: 已核对指纹的验证样本。

    Returns:
        分数、固定阈值和模型指纹。
    """
    scores, thresholds, fingerprints = {}, {}, {}
    for name, experiment in [
        ("lr_24", "lr_2026-11-17"),
        ("hgb_31", "tree_validation_2026-11-17"),
    ]:
        path = root / "data/models" / experiment / f"{name}.joblib"
        bundle = joblib.load(path)
        metrics_path = root / "reports/experiments" / experiment / "metrics.json"
        expected = json.loads(metrics_path.read_text())["models"][name]["validation"]
        if (
            bundle["features"] != FEATURE_COLUMNS
            or bundle["threshold"] != expected["threshold"]
        ):
            raise ValueError("模型特征或阈值不符")
        values = (
            transform(frame, FEATURE_COLUMNS)
            if name == "lr_24"
            else frame[FEATURE_COLUMNS]
        )
        scores[name] = bundle["model"].predict_proba(values)[:, 1]
        thresholds[name] = bundle["threshold"]
        measured = evaluate(frame.label, scores[name], thresholds[name])
        if any(
            not np.isclose(measured[key], value, rtol=1e-12, atol=1e-12)
            for key, value in expected.items()
        ):
            raise ValueError("验证结果未复现")
        fingerprints[name] = {
            "model": file_digest(path),
            "metrics": file_digest(metrics_path),
        }
    return scores, thresholds, fingerprints


def plot_comparison(statistics: pd.DataFrame, output: Path) -> None:
    """绘制等预算下重点分组的命中数量。

    Args:
        statistics: 两模型分组诊断结果。
        output: 公开结果目录。
    """
    plt.switch_backend("Agg")
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    names = ["all", "older_gt24h", "low_frequency_le5", "older_and_low"]
    for axis, budget in zip(axes, BUDGETS):
        subset = statistics.loc[statistics.policy == f"top_{budget}"]
        values = subset.pivot(index="group", columns="model", values="hits")
        values.loc[names].plot.bar(ax=axis, rot=20)
        axis.set(title=f"Global top {budget}: validation", ylabel="Positive pairs hit")
        axis.set_ylim(0, values.hgb_31.max() * 1.25)
    figure.tight_layout()
    figure.savefig(output / "equal_budget_hits.png", dpi=150)
    plt.close(figure)


def run(root: Path) -> None:
    """保存诊断协议，执行不重训的验证集对照。

    Args:
        root: 项目目录。
    """
    _, manifest = verify_protocol(root)
    output = root / "reports/errors/lr_tree_comparison_2026-11-18"
    output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "budgets": BUDGETS,
        "budget_reason": "previous fixed predicted-positive counts: "
        + "tree 5060, LR 12400",
        "tie_break": "stable validation row order (user_id, item_id)",
        "code_sha256": file_digest(Path(__file__)),
        "validation_sha256": manifest["artifacts"]["validation"]["sha256"],
        "test_accessed": False,
        "retrained": False,
        "status": "development_diagnostics_not_independent_evaluation",
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    frame = load_sample(root, "validation", manifest)
    scores, thresholds, fingerprints = verified_scores(root, frame)
    statistics, overlaps = compare(frame, scores, thresholds)
    statistics.to_csv(output / "comparison.csv", index=False)
    overlaps.to_csv(output / "overlap.csv", index=False)
    plot_comparison(statistics, output)
    (output / "models.json").write_text(
        json.dumps(
            {
                "thresholds": thresholds,
                "fingerprints": fingerprints,
                "metrics_reproduced": True,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    run(Path.cwd())
