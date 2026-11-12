"""独立核对原始计数、清洗守恒、Parquet 和 SQLite 聚合结果。"""

import json
import sqlite3
from pathlib import Path

import pandas as pd
from pyarrow import parquet


def validate(root: Path) -> dict[str, bool]:
    """执行跨存储格式的一致性核验。

    Args:
        root: 项目根目录。

    Returns:
        每个核验项目的成功标记；失败直接抛出异常。
    """
    quality = json.loads((root / "reports/quality.json").read_text(encoding="utf-8"))
    raw = json.loads((root / "reports/raw_profile.json").read_text(encoding="utf-8"))
    assert raw["rows"] == quality["raw_rows"]
    assert quality["raw_rows"] == sum(
        quality[name] for name in ["invalid_rows", "duplicate_rows", "clean_rows"]
    )
    source = parquet.ParquetFile(root / "data/processed/events.parquet")
    assert source.metadata.num_rows == quality["clean_rows"]
    with sqlite3.connect(root / "data/behavior.sqlite") as connection:
        actual = pd.read_sql_query(
            """SELECT behavior_type,COUNT(*) AS events,
            COUNT(DISTINCT user_id) AS users FROM events
            GROUP BY behavior_type ORDER BY behavior_type""",
            connection,
        )
        expected = pd.read_csv(root / "reports/behavior.csv")
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        columns = connection.execute("PRAGMA table_info(events)").fetchall()
        assert "category_id" not in {column[1] for column in columns}
    return {
        "independent_raw_count": True,
        "row_conservation": True,
        "parquet_count": True,
        "sqlite_behavior_aggregation": True,
        "foreign_keys": True,
        "normalized_item_category": True,
    }


def main() -> None:
    """核对当前目录中的运行产物并保存结果。"""
    root = Path.cwd()
    result = validate(root)
    (root / "reports/output_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print("Cross-format validation passed.")


if __name__ == "__main__":
    main()
