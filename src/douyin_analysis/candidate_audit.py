"""仅在训练和验证窗口核验历史候选的覆盖范围。"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from douyin_analysis.features import validate_window
from douyin_analysis.pipeline import file_digest


def build_candidates(connection: duckdb.DuckDBPyConnection, cutoff: datetime) -> None:
    """只使用截止时间之前的历史事件生成固定规则候选。

    Args:
        connection: 含 events 视图的连接。
        cutoff: 自然小时边界。
    """
    validate_window(connection, cutoff)
    connection.execute(
        """CREATE OR REPLACE TEMP TABLE history AS SELECT * FROM events
        WHERE event_time>=? AND event_time<?""",
        [cutoff - timedelta(days=7), cutoff],
    )
    connection.execute("""CREATE OR REPLACE TEMP TABLE candidates AS
        WITH base AS (SELECT DISTINCT user_id,item_id FROM history),
        users AS (SELECT DISTINCT user_id FROM history),
        popular AS (
            SELECT item_id,row_number() OVER (
                ORDER BY count(DISTINCT user_id) DESC,item_id) AS ranking
            FROM history GROUP BY item_id
        ), preferences AS (
            SELECT user_id,category_id,row_number() OVER (
                PARTITION BY user_id ORDER BY count(DISTINCT item_id) DESC,
                category_id) AS ranking
            FROM history GROUP BY user_id,category_id
        ), category_popular AS (
            SELECT category_id,item_id,row_number() OVER (
                PARTITION BY category_id ORDER BY count(DISTINCT user_id) DESC,
                item_id) AS ranking
            FROM history GROUP BY category_id,item_id
        )
        SELECT rule,user_id,item_id FROM base CROSS JOIN
            (VALUES ('history_7d'),('global_20'),('global_50'),('category_3x10'))
            AS rules(rule)
        UNION SELECT 'global_20',user_id,item_id FROM users CROSS JOIN popular
            WHERE ranking<=20
        UNION SELECT 'global_50',user_id,item_id FROM users CROSS JOIN popular
            WHERE ranking<=50
        UNION SELECT 'category_3x10',preferences.user_id,category_popular.item_id
            FROM preferences JOIN category_popular USING(category_id)
            WHERE preferences.ranking<=3 AND category_popular.ranking<=10""")


def evaluate_coverage(
    connection: duckdb.DuckDBPyConnection, cutoff: datetime
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """用未来唯一代码 4 用户商品对评价覆盖，并分解未覆盖原因。

    Args:
        connection: 含 history 和 candidates 的连接。
        cutoff: 标签窗口起点。

    Returns:
        各规则覆盖统计与互斥的未来对分组计数。
    """
    connection.execute(
        """CREATE OR REPLACE TEMP TABLE future AS
        SELECT DISTINCT user_id,item_id FROM events
        WHERE event_time>=? AND event_time<? AND behavior_type=4""",
        [cutoff, cutoff + timedelta(days=7)],
    )
    coverage = connection.execute(
        """SELECT rule,count(*) AS candidates,count(future.user_id) AS covered,
        (SELECT count(*) FROM future) AS future_pairs
        FROM candidates LEFT JOIN future USING(user_id,item_id) GROUP BY rule
        ORDER BY rule"""
    ).df()
    strata = connection.execute("""WITH users AS (SELECT DISTINCT user_id FROM history),
        items AS (SELECT DISTINCT item_id FROM history),
        base AS (SELECT user_id,item_id FROM candidates WHERE rule='history_7d')
        SELECT CASE WHEN base.user_id IS NOT NULL THEN 'covered_pair'
            WHEN users.user_id IS NOT NULL AND items.item_id IS NOT NULL
                THEN 'new_pair_known_user_known_item'
            WHEN users.user_id IS NOT NULL THEN 'known_user_unseen_item'
            WHEN items.item_id IS NOT NULL THEN 'unseen_user_known_item'
            ELSE 'unseen_user_unseen_item' END AS stratum,count(*) AS pairs
        FROM future LEFT JOIN base USING(user_id,item_id)
        LEFT JOIN users USING(user_id) LEFT JOIN items USING(item_id)
        GROUP BY stratum ORDER BY stratum""").df()
    baseline = coverage.loc[coverage.rule == "history_7d"].iloc[0]
    coverage["coverage"] = coverage.covered / coverage.future_pairs.replace(
        0, float("nan")
    )
    coverage["extra_candidates"] = coverage.candidates - baseline.candidates
    coverage["extra_covered"] = coverage.covered - baseline.covered
    if int(strata.pairs.sum()) != int(baseline.future_pairs):
        raise ValueError("未来对分组计数不守恒")
    return coverage, strata


def run(root: Path) -> None:
    """验证快照并输出两个开发窗口的汇总；不读取测试样本。

    Args:
        root: 项目根目录。
    """
    manifest = json.loads((root / "reports/features/manifest.json").read_text())
    source = root / "data/processed/events.parquet"
    if file_digest(source) != manifest["events_sha256"]:
        raise ValueError("事件数据指纹不符")
    output = root / "reports/candidates"
    output.mkdir(parents=True, exist_ok=True)
    summaries, groups = [], []
    with duckdb.connect() as connection:
        connection.execute("SET threads=4")
        connection.execute("SET memory_limit='2GB'")
        connection.from_parquet(str(source)).create_view("events")
        for split, day in [("train", "2025-11-25"), ("validation", "2025-12-02")]:
            cutoff = datetime.fromisoformat(day)
            build_candidates(connection, cutoff)
            coverage, strata = evaluate_coverage(connection, cutoff)
            summaries.append(coverage.assign(split=split, cutoff=day))
            groups.append(strata.assign(split=split, cutoff=day))
    combined = pd.concat(summaries, ignore_index=True)
    combined.to_csv(output / "coverage.csv", index=False)
    pd.concat(groups, ignore_index=True).to_csv(output / "strata.csv", index=False)
    plt.switch_backend("Agg")
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    for axis, column in zip(axes, ["coverage", "candidates"]):
        combined.pivot(index="rule", columns="split", values=column).plot.bar(ax=axis)
        axis.set_ylabel(column)
        axis.set_ylim(0, combined[column].max() * 1.3)
        axis.tick_params(axis="x", rotation=25)
    figure.tight_layout()
    figure.savefig(output / "coverage.png", dpi=150)
    plt.close(figure)
    metadata = {
        "data_snapshot_id": manifest["data_snapshot_id"],
        "events_sha256": manifest["events_sha256"],
        "code_sha256": file_digest(Path(__file__)),
        "splits": ["train", "validation"],
        "test_evaluated": False,
        "semantics": manifest["semantic_confirmations"],
        "status": "candidate_diagnostics_only_no_expanded_model",
        "ranking": "historical distinct users; ties by item_id",
        "preferences": "top 3 categories by historical distinct items; "
        + "ties by category_id",
        "rules": ["history_7d", "global_20", "global_50", "category_3x10"],
    }
    (output / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    run(Path.cwd())
