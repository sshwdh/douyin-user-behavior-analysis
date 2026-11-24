"""首次观测队列的自然日回访汇总，明确截尾与观测期边界。"""

import json
from pathlib import Path

import duckdb
import pandas as pd

from douyin_analysis.pipeline import file_digest


def cohort_table(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """从 events 生成首观测日期与 D0-D7 回访，不把未成熟日期填零。

    Args:
        connection: 含 events 视图的连接。

    Returns:
        队列、相隔天数、队列人数、当天回访人数及比率。
    """
    return connection.execute("""WITH days AS (
        SELECT DISTINCT user_id,CAST(event_time AS DATE) AS day FROM events
    ), first_seen AS (
        SELECT user_id,min(day) AS cohort FROM days GROUP BY user_id
    ), sizes AS (
        SELECT cohort,count(*) AS cohort_users FROM first_seen GROUP BY cohort
    ), counts AS (
        SELECT f.cohort,date_diff('day',f.cohort,d.day) AS elapsed,
        count(*) AS returning_users FROM first_seen f JOIN days d USING(user_id)
        WHERE date_diff('day',f.cohort,d.day) BETWEEN 0 AND 7 GROUP BY 1,2
    ), grid AS (
        SELECT s.*,r.range AS elapsed,
        s.cohort + CAST(r.range AS INTEGER) <= (SELECT max(day) FROM days) AS mature
        FROM sizes s CROSS JOIN range(8) r
    ) SELECT g.cohort,g.elapsed,g.cohort_users,g.mature,
        CASE WHEN mature THEN coalesce(c.returning_users,0)
            ELSE NULL END AS returning_users,
        CASE WHEN mature THEN coalesce(c.returning_users,0)::DOUBLE/g.cohort_users
            ELSE NULL END AS return_rate
        FROM grid g LEFT JOIN counts c USING(cohort,elapsed)
        ORDER BY cohort,elapsed""").df()


def run(root: Path) -> None:
    """校验全量事件指纹后导出无用户标识的队列汇总。

    Args:
        root: 项目根目录。
    """
    source = root / "data/processed/events.parquet"
    snapshot = json.loads(
        (root / "reports/audits/2026-11-17/data_snapshot.json").read_text()
    )
    digest = file_digest(source)
    if digest != snapshot["artifacts"]["data/processed/events.parquet"]["sha256"]:
        raise ValueError("事件数据指纹变化")
    with duckdb.connect() as connection:
        connection.execute("SET threads=4")
        connection.from_parquet(str(source)).create_view("events")
        table = cohort_table(connection)
    quality = json.loads((root / "reports/quality.json").read_text())
    if int(table.loc[table.elapsed == 0, "cohort_users"].sum()) != quality["users"]:
        raise ValueError("队列人数与全期用户数不一致")
    output = root / "reports/dashboard/research"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "cohorts.csv"
    table.to_csv(path, index=False)
    (output / "cohorts_manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": digest,
                "sha256": file_digest(path),
                "rows": len(table),
                "definition": "first observed day within sample, not registration day",
                "return": "any observed behavior on exact day D+n; not cumulative",
                "censoring": "immature is null; completeness unconfirmed",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    run(Path.cwd())
