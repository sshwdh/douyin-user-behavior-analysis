"""展示训练边界固定的特征关联与匿名用户、商品分层表现。"""

import json

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import REPORTS
from douyin_analysis.pipeline import file_digest
from douyin_analysis.segment_analysis import FEATURES

MODEL_LABELS = {
    "lr_24": "LR24 加权",
    "lr_24_unweighted": "LR24 未加权",
    "hgb_31": "HGB31",
}


def load_segments(name: str) -> pd.DataFrame:
    """读取已核对指纹的公开分箱结果。

    Args:
        name: associations 或 performance。

    Returns:
        不含用户商品标识的汇总表。
    """
    if name not in {"associations", "performance"}:
        raise ValueError("未知分箱结果")
    directory = REPORTS / "dashboard/segments"
    manifest = json.loads((directory / "manifest.json").read_text())
    path = directory / f"{name}.csv"
    if file_digest(path) != manifest["files"][path.name]:
        raise ValueError("分箱结果指纹不一致")
    return pd.read_csv(path)


def show_associations() -> None:
    """解释固定验证候选内的特征分箱正例率与支持量。"""
    st.subheader("历史特征与未来七日正例率")
    st.caption(
        "固定验证窗口；不随顶部日期、行为筛选变化。分箱仅由训练历史特征确定，"
        + "零值单独成箱，正值三分位重复边界合并。标签为未来七日观察到行为码 4。"
    )
    choice = st.selectbox("关联分析特征", list(FEATURES.values()))
    feature = next(key for key, value in FEATURES.items() if value == choice)
    table = load_segments("associations")
    table = table.loc[table.feature == feature].copy()
    baseline = table.positives.sum() / table.rows.sum()
    left, right = st.columns(2)
    chart_table = table.loc[table.rows > 0].assign(
        support_label=table.low_positive_support.map(
            {True: "正例少于30对", False: "正例至少30对"}
        )
    )
    base = alt.Chart(chart_table).encode(
        x=alt.X(
            "segment:N",
            sort=chart_table.segment.tolist(),
            title="训练历史特征区间",
            axis=alt.Axis(labelAngle=0),
        ),
        tooltip=[
            alt.Tooltip("segment:N", title="历史区间"),
            alt.Tooltip("rows:Q", title="候选对数", format=",d"),
            alt.Tooltip("positives:Q", title="正例对数", format=",d"),
            alt.Tooltip("positive_rate:Q", title="正例率", format=".3%"),
        ],
    )
    with left:
        st.altair_chart(
            base.mark_bar(color="#147D92")
            .encode(y=alt.Y("rows:Q", title="验证候选对数"))
            .properties(height=280)
        )
    with right:
        rates = base.mark_point(filled=True, size=100).encode(
            y=alt.Y("positive_rate:Q", title="箱内正例率", axis=alt.Axis(format=".2%")),
            color=alt.Color(
                "support_label:N",
                title="分组支持量",
                scale=alt.Scale(
                    domain=["正例少于30对", "正例至少30对"],
                    range=["#dfa24b", "#147D92"],
                ),
            ),
        )
        line = (
            alt.Chart(pd.DataFrame({"baseline": [baseline]}))
            .mark_rule(strokeDash=[5, 5], color="#9baeb8")
            .encode(y="baseline:Q")
        )
        st.altair_chart((rates + line).properties(height=280))
    st.caption(
        f"虚线为验证候选总体正例率 {baseline:.4%}。分母是用户商品对，不是事件次数；"
        + "不同特征包含同一批候选，不能跨特征累加。图中仅显示有样本的箱，空箱保留在表中。"
    )
    st.dataframe(
        table[
            [
                "segment",
                "rows",
                "positives",
                "positive_rate",
                "train_pair_count",
                "low_positive_support",
            ]
        ]
        .rename(
            columns={
                "rows": "验证候选对数",
                "positives": "实际正例对",
                "segment": "历史区间",
                "positive_rate": "箱内正例率",
                "train_pair_count": "训练候选对数",
                "tp": "命中",
                "fp": "误报",
                "fn": "漏报",
                "tn": "正确排除",
                "precision": "精确率",
                "recall": "候选内召回率",
                "predicted_positive": "预测正例对",
                "model": "模型",
                "low_positive_support": "正例少于30",
                "low_prediction_support": "预测正例少于30",
            }
        )
        .style.format({"箱内正例率": "{:.3%}"}, na_rep="—"),
        hide_index=True,
    )
    st.caption(
        "右闭区间，inf 表示无上限；正例少于 30 对仅作描述。关联不代表因果、"
        + "特征独立贡献或稳定提升；同一用户的候选相关，未提供独立样本置信区间。"
    )
    st.caption("CSV 保留原始数值：比率 0.01 表示 1%；空值表示无有效分母，不能当作零。")
    st.download_button(
        "下载当前特征分箱汇总",
        table.to_csv(index=False).encode("utf-8-sig"),
        f"feature_bins_{feature}.csv",
        "text/csv",
    )


def show_segment_performance() -> None:
    """对照三种存档模型在相同用户、商品分箱下的表现。"""
    st.subheader("用户活跃度与商品热度分层")
    st.caption(
        "独立对照 LR24 加权、LR24 未加权、HGB31；不随页首模型选择变化。"
        + "沿用各自已存档的全局验证阈值，未分组调阈值。"
    )
    choice = st.selectbox("分层维度", ["用户历史交互次数", "商品历史交互用户数"])
    feature = "user_events" if choice == "用户历史交互次数" else "item_users"
    metric_names = {
        "候选内召回率": "recall",
        "精确率": "precision",
        "命中正例对": "tp",
        "预测正例对数": "predicted_positive",
        "平均精度 AP": "ap",
        "ROC AUC": "roc_auc",
    }
    metric_label = st.selectbox("分层展示指标", list(metric_names))
    metric = metric_names[str(metric_label)]
    table = load_segments("performance")
    table = table.loc[table.feature == feature].copy()
    chart_table = table.loc[table.rows > 0].assign(
        model_label=table.model.map(MODEL_LABELS)
    )
    st.altair_chart(
        alt.Chart(chart_table)
        .mark_bar()
        .encode(
            x=alt.X(
                "segment:N",
                sort=chart_table.segment.unique().tolist(),
                title="历史区间",
                axis=alt.Axis(labelAngle=0),
            ),
            xOffset=alt.XOffset("model_label:N", sort=list(MODEL_LABELS.values())),
            y=alt.Y(
                f"{metric}:Q",
                title=str(metric_label),
                axis=alt.Axis(
                    format=(
                        ",d"
                        if metric in {"tp", "predicted_positive"}
                        else (".4f" if metric == "ap" else ".1%")
                    )
                ),
            ),
            color=alt.Color(
                "model_label:N",
                title="模型",
                scale=alt.Scale(
                    domain=list(MODEL_LABELS.values()),
                    range=["#dfa24b", "#58a6ab", "#176a80"],
                ),
            ),
            tooltip=[
                alt.Tooltip("model_label:N", title="模型"),
                alt.Tooltip("segment:N", title="历史区间"),
                alt.Tooltip("rows:Q", title="候选对数", format=",d"),
                alt.Tooltip("positives:Q", title="正例对数", format=",d"),
                alt.Tooltip("predicted_positive:Q", title="预测正例对数", format=",d"),
                alt.Tooltip("tp:Q", title="命中", format=",d"),
                alt.Tooltip("precision:Q", title="精确率", format=".2%"),
                alt.Tooltip("recall:Q", title="召回率", format=".2%"),
                alt.Tooltip(f"{metric}:Q", title=str(metric_label)),
            ],
        )
        .properties(height=320)
    )
    st.dataframe(
        table.assign(model=table.model.map(MODEL_LABELS))[
            [
                "model",
                "segment",
                "rows",
                "positives",
                "predicted_positive",
                "tp",
                "precision",
                "recall",
                "ap",
                "roc_auc",
                "fp",
                "fn",
                "tn",
                "low_positive_support",
                "low_prediction_support",
            ]
        ]
        .rename(
            columns={
                "rows": "验证候选对数",
                "positives": "实际正例对",
                "segment": "历史区间",
                "positive_rate": "箱内正例率",
                "train_pair_count": "训练候选对数",
                "tp": "命中",
                "fp": "误报",
                "fn": "漏报",
                "tn": "正确排除",
                "precision": "精确率",
                "recall": "候选内召回率",
                "predicted_positive": "预测正例对",
                "model": "模型",
                "low_positive_support": "正例少于30",
                "low_prediction_support": "预测正例少于30",
            }
        )
        .style.format(
            {
                "精确率": "{:.2%}",
                "候选内召回率": "{:.2%}",
                "ap": "{:.4f}",
                "roc_auc": "{:.4f}",
            },
            na_rep="—",
        ),
        hide_index=True,
    )
    st.caption(
        "recall=命中/箱内实际正例，precision=命中/箱内预测正例，tp=命中对数。"
        + "各模型预测量不同，不是相同预算比较。AP 随分组正例率变化，"
        + "跨组不能仅凭 AP 高低判断模型强弱；无分母、单类别 AP/AUC 留空。"
    )
    st.caption(
        "用户、商品边界分别按训练窗口的去重用户、去重商品确定；"
        + "展示指标仍按验证候选对计数，不是用户平均。正例或预测正例少于 30 对已标记。"
        + "历史候选不覆盖真正无交互对象，不作为冷启动专项结论。"
    )
    st.caption("CSV 保留原始数值：比率 0.01 表示 1%；空值表示无有效分母，不能当作零。")
    st.download_button(
        "下载当前分层模型汇总",
        table.to_csv(index=False).encode("utf-8-sig"),
        f"model_segments_{feature}.csv",
        "text/csv",
    )
