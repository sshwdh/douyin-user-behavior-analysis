"""磁盘支持的全量清洗、Parquet 导出和聚合结果生成。"""

import argparse
import hashlib
import json
import logging
from pathlib import Path

import duckdb

LOGGER = logging.getLogger(__name__)
BEHAVIORS = {1: "pv", 2: "fav", 3: "cart", 4: "buy"}


def file_digest(path: Path) -> str:
    """分块计算来源文件指纹。

    Args:
        path: 输入文件路径。

    Returns:
        SHA256 十六进制摘要。
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_data(connection: duckdb.DuckDBPyConnection, source: Path) -> dict:
    """校验字段并按四元组全局去重；修改连接中的工作表。

    Args:
        connection: 工作数据库连接。
        source: CSV 文件路径。

    Returns:
        原始行数、无效行数、重复行数及类目冲突计数。

    Raises:
        ValueError: 字段不匹配或无有效记录。
    """
    connection.execute(
        "CREATE OR REPLACE TABLE raw AS SELECT * FROM read_csv(?, all_varchar=true)",
        [str(source.resolve())],
    )
    columns = {row[0] for row in connection.execute("DESCRIBE raw").fetchall()}
    required = {"time", "user_id", "item_id", "item_category", "behavior_type"}
    if columns != required:
        raise ValueError(f"CSV 字段应为 {required}，实际为 {columns}")
    connection.execute("""
        CREATE OR REPLACE TABLE parsed AS
        SELECT *, try_strptime(time, '%Y-%m-%d %H') AS event_time,
               try_cast(behavior_type AS INTEGER) AS behavior
        FROM raw
        """)
    valid = """
        event_time IS NOT NULL AND behavior IN (1, 2, 3, 4)
        AND regexp_full_match(user_id, '[0-9]+')
        AND regexp_full_match(item_id, '[0-9]+')
        AND regexp_full_match(item_category, '[0-9]+')
    """
    connection.execute(
        f"CREATE OR REPLACE TABLE valid AS SELECT * FROM parsed WHERE {valid}"
    )
    connection.execute("""
        CREATE OR REPLACE TABLE events AS
        SELECT user_id, item_id, item_category AS category_id,
               behavior AS behavior_type, event_time
        FROM valid
        QUALIFY row_number() OVER (
            PARTITION BY user_id, item_id, behavior, event_time
            ORDER BY item_category
        ) = 1
        """)
    raw_count = connection.execute("SELECT count(*) FROM raw").fetchall()[0][0]
    valid_count = connection.execute("SELECT count(*) FROM valid").fetchall()[0][0]
    clean_count = connection.execute("SELECT count(*) FROM events").fetchall()[0][0]
    conflicts = connection.execute("""
        SELECT count(*) FROM (
            SELECT item_id FROM valid GROUP BY item_id
            HAVING count(DISTINCT item_category) > 1
        )
        """).fetchall()[0][0]
    if not clean_count:
        raise ValueError("没有可分析的有效记录")
    return {
        "raw_rows": raw_count,
        "invalid_rows": raw_count - valid_count,
        "duplicate_rows": valid_count - clean_count,
        "clean_rows": clean_count,
        "items_with_multiple_categories": conflicts,
    }


def export_results(connection: duckdb.DuckDBPyConnection, root: Path) -> None:
    """导出本地数据及可提交的聚合表。

    Args:
        connection: 含 events 表的连接。
        root: 项目根目录。
    """
    data_path = root / "data/processed/events.parquet"
    connection.sql("SELECT * FROM events").write_parquet(str(data_path))
    queries = {
        "dedup_sensitivity": """WITH before AS (
            SELECT behavior AS behavior_type,count(*) AS raw_valid_events
            FROM valid GROUP BY 1), after AS (
            SELECT behavior_type,count(*) AS clean_events FROM events GROUP BY 1)
            SELECT *,raw_valid_events-clean_events AS removed_events,
            1.0*(raw_valid_events-clean_events)/raw_valid_events AS removed_share
            FROM before JOIN after USING(behavior_type) ORDER BY behavior_type""",
        "duplicate_multiplicity": """WITH keys AS (
            SELECT count(*) AS multiplicity FROM valid
            GROUP BY user_id,item_id,behavior,event_time)
            SELECT multiplicity,count(*) AS keys FROM keys GROUP BY 1 ORDER BY 1""",
        "behavior": """SELECT behavior_type, count(*) AS events,
            count(DISTINCT user_id) AS users FROM events
            GROUP BY 1 ORDER BY 1""",
        "daily": """SELECT CAST(event_time AS DATE) AS day, count(*) AS events,
            count(DISTINCT user_id) AS dau,
            count(DISTINCT CASE WHEN behavior_type=4 THEN user_id END) AS buyers
            FROM events GROUP BY 1 ORDER BY 1""",
        "hourly": """SELECT hour(event_time) AS hour, count(*) AS events,
            sum(CASE WHEN behavior_type=4 THEN 1 ELSE 0 END) AS purchases
            FROM events GROUP BY 1 ORDER BY 1""",
        "categories": """SELECT category_id, count(*) AS events,
            count(DISTINCT user_id) AS users,
            count(DISTINCT CASE WHEN behavior_type=4 THEN user_id END) AS buyers
            FROM events GROUP BY 1 ORDER BY events DESC""",
        "weekly": """SELECT date_trunc('week',event_time) AS week,
            count(DISTINCT user_id) AS wau FROM events GROUP BY 1 ORDER BY 1""",
        "weekday": """SELECT isodow(event_time) AS weekday,
            count(*) AS events,
            count(DISTINCT CAST(event_time AS DATE)) AS days
            FROM events GROUP BY 1 ORDER BY 1""",
        "activity": """WITH users AS (
            SELECT user_id, count(*) AS events FROM events GROUP BY 1)
            SELECT CASE WHEN events<10 THEN '01: 1-9'
            WHEN events<50 THEN '02: 10-49' WHEN events<100 THEN '03: 50-99'
            ELSE '04: 100+' END AS activity, count(*) AS users
            FROM users GROUP BY 1 ORDER BY 1""",
        "repeat": """WITH buyers AS (
            SELECT user_id, count(*) AS purchases FROM events
            WHERE behavior_type=4 GROUP BY 1)
            SELECT CASE WHEN purchases=1 THEN 'one purchase event'
            ELSE 'multiple purchase events' END AS frequency, count(*) AS users
            FROM buyers GROUP BY 1 ORDER BY 1""",
        "funnel": """WITH pairs AS (
            SELECT user_id,item_id,
            min(event_time) FILTER (WHERE behavior_type=1) AS first_pv,
            max(event_time) FILTER (WHERE behavior_type=4) AS last_buy
            FROM events GROUP BY 1,2)
            SELECT count(*) FILTER (WHERE first_pv IS NOT NULL) AS viewed_pairs,
            count(*) FILTER (WHERE last_buy>first_pv) AS later_buy_pairs,
            count(*) FILTER (WHERE last_buy=first_pv) AS tied_hour_pairs
            FROM pairs""",
    }
    for name, query in queries.items():
        connection.sql(query).df().to_csv(root / f"reports/{name}.csv", index=False)
    connection.execute("""CREATE OR REPLACE TABLE user_summary AS SELECT user_id,
        count(*) AS events, count(DISTINCT item_id) AS distinct_items,
        count(DISTINCT CAST(event_time AS DATE)) AS active_days,
        max(event_time) AS last_active FROM events GROUP BY 1""")
    connection.execute("""CREATE OR REPLACE TABLE item_summary AS SELECT item_id,
        count(*) AS events, count(DISTINCT user_id) AS users
        FROM events GROUP BY 1""")
    for name in ["user_summary", "item_summary"]:
        connection.table(name).write_parquet(
            str(root / f"data/processed/{name}.parquet")
        )


def run(source: Path, root: Path) -> None:
    """运行全量分析，保存来源指纹及质量报告。

    Args:
        source: 原始 CSV。
        root: 输出项目目录。
    """
    for directory in ["data/processed", "reports", "reports/figures"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(root / "data/work.duckdb")) as connection:
        connection.execute("SET memory_limit='2GB'")
        connection.execute("SET threads=4")
        quality = clean_data(connection, source)
        quality["source_sha256"] = file_digest(source)
        summary = connection.execute(
            """SELECT count(DISTINCT user_id),count(DISTINCT item_id),
            count(DISTINCT category_id),min(event_time),max(event_time) FROM events"""
        ).fetchall()[0]
        quality.update(
            dict(zip(["users", "items", "categories", "start", "end"], summary))
        )
        export_results(connection, root)
    (root / "reports/quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("分析完成：%s", quality)


def main() -> None:
    """解析命令行并执行流水线。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(args.input, args.root.resolve())


if __name__ == "__main__":
    main()
