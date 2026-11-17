"""核对分组错误率分母、阈值边界及空组处理。"""

import numpy as np
import pandas as pd
import pytest

from douyin_analysis.error_analysis import BINS, segment_errors


def test_segment_counts_and_zero_denominators() -> None:
    """手算 TP、FP、FN、TN 并验证每个维度计数守恒。"""
    frame = pd.DataFrame({name: [1, 1, 1, 1] for name in BINS})
    frame["label"] = [1, 0, 1, 0]
    frame["user_buy"] = [0, 0, 1, 1]
    frame["user_events"] = [100, 100, 101, 101]
    table = segment_errors(frame, np.array([0.5, 0.9, 0.4, 0.1]), 0.5)
    for _, group in table.groupby("feature"):
        assert group[["tp", "fp", "fn", "tn"]].sum().tolist() == [1, 1, 1, 1]
        assert group.rows.sum() == 4
    activity = table.loc[table.feature == "user_events"].reset_index(drop=True)
    assert activity.loc[0, "rows"] == 2
    assert activity.loc[0, "false_positive_rate"] == 1
    assert activity.loc[1, "false_negative_rate"] == 1
    assert np.isnan(activity.loc[2, "false_negative_rate"])
    assert np.isnan(activity.loc[1, "precision"])


def test_nonfinite_scores_rejected() -> None:
    """非法预测不得被静默归类为负例。"""
    frame = pd.DataFrame({name: [1] for name in BINS})
    frame["label"] = [1]
    with pytest.raises(ValueError, match="非有限"):
        segment_errors(frame, np.array([np.nan]), 0.5)
