"""验证训练分箱边界、空箱与分层混淆计数的手算结果。"""

import numpy as np
import pandas as pd
import pytest

from douyin_analysis.segment_analysis import fit_edges, ranking_by_bin, summarize


def test_training_edges_and_boundary_counts() -> None:
    """训练分位点右闭，验证超出训练最大值仍进入末箱。"""
    edges = fit_edges(pd.Series([0, 1, 2, 3]))
    assert edges == [-np.inf, 0, 2, np.inf]
    frame = pd.DataFrame({"x": [0, 1, 2, 100], "label": [0, 1, 0, 1]})
    result = summarize(frame, "x", edges, np.array([False, True, True, False]))
    assert result.rows.tolist() == [1, 2, 1]
    assert result.positives.tolist() == [0, 1, 1]
    assert result.tp.tolist() == [0, 1, 0]
    assert result.fp.tolist() == [0, 1, 0]
    assert result.fn.tolist() == [0, 0, 1]
    assert result.precision.iloc[1] == 0.5
    assert result.recall.iloc[1] == 1
    assert np.isnan(result.recall.iloc[0])


def test_empty_and_single_class_bins() -> None:
    """空箱和无正例组不输出伪造的零分母比率或排名指标。"""
    frame = pd.DataFrame({"x": [1, 1], "label": [0, 0]})
    edges = fit_edges(pd.Series([0, 1, 1, 1]))
    result = summarize(frame, "x", edges, np.array([False, False]))
    assert result.rows.tolist() == [0, 2]
    assert np.isnan(result.positive_rate.iloc[0])
    assert result.precision.isna().all()
    ranking = ranking_by_bin(frame, "x", edges, np.array([0.1, 0.2]))
    assert ranking.ap.isna().all()
    assert ranking.roc_auc.isna().all()


def test_invalid_features_rejected() -> None:
    """缺失和负值不能静默落入零值分箱。"""
    with pytest.raises(ValueError, match="有限"):
        fit_edges(pd.Series([0, np.nan]))
    with pytest.raises(ValueError, match="非负"):
        fit_edges(pd.Series([-1, 0]))


def test_bin_ranking_matches_hand_order() -> None:
    """正例排名第一的双类别箱 AP 与 AUC 均为一。"""
    frame = pd.DataFrame({"x": [1, 1, 2, 2], "label": [0, 1, 0, 1]})
    table = ranking_by_bin(
        frame, "x", [-np.inf, 0, np.inf], np.array([0.1, 0.9, 0.2, 0.8])
    )
    assert table.ap.iloc[1] == 1
    assert table.roc_auc.iloc[1] == 1


def test_published_segments_conserve_validation_counts() -> None:
    """所有特征与模型维度必须覆盖同一批验证样本且恢复全局命中。"""
    from douyin_analysis.dashboard_segments import load_segments

    association = load_segments("associations")
    for _, table in association.groupby("feature"):
        assert table.rows.sum() == 1061515
        assert table.positives.sum() == 2525
        assert table.train_pair_count.sum() == 1030893
    performance = load_segments("performance")
    for (model, _), table in performance.groupby(["model", "feature"]):
        assert table.rows.sum() == 1061515
        assert table.positives.sum() == 2525
        assert (
            table.tp.sum()
            == {"lr_24": 506, "hgb_31": 367, "lr_24_unweighted": 474}[model]
        )


def test_segment_dashboard_switches() -> None:
    """关联特征及商品分层切换后正确读取汇总而不触发训练。"""
    from streamlit.testing.v1 import AppTest

    source = (
        "from douyin_analysis.dashboard_segments import "
        + "show_associations, show_segment_performance\n"
        + "show_associations()\nshow_segment_performance()"
    )
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    app.selectbox[0].select("历史加购次数（暂释）")
    app.selectbox[1].select("商品历史交互用户数")
    app.selectbox[2].select("精确率").run()
    assert not app.exception
    assert app.dataframe[0].value["实际正例对"].tolist() == [1300, 1036, 189]
    assert set(app.dataframe[1].value["验证候选对数"]) == {0, 697735, 363780}
