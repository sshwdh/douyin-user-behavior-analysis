"""将已验证的第一周结果编排为含八张图表的中文 PDF。"""

import json
from pathlib import Path

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
        str(output / "2026-11-13_第一周项目汇报.pdf"),
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=42,
        bottomMargin=42,
        title="第一周项目汇报 - 抖音商城用户行为分析",
        author="sshwdh",
    )
    story = []

    def paragraph(text: str, style: str = "BodyCN") -> None:
        """将一段文字加入报告。"""
        story.append(Paragraph(text, styles[style]))

    paragraph("第一周项目工作汇报", "TitleCN")
    paragraph("抖音商城用户行为数据分析 · 第一阶段", "SectionCN")
    paragraph("汇报周期：2026-11-06 至 2026-11-13　｜　提交：2026-11-13")
    paragraph(
        "本周重点完成工程环境搭建、数据处理与质量核查；11/13 补齐文献调研和清洗口径确认单。"
    )
    paragraph("一、本周已完成", "SectionCN")
    paragraph(
        "核对项目要求和编码规范；完成全量 CSV 校验、小时四元组全局去重、"
        + "Parquet 与用户/商品汇总、SQLite 维表和索引、八类图表、解释文档及周计划。"
    )
    table = Table(
        [
            ["质量指标", "实际结果"],
            ["原始记录", f"{quality['raw_rows']:,}"],
            ["清洗后记录", f"{quality['clean_rows']:,}"],
            ["四元组合并记录", f"{quality['duplicate_rows']:,}（49.31%）"],
            ["无效记录 / 多类目商品", "0 / 0"],
            ["用户 / 商品 / 类目", "10,000 / 2,876,947 / 8,916"],
            ["数据观察期", "2025-11-18 至 2025-12-18"],
        ],
        colWidths=[180, 315],
        rowHeights=28,
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
    paragraph("二、关键发现", "SectionCN")
    paragraph(
        "清洗后购买事件 106,678 条，占全部事件 1.72%；"
        + "12 月 12 日事件量最高，为 346,464 条；聚合事件峰值在 22 时。"
    )
    paragraph(
        "浏览过的用户商品对共 4,677,501 对，严格后续小时购买 54,305 对（1.16%）。"
        + "另有 41,221 对首次浏览与最后购买同小时，无法确认顺序。"
    )
    paragraph(
        "首要待确认问题：是否采用小时四元组去重？该规则合并了 49.31% 的记录。"
        + "其中可能含真实重复交互，不能全部称为脏数据；请同时确认行为码映射、时区及采样完整性。"
    )
    story.append(PageBreak())
    paragraph("方法、验证与下一周安排", "TitleCN")
    paragraph("三、实施方案与验证", "SectionCN")
    paragraph(
        "采用磁盘支持的 DuckDB 处理全量数据，查询内存上限设为 2GB，"
        + "不将本次 1226 万行验证表述为亿级压测。ID 保留字符串，时间按小时解析。"
    )
    paragraph(
        "SQLite 共导入 6,213,379 行，外键校验无异常；独立原始计数、行数守恒、"
        + "Parquet 行数及 SQLite 行为汇总均已交叉核验。"
    )
    paragraph(
        "代码采用 4 空格、88 字符行宽、类型注解和 Google 文档字符串。"
        + "测试覆盖去重、非法输入、前导零 ID、标签边界和右截尾；实际检查日志随仓库提交。"
    )
    paragraph("四、文献调研与方法总结", "SectionCN")
    paragraph(
        "实际只有 1 万用户，与说明中的平台整体规模不同；来源及采样方式待带教确认。"
        + "缺少金额、订单、曝光及内容侧字段，因此不计算虚假 GMV、RFM 金额或跨场景归因。"
    )
    paragraph(
        "已整理 Wide & Deep、DIN、BST 三篇文献的方法、实验与适用限制，"
        + "形成比较笔记。方法总结：先确定样本与指标口径，再比较模型；论文效果不能直接迁移为本项目收益。"
    )
    paragraph("五、下一周安排：11/16 - 11/20", "SectionCN")
    for text in [
        "周一：跟进清洗口径与行为码确认，根据反馈固定数据版本及指标定义。",
        "周二：完善用户、商品与交互统计特征，记录计算窗口及字段说明。",
        "周三：检查候选覆盖、时间窗口和标签边界，完善特征防泄漏验证。",
        "周四：复核已完成的初步 LR 基线；视口径确认进度开展树模型对照。",
        "周五：汇总实际实验与问题，提交第二周报告；按带教反馈调整后续安排。",
    ]:
        paragraph(text)
    paragraph("六、未完成项与附件", "SectionCN")
    paragraph(
        "论文实验复现、完整预测特征、树/深度模型、融合解释性和最终 PPT 尚未完成。"
        + "已提前运行初步 LR，仅作诊断性探索，候选覆盖与预测效果仍需改进。"
    )
    paragraph("仓库：https://github.com/sshwdh/douyin-user-behavior-analysis")
    paragraph(
        "仓库含文献调研、质量报告、清洗口径确认单及代码。仓库已公开，可通过上述链接直接查看。"
    )
    charts = [
        (
            "行为结构与活跃趋势",
            "01_behavior.png",
            "图 1：各类行为事件数",
            "pv=浏览，fav=收藏，cart=加购，buy=购买。采用小时去重事件数；四类行为不构成严格四步漏斗。",
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
            "按整个观察期的小时去重事件数分组：1-9、10-49、50-99、100 及以上；分组受去重规则影响。",
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
        canvas.drawString(48, 23, "第一周工作汇报 | 2026-11-13")
        canvas.drawRightString(547, 23, f"{doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    """以当前目录为项目根目录生成 PDF。"""
    build(Path.cwd())


if __name__ == "__main__":
    main()
