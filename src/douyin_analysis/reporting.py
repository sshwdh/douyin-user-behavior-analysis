"""从真实汇总文件生成分析报告及首周汇报草稿。"""

import argparse
import json
from pathlib import Path

import pandas as pd


def create_reports(root: Path) -> None:
    """读取已运行产物并输出可核对的中文 Markdown。

    Args:
        root: 项目根目录。
    """
    quality = json.loads((root / "reports/quality.json").read_text(encoding="utf-8"))
    daily = pd.read_csv(root / "reports/daily.csv")
    behavior = pd.read_csv(root / "reports/behavior.csv")
    hourly = pd.read_csv(root / "reports/hourly.csv")
    funnel = pd.read_csv(root / "reports/funnel.csv").iloc[0]
    purchases = int(behavior.loc[behavior.behavior_type == 4, "events"].iloc[0])
    peak = daily.iloc[int(daily["events"].argmax())]
    peak_hour = hourly.iloc[int(hourly["events"].argmax())]
    rate = funnel.later_buy_pairs / funnel.viewed_pairs
    lines = [
        "# 数据处理与探索分析报告",
        "",
        "生成依据：本地全量 CSV 清洗后的实际运行产物。不是平台总体统计。",
        "",
        "## 数据质量与规模",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 原始记录 | {quality['raw_rows']:,} |",
        f"| 无效记录 | {quality['invalid_rows']:,} |",
        f"| 四元组重复记录 | {quality['duplicate_rows']:,} |",
        f"| 清洗后记录 | {quality['clean_rows']:,} |",
        f"| 独立用户 | {quality['users']:,} |",
        f"| 独立商品 | {quality['items']:,} |",
        f"| 独立类目 | {quality['categories']:,} |",
        f"| 多类目商品 | {quality['items_with_multiple_categories']:,} |",
        "",
        f"数据范围：{quality['start']} 至 {quality['end']}。",
        f"来源 SHA256：`{quality['source_sha256']}`。",
        "",
        "口径：按用户、商品、行为、小时全局去重。小时内真实重复行为也可能被折叠。",
        f"折叠比例 {quality['duplicate_rows'] / quality['raw_rows']:.2%}，必须优先核实。",
        "逐行为影响见 dedup_sensitivity.csv；键重复次数分布见 duplicate_multiplicity.csv。",
        "未按 IQR 删除重度用户或活动日峰值。没有订单号和金额，购买事件不是订单/GMV。",
        "",
        "## 主要发现与待验证建议",
        "",
        f"1. 清洗后购买行为 {purchases:,} 条，占事件 {purchases / quality['clean_rows']:.2%}。",
        "   这只是事件结构，不是购买用户率；后续模型须关注自然正例率及 PR-AUC。",
        f"2. 日事件峰值为 {peak['day']}，共 {int(peak['events']):,} 条。",
        "   建议进一步拆解用户、类目与重复行为贡献；不能仅凭日期推断促销造成增长。",
        f"3. 聚合事件峰值时段为 {int(peak_hour['hour']):02d} 时。",
        "   可作为运营时段研究起点，需再对比购买用户率和流量构成，不能直接认定最优投放。",
        f"4. 浏览过的用户商品对为 {int(funnel.viewed_pairs):,}；",
        f"   其中严格后续小时购买的对为 {int(funnel.later_buy_pairs):,}，占 {rate:.2%}。",
        f"   首次浏览和最后购买同小时的对为 {int(funnel.tied_hour_pairs):,}，顺序不明。",
        "   此指标受观察窗截尾影响，不是七日预测的标签转化率。",
        "",
        "## 图表与追溯",
        "",
        "![八图总览](figures/overview.png)",
        "",
        "八类图对应行为分布、DAU、日购买用户、小时分布、类目买家、",
        "按星期的日均事件、用户交互强度、购买事件频次。",
        "所有数值见 reports/*.csv，单图见 figures/。",
        "",
        "## 限制与下一步",
        "",
        "只有 1 万用户样本，采样机制未知；不能外推到百万用户全量。",
        "没有内容侧、金额或曝光数据；无法完成真实 RFM、短视频归因或 CTR。",
        "同小时顺序不可辨，标准化去重须做敏感性分析。",
        "下一步：历史窗口特征、候选召回覆盖、七日标签与时间外推 LR；",
        "扩展树模型和深度模型前先验证无数据泄漏。",
        "",
    ]
    (root / "reports/analysis_report.md").write_text("\n".join(lines), encoding="utf-8")
    sqlite_complete = (root / "reports/sqlite_check.txt").exists()
    sqlite_status = (
        "已导入并校验" if sqlite_complete else "脚本已编写，尚未完成运行验证"
    )
    weekly = [
        "# 第一周项目工作汇报（提交前核对稿）",
        "",
        "项目：抖音商城用户行为数据分析；实习开始：2026-11-06；提交：2026-11-13。",
        "本稿反映 11/12 集中推进的实际产物，不代表此前每日均完成开发。",
        "汇报人：【本人填写】；版本：v0.1.0-week1。",
        "GitHub：https://github.com/sshwdh/douyin-user-behavior-analysis 。",
        "",
        "## 本周工作内容",
        "",
        "完成项目资料、编码规范、字段映射和数据范围核验；建立模块化代码及四周计划。",
        f"全量处理 {quality['raw_rows']:,} 条行为，清洗后 {quality['clean_rows']:,} 条，",
        f"涉及 {quality['users']:,} 位用户和 {quality['items']:,} 件商品。",
        "已输出 Parquet、用户与商品汇总、质量 JSON、八类图表及解释报告。",
        f"SQLite：{sqlite_status}。质量工具实际运行记录见 reports/quality_checks.txt。",
        "",
        "## 实施方案",
        "",
        "使用磁盘支持的查询处理全量 CSV，校验时间/ID/行为码，按四元组全局去重；",
        "采用 SHA256 标识数据版本，保存聚合 CSV 和可复现绘图命令。",
        "代码采用 src 布局、类型注解、Google docstring；配置格式、静态检查和单元测试。",
        "",
        "## 关键结果与业务解释",
        "",
        f"购买事件占比 {purchases / quality['clean_rows']:.2%}；日事件峰值 {peak['day']}；",
        f"严格后续小时购买/浏览用户商品对占比 {rate:.2%}。",
        "这些是描述性结果，不等于线上业务收益。详见分析报告中的分子分母与限制。",
        "",
        "## 能力提升与收获（本人核实后填写）",
        "",
        "建议围绕三点写自己的理解：事件与用户口径差异、全局去重与分块去重差异、",
        "观察窗和标签窗为何不能混用。请补一个自己实际运行/修改代码的例子。",
        "",
        "## 工作难点与处理",
        "",
        "项目描述规模与实际样本不一致：以真实扫描结果为准，待带教确认采样方式。",
        "缺少金额/订单/内容字段：不构造虚假 GMV、RFM 金额或归因结论。",
        "时间只有小时：同小时行为不强行排序，漏斗注明顺序不确定性。",
        f"四元组重复比例达 {quality['duplicate_rows'] / quality['raw_rows']:.2%}；",
        "已提供去重前后敏感性对照，需带教确认是采集重复还是小时内真实重复交互。",
        "",
        "## 尚未完成",
        "",
        "论文全文精读与复现、完整预测特征体系、树模型/深度模型/融合与解释性、",
        "最终 PPT 尚未完成。助教接收渠道与私有仓库访问账号尚待提供。",
        "",
        "## 下一周安排（11/16—11/20）",
        "",
        "- 周一：补齐文献精读，用户/商品/交叉窗口特征，完成候选覆盖核验。",
        "- 周二：RF、偏好与序列特征；完善同小时行为处理与边界测试。",
        "- 周三：SVD/共现与特征筛选；训练数据拟合，验证数据仅变换。",
        "- 周四：固定七日标签窗，时间划分主评估与 7:2:1 对照，LR 基线。",
        "- 周五：树模型和不平衡处理初步对照，提交第二周汇报与实验记录。",
        "",
        "## 提交附件",
        "",
        "[分析报告](../../reports/analysis_report.md)、",
        "[质量报告](../../reports/quality.json)、",
        "[结果总览](../../reports/figures/overview.png)、",
        "[执行计划](../01_项目执行计划.md)、[方法说明](../02_口径与技术说明.md)。",
        "",
    ]
    if (root / "reports/lr_metrics.json").exists():
        weekly.extend(
            [
                "## 提前完成的基线实验",
                "",
                "已运行时间外推 LR，结果见 reports/lr_baseline_report.md。",
                "当前候选覆盖有限，精确率/召回率较低，属于诊断性基线，不代表可上线效果。",
                "",
            ]
        )
    (root / "docs/weekly/2026-11-13_第一周汇报.md").write_text(
        "\n".join(weekly), encoding="utf-8"
    )


def main() -> None:
    """解析项目目录并生成报告。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    create_reports(parser.parse_args().root)


if __name__ == "__main__":
    main()
