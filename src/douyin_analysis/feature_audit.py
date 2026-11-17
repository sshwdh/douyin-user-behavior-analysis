"""生成可追溯的窗口样本、特征质量与候选覆盖报告，不训练模型。"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from douyin_analysis.features import FEATURE_COLUMNS, build_features
from douyin_analysis.pipeline import file_digest

CUTOFFS = ["2025-11-25", "2025-12-02", "2025-12-09"]


def feature_quality(frame: pd.DataFrame, split: str) -> pd.DataFrame:
    """汇总特征缺失、非有限值与分布，遇到非法值失败。

    Args:
        frame: 当前窗口的样本。
        split: 时间数据集名称。

    Returns:
        每个特征一行的质量统计，不含用户或商品标识。

    Raises:
        ValueError: 特征含缺失、非有限值、负值或候选键重复。
    """
    values = frame[FEATURE_COLUMNS]
    if frame.duplicated(["user_id", "item_id"]).any():
        raise ValueError("候选键重复")
    if values.isna().any().any() or not np.isfinite(values.to_numpy()).all():
        raise ValueError("特征含缺失或非有限值")
    if (values < 0).any().any():
        raise ValueError("计数和时间间隔不得为负")
    return pd.DataFrame(
        {
            "split": split,
            "feature": FEATURE_COLUMNS,
            "missing_rate": values.isna().mean().to_numpy(),
            "zero_rate": values.eq(0).mean().to_numpy(),
            "unique_values": values.nunique().to_numpy(),
            "minimum": values.min().to_numpy(),
            "maximum": values.max().to_numpy(),
            "mean": values.mean().to_numpy(),
            "std": values.std(ddof=0).to_numpy(),
            "p50": values.quantile(0.5).to_numpy(),
            "p95": values.quantile(0.95).to_numpy(),
        }
    )


def plot_results(output: Path) -> None:
    """绘制时间分组覆盖与训练特征相关性。

    Args:
        output: 已生成 CSV 汇总的目录。
    """
    plt.switch_backend("Agg")
    coverage = pd.read_csv(output / "sample_summary.csv")
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].bar(coverage["split"], coverage["coverage"] * 100, color="#287f94")
    axes[0].set_title("Coverage of future code-4 user-item pairs")
    axes[0].set_ylabel("Covered pairs / all future pairs (%)")
    axes[1].bar(coverage["split"], coverage["positive_rate"] * 100, color="#d28b46")
    axes[1].set_title("Observed positive rate among candidates")
    axes[1].set_ylabel("Code-4 positive candidates (%)")
    for axis in axes:
        axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output / "candidate_coverage.png", dpi=150)
    plt.close(figure)
    correlation = pd.read_csv(output / "train_correlation.csv", index_col=0)
    figure, axis = plt.subplots(figsize=(12, 10))
    heatmap = axis.imshow(correlation.to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
    axis.set_xticks(range(len(correlation)), correlation.columns, rotation=90)
    axis.set_yticks(range(len(correlation)), correlation.index)
    axis.set_title("Training-window Pearson correlation (raw features only)")
    figure.colorbar(heatmap, ax=axis, shrink=0.8)
    figure.tight_layout()
    figure.savefig(output / "train_correlation.png", dpi=150)
    plt.close(figure)


def run(root: Path, snapshot: Path) -> None:
    """校验来源指纹，依次生成三个窗口样本与公开汇总。

    Args:
        root: 项目根目录。
        snapshot: 已验证的数据快照 JSON。

    Raises:
        ValueError: 数据指纹不符或样本与独立标签统计不一致。
    """
    manifest = json.loads(snapshot.read_text(encoding="utf-8"))
    source = root / "data/processed/events.parquet"
    expected = manifest["artifacts"]["data/processed/events.parquet"]["sha256"]
    if file_digest(source) != expected:
        raise ValueError("数据指纹与快照不符，请先完成数据审计")
    output = root / "reports/features"
    local = root / "data/features"
    output.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    summaries, qualities, artifacts = [], [], {}
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit='2GB'")
        connection.execute("SET threads=4")
        connection.from_parquet(str(source)).create_view("events")
        for split, day in zip(["train", "validation", "test"], CUTOFFS):
            cutoff = datetime.fromisoformat(day)
            frame = build_features(connection, cutoff)
            qualities.append(feature_quality(frame, split))
            future, covered = connection.execute(
                """WITH candidates AS (
                    SELECT DISTINCT user_id,item_id FROM events
                    WHERE event_time>=? AND event_time<?
                ), future AS (
                    SELECT DISTINCT user_id,item_id FROM events
                    WHERE event_time>=? AND event_time<? AND behavior_type=4
                ) SELECT count(*),count(candidates.user_id) FROM future
                LEFT JOIN candidates USING(user_id,item_id)""",
                [
                    cutoff - timedelta(days=7),
                    cutoff,
                    cutoff,
                    cutoff + timedelta(days=7),
                ],
            ).fetchall()[0]
            if int(frame["label"].sum()) != covered:
                raise ValueError("独立标签计数与样本不符")
            summaries.append(
                {
                    "split": split,
                    "cutoff": day,
                    "history_start": (cutoff - timedelta(days=7)).isoformat(),
                    "label_end_exclusive": (cutoff + timedelta(days=7)).isoformat(),
                    "candidates": len(frame),
                    "positives": covered,
                    "positive_rate": float(frame["label"].mean()),
                    "future_code4_pairs": future,
                    "uncovered_future_pairs": future - covered,
                    "coverage": covered / future if future else None,
                    "observed_hours": 336,
                }
            )
            path = local / f"{split}.parquet"
            frame.to_parquet(path, index=False)
            artifacts[split] = {"sha256": file_digest(path), "rows": len(frame)}
            if split == "train":
                frame[FEATURE_COLUMNS].corr().to_csv(output / "train_correlation.csv")
    pd.DataFrame(summaries).to_csv(output / "sample_summary.csv", index=False)
    pd.concat(qualities, ignore_index=True).to_csv(
        output / "feature_quality.csv", index=False
    )
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_snapshot_id": manifest["snapshot_id"],
        "events_sha256": expected,
        "source_sha256": manifest["source_sha256"],
        "semantic_confirmations": manifest["semantic_confirmations"],
        "status": "technical_samples_only_semantics_pending",
        "label_definition": "observed behavior_type=4 in [cutoff,cutoff+7d)",
        "candidate_definition": "interacted pair in [cutoff-7d,cutoff)",
        "features": FEATURE_COLUMNS,
        "cutoffs": CUTOFFS,
        "artifacts": artifacts,
        "code_sha256": {
            name: file_digest(root / "src/douyin_analysis" / name)
            for name in ["features.py", "feature_audit.py"]
        },
        "model_trained": False,
    }
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    plot_results(output)


def main() -> None:
    """解析路径并生成特征审计产物。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.snapshot)


if __name__ == "__main__":
    main()
