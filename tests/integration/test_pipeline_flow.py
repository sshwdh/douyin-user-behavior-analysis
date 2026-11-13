"""以合成数据验证清洗到数据库、绘图与报告的完整流程。"""

from pathlib import Path

import pandas as pd

from douyin_analysis.pipeline import run
from douyin_analysis.plots import render
from douyin_analysis.reporting import create_reports
from douyin_analysis.sqlite_store import build_database, query_frame


def test_pipeline_preserves_published_report(tmp_path: Path) -> None:
    """全流程保留正确计数，报告重建不得覆盖已发布周报。"""
    # Arrange: 合成样本覆盖四类行为、重复记录和多日购买。
    source = tmp_path / "input.csv"
    source.write_text(
        "\n".join(
            [
                "time,user_id,item_id,item_category,behavior_type",
                "2025-11-18 00,001,002,003,1",
                "2025-11-18 00,001,002,003,1",
                "2025-11-18 01,001,002,003,2",
                "2025-11-18 02,001,002,003,3",
                "2025-11-19 03,001,002,003,4",
                "2025-11-20 04,001,002,003,4",
            ]
        ),
        encoding="utf-8",
    )
    weekly = tmp_path / "docs/weekly/2026-11-13_第一周汇报.md"
    weekly.parent.mkdir(parents=True)
    weekly.write_text("已发布的独立周报\n", encoding="utf-8")

    # Act: 运行与 README 相同的主要步骤。
    run(source, tmp_path)
    build_database(tmp_path)
    render(tmp_path)
    create_reports(tmp_path)

    # Assert: 重复折叠、持久化、绘图和报告均可追溯。
    result = query_frame(tmp_path / "data/behavior.sqlite", "SELECT * FROM events")
    assert len(result) == 5
    assert set(result["user_id"]) == {"001"}
    assert pd.read_csv(tmp_path / "reports/behavior.csv")["events"].sum() == 5
    assert len(list((tmp_path / "reports/figures").glob("*.png"))) == 9
    assert "40.00%" in (tmp_path / "reports/analysis_report.md").read_text()
    assert weekly.read_text(encoding="utf-8") == "已发布的独立周报\n"
