"""验证等预算选择及两模型命中交集。"""

import numpy as np
import pandas as pd
import pytest

from douyin_analysis.error_comparison import compare, top_k


def test_top_k_stable_ties() -> None:
    """同分时稳定选择较前行，并拒绝超范围预算。"""
    assert top_k(np.array([0.5, 0.5, 0.9]), 2).tolist() == [True, False, True]
    with pytest.raises(ValueError):
        top_k(np.array([0.5]), 2)


def test_overlap_and_global_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """分组不能重新分配预算，四类交集计数必须覆盖全部正例。"""
    monkeypatch.setattr("douyin_analysis.error_comparison.BUDGETS", [2])
    frame = pd.DataFrame(
        {
            "label": [1, 1, 1, 0],
            "pair_recency_hours": [48, 48, 1, 1],
            "pair_events": [1, 2, 6, 6],
        }
    )
    scores = {
        "lr_24": np.array([0.9, 0.1, 0.8, 0.2]),
        "hgb_31": np.array([0.1, 0.9, 0.8, 0.2]),
    }
    statistics, overlap = compare(frame, scores, {"lr_24": 0.5, "hgb_31": 0.5})
    overall = overlap.loc[(overlap.group == "all") & (overlap.policy == "top_2")].iloc[
        0
    ]
    assert overall[["both", "lr_only", "tree_only", "neither"]].tolist() == [1, 1, 1, 0]
    older = statistics.loc[
        (statistics.group == "older_gt24h") & (statistics.policy == "top_2")
    ]
    assert older.predicted.tolist() == [1, 1]
    assert older.hits.tolist() == [1, 1]
