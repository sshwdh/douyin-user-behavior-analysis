"""从已核验事件生成公开看板聚合，导出文件不含用户或商品明细。"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from douyin_analysis.pipeline import file_digest


def aggregate_events(connection: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    """聚合 events 视图，分离可加事件计数与不可跨期相加的用户分布。

    Args:
        connection: 包含有效 events 表的只读数据连接。

    Returns:
        小时行为、日类目行为、逐日去重用户和全期用户频次分布。
    """
    hourly = connection.execute("""SELECT event_time,behavior_type,count(*) AS events
        FROM events GROUP BY event_time,behavior_type
        ORDER BY event_time,behavior_type""").df()
    categories = connection.execute(
        """SELECT CAST(event_time AS DATE) AS day,category_id,
        behavior_type,count(*) AS events FROM events
        GROUP BY day,category_id,behavior_type ORDER BY day,category_id,behavior_type"""
    ).df()
    daily_users = connection.execute(
        """SELECT CAST(event_time AS DATE) AS day,behavior_type,
        count(DISTINCT user_id) AS users FROM events GROUP BY day,behavior_type
        UNION ALL
        SELECT CAST(event_time AS DATE) AS day,0 AS behavior_type,
        count(DISTINCT user_id) AS users FROM events GROUP BY day
        ORDER BY day,behavior_type"""
    ).df()
    activity = connection.execute(
        """WITH counts AS (
            SELECT user_id,behavior_type,count(*) AS events FROM events
            GROUP BY user_id,behavior_type
            UNION ALL
            SELECT user_id,0 AS behavior_type,count(*) AS events FROM events
            GROUP BY user_id
        ), bins AS (
            SELECT behavior_type,
                CASE WHEN events<10 THEN '01: 1–9'
                     WHEN events<50 THEN '02: 10–49'
                     WHEN events<100 THEN '03: 50–99'
                     WHEN events<500 THEN '04: 100–499'
                     WHEN events<1000 THEN '05: 500–999'
                     WHEN events<5000 THEN '06: 1000–4999'
                     ELSE '07: 5000+' END AS activity,
                events FROM counts
        ) SELECT behavior_type,activity,count(*) AS users,sum(events) AS events
        FROM bins GROUP BY behavior_type,activity ORDER BY behavior_type,activity"""
    ).df()
    return {
        "hourly_behavior": hourly,
        "daily_categories": categories,
        "user_activity": activity,
        "daily_users": daily_users,
    }


def export_dashboard(root: Path) -> dict:
    """核验源文件指纹、聚合计数后导出四表和版本清单。

    Args:
        root: 项目根目录。

    Returns:
        来源与每张输出表的 SHA256、行数、生成时间。
    """
    source = root / "data/processed/events.parquet"
    snapshot = json.loads(
        (root / "reports/audits/2026-11-17/data_snapshot.json").read_text("utf-8")
    )
    digest = file_digest(source)
    if digest != snapshot["artifacts"]["data/processed/events.parquet"]["sha256"]:
        raise ValueError("事件数据与已核验快照不一致")
    quality = json.loads((root / "reports/quality.json").read_text("utf-8"))
    with duckdb.connect() as connection:
        connection.execute("SET threads=4")
        connection.from_parquet(str(source)).create_view("events")
        frames = aggregate_events(connection)
        total = connection.execute("SELECT count(*) FROM events").fetchone()
    if total is None or total[0] != quality["clean_rows"]:
        raise ValueError("事件行数与清洗报告不一致")
    for name in ["hourly_behavior", "daily_categories"]:
        if int(frames[name].events.sum()) != total[0]:
            raise ValueError(f"{name} 聚合丢失或重复事件")
    all_users = frames["user_activity"].query("behavior_type == 0")
    if int(all_users.users.sum()) != quality["users"]:
        raise ValueError("用户分布与全期去重人数不一致")
    output = root / "reports/dashboard/aggregates"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": snapshot["snapshot_id"],
        "source_sha256": digest,
        "quality_sha256": file_digest(root / "reports/quality.json"),
        "events": total[0],
        "users": quality["users"],
        "start": quality["start"],
        "end": quality["end"],
        "files": {},
    }
    for name, frame in frames.items():
        path = output / f"{name}.csv.gz"
        frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        manifest["files"][name] = {
            "sha256": file_digest(path),
            "rows": len(frame),
            "bytes": path.stat().st_size,
        }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    """从命令行生成看板汇总包，不修改源事件和模型产物。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    print(json.dumps(export_dashboard(parser.parse_args().root), indent=2))


if __name__ == "__main__":
    main()
