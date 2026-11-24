"""首次观测用户回访的热力图与成熟队列汇总。"""

import hashlib
import json

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import REPORTS
from douyin_analysis.dashboard_theme import polish


def load_cohorts() -> pd.DataFrame:
    """核对队列汇总指纹，未成熟观察天保留缺失值。"""
    path = REPORTS / "dashboard/research/cohorts.csv"
    manifest = json.loads(path.with_name("cohorts_manifest.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("回访汇总指纹不一致")
    return pd.read_csv(path)


def show_retention() -> None:
    """展示全观察期首观测队列，不将样本回访视为注册留存。"""
    st.subheader("首次观测后的用户回访")
    st.caption(
        "固定全观察期、全部行为；不随顶部筛选变化。首次观测不是注册，不代表新增用户。"
    )
    table = load_cohorts()
    table["首观测日"] = pd.to_datetime(table.cohort).dt.strftime("%m/%d")
    table["观察日"] = "D" + table.elapsed.astype(str)
    mature = table.loc[table.mature]
    summary = mature.groupby("elapsed")[["returning_users", "cohort_users"]].sum()
    summary["rate"] = summary.returning_users / summary.cohort_users
    columns = st.columns(3)
    for column, day in zip(columns, [1, 3, 7]):
        if day in summary.index:
            row = summary.loc[day]
            column.metric(f"D{day} 当日回访率", f"{row.rate:.2%}")
            column.caption(
                f"成熟队列人数 {int(row.cohort_users):,} · 回访 {int(row.returning_users):,}"
            )
    st.caption("每个 Dn 仅纳入有足够后续观察天数的队列；不是 D1 至 Dn 的累计回访。")
    chart = (
        alt.Chart(table)
        .mark_rect(cornerRadius=3)
        .encode(
            x=alt.X("观察日:O", sort=[f"D{day}" for day in range(8)], title=None),
            y=alt.Y("首观测日:O", title="首次观测日期"),
            color=alt.Color(
                "return_rate:Q",
                title="当日回访率",
                scale=alt.Scale(domain=[0, 1], scheme="tealblues"),
                legend=alt.Legend(format=".0%"),
            ),
            tooltip=[
                "首观测日:O",
                "观察日:O",
                alt.Tooltip("cohort_users:Q", title="队列人数", format=","),
                alt.Tooltip("returning_users:Q", title="回访人数", format=","),
                alt.Tooltip("return_rate:Q", title="回访率", format=".1%"),
            ],
        )
        .properties(height=max(240, table.cohort.nunique() * 22))
    )
    labels = (
        alt.Chart(table.loc[table.mature])
        .mark_text(fontSize=10)
        .encode(
            x=alt.X("观察日:O", sort=[f"D{day}" for day in range(8)]),
            y="首观测日:O",
            text=alt.Text("return_rate:Q", format=".0%"),
            color=alt.condition(
                alt.datum.return_rate > 0.55, alt.value("white"), alt.value("#254356")
            ),
        )
    )
    st.altair_chart(polish(chart + labels))
    st.caption(
        "空白表示后续观察不足；队列规模见悬浮提示。采样完整性未确认，回访高低不能直接解释为运营效果。"
    )
    with st.expander("查看回访统计明细与分母"):
        st.dataframe(table, hide_index=True)
        st.download_button(
            "下载回访汇总", table.to_csv(index=False).encode("utf-8-sig"), "cohorts.csv"
        )
