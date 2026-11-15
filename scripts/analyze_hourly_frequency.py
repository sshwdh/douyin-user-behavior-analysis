"""对比两种小时频次分组与多个阈值，仅导出汇总统计。"""

from pathlib import Path

import duckdb


def analyze(root: Path) -> None:
    """读取有效记录，输出分布与整组隔离的敏感性结果。

    Args:
        root: 含工作数据库的项目目录。
    """
    with duckdb.connect(str(root / "data/work.duckdb"), read_only=True) as connection:
        connection.execute("""CREATE TEMP TABLE frequency_groups AS
            SELECT 'user_behavior_hour' AS scope, count(*) AS frequency
            FROM valid GROUP BY user_id,behavior,event_time
            UNION ALL
            SELECT 'user_item_behavior_hour' AS scope, count(*) AS frequency
            FROM valid GROUP BY user_id,item_id,behavior,event_time""")
        connection.sql("""SELECT scope, count(*) AS groups,
            max(frequency) AS max_frequency,
            quantile_cont(frequency,0.95) AS p95,
            quantile_cont(frequency,0.99) AS p99,
            quantile_cont(frequency,0.999) AS p999
            FROM frequency_groups GROUP BY scope ORDER BY scope""").df().to_csv(
            root / "reports/hourly_frequency_profile.csv", index=False
        )
        connection.sql("""SELECT scope,threshold,
            count(*) FILTER (WHERE frequency>threshold) AS quarantined_groups,
            coalesce(sum(frequency) FILTER (WHERE frequency>threshold),0)
                AS quarantined_rows,
            sum(frequency) AS valid_rows,
            coalesce(sum(frequency) FILTER (WHERE frequency>threshold),0)
                /sum(frequency) AS quarantined_share
            FROM frequency_groups CROSS JOIN (VALUES (50),(100),(200)) t(threshold)
            GROUP BY scope,threshold ORDER BY scope,threshold""").df().to_csv(
            root / "reports/threshold_sensitivity.csv", index=False
        )


def main() -> None:
    """分析当前项目目录的频次统计。"""
    analyze(Path.cwd())


if __name__ == "__main__":
    main()
