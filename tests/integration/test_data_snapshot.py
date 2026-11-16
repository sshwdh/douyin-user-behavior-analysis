"""用合成重复事件核验数据快照及来源变化拒绝逻辑。"""

from datetime import date
from pathlib import Path

import pytest
from pyarrow import parquet

from douyin_analysis.data_audit import audit
from douyin_analysis.pipeline import run


@pytest.mark.parametrize("tamper", ["source", "parquet"])
def test_audit_detects_changed_data(
    tmp_path: Path,
    tamper: str,
) -> None:
    """快照检查通过后，来源变化或重复记录丢失都必须被识别。"""
    source = tmp_path / "input.csv"
    source.write_text(
        "\n".join(
            ["time,user_id,item_id,item_category,behavior_type"]
            + ["2025-11-18 00,1,2,3,1"] * 2
            + ["2025-11-18 02,2,2,3,1"] * 101
        ),
        encoding="utf-8",
    )
    run(source, tmp_path)
    result = audit(tmp_path, source, date(2026, 11, 16))
    assert result["parquet_multiset_matches_rule"]
    assert result["coverage"]["missing_hours"] == ["2025-11-18T01:00:00"]
    assert result["status"] == "provisional_not_business_approved"
    if tamper == "source":
        source.write_text(source.read_text() + "\n2025-11-18 03,3,2,3,4")
        message = "指纹已变化"
    else:
        events = tmp_path / "data/processed/events.parquet"
        table = parquet.read_table(events)
        parquet.write_table(table.slice(0, 1), events)
        message = "记录及重复次数不一致"
    with pytest.raises(ValueError, match=message):
        audit(tmp_path, source, date(2026, 11, 16))
