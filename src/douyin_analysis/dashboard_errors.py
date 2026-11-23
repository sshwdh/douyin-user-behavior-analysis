"""展示已存档的验证集分组误差与相同预算对照。"""

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import model_metrics, read_report

FEATURES = {
    "用户交互次数": "user_events",
    "用户行为码 4 次数": "user_buy",
    "用户交互商品数": "user_distinct_items",
    "商品交互用户数": "item_users",
    "商品行为码 4 用户数": "item_buyers",
    "用户商品对交互次数": "pair_events",
    "用户商品对行为码 4 次数": "pair_buy",
    "距最近交互小时数": "pair_recency_hours",
}
GROUPS = {
    "全部候选": "all",
    "最近交互不超过 24 小时": "recent_le24h",
    "最近交互超过 24 小时": "older_gt24h",
    "交互不超过 5 次": "low_frequency_le5",
    "仅交互 1 次": "single_event",
    "交互超过 5 次": "high_frequency_gt5",
    "超过 24 小时且不超过 5 次": "older_and_low",
}


def error_groups(feature: str) -> pd.DataFrame:
    """读取单一分组维度，并对账固定 HGB31 的混淆计数。

    Args:
        feature: 已存档的历史特征字段。

    Returns:
        通过计数校验的分组明细。
    """
    if feature not in FEATURES.values():
        raise ValueError("未知误差分组维度")
    table = read_report("errors/tree_validation_2026-11-17/segments.csv")
    table = table.loc[table.feature == feature].copy()
    expected = model_metrics().loc["hgb_31"]
    columns = {
        "tp": "true_positive",
        "fp": "false_positive",
        "fn": "false_negative",
        "tn": "true_negative",
    }
    for column, metric in columns.items():
        if int(table[column].sum()) != int(expected[metric]):
            raise ValueError("误差分组与模型计数不一致")
    if not (table[["tp", "fp", "fn", "tn"]].sum(axis=1) == table.rows).all():
        raise ValueError("误差分组行数不守恒")
    return table


def show_error_groups() -> None:
    """展示固定 HGB31 的分组错误率及对应样本量。"""
    st.subheader("误报、漏报集中在哪些分组")
    st.caption(
        "本节固定为 HGB31 原有 F1 阈值，不随上方模型选择变化；特征均取历史七日。"
    )
    feature = st.selectbox("误差分组维度", list(FEATURES))
    if feature is None:
        return
    table = error_groups(FEATURES[feature])
    rates = table.melt(
        id_vars="segment",
        value_vars=["false_positive_rate", "false_negative_rate"],
        var_name="metric",
        value_name="rate",
    )
    rates["指标"] = rates.metric.map(
        {
            "false_positive_rate": "误报率（FP / 实际负例）",
            "false_negative_rate": "漏报率（FN / 实际正例）",
        }
    )
    st.altair_chart(
        alt.Chart(rates)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("segment:N", title="历史特征区间", sort=table.segment.tolist()),
            xOffset="指标:N",
            y=alt.Y(
                "rate:Q",
                title="分组错误率",
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color("指标:N", scale=alt.Scale(range=["#147D92", "#D76B78"])),
            tooltip=[
                alt.Tooltip("segment:N", title="分组"),
                "指标:N",
                alt.Tooltip("rate:Q", title="错误率", format=".2%"),
            ],
        )
        .properties(height=300)
    )
    st.caption(
        "比率范围 0—1；区间左开右闭，inf 表示无上限。不同维度包含同一批候选，不能跨维度累加。"
    )
    labels = {
        "segment": "历史特征区间",
        "rows": "候选对数",
        "positives": "实际正例",
        "tp": "命中",
        "fp": "误报",
        "fn": "漏报",
        "tn": "正确排除",
        "low_positive_support": "正例少于 30 对",
    }
    st.dataframe(table[list(labels)].rename(columns=labels), hide_index=True)
    st.caption("正例少于 30 对的分组仅作描述，不能据此判断稳定规律；零分母比率为空。")


def show_budget_comparison() -> None:
    """比较固定全局预算下两种模型的分组命中与预测分配。"""
    st.subheader("固定全局预算下的命中对照")
    budget = st.selectbox("全局预测候选对数", [5060, 12400])
    group = st.selectbox("重点交互分组", list(GROUPS))
    if group is None:
        return
    table = read_report("errors/lr_tree_comparison_2026-11-18/comparison.csv")
    table = table.loc[
        (table.policy == f"top_{budget}") & (table.group == GROUPS[group])
    ].set_index("model")
    labels = {
        "rows": "分组候选对",
        "positives": "分组实际正例",
        "predicted": "分组预测对数",
        "hits": "分组命中",
        "recall": "分组召回率",
        "precision": "分组精确率",
    }
    st.dataframe(table[list(labels)].rename(columns=labels))
    st.bar_chart(table[["hits"]].rename(columns={"hits": "分组命中对数"}))
    st.caption(
        "先在全部验证候选中取全局 Top-K，再统计分组；不是每组或每用户各取 K 个。分组之间可能重叠。"
    )
    st.caption(
        "召回率分母为该分组实际正例，精确率分母为该分组预测对数；预算仅供离线比较，尚非业务投放量。"
    )
