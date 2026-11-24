"""双看板的统一视觉样式与可核对的补充图表。"""

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_theme import polish

PALETTE = ["#147D92", "#E5A24A", "#7867B5", "#D76B78"]


def show_behavior_mix(frame: pd.DataFrame) -> None:
    """展示所选日期内四类行为的结构，独立于单行为筛选。

    Args:
        frame: 所选日期范围内包含全部行为的小时聚合。
    """
    st.subheader("行为结构 · 所选日期")
    counts = frame.groupby("behavior_type")[["events"]].sum().reset_index()
    counts["行为"] = "行为码 " + counts.behavior_type.astype(str)
    total = counts.events.sum()
    counts["占比"] = counts.events / total if total else 0.0
    left, right = st.columns([1, 1.4])
    chart = (
        alt.Chart(counts)
        .mark_arc(innerRadius=70, outerRadius=110)
        .encode(
            theta=alt.Theta("events:Q"),
            color=alt.Color("行为:N", scale=alt.Scale(range=PALETTE)),
            tooltip=[
                "行为:N",
                alt.Tooltip("events:Q", title="事件数", format=","),
                alt.Tooltip("占比:Q", format=".2%"),
            ],
        )
        .properties(height=270)
    )
    left.altair_chart(polish(chart))
    table = counts[["行为", "events", "占比"]].rename(columns={"events": "事件数"})
    right.dataframe(
        table,
        hide_index=True,
        column_config={"占比": st.column_config.NumberColumn(format="percent")},
    )
    right.caption(
        "四类行为完整展示，仅随日期变化。事件占比不是转化率；重复交互全部保留。"
    )


def show_hour_profile(frame: pd.DataFrame, days: int) -> None:
    """展示当前筛选范围的小时日均强度与峰值。

    Args:
        frame: 日期和行为筛选后的小时聚合。
        days: 日期范围包含的自然日数。
    """
    st.subheader("一天中的交互节律")
    hours = pd.to_datetime(frame.event_time).dt.hour
    totals = frame.assign(hour=hours).groupby("hour").events.sum()
    table = totals.reindex(range(24), fill_value=0).rename("事件数").reset_index()
    table["日均事件数"] = table["事件数"] / days
    chart = (
        alt.Chart(table)
        .mark_bar(color=PALETTE[0], cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("hour:O", title="原始时间小时"),
            y=alt.Y("日均事件数:Q"),
            tooltip=[
                alt.Tooltip("hour:O", title="小时"),
                alt.Tooltip("日均事件数:Q", format=",.1f"),
                alt.Tooltip("事件数:Q", format=","),
            ],
        )
        .properties(height=240)
    )
    st.altair_chart(polish(chart))
    peak = table.loc[table["事件数"].idxmax()]
    st.caption(
        f"当前筛选下峰值小时为 {int(peak['hour']):02d}:00，"
        + f"日均 {peak['日均事件数']:,.1f} 次；以所选 {days} 个自然日为分母。"
        + "若并列仅展示最早小时；时区尚未确认。"
    )


def show_precision_recall(metrics: pd.DataFrame) -> None:
    """以固定阈值散点展示精确率与召回率取舍，不伪造连续曲线。

    Args:
        metrics: 各模型已存档的验证指标。
    """
    st.subheader("精确率与召回率取舍")
    table = metrics.rename_axis("模型").reset_index()
    chart = (
        alt.Chart(table)
        .mark_circle(size=180, opacity=0.85)
        .encode(
            x=alt.X("recall:Q", title="候选内召回率", axis=alt.Axis(format=".0%")),
            y=alt.Y("precision:Q", title="精确率", axis=alt.Axis(format=".0%")),
            color=alt.Color("模型:N", scale=alt.Scale(scheme="tableau10")),
            tooltip=[
                "模型:N",
                alt.Tooltip("precision:Q", title="精确率", format=".2%"),
                alt.Tooltip("recall:Q", title="召回率", format=".2%"),
                alt.Tooltip("true_positive:Q", title="命中对数", format=","),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(polish(chart))
    st.caption(
        "每个点使用该模型各自已存档的验证 F1 阈值，预测数量不同；公平预算对照见下方。"
    )
