"""Streamlit 双看板第一版：展示既有汇总、特征目录与验证结果。"""

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_behavior import render_behavior
from douyin_analysis.dashboard_data import (
    ROOT,
    model_metrics,
    read_report,
)
from douyin_analysis.dashboard_errors import show_budget_comparison, show_error_groups
from douyin_analysis.dashboard_model_charts import (
    show_coefficients,
    show_confusion,
    show_coverage,
    show_curves,
    show_weight_experiment,
)
from douyin_analysis.dashboard_theme import hero, polish, style_page
from douyin_analysis.dashboard_visuals import show_precision_recall


def show_features() -> None:
    """展示特征实现状态与可下载的带教审阅表。"""
    st.subheader("特征实现清单")
    st.caption("24 项基础特征、6 项实验特征；类别特征仍待实现。")
    catalog = read_report("features/feature_catalog.csv")
    scope = st.selectbox("特征层级", ["全部", *catalog["所在表"].unique()])
    if scope != "全部":
        catalog = catalog.loc[catalog["所在表"] == scope]
    st.dataframe(catalog, hide_index=True)
    path = ROOT / "outputs/2026-11-22/特征拆分整理_实现核对版.xlsx"
    if path.exists():
        st.download_button("下载完整特征汇总表", path.read_bytes(), path.name)


def behavior_page() -> None:
    """展示联动行为分析及独立的特征实现清单。"""
    render_behavior()
    with st.expander("特征工程 · 实现目录与完整下载"):
        show_features()


def model_page() -> None:
    """展示固定验证窗口的指标和混淆矩阵，避免伪造可调业务阈值。"""
    hero(
        "模型评估与诊断",
        "从识别能力到错误分布，区分候选覆盖、分类效果与预测取舍。",
        "MODEL INTELLIGENCE",
    )
    metrics = model_metrics()
    name = st.selectbox("查看模型", list(metrics.index), index=3, key="selected_model")
    row = metrics.loc[name]
    columns = st.columns(4)
    for column, label, value, explanation in zip(
        columns,
        ["平均精度 AP", "精确率", "候选内召回率", "命中正例对"],
        [
            f"{row.pr_auc_average_precision:.4f}",
            f"{row.precision:.2%}",
            f"{row.recall:.2%}",
            f"{int(row.true_positive):,}",
        ],
        [
            "全部验证预测计算的 Average Precision；不是准确率，也不是展示曲线的面积。",
            "命中正例对 ÷ 预测正例对；使用当前模型的验证 F1 阈值。",
            "命中正例对 ÷ 候选内 2,525 个正例对；不包含候选外正例。",
            "当前模型阈值下正确识别的正例用户商品对数；不是购买事件次数。",
        ],
    ):
        column.metric(label, value, help=explanation)
    st.caption(
        "验证历史窗 2025/11/25—12/02；标签窗 12/02—12/09，均左闭右开。"
        + f"当前模型阈值 {row.threshold:.6f}，尚非业务阈值。"
    )
    st.caption(
        "固定验证候选 1,061,515 对，正例 2,525 对；不随行为页日期筛选变化。"
        + "各模型阈值与预测量不同，相同预算比较请查看全局 Top-K。"
    )
    overview_tab, curves_tab, errors_tab, research_tab = st.tabs(
        ["模型总览", "曲线与阈值", "误差与预算", "权重对照与解释"]
    )
    with overview_tab:
        left, right = st.columns(2)
        with left, st.container(border=True):
            st.subheader("模型排序能力 · AP 对照")
            comparison = metrics.rename_axis("model").reset_index()
            chart = (
                alt.Chart(comparison)
                .mark_bar(cornerRadiusEnd=4, color="#147D92")
                .encode(
                    x=alt.X("pr_auc_average_precision:Q", title="Average Precision"),
                    y=alt.Y(
                        "model:N", sort="-x", title=None, axis=alt.Axis(labelLimit=190)
                    ),
                    tooltip=[
                        "model:N",
                        alt.Tooltip(
                            "pr_auc_average_precision:Q", title="AP", format=".4f"
                        ),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(polish(chart))
            st.caption(
                "自然正例率 0.2379%。AP 适合观察稀少正例的排序质量；扩展特征仍为探索方案。"
            )
        with right, st.container(border=True):
            show_precision_recall(metrics)
        left, right = st.columns(2)
        with left, st.container(border=True):
            st.subheader("混淆矩阵 · 数量与行占比")
            show_confusion(row)
        with right, st.container(border=True):
            st.subheader("覆盖分解 · 分类器之外的限制")
            show_coverage(row)
        with st.expander("查看完整模型指标与混淆计数"):
            st.dataframe(
                metrics[
                    ["pr_auc_average_precision", "roc_auc", "precision", "recall", "f1"]
                ]
            )
            matrix = pd.DataFrame(
                [
                    [int(row.true_negative), int(row.false_positive)],
                    [int(row.false_negative), int(row.true_positive)],
                ],
                index=["实际负例", "实际正例"],
                columns=["预测负例", "预测正例"],
            )
            st.dataframe(matrix)
    with curves_tab:
        show_curves()
    with errors_tab:
        with st.container(border=True):
            show_error_groups()
        with st.container(border=True):
            show_budget_comparison()
    with research_tab:
        with st.container(border=True):
            show_weight_experiment()
        with st.container(border=True):
            show_coefficients()
    st.caption(
        "验证集用于多次探索比较；LR 已使用测试集，后续树模型及本次权重对照未访问测试集。标签是未来七日是否观察到行为码 4，样本单位为用户商品对。"
    )


def main() -> None:
    """配置双页面导航及共用口径说明。"""
    st.set_page_config(page_title="抖音商城用户行为分析", layout="wide")
    style_page()
    st.sidebar.title("抖音商城分析")
    st.sidebar.caption("第五版 · 2026-11-23\n基于已保存的分析结果")
    st.sidebar.info("行为码释义、时区与采样完整性待确认；当前仅作离线分析。")
    page = st.navigation(
        [
            st.Page(behavior_page, title="用户行为与特征", default=True),
            st.Page(model_page, title="模型验证与误差"),
        ]
    )
    try:
        page.run()
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error(f"结果文件缺失或不一致：{error}。请按 README 准备完整仓库结果。")
