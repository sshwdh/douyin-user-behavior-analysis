"""核对补充评估页面的选择联动及发布文件完整性。"""

import hashlib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from douyin_analysis import dashboard_evaluation as module


def test_artifacts_and_invalid_path() -> None:
    """下载来自已发布 PDF，未知文件和篡改文件拒绝读取。"""
    for filename in module.DOCUMENTS.values():
        assert module.verified_bytes(filename).startswith(b"%PDF")
    with pytest.raises(ValueError, match="未知"):
        module.verified_bytes("../../data/features/test.parquet")


def test_changed_bytes_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """摘要校验能发现内容变化，不能默默展示过期评估。"""
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": {"x.csv": hashlib.sha256(b"original").hexdigest()}})
    )
    (tmp_path / "figure_sources.json").write_text(
        json.dumps({"benchmark_summary_sha256": "unused", "figure_sha256": {}})
    )
    (tmp_path / "delivery_check.json").write_text('{"files": {}}')
    (tmp_path / "x.csv").write_text("changed")
    monkeypatch.setattr(module, "DIRECTORY", tmp_path)
    with pytest.raises(ValueError, match="指纹"):
        module.verified_bytes("x.csv")


def test_evaluation_controls_match_archived_results() -> None:
    """模型、错误类型和批大小切换后保持与存档数值一致。"""
    app = AppTest.from_string(
        "from douyin_analysis.dashboard_evaluation import show_evaluation\n"
        + "show_evaluation()",
        default_timeout=30,
    ).run()
    assert not app.exception
    app.selectbox[0].select("hgb_31")
    app.selectbox[1].select("hgb_31")
    app.radio[0].set_value("漏报 FN")
    app.selectbox[2].select(1000).run()
    assert not app.exception
    table = app.dataframe[0].value
    assert table.iloc[-1]["验证 AP"] == pytest.approx(0.03932840231904845)
    assert table["训练候选对"].tolist() == [103088, 309267, 618535, 1030893]
    assert any("FN-1" in value.value for value in app.markdown)
    assert not any("FP-1" in value.value for value in app.markdown)
    assert len(app.get("download_button")) == 5
