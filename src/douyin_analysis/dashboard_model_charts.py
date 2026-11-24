"""模型看板的真实曲线、覆盖分解、权重对照和系数解释。"""

import hashlib
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import REPORTS, read_report
from douyin_analysis.dashboard_theme import ORANGE, TEAL, polish


@st.cache_data(max_entries=8)
def _read_verified(path: str, digest: str) -> pd.DataFrame:
    """缓存经指纹验证的公开研究汇总。

    Args:
        path: 汇总文件路径。
        digest: 清单中的 SHA256。

    Returns:
        已验证的表格副本。
    """
    source = Path(path)
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError("模型研究汇总指纹不一致")
    return pd.read_csv(source)


def research_table(name: str) -> pd.DataFrame:
    """按白名单加载研究表，避免读取任意路径。

    Args:
        name: metrics、budgets、curves 或 thresholds。

    Returns:
        经过指纹核对的汇总。
    """
    if name not in {"metrics", "budgets", "curves", "thresholds"}:
        raise ValueError("未知研究汇总")
    root = REPORTS / "dashboard/research"
    manifest = json.loads((root / "manifest.json").read_text())
    return _read_verified(str(root / f"{name}.csv"), manifest["files"][name]["sha256"])


def show_curves() -> None:
    """展示三模型验证 PR/ROC 和各自的阈值敏感性。"""
    curves = research_table("curves")
    models = st.multiselect(
        "曲线模型",
        list(curves.model.unique()),
        default=["lr_24", "hgb_31", "lr_24_unweighted"],
        key="curve_models",
    )
    if not models:
        st.info("至少选择一个模型查看曲线。")
        return
    curves = curves.loc[curves.model.isin(models)]
    zoom = st.checkbox("放大 PR 区间：精确率 0–12%", value=True, key="pr_zoom")
    columns = st.columns(2)
    for column, kind, title, x_label, y_label in [
        (columns[0], "pr", "PR · 稀少正例下的识别能力", "召回率", "精确率"),
        (columns[1], "roc", "ROC · 整体区分能力", "误报率", "召回率"),
    ]:
        with column, st.container(border=True):
            st.subheader(title)
            chart = (
                alt.Chart(curves.loc[curves.kind == kind])
                .mark_line(strokeWidth=2.4, clip=True)
                .encode(
                    x=alt.X(
                        "x:Q",
                        title=x_label,
                        scale=alt.Scale(domain=[0, 1]),
                        axis=alt.Axis(format=".0%"),
                    ),
                    y=alt.Y(
                        "y:Q",
                        title=y_label,
                        scale=alt.Scale(
                            domain=[0, 0.12 if kind == "pr" and zoom else 1]
                        ),
                        axis=alt.Axis(format=".0%"),
                    ),
                    color=alt.Color(
                        "model:N", title="模型", legend=alt.Legend(orient="bottom")
                    ),
                    order="order:Q",
                    tooltip=[
                        "model:N",
                        alt.Tooltip("x:Q", title=x_label, format=".3f"),
                        alt.Tooltip("y:Q", title=y_label, format=".3f"),
                    ],
                )
                .properties(height=300)
            )
            if kind == "pr":
                baseline = float(research_table("metrics").positive_rate.iloc[0])
                reference = (
                    alt.Chart(pd.DataFrame({"value": [baseline]}))
                    .mark_rule(strokeDash=[5, 4], color="#8C9BAA")
                    .encode(y="value:Q")
                )
            else:
                reference = (
                    alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
                    .mark_line(strokeDash=[5, 4], color="#8C9BAA")
                    .encode(x="x:Q", y="y:Q")
                )
            st.altair_chart(polish(chart + reference))
    st.caption(
        "曲线最多抽取 400 个有序展示点；AP / AUC 使用全量预测计算。PR 虚线为自然正例率，ROC 虚线为随机参考。"
    )
    st.subheader("阈值敏感性 · 离线诊断")
    selected = st.selectbox("阈值曲线模型", models, key="threshold_model")
    table = research_table("thresholds")
    table = table.loc[table.model == selected]
    melted = table.melt(
        id_vars="threshold",
        value_vars=["precision", "recall", "f1"],
        var_name="指标",
        value_name="value",
    )
    chart = (
        alt.Chart(melted)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("threshold:Q", title="分类分数阈值"),
            y=alt.Y("value:Q", title="指标值", axis=alt.Axis(format=".0%")),
            color="指标:N",
            tooltip=[
                alt.Tooltip("threshold:Q", title="阈值", format=".5f"),
                "指标:N",
                alt.Tooltip("value:Q", format=".2%"),
            ],
        )
        .properties(height=260)
    )
    st.altair_chart(polish(chart))
    st.caption(
        "网格包含等距点、分数分位点和原 F1 阈值；这不是业务阈值建议。模型分数未经概率校准。"
    )


def show_confusion(row: pd.Series) -> None:
    """展示行归一化混淆矩阵并保留每格绝对计数。

    Args:
        row: 单模型验证指标，含 true_negative。
    """
    table = pd.DataFrame(
        {
            "实际": ["实际负例", "实际负例", "实际正例", "实际正例"],
            "预测": ["预测负例", "预测正例", "预测负例", "预测正例"],
            "count": [
                row.true_negative,
                row.false_positive,
                row.false_negative,
                row.true_positive,
            ],
        }
    )
    table["rate"] = table["count"] / table.groupby("实际")["count"].transform("sum")
    table["label"] = [
        f"{int(count):,} · {rate:.1%}"
        for count, rate in zip(table["count"], table.rate)
    ]
    base = alt.Chart(table).encode(
        x=alt.X("预测:N", title=None), y=alt.Y("实际:N", title=None)
    )
    blocks = base.mark_rect(cornerRadius=7).encode(
        color=alt.Color(
            "rate:Q", scale=alt.Scale(domain=[0, 1], scheme="tealblues"), legend=None
        ),
        tooltip=[
            "实际:N",
            "预测:N",
            alt.Tooltip("count:Q", title="对数", format=","),
            alt.Tooltip("rate:Q", title="行占比", format=".2%"),
        ],
    )
    labels = base.mark_text(fontSize=15, fontWeight=600).encode(
        text="label:N",
        color=alt.condition(
            alt.datum.rate > 0.55, alt.value("white"), alt.value("#20364B")
        ),
    )
    st.altair_chart(polish((blocks + labels).properties(height=210)))
    st.caption("每行归一化为 100%；正例行体现漏报与召回，负例行体现误报。")


def show_coverage(row: pd.Series) -> None:
    """将未来正例拆为候选外、候选内漏报和命中。

    Args:
        row: 当前模型验证指标。
    """
    samples = read_report("features/sample_summary.csv")
    sample = samples.loc[samples.split == "validation"].iloc[0]
    total = int(sample.future_code4_pairs)
    values = [
        int(row.true_positive),
        int(row.false_negative),
        total - int(row.positives),
    ]
    table = pd.DataFrame(
        {"去向": ["候选内命中", "候选内漏报", "未进入候选"], "对数": values}
    )
    chart = (
        alt.Chart(table)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("去向:N", sort=None, title=None),
            x=alt.X("对数:Q", title="未来行为码 4 用户商品对"),
            color=alt.Color(
                "去向:N", scale=alt.Scale(range=[ORANGE, TEAL, "#9AAABC"]), legend=None
            ),
            tooltip=["去向:N", alt.Tooltip("对数:Q", format=",")],
        )
        .properties(height=210)
    )
    st.altair_chart(polish(chart))
    st.caption(
        f"分母为全部 {total:,} 个未来正例对；未入候选的正例不参与当前分类器评分。不是全站线上效果。"
    )


def show_weight_experiment() -> None:
    """展示仅改变 LR 类别权重的已完成对照及固定预算命中。"""
    st.subheader("样本不平衡 · 权重并非越强越好")
    st.caption(
        "新实验只将 LR24 的 class_weight 从 balanced 改为 None；特征、窗口、C、优化器与随机种子不变。"
    )
    metrics = research_table("metrics").set_index("model")
    st.dataframe(
        metrics[
            ["pr_auc_average_precision", "roc_auc", "precision", "recall", "f1"]
        ].rename(
            columns={
                "pr_auc_average_precision": "AP",
                "roc_auc": "ROC AUC",
                "precision": "精确率",
                "recall": "召回率",
            }
        ),
        column_config={
            name: st.column_config.NumberColumn(format="%.4f")
            for name in ["AP", "ROC AUC", "精确率", "召回率", "f1"]
        },
    )
    budgets = research_table("budgets")
    chart = (
        alt.Chart(budgets)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("budget:O", title="全局预测预算"),
            xOffset="model:N",
            y=alt.Y("hits:Q", title="命中正例对数"),
            color="model:N",
            tooltip=[
                "model:N",
                "budget:O",
                "hits:Q",
                alt.Tooltip("precision:Q", format=".2%"),
                alt.Tooltip("recall:Q", format=".2%"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(polish(chart))
    st.caption(
        "两个预算为此前固定的 5,060 / 12,400，不按新结果挑选。未重采样、不访问测试集、不替换基线；验证集反复使用，结果仍属探索。"
    )


def show_coefficients() -> None:
    """展示 LR24 标准化系数，不将相关解释为因果或 SHAP。"""
    st.subheader("特征解释 · LR24 标准化系数")
    table = read_report("experiments/lr_2026-11-17/coefficients.csv")
    table = table.loc[table.variant == "lr_24"].copy()
    table = table.loc[table.coefficient.abs().nlargest(12).index]
    table["方向"] = table.coefficient.map(
        lambda value: "正系数" if value >= 0 else "负系数"
    )
    chart = (
        alt.Chart(table)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("coefficient:Q", title="标准化输入的线性系数"),
            y=alt.Y("feature:N", sort="-x", title=None),
            color=alt.Color(
                "方向:N",
                scale=alt.Scale(domain=["正系数", "负系数"], range=[ORANGE, TEAL]),
            ),
            tooltip=["feature:N", alt.Tooltip("coefficient:Q", format=".3f")],
        )
        .properties(height=360)
    )
    st.altair_chart(polish(chart))
    st.caption(
        "仅展示绝对值最大的 12 项。计数与间隔先 log1p，再使用训练集标准化；相关特征会共同影响系数，不表示因果效应，也不是树模型 SHAP。"
    )
