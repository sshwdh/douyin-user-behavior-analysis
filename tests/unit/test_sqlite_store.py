"""验证 SQLite 批次导入、外键与只读查询接口。"""

from pathlib import Path

import pandas as pd

from douyin_analysis.sqlite_store import build_database, query_frame


def test_import_and_query(tmp_path: Path) -> None:
    """含前导零的 ID 经导入和参数化查询后仍保持不变。"""
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    frame = pd.DataFrame(
        {
            "user_id": ["001"],
            "item_id": ["002"],
            "category_id": ["003"],
            "behavior_type": [1],
            "event_time": pd.to_datetime(["2025-11-18"]),
        }
    )
    frame.to_parquet(tmp_path / "data/processed/events.parquet", index=False)
    build_database(tmp_path)
    result = query_frame(
        tmp_path / "data/behavior.sqlite",
        "SELECT user_id FROM events WHERE item_id=?",
        ("002",),
    )
    assert result.iloc[0]["user_id"] == "001"
