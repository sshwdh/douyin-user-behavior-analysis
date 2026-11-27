"""补充固定模型的训练规模曲线、匿名错误案例与本机推理基准。"""

import argparse
import json
import platform
import resource
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import sklearn
from sklearn.base import clone
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import average_precision_score, roc_auc_score
from threadpoolctl import threadpool_limits

from douyin_analysis.lr_experiment import load_sample, transform
from douyin_analysis.pipeline import file_digest
from douyin_analysis.segment_analysis import MODELS

OUTPUT = "reports/evaluation/2026-11-27"
FRACTIONS = [0.1, 0.3, 0.6, 1.0]
CASE_FEATURES = [
    "pair_events",
    "pair_recency_hours",
    "pair_pv",
    "pair_fav",
    "pair_cart",
    "pair_buy",
    "user_events",
    "item_users",
]


def nested_indices(labels: np.ndarray, fraction: float) -> np.ndarray:
    """产生固定种子、类别内嵌套的训练子集，不接收验证标签。

    Args:
        labels: 含两类的训练标签。
        fraction: 每个类别保留的比例。

    Returns:
        确定性排列的子集位置；各类别至少一行。
    """
    if not 0 < fraction <= 1 or set(np.unique(labels)) != {0, 1}:
        raise ValueError("比例或训练标签无效")
    rng = np.random.default_rng(42)
    parts = []
    for value in [0, 1]:
        indices = rng.permutation(np.flatnonzero(labels == value))
        parts.append(indices[: max(1, int(len(indices) * fraction))])
    return np.sort(np.concatenate(parts))


def inputs(frame: pd.DataFrame, bundle: dict, name: str) -> pd.DataFrame:
    """按存档方案执行无标签预处理，缩放器仍保留在 LR 模型内部。"""
    if name.startswith("lr"):
        return transform(frame, bundle["features"])
    return frame[bundle["features"]]


def error_cases(
    frame: pd.DataFrame, scores: np.ndarray, threshold: float
) -> pd.DataFrame:
    """选择分数最高的误报和最低的漏报各两条，不导出原始标识。

    Args:
        frame: 固定验证样本。
        scores: 与验证样本逐行对齐的分数。
        threshold: 已存档的全局阈值。

    Returns:
        仅含匿名案例序号、历史特征、标签、分数及阈值的表。
    """
    if len(frame) != len(scores) or not np.isfinite(scores).all():
        raise ValueError("分数长度或数值不合法")
    labels = frame.label.to_numpy()
    if not set(np.unique(labels)).issubset({0, 1}):
        raise ValueError("标签必须为二元")
    selected = []
    for kind, mask, direction in [
        ("FP", (labels == 0) & (scores >= threshold), -1),
        ("FN", (labels == 1) & (scores < threshold), 1),
    ]:
        positions = np.flatnonzero(mask)
        order = np.argsort(direction * scores[positions], kind="stable")
        for number, position in enumerate(positions[order[:2]], 1):
            selected.append(
                {
                    "case": f"{kind}-{number}",
                    "error": kind,
                    "label": int(labels[position]),
                    "score": float(scores[position]),
                    "threshold": threshold,
                    **{key: float(frame.iloc[position][key]) for key in CASE_FEATURES},
                }
            )
    return pd.DataFrame(selected)


def rank_metrics(labels: np.ndarray, scores: np.ndarray) -> dict:
    """计算全部样本排名指标，不选择阈值。"""
    return {
        "ap": float(average_precision_score(labels, scores)),
        "roc_auc": float(roc_auc_score(labels, scores)),
    }


def benchmark(root: Path, name: str) -> None:
    """在独立进程内测量已加载数据上的预处理加推理时间。

    Args:
        root: 本地项目根目录。
        name: 存档模型名称。
    """
    model_path = root / "data/models" / MODELS[name]
    bundle = joblib.load(model_path)
    source = pq.ParquetFile(root / "data/features/validation.parquet")
    frame = next(
        source.iter_batches(batch_size=10000, columns=bundle["features"])
    ).to_pandas()
    rows = []
    with threadpool_limits(limits=1):
        for size in [1, 1000, 10000]:
            batch = frame.iloc[:size]
            for _ in range(2):
                bundle["model"].predict_proba(inputs(batch, bundle, name))
            for repeat in range(7):
                cpu_start = time.process_time()
                started = time.perf_counter()
                scores = bundle["model"].predict_proba(inputs(batch, bundle, name))
                elapsed = time.perf_counter() - started
                cpu_elapsed = time.process_time() - cpu_start
                if scores.shape != (size, 2) or not np.isfinite(scores).all():
                    raise ValueError("推理输出异常")
                usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                divisor = 1024**2 if sys.platform == "darwin" else 1024
                rows.append(
                    {
                        "model": name,
                        "batch_size": size,
                        "repeat": repeat,
                        "wall_ms": elapsed * 1000,
                        "cpu_ms": cpu_elapsed * 1000,
                        "process_peak_rss_mib": usage / divisor,
                        "model_file_bytes": model_path.stat().st_size,
                    }
                )
    pd.DataFrame(rows).to_csv(root / OUTPUT / f"benchmark_{name}.csv", index=False)


def learning(root: Path, manifest: dict) -> None:
    """固定验证集和模型配置，比较嵌套训练规模并复核全量存档分数。"""
    train = load_sample(root, "train", manifest)
    validation = load_sample(root, "validation", manifest)
    archived = pd.read_csv(root / "reports/dashboard/research/metrics.csv").set_index(
        "model"
    )
    curves, cases = [], []
    with threadpool_limits(limits=1):
        for name, relative in MODELS.items():
            bundle = joblib.load(root / "data/models" / relative)
            train_x = inputs(train, bundle, name)
            valid_x = inputs(validation, bundle, name)
            for fraction in FRACTIONS:
                indices = nested_indices(train.label.to_numpy(), fraction)
                x_part = train_x.iloc[indices]
                y_part = train.label.iloc[indices]
                model = bundle["model"] if fraction == 1 else clone(bundle["model"])
                fit_seconds = None
                if fraction < 1:
                    started = time.perf_counter()
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", ConvergenceWarning)
                        model.fit(x_part, y_part)
                    fit_seconds = time.perf_counter() - started
                train_scores = model.predict_proba(x_part)[:, 1]
                valid_scores = model.predict_proba(valid_x)[:, 1]
                measured = rank_metrics(validation.label.to_numpy(), valid_scores)
                if fraction == 1:
                    for key, column in [
                        ("ap", "pr_auc_average_precision"),
                        ("roc_auc", "roc_auc"),
                    ]:
                        if not np.isclose(
                            measured[key], archived.loc[name, column], rtol=1e-8
                        ):
                            raise ValueError(f"存档结果不一致: {name}/{key}")
                    cases.append(
                        error_cases(
                            validation, valid_scores, bundle["threshold"]
                        ).assign(model=name)
                    )
                curves.append(
                    {
                        "model": name,
                        "fraction": fraction,
                        "train_rows": len(indices),
                        "train_positives": int(y_part.sum()),
                        "fit_seconds": fit_seconds,
                        "full_model_reused": fraction == 1,
                        **{
                            f"train_{key}": value
                            for key, value in rank_metrics(
                                y_part.to_numpy(), train_scores
                            ).items()
                        },
                        **{
                            f"validation_{key}": value
                            for key, value in measured.items()
                        },
                    }
                )
                print(name, fraction, measured, flush=True)
                pd.DataFrame(curves).to_csv(
                    root / OUTPUT / "learning_curves.csv", index=False
                )
    pd.concat(cases).to_csv(root / OUTPUT / "error_cases.csv", index=False)


def run(root: Path) -> None:
    """先冻结补充协议，再生成学习曲线与独立进程推理基准。"""
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    feature_path = root / "reports/features/manifest.json"
    manifest = json.loads(feature_path.read_text())
    protocol = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_manifest_sha256": file_digest(feature_path),
        "code_sha256": file_digest(Path(__file__)),
        "models": {
            key: file_digest(root / "data/models" / path)
            for key, path in MODELS.items()
        },
        "fractions": FRACTIONS,
        "seed": 42,
        "threads": 1,
        "sampling": "nested stratified subsets of training only; same full validation",
        "full_model": "reuse archived fitted model at 100%; no refit or overwrite",
        "preprocessing": "clone refits scaler on each training subset",
        "selection": "diagnostic only; no threshold or model selection",
        "test_accessed_this_run": False,
        "test_history": "LR test evaluated on 2026-11-17; not a fresh holdout",
        "cases": (
            "highest-score FP and lowest-score FN, two each per model; "
            + "illustrative extremes"
        ),
        "benchmark": "separate process per model; batches 1/1000/10000",
        "warmups": 2,
        "repetitions": 7,
        "timed_scope": (
            "in-memory feature transform plus predict_proba; "
            + "excludes IO, load, feature generation, HTTP"
        ),
        "memory": (
            "process lifetime peak RSS includes Python, imports, model and batch; "
            + "not model incremental memory"
        ),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "gpu": "not used",
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    learning(root, manifest)
    for name in MODELS:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "douyin_analysis.evaluation_supplement",
                "--benchmark",
                name,
            ],
            cwd=root,
            check=True,
        )
    files = {path.name: file_digest(path) for path in sorted(output.glob("*.csv"))}
    (output / "manifest.json").write_text(
        json.dumps({"files": files, "test_accessed_this_run": False}, indent=2) + "\n"
    )


def main() -> None:
    """运行完整补充评估，或进入单一模型的独立基准进程。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=list(MODELS))
    args = parser.parse_args()
    if args.benchmark:
        benchmark(Path.cwd(), args.benchmark)
    else:
        run(Path.cwd())


if __name__ == "__main__":
    main()
