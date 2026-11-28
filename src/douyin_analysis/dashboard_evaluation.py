"""展示已完成的补充评估与交付材料，不加载训练数据或模型。"""

import hashlib
import json
from io import BytesIO

import altair as alt
import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import ROOT
from douyin_analysis.dashboard_segments import MODEL_LABELS

DIRECTORY = ROOT / "reports/evaluation/2026-11-27"
DOCUMENTS = {
    "模型评估补充报告（8 页）": "2026-11-27_模型评估补充报告.pdf",
    "项目总结简报（3 页，结项准备版）": "2026-11-27_项目总结简报_结项准备版.pdf",
}


def verified_bytes(name: str) -> bytes:
    """按已发布清单校验允许展示的文件，拒绝未知路径或陈旧产物。"""
    manifest = json.loads((DIRECTORY / "manifest.json").read_text())["files"]
    figures = json.loads((DIRECTORY / "figure_sources.json").read_text())
    manifest["benchmark_summary.csv"] = figures["benchmark_summary_sha256"]
    manifest.update(figures["figure_sha256"])
    pdfs = json.loads((DIRECTORY / "delivery_check.json").read_text())["files"]
    if name in DOCUMENTS.values():
        relative = f"output/pdf/{name}"
        path, expected = ROOT / relative, pdfs[relative]
    elif name in manifest:
        path, expected = DIRECTORY / name, manifest[name]
    else:
        raise ValueError("未知评估文件")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("评估文件指纹不一致")
    return content


def csv_download(label: str, table: pd.DataFrame, filename: str) -> None:
    """下载当前选择的汇总，数值保留原始精度。"""
    st.download_button(
        label, table.to_csv(index=False).encode("utf-8-sig"), filename, "text/csv"
    )


def read_table(name: str) -> pd.DataFrame:
    """从校验过的内存内容读取 CSV，不触发分析计算。"""
    return pd.read_csv(BytesIO(verified_bytes(name)))


def show_learning() -> None:
    """交互查看固定验证窗口上的训练规模曲线。"""
    st.subheader("训练规模与泛化差距")
    choice = st.selectbox(
        "学习曲线模型", list(MODEL_LABELS), format_func=lambda key: MODEL_LABELS[key]
    )
    table = read_table("learning_curves.csv")
    table = table[table.model == choice].copy()
    chart = table.melt(
        id_vars=["fraction", "train_rows", "train_positives"],
        value_vars=["train_ap", "validation_ap"],
        var_name="来源",
        value_name="AP",
    )
    chart["来源"] = chart["来源"].map(
        {"train_ap": "训练子集", "validation_ap": "固定验证集"}
    )
    st.altair_chart(
        alt.Chart(chart)
        .mark_line(point=True)
        .encode(
            x=alt.X("fraction:Q", title="训练样本比例", axis=alt.Axis(format=".0%")),
            y=alt.Y("AP:Q", title="平均精度 AP", scale=alt.Scale(zero=True)),
            color=alt.Color(
                "来源:N",
                scale=alt.Scale(
                    domain=["训练子集", "固定验证集"], range=["#9BAEB8", "#176A80"]
                ),
            ),
            tooltip=[
                alt.Tooltip("来源:N"),
                alt.Tooltip("fraction:Q", format=".0%"),
                alt.Tooltip("AP:Q", format=".6f"),
                alt.Tooltip("train_rows:Q", title="训练候选对"),
                alt.Tooltip("train_positives:Q", title="训练正例对"),
            ],
        )
        .properties(height=310)
    )
    st.caption(
        "固定种子 42，训练窗口内分层嵌套抽样；"
        + "前三档重拟合，100% 复用存档。缩放器只拟合当前训练子集。单种子、单窗口，无置信区间；不是迭代次数曲线，也不能严格分解偏差和方差。"
    )
    st.dataframe(
        table[
            ["fraction", "train_rows", "train_positives", "train_ap", "validation_ap"]
        ]
        .rename(
            columns={
                "fraction": "训练比例",
                "train_rows": "训练候选对",
                "train_positives": "训练正例对",
                "train_ap": "训练 AP",
                "validation_ap": "验证 AP",
            }
        )
        .style.format({"训练比例": "{:.0%}", "训练 AP": "{:.6f}", "验证 AP": "{:.6f}"}),
        hide_index=True,
    )
    csv_download("下载当前学习曲线数据", table, f"learning_{choice}.csv")


def show_cases() -> None:
    """呈现匿名极端错误案例，限定解释而不推断真实动机。"""
    st.subheader("错误案例：历史信号不等于未来结果")
    choice = st.selectbox(
        "错误案例模型", list(MODEL_LABELS), format_func=lambda key: MODEL_LABELS[key]
    )
    kind = st.radio("错误类型", ["误报 FP", "漏报 FN"], horizontal=True)
    table = read_table("error_cases.csv")
    selected = table[(table.model == choice) & (table.error == str(kind)[-2:])].copy()
    st.caption(
        "每模型选最高分误报、最低分漏报各两条；"
        + "是极端示例，不代表典型群体占比。隐藏用户和商品标识。标签 0 仅表示未来七日未观测到行为码 4；分数不是已校准购买概率。"
    )
    for row in selected.itertuples():
        with st.container(border=True):
            st.markdown(
                f"**{row.case} · 分数 {row.score:.6f} / 固定阈值 {row.threshold:.6f}**"
            )
            st.write(
                f"实际标签 {row.label}；"
                + f"历史交互 {int(row.pair_events)} 次；"
                + f"距最近交互 {int(row.pair_recency_hours)} 小时；"
                + f"历史行为码 3 / 4 分别为 {int(row.pair_cart)} / {int(row.pair_buy)} 次。"
            )
    st.info(
        "误报可能反映历史兴趣不延续、窗口或采样限制；漏报可能反映历史信号较弱。均为待验证解释，不是因果归因，也不能据此删除正常交互或单独调阈值。"
    )
    csv_download("下载当前匿名案例", selected, f"cases_{choice}_{str(kind)[-2:]}.csv")


def show_cost() -> None:
    """对比同一批大小的本机推理与存档体积，说明测量边界。"""
    st.subheader("推理耗时与模型体积")
    size = st.selectbox("推理批大小", [1, 1000, 10000], index=2)
    table = read_table("benchmark_summary.csv")
    selected = table[table.batch_size == size].copy()
    selected["模型"] = selected.model.map(MODEL_LABELS)
    selected["模型 KiB"] = selected.model_bytes / 1024
    left, right = st.columns(2)
    for target, field, title in [
        (left, "median_ms", "中位耗时（ms）"),
        (right, "模型 KiB", "模型文件（KiB）"),
    ]:
        with target:
            st.altair_chart(
                alt.Chart(selected)
                .mark_bar(color="#176A80")
                .encode(
                    x=alt.X("模型:N", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y(f"{field}:Q", title=title),
                    tooltip=["模型", alt.Tooltip(f"{field}:Q", format=".3f")],
                )
                .properties(height=260)
            )
    st.dataframe(
        selected[
            ["模型", "median_ms", "p95_ms", "median_cpu_ms", "peak_rss_mib", "模型 KiB"]
        ]
        .rename(
            columns={
                "median_ms": "中位 ms",
                "p95_ms": "P95 ms",
                "median_cpu_ms": "CPU中位 ms",
                "peak_rss_mib": "进程峰值 MiB",
            }
        )
        .style.format(
            {
                "中位 ms": "{:.3f}",
                "P95 ms": "{:.3f}",
                "CPU中位 ms": "{:.3f}",
                "进程峰值 MiB": "{:.1f}",
                "模型 KiB": "{:.2f}",
            }
        ),
        hide_index=True,
    )
    st.caption(
        "2026-11-27 本机 macOS / arm64；"
        + "Python 3.12.2，scikit-learn 1.9.1，单线程、无 GPU。"
        + "每模型独立进程，预热 2 次、测量 7 次。"
        + "计时只含内存特征变换与预测，不含读取、加载、特征生成、网络或页面响应。P95 仅描述这 7 次测量。"
    )
    st.caption(
        "峰值内存是整个进程生命周期的高水位，含 Python、依赖、模型及数据；不是模型增量内存或最低部署要求。看板展示预计算结果，并不提供实时推理服务。"
    )
    csv_download(
        "下载当前批量推理基准",
        selected.drop(columns=["模型", "模型 KiB"]),
        f"inference_batch_{size}.csv",
    )


def show_evaluation() -> None:
    """在独立专题中展示补充评估及经校验的 PDF 下载。"""
    st.caption(
        "评估数据截至 2026-11-27；独立查看三个固定模型，不随页首模型或行为页日期筛选变化。本次接入不重训、不改阈值、不新增测试集评价。"
    )
    learning, cases, cost, delivery = st.tabs(
        ["学习曲线", "匿名错误案例", "推理与资源", "报告下载"]
    )
    with learning:
        show_learning()
    with cases:
        show_cases()
    with cost:
        show_cost()
    with delivery:
        st.subheader("评估报告与结项准备材料")
        st.write(
            "评估报告 8 页：方法、曲线、案例与部署成本。总结简报 3 页：核心结论、方案亮点、可复用方法、局限及下周安排。"
        )
        for label, filename in DOCUMENTS.items():
            st.download_button(
                f"下载{label}", verified_bytes(filename), filename, "application/pdf"
            )
        st.caption(
            "均为 2026-11-27 版本；总结简报是结项准备版，不能替代最终验收。原第三周周报保持不变。"
        )
