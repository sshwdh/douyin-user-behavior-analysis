"""验证看板的日期边界、计数一致性与交互加载。"""

from datetime import date

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from douyin_analysis.dashboard_data import (
    ROOT,
    model_metrics,
    overview,
    read_report,
    select_days,
)
from douyin_analysis.extra_features import EXTRA_COLUMNS
from douyin_analysis.features import FEATURE_COLUMNS


def test_date_filter_keeps_both_boundary_days() -> None:
    """日期范围含首尾，不修改来源或将 DAU 当作区间去重人数。"""
    frame = pd.DataFrame(
        {
            "day": ["2025-11-18", "2025-11-19", "2025-11-20"],
            "events": [10, 20, 30],
            "dau": [3, 3, 3],
        }
    )
    selected = select_days(frame, date(2025, 11, 18), date(2025, 11, 19))
    assert selected.events.sum() == 30
    assert len(frame) == 3
    with pytest.raises(ValueError, match="开始日期"):
        select_days(frame, date(2025, 11, 20), date(2025, 11, 18))


def test_report_path_rejects_escape() -> None:
    """拒绝读取仓库 reports 之外的路径。"""
    with pytest.raises(ValueError, match="仅允许"):
        read_report("../../user_behavior.csv")


def test_dashboard_totals_and_features_match_sources() -> None:
    """全量计数及30项已实现特征必须与现有产物对应。"""
    assert overview()["clean_rows"] == 12256906
    catalog = read_report("features/feature_catalog.csv")
    fields = catalog.loc[catalog["代码字段"] != "未实现", "代码字段"]
    assert set(fields) == set(FEATURE_COLUMNS + EXTRA_COLUMNS)
    assert not fields.duplicated().any()
    metrics = model_metrics()
    assert len(metrics) == 5
    assert (metrics["positives"] == 2525).all()
    assert metrics.loc["hgb_31", "true_positive"] == 367


def test_behavior_page_and_filters() -> None:
    """运行入口并切换日期、指标及特征层级，页面不能报错。"""
    app = AppTest.from_file(str(ROOT / "scripts/run_dashboard.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert not app.error
    assert app.metric[0].value == "12,256,906"
    app.date_input[0].set_value((date(2025, 11, 18), date(2025, 11, 18)))
    app.selectbox[0].select("全部行为")
    app.selectbox[1].select("类别")
    app.run()
    assert not app.exception
    assert not app.error
    assert app.metric[4].value == "366,701"
    assert len(app.dataframe[-1].value) == 3


def test_model_page_selection() -> None:
    """模型切换须更新混淆矩阵且不执行新训练。"""
    source = "from douyin_analysis.dashboard import model_page\nmodel_page()"
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    app.selectbox[0].select("hgb_31_extended30").run()
    assert not app.exception
    assert int(app.dataframe[1].value.iloc[1, 1]) == 366
