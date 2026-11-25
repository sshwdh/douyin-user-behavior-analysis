"""用训练历史特征确定分箱，汇总固定验证样本的关联与分层模型表现。"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from douyin_analysis.experiment_metrics import evaluate
from douyin_analysis.lr_experiment import load_sample, transform
from douyin_analysis.pipeline import file_digest

FEATURES = {
    "pair_pv": "历史浏览次数（暂释）",
    "pair_fav": "历史收藏次数（暂释）",
    "pair_cart": "历史加购次数（暂释）",
    "pair_recency_hours": "距最近交互小时数",
    "user_events": "用户历史交互次数",
    "item_users": "商品历史交互用户数",
}
OUTPUT = "reports/dashboard/segments"
MODELS = {
    "lr_24": "lr_2026-11-17/lr_24.joblib",
    "hgb_31": "tree_validation_2026-11-17/hgb_31.joblib",
    "lr_24_unweighted": "dashboard_research_2026-11-23/lr_24_unweighted.joblib",
}


def fit_edges(values: pd.Series) -> list[float]:
    """仅根据非负历史数值计算零值箱及正值三分位边界。

    Args:
        values: 训练历史特征，不接收标签。

    Returns:
        有序右闭区间边界；重复分位点合并，末箱允许验证超出训练最大值。
    """
    if values.empty or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("分箱输入必须为非空、有限且非负")
    positive = values[values > 0]
    cuts = [0.0]
    if not positive.empty:
        cuts += [
            float(value)
            for value in np.quantile(positive, [1 / 3, 2 / 3], method="higher")
            if value < positive.max()
        ]
    return [-float("inf"), *sorted(set(cuts)), float("inf")]


def summarize(
    frame: pd.DataFrame, feature: str, edges: list[float], predicted: np.ndarray
) -> pd.DataFrame:
    """汇总单一特征分箱，保留空箱并对无分母的比例留空。

    Args:
        frame: 含历史特征及二元 label 的验证样本。
        feature: 要统计的特征字段。
        edges: 在训练特征上确定的区间。
        predicted: 与样本逐行一致的布尔预测。

    Returns:
        每箱支持量、混淆计数、正例率、精确率与召回率。
    """
    if len(predicted) != len(frame) or not frame.label.isin([0, 1]).all():
        raise ValueError("预测长度或二元标签不合法")
    if predicted.dtype != bool:
        raise ValueError("预测须为布尔数组")
    values = frame[feature].reset_index(drop=True)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("验证历史特征须为有限非负值")
    groups = pd.cut(values, edges, labels=False, right=True)
    if groups.isna().any():
        raise ValueError("分箱边界未覆盖验证样本")
    actual = frame.label.to_numpy().astype(bool)
    counts = pd.DataFrame(
        {
            "rows": 1,
            "positives": actual,
            "tp": actual & predicted,
            "fp": ~actual & predicted,
            "fn": actual & ~predicted,
            "tn": ~actual & ~predicted,
        }
    )
    result = counts.groupby(groups).sum().reindex(range(len(edges) - 1), fill_value=0)
    result.index.name = "bin_id"
    result = result.reset_index()
    result["feature"] = feature
    result["segment"] = [
        "= 0" if index == 0 else f"({edges[index]:g}, {edges[index + 1]:g}]"
        for index in range(len(edges) - 1)
    ]
    result["predicted_positive"] = result.tp + result.fp
    result["positive_rate"] = result.positives / result.rows.replace(0, np.nan)
    result["precision"] = result.tp / result.predicted_positive.replace(0, np.nan)
    result["recall"] = result.tp / result.positives.replace(0, np.nan)
    result["low_positive_support"] = result.positives < 30
    result["low_prediction_support"] = result.predicted_positive < 30
    if int(result.rows.sum()) != len(frame):
        raise ValueError("分箱样本数不守恒")
    if not (result.tp + result.fp + result.fn + result.tn).equals(result.rows):
        raise ValueError("分箱混淆计数不守恒")
    return result


def ranking_by_bin(
    frame: pd.DataFrame, feature: str, edges: list[float], scores: np.ndarray
) -> pd.DataFrame:
    """计算箱内 AP 与 AUC，单一类别或空箱不提供排名指标。

    Args:
        frame: 自然分布验证样本。
        feature: 分箱特征。
        edges: 训练边界。
        scores: 固定模型的验证分数。

    Returns:
        与分箱序号一致的指标；不执行阈值选择。
    """
    if len(scores) != len(frame) or not np.isfinite(scores).all():
        raise ValueError("预测长度或分数无效")
    groups = pd.cut(frame[feature], edges, labels=False).to_numpy()
    rows = []
    for index in range(len(edges) - 1):
        mask = groups == index
        labels = frame.label.to_numpy()[mask]
        valid = len(np.unique(labels)) == 2
        rows.append(
            {
                "bin_id": index,
                "ap": (
                    average_precision_score(labels, scores[mask]) if valid else np.nan
                ),
                "roc_auc": roc_auc_score(labels, scores[mask]) if valid else np.nan,
            }
        )
    return pd.DataFrame(rows)


def run(root: Path) -> None:
    """固定训练边界后读取验证集，复现三模型指标并导出匿名分组汇总。

    Args:
        root: 含已验证本地样本与模型的项目根目录。
    """
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "reports/features/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    protocol = {
        "boundary_rule": "zero bin; positive train-only thirds; higher quantiles; "
        + "merge duplicate cuts; right closed; overflow in last bin",
        "boundary_population": "pair features: training candidate pairs; "
        + "user_events: distinct training users; item_users: distinct training items",
        "features": FEATURES,
        "test_accessed": False,
        "model_retrained": False,
        "threshold_changed": False,
        "feature_manifest_sha256": file_digest(manifest_path),
        "model_hashes": {
            name: file_digest(root / "data/models" / path)
            for name, path in MODELS.items()
        },
        "code_sha256": file_digest(Path(__file__)),
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    train = load_sample(root, "train", manifest)
    boundaries = {}
    for feature in FEATURES:
        entity = {"user_events": "user_id", "item_users": "item_id"}.get(feature)
        source = train.drop_duplicates(entity) if entity else train
        boundaries[feature] = fit_edges(source[feature])
    (output / "bins.json").write_text(
        json.dumps({key: [str(x) for x in edges] for key, edges in boundaries.items()})
        + "\n"
    )
    validation = load_sample(root, "validation", manifest)
    associations = []
    for feature, edges in boundaries.items():
        table = summarize(validation, feature, edges, np.zeros(len(validation), bool))
        train_groups = pd.cut(train[feature], edges, labels=False)
        table["train_pair_count"] = (
            train_groups.value_counts().reindex(table.bin_id, fill_value=0).to_numpy()
        )
        associations.append(
            table[
                [
                    "feature",
                    "bin_id",
                    "segment",
                    "train_pair_count",
                    "rows",
                    "positives",
                    "positive_rate",
                    "low_positive_support",
                ]
            ]
        )
    expected = pd.read_csv(root / "reports/dashboard/research/metrics.csv").set_index(
        "model"
    )
    segments = []
    for name, relative in MODELS.items():
        bundle = joblib.load(root / "data/models" / relative)
        features = validation[bundle["features"]]
        if name.startswith("lr"):
            features = transform(validation, bundle["features"])
        scores = bundle["model"].predict_proba(features)[:, 1]
        threshold = bundle["threshold"]
        measured = evaluate(validation.label, scores, threshold)
        for key, value in measured.items():
            if not np.isclose(value, expected.loc[name, key], rtol=1e-10, atol=1e-12):
                raise ValueError(f"模型结果未复现: {name}/{key}")
        for feature in ["user_events", "item_users"]:
            edges = boundaries[feature]
            table = summarize(validation, feature, edges, scores >= threshold)
            table = table.merge(ranking_by_bin(validation, feature, edges, scores))
            segments.append(table.assign(model=name, threshold=threshold))
        print(f"{name}: archived metrics reproduced", flush=True)
    files = {}
    for name, tables in [("associations", associations), ("performance", segments)]:
        path = output / f"{name}.csv"
        pd.concat(tables, ignore_index=True).to_csv(path, index=False)
        files[path.name] = file_digest(path)
    for name in ["bins.json", "protocol.json"]:
        files[name] = file_digest(output / name)
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "files": files,
                "train_sha256": manifest["artifacts"]["train"]["sha256"],
                "validation_sha256": manifest["artifacts"]["validation"]["sha256"],
                "validation_rows": len(validation),
                "validation_positives": int(validation.label.sum()),
                "test_accessed": False,
                "model_retrained": False,
                "threshold_changed": False,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    run(Path.cwd())
