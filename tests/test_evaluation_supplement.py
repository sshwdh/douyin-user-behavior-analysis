"""验证补充评估抽样边界和错误案例选择，不依赖真实数据。"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from douyin_analysis.evaluation_figures import NAMES, summarize_benchmarks
from douyin_analysis.evaluation_supplement import (
    CASE_FEATURES,
    error_cases,
    nested_indices,
)


def test_nested_sampling_preserves_classes() -> None:
    """同种子子集嵌套，两类数量按比例取整，全量覆盖所有行。"""
    labels = np.array([0] * 100 + [1] * 10)
    small = nested_indices(labels, 0.1)
    large = nested_indices(labels, 0.6)
    assert set(small).issubset(large)
    assert len(small) == 11
    assert labels[small].sum() == 1
    assert labels[large].sum() == 6
    np.testing.assert_array_equal(nested_indices(labels, 1), np.arange(110))
    np.testing.assert_array_equal(small, nested_indices(labels, 0.1))
    with pytest.raises(ValueError):
        nested_indices(labels, 0)
    with pytest.raises(ValueError):
        nested_indices(np.zeros(20), 0.5)


def test_error_cases_use_frozen_boundary_and_hide_ids() -> None:
    """阈值等号归为预测正类，按极端分数选例，不泄露用户商品键。"""
    frame = pd.DataFrame({key: np.arange(6) for key in CASE_FEATURES})
    frame["label"] = [0, 0, 0, 1, 1, 1]
    frame["user_id"] = [111] * 6
    frame["item_id"] = np.arange(6)
    scores = np.array([0.5, 0.9, 0.1, 0.49, 0.2, 0.8])
    cases = error_cases(frame, scores, 0.5)
    assert cases.case.tolist() == ["FP-1", "FP-2", "FN-1", "FN-2"]
    assert cases.score.tolist() == [0.9, 0.5, 0.2, 0.49]
    assert cases.label.tolist() == [0, 0, 1, 1]
    assert not {"user_id", "item_id"}.intersection(cases.columns)
    with pytest.raises(ValueError):
        error_cases(frame, scores[:-1], 0.5)


def test_benchmark_summary_does_not_ingest_previous_summary(tmp_path: Path) -> None:
    """重复生成不会把上一次汇总混入原始基准或重复计数。"""
    for name in NAMES:
        pd.DataFrame(
            {
                "model": [name] * 3,
                "batch_size": [1000] * 3,
                "wall_ms": [1.0, 2.0, 3.0],
                "cpu_ms": [1.0, 2.0, 3.0],
                "process_peak_rss_mib": [200.0] * 3,
                "model_file_bytes": [100] * 3,
            }
        ).to_csv(tmp_path / f"benchmark_{name}.csv", index=False)
    first = summarize_benchmarks(tmp_path)
    second = summarize_benchmarks(tmp_path)
    pd.testing.assert_frame_equal(first, second)
    assert first.repeats.tolist() == [3, 3, 3]
    assert first.median_ms.tolist() == [2.0, 2.0, 2.0]
    assert first.rows_per_second.tolist() == [500000.0] * 3
