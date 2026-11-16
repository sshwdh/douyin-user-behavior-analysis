"""核验小时空白检测与数据快照版本边界。"""

from datetime import datetime

import pytest

from douyin_analysis.data_audit import hour_coverage, snapshot_id


def test_internal_missing_hour() -> None:
    """首尾齐全不能掩盖中间小时缺失，重复时点不增加覆盖。"""
    start = datetime(2025, 11, 18)
    end = datetime(2025, 11, 18, 2)
    result = hour_coverage([start, start, end])
    assert result["expected_hours"] == 3
    assert result["observed_hours"] == 2
    assert result["missing_hours"] == ["2025-11-18T01:00:00"]
    assert result["collection_completeness"] == "unconfirmed"


def test_empty_coverage() -> None:
    """空数据不能得到覆盖成功的结论。"""
    with pytest.raises(ValueError, match="没有"):
        hour_coverage([])


def test_snapshot_tracks_source_rule_and_output() -> None:
    """任何数据或规则变化都产生新快照，字典顺序不影响标识。"""
    rule = {"threshold": 100, "scope": "user_behavior_hour"}
    original = snapshot_id("source", rule, "output")
    assert original == snapshot_id(
        "source", dict(reversed(list(rule.items()))), "output"
    )
    assert original != snapshot_id("changed", rule, "output")
    assert original != snapshot_id("source", {**rule, "threshold": 101}, "output")
    assert original != snapshot_id("source", rule, "changed")
