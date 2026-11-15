"""验证清洗口径、跨行去重和异常输入。"""

from pathlib import Path

import duckdb
import pytest

from douyin_analysis.pipeline import clean_data, file_digest


def test_repeated_interactions_preserved(tmp_path: Path) -> None:
    """相同四元组的正常重复记录全部保留，并报告类目冲突。"""
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
        assert result["clean_rows"] == 3
        assert result["deduplicated_rows"] == 0
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


@pytest.mark.parametrize("count", [99, 100, 101])
def test_hourly_threshold(tmp_path: Path, count: int) -> None:
    """等于阈值全部保留，超过阈值隔离整组且不波及其他用户。"""
    source = tmp_path / "input.csv"
    lines = ["time,user_id,item_id,item_category,behavior_type"]
    lines.extend(["2025-12-01 01,001,2,3,1"] * count)
    lines.append("2025-12-01 01,002,2,3,1")
    source.write_text("\n".join(lines), encoding="utf-8")
    with duckdb.connect() as connection:
        result = clean_data(connection, source)
        assert result["clean_rows"] == (count + 1 if count <= 100 else 1)
        assert result["quarantined_rows"] == (count if count > 100 else 0)
        assert result["deduplicated_rows"] == 0


@pytest.mark.parametrize(
    ("scope", "expected"),
    [("user_behavior_hour", 1), ("user_item_behavior_hour", 121)],
)
def test_frequency_scope(tmp_path: Path, scope: str, expected: int) -> None:
    """跨商品累积与按商品分组必须得到不同且明确的结果。"""
    source = tmp_path / "input.csv"
    lines = ["time,user_id,item_id,item_category,behavior_type"]
    lines.extend(["2025-12-01 01,001,2,3,1"] * 60)
    lines.extend(["2025-12-01 01,001,4,3,1"] * 60)
    lines.append("2025-12-01 01,001,2,3,4")
    source.write_text("\n".join(lines), encoding="utf-8")
    with duckdb.connect() as connection:
        result = clean_data(connection, source, scope=scope)
        assert result["clean_rows"] == expected


def test_invalid_threshold(tmp_path: Path) -> None:
    """无效阈值在读取或覆盖工作表之前失败。"""
    with duckdb.connect() as connection:
        with pytest.raises(ValueError, match="正整数"):
            clean_data(connection, tmp_path / "missing.csv", threshold=0)
