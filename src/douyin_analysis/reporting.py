"""从实际汇总文件生成分析报告；已发布周报独立维护。"""

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
        f"| 超阈值隔离记录 | {quality['quarantined_rows']:,} |",
        f"| 清洗后记录 | {quality['clean_rows']:,} |",
        f"| 独立用户 | {quality['users']:,} |",
        f"| 独立商品 | {quality['items']:,} |",
        f"| 独立类目 | {quality['categories']:,} |",
        f"| 多类目商品 | {quality['items_with_multiple_categories']:,} |",
        "",
        f"数据范围：{quality['start']} 至 {quality['end']}。",
        f"来源 SHA256：`{quality['source_sha256']}`。",
        "",
        "口径：保留正常重复记录；超过阈值的整组记录进入本地隔离区，不直接认定为恶意数据。",
        f"隔离比例 {quality['quarantined_rows'] / quality['raw_rows']:.2%}。",
        f"频次分组：{quality['frequency_scope']}；阈值：{quality['threshold']}。",
        (
            "当前未触发超阈值处置；未来批次触发时须确认处置策略。"
            if quality["quarantined_rows"] == 0
            else "当前存在超阈值隔离组，处置是否适用于主分析须结合业务确认。"
        ),
        "行为码映射、业务时区及采集完整性仍待确认。",
        "逐行为影响见 filter_sensitivity.csv；历史重复分布仅作诊断，不再作为去重依据。",
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
        "同小时顺序不可辨，阈值为启发式筛查规则；仍需结合业务判断异常组。",
        "旧口径 LR 指标已失效；应在新数据口径固定后重跑基线；",
        "扩展树模型和深度模型前先验证无数据泄漏。",
        "",
    ]
    (root / "reports/analysis_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """解析项目目录并生成报告。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    create_reports(parser.parse_args().root)


if __name__ == "__main__":
    main()
