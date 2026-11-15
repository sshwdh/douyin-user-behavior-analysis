"""将已验证的第一周结果编排为含八张图表的中文 PDF。"""

import json
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def build(root: Path) -> None:
    """读取质量报告，生成第一周正式提交 PDF。

    Args:
        root: 项目根目录。
    """
    quality = json.loads((root / "reports/quality.json").read_text(encoding="utf-8"))
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "STSong-Light"
    styles.add(
        ParagraphStyle(
            "BodyCN", fontName="STSong-Light", fontSize=10.5, leading=17, spaceAfter=9
        )
    )
    styles.add(
        ParagraphStyle(
            "TitleCN",
            fontName="STSong-Light",
            fontSize=22,
            leading=29,
            spaceAfter=14,
            textColor=colors.HexColor("#17576A"),
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionCN",
            fontName="STSong-Light",
            fontSize=14,
            leading=20,
            spaceBefore=10,
            spaceAfter=8,
            textColor=colors.HexColor("#17576A"),
        )
    )
    styles.add(
        ParagraphStyle(
            "CaptionCN",
            fontName="STSong-Light",
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
        )
    )
    output = root / "output/pdf"
    output.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output / "2026-11-15_第一周项目汇报_口径修订.pdf"),
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=42,
        bottomMargin=42,
        title="第一周项目汇报修订 - 抖音商城用户行为分析",
        author="sshwdh",
    )
    story = []

    def paragraph(text: str, style: str = "BodyCN") -> None:
        """将一段文字加入报告。"""
        story.append(Paragraph(text, styles[style]))

    behavior = pd.read_csv(root / "reports/behavior.csv")
    daily = pd.read_csv(root / "reports/daily.csv")
    funnel = pd.read_csv(root / "reports/funnel.csv").iloc[0]
    purchases = int(behavior.loc[behavior.behavior_type == 4, "events"].iloc[0])
    peak = daily.iloc[int(daily["events"].argmax())]
    paragraph("第一周项目汇报 · 口径修订", "TitleCN")
    paragraph("抖音商城用户行为数据分析", "SectionCN")
    paragraph("原汇报周期：2026-11-06 至 2026-11-13　｜　修订：2026-11-15")
    paragraph(
        "依据带教反馈，撤销小时四元组全局去重。原规则会合并正常重复交互，"
        + "原周报的事件频次和相关模型指标不再作为当前结论。"
    )
    paragraph("一、暂行修正规则与确认边界", "SectionCN")
    paragraph(
        "同一用户、同一行为、同一自然小时跨商品累计：100 次及以下全部保留；"
        + "超过 100 次的整组记录进入本地隔离区。原始 CSV 保持不变。"
    )
    paragraph(
        "待确认：阈值是否应跨商品累计，以及超阈值是否整组隔离。"
        + "100 次为启发式筛查阈值，超阈值不等于已经证明恶意行为。"
    )
    paragraph("二、实际重跑结果（上述暂行口径）", "SectionCN")
    table = Table(
        [
            ["指标", "结果"],
            ["原始记录", f"{quality['raw_rows']:,}"],
            ["无效记录", f"{quality['invalid_rows']:,}"],
            ["隔离记录", f"{quality['quarantined_rows']:,}"],
            ["保留记录", f"{quality['clean_rows']:,}"],
            ["正常重复合并数", "0"],
            ["保留购买记录", f"{purchases:,}"],
            [
                "用户 / 商品 / 类目",
                f"{quality['users']:,} / {quality['items']:,}"
                + f" / {quality['categories']:,}",
            ],
        ],
        colWidths=[180, 315],
        rowHeights=26,
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F0F3")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D6DEE2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend([table, Spacer(1, 8)])
    paragraph(
        f"隔离占原始记录 {quality['quarantined_rows'] / quality['raw_rows']:.2%}；"
        + f"购买记录占保留事件 {purchases / quality['clean_rows']:.2%}。"
        + "这是事件结构，不是订单转化率。"
    )
    paragraph(
        f"日事件峰值：{peak['day']}，{int(peak['events']):,} 条；"
        + f"浏览用户商品对 {int(funnel.viewed_pairs):,} 对，"
        + f"严格后续小时购买 {int(funnel.later_buy_pairs):,} 对。"
    )
    story.append(PageBreak())
    paragraph("修正依据、验证与后续安排", "TitleCN")
    paragraph("三、分组范围为何必须确认", "SectionCN")
    paragraph(
        "按用户、商品、行为、小时分组，最大频次仅 22，没有超过 100 次的组；"
        + "按用户、行为、小时跨商品累计，最大频次 792，超过 100 次共 9,681 组。"
    )
    paragraph(
        "当前暂用跨商品分组，并提供 50/100/200 三档阈值的敏感性对照。"
        + "若带教要求按同商品统计，阈值 100 下本批有效记录将全部保留，需相应重跑。"
    )
    paragraph("四、工程修正与验证", "SectionCN")
    paragraph(
        "清洗不再合并重复事件；SQLite 改为普通索引以允许重复记录。"
        + "新增 99/100/101 次边界、跨商品分组和正常重复保留测试。"
    )
    paragraph(
        "已重建 Parquet、SQLite、汇总表及八张图。原始记录等于无效、隔离与保留记录之和；"
        + "跨格式核验结果与质量检查日志随仓库提交。"
    )
    paragraph(
        "旧模型指标已移入历史归档并标记失效。新口径下模型尚未重跑，"
        + "待规则确认后再进行基线实验；本次不新增后续阶段模型。"
    )
    paragraph("五、已完成工作与方法总结", "SectionCN")
    paragraph(
        "第一阶段已建立处理工程、SQL 分析、质量检查、八图与三篇文献调研笔记。"
        + "本次修正说明：相同字段不一定代表重复采集；事件唯一性需要日志语义支持。"
    )
    paragraph("六、下一周安排：11/16 - 11/20", "SectionCN")
    for text in [
        "周一：与带教确认频次分组、阈值及隔离方式，冻结数据口径。",
        "周二：据确认结果完善用户、商品、交互窗口特征及字典。",
        "周三：检查候选覆盖、标签边界与防泄漏测试。",
        "周四：在新口径上重跑 LR，条件满足后开展树模型对照。",
        "周五：汇总实验、限制及下周计划，提交第二周报告。",
    ]:
        paragraph(text)
    paragraph("仓库：https://github.com/sshwdh/douyin-user-behavior-analysis")
    paragraph("八张图均基于本次暂行规则；历史结果独立归档，不与当前结果混用。")
    charts = [
        (
            "行为结构与活跃趋势",
            "01_behavior.png",
            "图 1：各类行为事件数",
            "pv=浏览，fav=收藏，cart=加购，buy=购买。采用保留的原始事件次数；四类行为不构成严格四步漏斗。",
        ),
        (
            "",
            "02_daily.png",
            "图 2：每日活跃用户",
            "同一天发生任意行为的用户去重计数；12 月 12 日出现峰值，原因仍需业务信息验证。",
        ),
        (
            "购买趋势与小时分布",
            "03_daily.png",
            "图 3：每日购买用户",
            "按日统计行为码为 4 的去重用户；购买用户数不等于订单数，行为映射待带教确认。",
        ),
        (
            "",
            "04_hourly.png",
            "图 4：一天内各小时的事件分布",
            "将观察期全部日期按小时汇总，22 时事件最多；使用原始时间值，业务时区待确认。",
        ),
        (
            "类目偏好与星期分布",
            "05_categories.png",
            "图 5：购买用户数前十类目",
            "按类目内去重购买用户数排序；用户可跨类目出现，不能把柱高相加当作总购买人数。",
        ),
        (
            "",
            "06_weekday.png",
            "图 6：不同星期的日均事件数",
            "1=周一，7=周日；各星期事件总数除以实际天数。仅一个月样本，不足以证明稳定周期规律。",
        ),
        (
            "用户活跃度与购买频次",
            "07_activity.png",
            "图 7：用户事件频次分布",
            "按整个观察期的保留事件次数分组：1-9、10-49、50-99、100 及以上；分组受频次筛查规则影响。",
        ),
        (
            "",
            "08_repeat.png",
            "图 8：购买用户的事件次数分布",
            "比较一次与多次购买事件的用户数，仅统计购买用户；缺少订单号，不能解释为真实订单复购率。",
        ),
    ]
    for index, (title, filename, heading, caption) in enumerate(charts):
        if index % 2 == 0:
            story.append(PageBreak())
            paragraph(title, "TitleCN")
        else:
            story.append(Spacer(1, 12))
        paragraph(heading, "SectionCN")
        story.append(
            Image(str(root / "reports/figures" / filename), width=495, height=270)
        )
        paragraph(caption, "CaptionCN")

    def footer(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        """绘制周报页码。

        Args:
            canvas: PDF 绘图对象。
            doc: 当前文档。
        """
        canvas.saveState()
        canvas.setFont("STSong-Light", 9)
        canvas.setFillColor(colors.HexColor("#647480"))
        canvas.drawString(48, 23, "第一周工作汇报修订 | 2026-11-15")
        canvas.drawRightString(547, 23, f"{doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    """以当前目录为项目根目录生成 PDF。"""
    build(Path.cwd())


if __name__ == "__main__":
    main()
