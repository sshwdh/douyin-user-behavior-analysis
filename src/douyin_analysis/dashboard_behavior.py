"""行为看板：日期和行为联动的趋势、热力图、类目与全期用户分布。"""

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_aggregates import (
    category_counts,
    filter_events,
    load_aggregate,
    weekday_heatmap,
)
from douyin_analysis.dashboard_data import overview

BEHAVIORS = {
    "全部行为": 0,
    "行为码 1（暂释浏览）": 1,
    "行为码 2（暂释收藏）": 2,
    "行为码 3（暂释加购）": 3,
    "行为码 4（暂释购买）": 4,
}
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def show_time_patterns(frame: pd.DataFrame, start: date, end: date) -> None:
    """按相同筛选范围绘制每日趋势与星期小时日均热力图。

    Args:
        frame: 已筛选的小时行为聚合。
        start: 所选首日。
        end: 所选末日。
    """
    st.subheader("每日行为趋势")
    times = pd.to_datetime(frame.event_time)
    daily = frame.assign(day=times.dt.normalize()).groupby("day").events.sum()
    daily = daily.reindex(pd.date_range(start, end), fill_value=0)
    st.line_chart(daily.rename("事件数"))
    st.subheader("星期 × 小时热力图")
    heat = weekday_heatmap(frame, start, end)
    heat["星期"] = heat.weekday.map(dict(enumerate(WEEKDAYS)))
    chart = (
        alt.Chart(heat)
        .mark_rect()
        .encode(
            x=alt.X("hour:O", title="小时"),
            y=alt.Y("星期:N", sort=WEEKDAYS),
            color=alt.Color(
                "mean_events:Q", title="日均事件数", scale=alt.Scale(scheme="blues")
            ),
            tooltip=[
                alt.Tooltip("星期:N"),
                alt.Tooltip("hour:O", title="小时"),
                alt.Tooltip("days:Q", title="区间内该星期天数"),
                alt.Tooltip("events:Q", title="事件总数", format=","),
                alt.Tooltip("mean_events:Q", title="日均事件数", format=",.1f"),
            ],
        )
        .properties(height=260)
    )
    st.altair_chart(chart)
    st.caption(
        "每格=该星期该小时事件数÷所选区间内该星期的天数。未包含的星期留空；保留小时内重复行为。"
    )


def show_categories(frame: pd.DataFrame) -> None:
    """展示当前日期和行为范围内的类目排行与完整累计分布。

    Args:
        frame: 日类目行为筛选结果，只有事件计数。
    """
    st.subheader("类目交互排行与长尾")
    counts = category_counts(frame)
    count = st.slider("展示类目数量", 5, 30, 20)
    top = counts.head(count).copy()
    top["类目"] = top.category_id.astype(str)
    chart = (
        alt.Chart(top)
        .mark_bar(color="#287f94")
        .encode(
            x=alt.X("events:Q", title="事件数"),
            y=alt.Y("类目:N", sort="-x"),
            tooltip=["类目:N", alt.Tooltip("events:Q", title="事件数", format=",")],
        )
        .properties(height=max(180, count * 23))
    )
    st.altair_chart(chart)
    top_share = top.events.sum() / counts.events.sum()
    st.caption(
        f"当前范围共 {len(counts):,} 个有交互类目；前 {len(top)} 类目占比 {top_share:.2%}。"
    )
    # 大类目表仅绘制最多500个秩点，保留两端；占比使用完整累计序列。
    step = max(1, len(counts) // 499)
    curve = pd.concat([counts.iloc[::step], counts.tail(1)]).drop_duplicates("rank")
    st.altair_chart(
        alt.Chart(curve)
        .mark_line()
        .encode(
            x=alt.X("rank:Q", title="类目排名（按事件数）"),
            y=alt.Y(
                "cumulative_share:Q", title="累计事件占比", axis=alt.Axis(format="%")
            ),
            tooltip=[
                alt.Tooltip("rank:Q", title="类目排名"),
                alt.Tooltip("cumulative_share:Q", title="累计占比", format=".2%"),
            ],
        )
        .properties(height=220)
    )
    st.caption("累计占比基于全部类目，曲线最多约500个展示点；不代表曝光或收入份额。")
    st.download_button(
        "下载当前类目汇总",
        counts.to_csv(index=False).encode("utf-8-sig"),
        "category_summary.csv",
        "text/csv",
    )


def show_daily_users(start: date, end: date, behavior: int) -> None:
    """展示所选行为的逐日去重人数，不加总为区间人数。

    Args:
        start: 所选首日。
        end: 所选末日。
        behavior: 0代表全行为，否则为指定行为码。
    """
    st.subheader("每日交互用户数")
    users = load_aggregate("daily_users")
    users = users.loc[users.behavior_type == behavior]
    selected = filter_events(users, start, end, 0)
    st.line_chart(
        selected.set_index("day")[["users"]].rename(columns={"users": "当日去重用户数"})
    )
    st.caption(
        "随日期和行为筛选；同一天同一用户只计一次，各天人数不可相加作为区间去重人数。"
    )


def show_activity(behavior: int) -> None:
    """展示所选行为的全期用户频次分布，明确不受日期筛选影响。

    Args:
        behavior: 0代表全行为，否则为指定行为码。
    """
    st.subheader("全观察期用户交互频次")
    st.caption(
        "本节固定为2025/11/18—12/18，仅随行为选择变化。日期范围不影响本节；人数不按日期累加。"
    )
    activity = load_aggregate("user_activity")
    selected = activity.loc[activity.behavior_type == behavior].copy()
    selected["频次区间"] = selected.activity.str.split(": ").str[-1]
    st.bar_chart(
        selected.set_index("频次区间")[["users"]].rename(columns={"users": "用户数"})
    )
    st.caption(
        f"该行为全期去重用户：{int(selected.users.sum()):,}。零次交互用户不在分布内。"
    )


def render_behavior() -> None:
    """展示版本一致的概况和行为分析区，缺失范围不绘制伪零值。"""
    st.title("用户行为与特征")
    quality = overview()
    start = date.fromisoformat(str(quality["start"])[:10])
    end = date.fromisoformat(str(quality["end"])[:10])
    st.caption(f"全观察期：{start} 至 {end}，原始时间未转换时区。")
    for column, label, key in zip(
        st.columns(4),
        ["有效事件", "用户", "商品", "类目"],
        ["clean_rows", "users", "items", "categories"],
    ):
        column.metric(label, f"{int(quality[key]):,}")
    st.caption("以上为全观察期概况。下面日期与行为联动影响趋势、热力图和类目分析。")
    selected = st.date_input(
        "分析日期范围", value=(start, end), min_value=start, max_value=end
    )
    selected_behavior = st.selectbox("分析行为", list(BEHAVIORS))
    if (
        selected_behavior is None
        or not isinstance(selected, tuple)
        or len(selected) != 2
    ):
        st.info("请选择完整日期范围与行为。")
        return
    behavior = BEHAVIORS[selected_behavior]
    hours = filter_events(load_aggregate("hourly_behavior"), *selected, behavior)
    categories = filter_events(load_aggregate("daily_categories"), *selected, behavior)
    if int(hours.events.sum()) != int(categories.events.sum()):
        raise ValueError("当前筛选范围的小时与类目事件数不一致")
    st.metric("当前筛选事件数", f"{int(hours.events.sum()):,}")
    if hours.empty:
        st.info("该范围未观察到所选行为，不生成转化率。")
    else:
        show_time_patterns(hours, *selected)
        show_daily_users(*selected, behavior)
        show_categories(categories)
    show_activity(behavior)
