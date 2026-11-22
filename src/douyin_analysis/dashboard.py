"""Streamlit 双看板第一版：展示既有汇总、特征目录与验证结果。"""

import pandas as pd
import streamlit as st

from douyin_analysis.dashboard_data import (
    REPORTS,
    ROOT,
    model_metrics,
    overview,
    read_report,
    select_days,
)


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
    """展示全观察期概况与独立的每日趋势日期筛选。"""
    st.title("用户行为与特征")
    quality = overview()
    st.caption(f"全观察期：{quality['start']} 至 {quality['end']}，原始时间未转换时区")
    columns = st.columns(4)
    for column, label, key in zip(
        columns,
        ["有效事件", "用户", "商品", "类目"],
        ["clean_rows", "users", "items", "categories"],
    ):
        column.metric(label, f"{int(quality[key]):,}")
    st.caption("小时内正常重复行为全部保留。以上为全观察期去重实体数。")
    st.subheader("每日趋势")
    daily = read_report("daily.csv")
    dates = pd.to_datetime(daily.day).dt.date
    selected = st.date_input(
        "趋势日期范围（仅影响本节）",
        value=(dates.min(), dates.max()),
        min_value=dates.min(),
        max_value=dates.max(),
    )
    if isinstance(selected, tuple) and len(selected) == 2:
        filtered = select_days(daily, selected[0], selected[1])
        if filtered.empty:
            st.info("所选日期没有记录。")
        else:
            metric = st.selectbox(
                "趋势指标", ["事件数", "日活跃用户数", "日行为码 4 用户数"]
            )
            if metric is None:
                return
            mapping = {
                "事件数": "events",
                "日活跃用户数": "dau",
                "日行为码 4 用户数": "buyers",
            }
            plot = filtered.rename(columns={"day": "日期", mapping[metric]: metric})
            st.line_chart(plot.set_index("日期")[[metric]])
            st.caption(
                f"所选范围事件合计：{int(filtered.events.sum()):,}；日用户数不可相加作为区间去重人数。"
            )
    else:
        st.info("请选择完整的开始与结束日期。")
    st.subheader("全观察期小时分布")
    hourly = read_report("hourly.csv").rename(
        columns={"hour": "小时", "events": "事件数"}
    )
    st.bar_chart(hourly.set_index("小时")[["事件数"]])
    st.caption("按一天中的小时汇总全部观察日；不受上方日期筛选影响。")
    st.subheader("全观察期类目交互排行")
    count = st.slider("展示类目数量", 5, 30, 20)
    categories = read_report("categories.csv").nlargest(count, "events")
    categories["category_id"] = categories.category_id.astype(str)
    st.dataframe(
        categories.rename(
            columns={
                "category_id": "类目编号",
                "events": "事件数",
                "users": "交互用户数",
                "buyers": "行为码 4 用户数",
            }
        ),
        hide_index=True,
    )
    show_features()


def model_page() -> None:
    """展示固定验证窗口的指标和混淆矩阵，避免伪造可调业务阈值。"""
    st.title("模型验证与误差")
    st.caption("历史窗 2025/11/25—12/02；标签窗 12/02—12/09，均为左闭右开。")
    st.info("样本为历史七日交互过的用户商品对，预测未来七日是否观察到行为码 4。")
    samples = read_report("features/sample_summary.csv")
    validation = samples.loc[samples.split == "validation"].iloc[0]
    columns = st.columns(3)
    columns[0].metric("验证候选对", f"{int(validation.candidates):,}")
    columns[1].metric("自然正例率", f"{validation.positive_rate:.4%}")
    columns[2].metric("候选覆盖率", f"{validation.coverage:.2%}")
    st.caption("覆盖率分母为未来全部行为码 4 用户商品对。候选内召回率使用不同分母。")
    st.write(
        "训练采用类别平衡权重；验证集保持自然分布，未过采样或欠采样。加权与不加权的独立对照尚未完成。"
    )
    metrics = model_metrics()
    labels = {
        "pr_auc_average_precision": "AP",
        "roc_auc": "ROC AUC",
        "precision": "精确率",
        "recall": "候选内召回率",
        "f1": "F1",
    }
    st.subheader("同一验证集上的模型比较")
    st.dataframe(metrics[list(labels)].rename(columns=labels))
    st.bar_chart(metrics[["pr_auc_average_precision"]].rename(columns=labels))
    name = st.selectbox("查看模型", list(metrics.index), index=3)
    row = metrics.loc[name]
    st.caption(f"既有验证集选出的 F1 阈值：{row.threshold:.6f}；尚非业务阈值。")
    matrix = pd.DataFrame(
        [
            [int(row.true_negative), int(row.false_positive)],
            [int(row.false_negative), int(row.true_positive)],
        ],
        index=["实际负例", "实际正例"],
        columns=["预测负例", "预测正例"],
    )
    st.subheader("混淆矩阵（用户商品对数）")
    st.dataframe(matrix)
    st.subheader("已有 PR 曲线")
    st.image(
        str(REPORTS / "experiments/tree_validation_2026-11-17/precision_recall.png")
    )
    st.caption("此图为 HGB15 与 HGB31 的验证 PR 对照，未包含 LR 或六项扩展特征模型。")
    st.subheader("固定全局预算下的命中对照")
    st.image(
        str(REPORTS / "errors/lr_tree_comparison_2026-11-18/equal_budget_hits.png")
    )
    st.caption("全局 Top-K，不等于每用户推荐 K 个商品。")
    st.warning(
        "验证集已用于多次比较，结果属于探索分析。LR 已评估测试集；后续树模型未访问测试集。类别加权分数未经概率校准。"
    )


def main() -> None:
    """配置双页面导航及共用口径说明。"""
    st.set_page_config(page_title="抖音商城用户行为分析", layout="wide")
    st.sidebar.title("抖音商城分析")
    st.sidebar.caption("第一版 · 2026-11-22\n基于已保存的分析结果")
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
