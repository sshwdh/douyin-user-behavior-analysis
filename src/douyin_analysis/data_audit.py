"""核验数据覆盖、筛查影响与产物指纹，记录可追溯的暂行数据快照。"""

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from douyin_analysis.pipeline import file_digest


def hour_coverage(hours: list[datetime]) -> dict:
    """检查观察范围内是否存在整小时空白，不推断采集完整性。

    Args:
        hours: 已观察到的小时，可包含重复值。

    Returns:
        观察边界、应有和实际小时数及缺失小时列表。

    Raises:
        ValueError: 未提供任何小时。
    """
    observed = set(hours)
    if not observed:
        raise ValueError("没有可核验的小时")
    start, end = min(observed), max(observed)
    expected = int((end - start).total_seconds() // 3600) + 1
    missing = [
        (start + timedelta(hours=index)).isoformat()
        for index in range(expected)
        if start + timedelta(hours=index) not in observed
    ]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "expected_hours": expected,
        "observed_hours": len(observed),
        "missing_hours": missing,
        "collection_completeness": "unconfirmed",
        "timezone": "unconfirmed; original naive timestamps preserved",
    }


def snapshot_id(source_digest: str, rule: dict, output_digest: str) -> str:
    """用数据来源、规则和产物内容生成快照标识。

    Args:
        source_digest: 原始文件 SHA256。
        rule: 影响清洗结果的规则定义。
        output_digest: 事件 Parquet SHA256。

    Returns:
        带固定前缀的快照标识，不代表业务审批。
    """
    payload = json.dumps(
        [source_digest, rule, output_digest], sort_keys=True, ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"provisional-{digest[:16]}"


def audit(
    root: Path, source: Path, audit_date: date, scope_confirmed: bool = False
) -> dict:
    """核验当前数据并导出日汇总及暂行快照，不修改清洗产物。

    Args:
        root: 项目目录。
        source: 原始 CSV 路径。
        audit_date: 核验日期，用于独立保存记录。
        scope_confirmed: 是否已有该分组范围的业务确认，不代表其他语义已确认。

    Returns:
        带覆盖检查、指纹和业务确认状态的清单。

    Raises:
        ValueError: 来源指纹、行数或隔离分区与记录不一致。
    """
    quality = json.loads((root / "reports/quality.json").read_text(encoding="utf-8"))
    source_digest = file_digest(source)
    if source_digest != quality["source_sha256"]:
        raise ValueError("原始 CSV 指纹已变化，须重新生成清洗产物")
    output = root / "reports/audits" / audit_date.isoformat()
    output.mkdir(parents=True, exist_ok=True)
    rule = {
        name: quality[name]
        for name in ["rule_version", "threshold", "frequency_scope", "action"]
    }
    rule["normal_repetitions"] = "preserve_all"
    rule["threshold_boundary"] = "strictly_greater_than"
    with duckdb.connect(str(root / "data/work.duckdb"), read_only=True) as connection:
        connection.execute("SET memory_limit='2GB'")
        connection.execute("SET threads=4")
        hours = connection.execute(
            "SELECT DISTINCT event_time FROM valid ORDER BY event_time"
        ).fetchall()
        coverage = hour_coverage([row[0] for row in hours])
        difference = connection.execute(
            """WITH stored_events AS (SELECT * FROM read_parquet(?)),
            recomputed AS (
                SELECT *,count(*) OVER (
                    PARTITION BY user_id,behavior,event_time,
                    CASE WHEN ?='user_item_behavior_hour' THEN item_id ELSE '' END
                ) AS group_count FROM valid
            ), expected AS (
                SELECT user_id,item_id,item_category AS category_id,
                       behavior AS behavior_type,event_time FROM recomputed
                WHERE group_count<=?
            ), difference AS (
                (SELECT * FROM expected EXCEPT ALL SELECT * FROM stored_events)
                UNION ALL
                (SELECT * FROM stored_events EXCEPT ALL SELECT * FROM expected)
            ) SELECT count(*) FROM difference""",
            [
                str(root / "data/processed/events.parquet"),
                quality["frequency_scope"],
                quality["threshold"],
            ],
        ).fetchall()[0][0]
        if difference:
            raise ValueError("Parquet 与频次规则的记录及重复次数不一致")
        quarantine_count, invalid_quarantine = connection.execute(
            """SELECT count(*),count(*) FILTER (WHERE group_count<=?)
            FROM read_parquet(?)""",
            [quality["threshold"], str(root / "data/processed/quarantined.parquet")],
        ).fetchall()[0]
        if quarantine_count != quality["quarantined_rows"] or invalid_quarantine:
            raise ValueError("隔离产物行数或阈值边界不一致")
        daily = connection.sql("""WITH before AS (
            SELECT CAST(event_time AS DATE) AS day,count(*) AS valid_events,
                count(DISTINCT user_id) AS valid_users,
                count(DISTINCT CASE WHEN behavior=4 THEN user_id END) AS valid_buyers,
                count(DISTINCT event_time) AS observed_hours
            FROM valid GROUP BY 1
        ), after AS (
            SELECT CAST(event_time AS DATE) AS day,count(*) AS retained_events,
                count(DISTINCT user_id) AS retained_users,
                count(DISTINCT CASE WHEN behavior_type=4 THEN user_id END)
                    AS retained_buyers
            FROM events GROUP BY 1
        ) SELECT before.*,coalesce(retained_events,0) AS retained_events,
            coalesce(retained_users,0) AS retained_users,
            coalesce(retained_buyers,0) AS retained_buyers,
            valid_events-coalesce(retained_events,0) AS quarantined_events,
            1.0*(valid_events-coalesce(retained_events,0))/valid_events
                AS quarantined_share
            FROM before LEFT JOIN after USING(day) ORDER BY day""").df()
        daily.to_csv(output / "daily_filter_impact.csv", index=False)
        behavior = connection.sql("""SELECT behavior,count(*) AS events
            FROM valid GROUP BY behavior ORDER BY behavior""").df()
        behavior.to_csv(output / "observed_behavior_codes.csv", index=False)
    artifacts = {}
    for relative in [
        "data/processed/events.parquet",
        "data/processed/quarantined.parquet",
        "reports/quality.json",
    ]:
        path = root / relative
        artifacts[relative] = {
            "sha256": file_digest(path),
            "bytes": path.stat().st_size,
        }
    result = {
        "snapshot_id": snapshot_id(
            source_digest,
            rule,
            str(artifacts["data/processed/events.parquet"]["sha256"]),
        ),
        "audit_date": audit_date.isoformat(),
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "provisional_not_business_approved",
        "source_sha256": source_digest,
        "rule": rule,
        "artifacts": artifacts,
        "coverage": coverage,
        "parquet_multiset_matches_rule": True,
        "quarantine_count_matches": True,
        "semantic_confirmations": {
            "frequency_scope": "confirmed" if scope_confirmed else "pending",
            "whole_group_quarantine": "pending",
            "behavior_code_meanings": "pending",
            "timezone": "pending",
            "sampling_and_collection": "pending",
        },
    }
    (output / "data_snapshot.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def plot_daily_impact(output: Path) -> None:
    """绘制逐日筛查影响图。

    Args:
        output: 已生成 daily_filter_impact.csv 的审计目录。
    """
    plt.switch_backend("Agg")
    frame = pd.read_csv(output / "daily_filter_impact.csv", parse_dates=["day"])
    figure, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(frame["day"], frame["valid_events"], label="Before filtering")
    axes[0].plot(frame["day"], frame["retained_events"], label="Retained")
    axes[0].set_ylabel("Events")
    axes[0].legend()
    axes[1].bar(frame["day"], frame["quarantined_share"] * 100, color="#287f94")
    axes[1].set_ylabel("Quarantined (%)")
    axes[1].set_xlabel("Date in source data (timezone unconfirmed)")
    for axis in axes:
        axis.grid(axis="y", alpha=0.2)
    manifest = json.loads((output / "data_snapshot.json").read_text(encoding="utf-8"))
    rule = manifest["rule"]
    scope = rule["frequency_scope"].replace("_", " + ")
    figure.suptitle(f"Frequency check: {scope}; count > {rule['threshold']}")
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(output / "daily_filter_impact.png", dpi=150)
    plt.close(figure)


def main() -> None:
    """解析原始路径与核验日期，生成独立核验快照。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--scope-confirmed", action="store_true")
    args = parser.parse_args()
    result = audit(args.root, args.input, args.date, args.scope_confirmed)
    plot_daily_impact(args.root / "reports/audits" / args.date.isoformat())
    print(result["snapshot_id"])


if __name__ == "__main__":
    main()
