"""冻结树模型对照配置，仅验证开发样本，不训练真实数据模型。"""

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from douyin_analysis.features import FEATURE_COLUMNS
from douyin_analysis.lr_experiment import load_sample
from douyin_analysis.pipeline import file_digest


def build_estimators() -> dict[str, HistGradientBoostingClassifier]:
    """创建固定的两组梯度提升树。

    Returns:
        未拟合的模型，关闭随机内部验证拆分。
    """
    return {
        f"hgb_{leaves}": HistGradientBoostingClassifier(
            max_leaf_nodes=leaves,
            max_iter=150,
            learning_rate=0.05,
            min_samples_leaf=50,
            l2_regularization=1.0,
            class_weight="balanced",
            early_stopping=False,
            random_state=42,
        )
        for leaves in [15, 31]
    }


def prepare(root: Path) -> None:
    """校验训练和验证输入，保存配置与后续比较规则。

    Args:
        root: 项目根目录。
    """
    path = root / "reports/features/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if file_digest(root / "data/processed/events.parquet") != manifest["events_sha256"]:
        raise ValueError("事件数据已改变")
    for split in ["train", "validation"]:
        frame = load_sample(root, split, manifest)
        if not np.isfinite(frame[FEATURE_COLUMNS].to_numpy()).all():
            raise ValueError("树模型输入包含非有限值")
    output = root / "reports/trees"
    output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "status": "prepared_not_trained",
        "feature_manifest_sha256": file_digest(path),
        "code_sha256": file_digest(Path(__file__)),
        "data_snapshot_id": manifest["data_snapshot_id"],
        "semantic_confirmations": manifest["semantic_confirmations"],
        "samples": {key: manifest["artifacts"][key] for key in ["train", "validation"]},
        "features": FEATURE_COLUMNS,
        "transform": "raw numeric values; no scaler; no resampling",
        "variants": {
            name: model.get_params() for name, model in build_estimators().items()
        },
        "selection": "validation average precision; ties prefer hgb_15",
        "threshold": "maximum validation F1; ties prefer higher threshold",
        "reference": "lr_24 validation AP=0.02782960959 on identical candidates",
        "test_policy": "No test access; existing test was used by LR. "
        + "Independent final evaluation requires a newly reserved dataset.",
        "real_data_fit": False,
    }
    (output / "preparation.json").write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    prepare(Path.cwd())
