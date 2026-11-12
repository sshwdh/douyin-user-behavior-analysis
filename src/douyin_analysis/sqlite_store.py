"""按批次导入 Parquet，构建 SQLite 维表与行为事实表。"""

import argparse
import sqlite3
from pathlib import Path

import pandas as pd
from pyarrow import parquet


def build_database(root: Path) -> None:
    """从清洗后的数据构建可查询的本地 SQLite 数据库。

    验证商品到类目唯一映射后，将类目放入商品维表。

    Args:
        root: 项目根目录。
    """
    source = parquet.ParquetFile(root / "data/processed/events.parquet")
    with sqlite3.connect(root / "data/behavior.sqlite") as connection:
        connection.executescript("""
            DROP TABLE IF EXISTS events;
            DROP TABLE IF EXISTS users;
            DROP TABLE IF EXISTS items;
            DROP TABLE IF EXISTS times;
            DROP TABLE IF EXISTS categories;
            CREATE TABLE users (user_id TEXT PRIMARY KEY);
            CREATE TABLE categories (category_id TEXT PRIMARY KEY);
            CREATE TABLE items (
                item_id TEXT PRIMARY KEY,
                category_id TEXT REFERENCES categories(category_id)
            );
            CREATE TABLE times (
                event_time TEXT PRIMARY KEY, day TEXT NOT NULL, hour INTEGER NOT NULL
            );
            CREATE TABLE events (
                user_id TEXT REFERENCES users(user_id),
                item_id TEXT REFERENCES items(item_id),
                category_id TEXT REFERENCES categories(category_id),
                behavior_type INTEGER CHECK(behavior_type BETWEEN 1 AND 4),
                event_time TEXT REFERENCES times(event_time)
            );
            """)
        for batch in source.iter_batches(batch_size=100_000):
            frame = batch.to_pandas()
            frame["event_time"] = frame["event_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
            connection.executemany(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                frame.itertuples(index=False, name=None),
            )
        conflicts = connection.execute("""SELECT item_id FROM events GROUP BY item_id
            HAVING COUNT(DISTINCT category_id)>1 LIMIT 1""").fetchone()
        if conflicts:
            raise ValueError("商品存在多个类目，需使用版本维表，不能直接构造该商品维表")
        connection.executescript("""
            INSERT INTO users SELECT DISTINCT user_id FROM events;
            INSERT INTO categories SELECT DISTINCT category_id FROM events;
            INSERT INTO items SELECT DISTINCT item_id,category_id FROM events;
            ALTER TABLE events DROP COLUMN category_id;
            INSERT INTO times SELECT DISTINCT event_time,substr(event_time,1,10),
                CAST(substr(event_time,12,2) AS INTEGER) FROM events;
            CREATE UNIQUE INDEX idx_event_key
                ON events(user_id,item_id,behavior_type,event_time);
            CREATE INDEX idx_event_time ON events(event_time);
            CREATE INDEX idx_item_behavior ON events(item_id,behavior_type);
            """)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"SQLite 外键校验失败：{violations[:5]}")
        rows = connection.execute("SELECT count(*) FROM events").fetchone()[0]
        if rows != source.metadata.num_rows:
            raise ValueError("SQLite 导入行数与 Parquet 不一致")
        (root / "reports/sqlite_check.txt").write_text(
            f"Imported rows: {rows}\nForeign key violations: 0\n",
            encoding="utf-8",
        )


def query_frame(database: Path, query: str, parameters: tuple = ()) -> pd.DataFrame:
    """通过只读连接执行参数化查询。

    Args:
        database: 本地 SQLite 文件。
        query: 受信任的查询 SQL，动态值必须用占位符。
        parameters: 占位符绑定参数。

    Returns:
        查询结果数据框。
    """
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return pd.read_sql_query(query, connection, params=parameters)


def main() -> None:
    """解析路径并导入。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    build_database(parser.parse_args().root)


if __name__ == "__main__":
    main()
