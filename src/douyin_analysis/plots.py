"""将聚合表绘制为八类可复现图表。"""

import argparse
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import pandas as pd


def render(root: Path) -> None:
    """保存八张 PNG 及总览图，不展示原始用户标识。

    Args:
        root: 含 reports 目录的项目根目录。
    """
    plt.switch_backend("Agg")
    specifications: list[tuple[str, str, str, str, Literal["bar", "line"]]] = [
        ("behavior", "behavior_type", "events", "Events by behavior", "bar"),
        ("daily", "day", "dau", "Daily active users", "line"),
        ("daily", "day", "buyers", "Daily purchasing users", "line"),
        ("hourly", "hour", "events", "Events by hour", "bar"),
        ("categories", "category_id", "buyers", "Top 10 categories by buyers", "bar"),
        ("weekday", "weekday", "per_day", "Mean daily events by weekday", "bar"),
        ("activity", "activity", "users", "Users by event frequency", "bar"),
        ("repeat", "frequency", "users", "Purchase-event frequency", "bar"),
    ]
    overview, axes = plt.subplots(4, 2, figsize=(16, 20))
    for index, (name, horizontal, vertical, title, kind) in enumerate(specifications):
        frame = pd.read_csv(root / f"reports/{name}.csv")
        if name == "categories":
            frame = frame.nlargest(10, "buyers")
        if name == "weekday":
            frame["per_day"] = frame["events"] / frame["days"]
        if name == "behavior":
            frame[horizontal] = frame[horizontal].map(
                {1: "pv", 2: "fav", 3: "cart", 4: "buy"}
            )
        figure, axis = plt.subplots(figsize=(11, 6))
        for target in [axis, axes.flat[index]]:
            frame.plot(
                x=horizontal,
                y=vertical,
                kind=kind,
                ax=target,
                legend=False,
                color="#287f94",
                title=title,
                rot=40,
            )
            target.set_ylabel(vertical)
            target.grid(axis="y", alpha=0.2)
        figure.tight_layout()
        figure.savefig(root / f"reports/figures/{index + 1:02d}_{name}.png", dpi=150)
        plt.close(figure)
    overview.suptitle("Behavior analysis | cleaned data | 2025-11-18 to 2025-12-18")
    overview.tight_layout(rect=(0, 0, 1, 0.98))
    overview.savefig(root / "reports/figures/overview.png", dpi=120)
    plt.close(overview)


def main() -> None:
    """读取项目路径并绘图。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    render(parser.parse_args().root)


if __name__ == "__main__":
    main()
