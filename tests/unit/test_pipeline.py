"""验证清洗口径、跨行去重和异常输入。"""

from pathlib import Path

import duckdb
import pytest

from douyin_analysis.pipeline import clean_data, file_digest


def test_global_duplicate(tmp_path: Path) -> None:
    """相同四元组只保留一条，即使类目不同。"""
    source = tmp_path / "input.csv"
    source.write_text(
        "\n".join(
            [
                "time,user_id,item_id,item_category,behavior_type",
                "2025-12-01 01,001,2,3,1",
                "2025-12-02 01,001,2,3,4",
                "2025-12-01 01,001,2,9,1",
            ]
        ),
        encoding="utf-8",
    )
    with duckdb.connect() as connection:
        result = clean_data(connection, source)
        assert result["clean_rows"] == 2
        assert result["duplicate_rows"] == 1
        assert result["items_with_multiple_categories"] == 1
        assert connection.table("events").limit(1).fetchall()[0][0] == "001"


def test_invalid_records(tmp_path: Path) -> None:
    """无效时间、缺失 ID 和未知行为不进入标准化表。"""
    source = tmp_path / "input.csv"
    source.write_text(
        "\n".join(
            [
                "time,user_id,item_id,item_category,behavior_type",
                "2025-12-01 01,1,2,3,1",
                "invalid,1,2,3,1",
                "2025-12-01 01,,2,3,1",
                "2025-12-01 01,1,2,3,9",
            ]
        ),
        encoding="utf-8",
    )
    with duckdb.connect() as connection:
        result = clean_data(connection, source)
        assert result["invalid_rows"] == 3


def test_schema_error(tmp_path: Path) -> None:
    """错误输入字段必须显式失败。"""
    source = tmp_path / "input.csv"
    source.write_text("wrong\n1\n", encoding="utf-8")
    with duckdb.connect() as connection:
        with pytest.raises(ValueError, match="CSV 字段"):
            clean_data(connection, source)


def test_file_digest(tmp_path: Path) -> None:
    """输入改变应改变来源指纹。"""
    source = tmp_path / "input.csv"
    source.write_text("first", encoding="utf-8")
    original = file_digest(source)
    source.write_text("second", encoding="utf-8")
    assert file_digest(source) != original
