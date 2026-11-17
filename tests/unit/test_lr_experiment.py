"""验证阈值并列处理、变换与固定样本实验的训练边界。"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from douyin_analysis.experiment_metrics import evaluate, select_threshold
from douyin_analysis.features import BASELINE_FEATURES, FEATURE_COLUMNS
from douyin_analysis.lr_experiment import EXPERIMENT, load_sample, run, transform
from douyin_analysis.pipeline import file_digest


def test_validation_threshold_tie() -> None:
    """两阈值 F1 相同时选更高阈值，测试评价不再改变阈值。"""
    labels = pd.Series([1, 0, 0, 1])
    scores = np.array([0.1, 0.2, 0.3, 0.4])
    threshold = select_threshold(labels, scores)
    assert threshold == 0.4
    result = evaluate(labels, scores, threshold)
    assert result["true_positive"] == 1
    assert result["false_negative"] == 1
    assert result["predicted_positive"] == 1
    assert result["threshold"] == 0.4


def test_transform_preserves_rates_and_input() -> None:
    """比例和二元标记不做 log1p，函数不修改原始样本。"""
    frame = pd.DataFrame(
        {"pair_events": [3], "item_buyer_rate": [0.5], "user_has_buy": [1]}
    )
    original = frame.copy()
    result = transform(frame, list(frame.columns))
    assert result.pair_events.item() == np.log(4)
    assert result.item_buyer_rate.item() == 0.5
    assert result.user_has_buy.item() == 1
    pd.testing.assert_frame_equal(frame, original)


def test_changed_sample_rejected(tmp_path: Path) -> None:
    """发生样本漂移时拒绝训练，不能悄悄换用新文件。"""
    path = tmp_path / "data/features/train.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="指纹"):
        load_sample(tmp_path, "train", {"artifacts": {"train": {"sha256": "old"}}})


def test_small_experiment_freezes_validation_decision(tmp_path: Path) -> None:
    """合成样本贯通训练及评价，验证缩放仅在训练拟合和阈值保持不变。"""
    local = tmp_path / "data/features"
    local.mkdir(parents=True)
    reports = tmp_path / "reports/features"
    reports.mkdir(parents=True)
    events = tmp_path / "data/processed/events.parquet"
    events.parent.mkdir(parents=True)
    pd.DataFrame({"event": [1]}).to_parquet(events, index=False)
    manifest = {
        "events_sha256": file_digest(events),
        "data_snapshot_id": "synthetic",
        "semantic_confirmations": {"behavior_code_meanings": "pending"},
        "artifacts": {},
    }
    rng = np.random.default_rng(42)
    training = pd.DataFrame()
    for index, split in enumerate(["train", "validation", "test"]):
        frame = pd.DataFrame(rng.integers(0, 8, size=(80, 24)), columns=FEATURE_COLUMNS)
        frame["user_has_buy"] = frame.user_has_buy.mod(2)
        frame["item_buyer_rate"] /= 7
        frame["label"] = np.tile([0, 1], 40)
        frame["pair_cart"] = frame.label * 20 + index
        frame["user_id"] = [str(value) for value in range(80)]
        frame["item_id"] = "1"
        path = local / f"{split}.parquet"
        frame.to_parquet(path, index=False)
        manifest["artifacts"][split] = {"sha256": file_digest(path), "rows": 80}
        if split == "train":
            training = frame
    (reports / "manifest.json").write_text(json.dumps(manifest))
    pd.DataFrame({"split": ["test"], "future_code4_pairs": [100]}).to_csv(
        reports / "sample_summary.csv", index=False
    )
    run(tmp_path)
    output = tmp_path / "reports/experiments" / EXPERIMENT
    decision = json.loads((output / "validation_decision.json").read_text())
    metrics = json.loads((output / "metrics.json").read_text())
    assert decision["test_loaded"] is False
    assert metrics["selected_by_validation"] == decision["selected_variant"]
    assert decision["decided_at_utc"] <= metrics["test_evaluated_at_utc"]
    for name, result in metrics["models"].items():
        assert result["validation"]["threshold"] == result["test"]["threshold"]
        assert result["test"]["recall_all_future_pairs"] <= 0.4
        assert "test" not in decision["validation_results"][name]
    saved = joblib.load(tmp_path / "data/models" / EXPERIMENT / "lr_10.joblib")
    expected = transform(training, BASELINE_FEATURES).mean().to_numpy()
    np.testing.assert_allclose(saved["model"][0].mean_, expected)
