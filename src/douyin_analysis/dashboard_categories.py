"""类目交互规模与行为结构，使用事件占比而非转化率。"""

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_theme import polish


def category_structure(frame: pd.DataFrame) -> pd.DataFrame:
    """将四类行为计数转为类目规模和行为码 4 事件占比。

    Args:
        frame: 所选日期内全部行为的日类目汇总。

    Returns:
        每个类目一行，零事件占比为空。
    """
    table = frame.pivot_table(
        index="category_id",
        columns="behavior_type",
        values="events",
        aggfunc="sum",
        fill_value=0,
    )
    table = table.reindex(columns=[1, 2, 3, 4], fill_value=0)
    result = pd.DataFrame({"events": table.sum(axis=1), "code4": table[4]})
    result["share"] = result.code4 / result.events.replace(0, float("nan"))
    return result.reset_index()


def show_category_structure(frame: pd.DataFrame) -> None:
    """以样本量门槛和散点图探索类目结构，不将事件份额称为转化。

    Args:
        frame: 所选日期内全部行为的日类目计数。
    """
    st.subheader("类目规模 × 行为码 4 事件占比")
    st.caption(
        "仅随日期筛选，固定包含全部行为；使用交互事件数，不是曝光量或用户转化率。"
    )
    minimum = st.slider("类目最少交互事件数", 1, 1000, 100, key="category_minimum")
    table = category_structure(frame)
    table = table.loc[table.events >= minimum].copy()
    table["类目"] = table.category_id.astype(str)
    if table.empty:
        st.info("当前门槛下没有类目，请降低最少事件数。")
        return
    chart = (
        alt.Chart(table)
        .mark_circle(size=55, opacity=0.55)
        .encode(
            x=alt.X(
                "events:Q", title="交互事件数（对数刻度）", scale=alt.Scale(type="log")
            ),
            y=alt.Y("share:Q", title="行为码 4 事件占比", axis=alt.Axis(format=".0%")),
            color=alt.Color(
                "share:Q", scale=alt.Scale(scheme="tealblues"), legend=None
            ),
            tooltip=[
                "类目:N",
                alt.Tooltip("events:Q", title="交互事件", format=","),
                alt.Tooltip("code4:Q", title="行为码 4 事件", format=","),
                alt.Tooltip("share:Q", title="事件占比", format=".2%"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(polish(chart))
    st.caption(
        f"展示 {len(table):,} 个满足门槛的类目。占比=行为码 4 事件数÷全部交互事件数；小样本比例波动较大。"
    )
