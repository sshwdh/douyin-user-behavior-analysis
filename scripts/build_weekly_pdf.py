"""将已验证的第一周结果编排为三页中文 PDF。"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
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
    """读取质量报告，生成供本人核对后提交的 PDF。

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
    paragraph("抖音商城用户行为数据分析 · 提交前核对稿", "SectionCN")
    paragraph("实习开始：2026-11-06　｜　计划提交：2026-11-13")
    paragraph(
        "本稿记录 11/12 集中推进的实际成果，不倒填此前每日工作。汇报人姓名及个人收获待本人确认。"
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
            ["四元组重复记录", f"{quality['duplicate_rows']:,}（49.31%）"],
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
        "首要待确认问题：49.31% 的记录被小时去重规则折叠。"
        + "这可能含真实重复浏览，不能全部称为脏数据；已保存逐行为去重敏感性对照。"
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
    paragraph("四、难点与能力收获", "SectionCN")
    paragraph(
        "实际只有 1 万用户，与说明中的平台整体规模不同；来源及采样方式待带教确认。"
        + "缺少金额、订单、曝光及内容侧字段，因此不计算虚假 GMV、RFM 金额或跨场景归因。"
    )
    paragraph(
        "个人收获待本人补充：请结合亲自运行的例子，解释事件与用户指标的区别、"
        + "全局去重的必要性，以及为什么未来标签不能参与特征计算。"
    )
    paragraph("五、下一周安排：11/16 - 11/20", "SectionCN")
    for text in [
        "周一：补全文献精读，构建用户、商品、交叉窗口特征，核验候选覆盖。",
        "周二：RF、偏好与序列特征，完善小时并列行为及边界测试。",
        "周三：稀疏 SVD、共现与特征筛选，严格限制拟合数据范围。",
        "周四：固定七日标签，完成时间外推 LR 与 7:2:1 分层对照。",
        "周五：树模型、不平衡处理初步对照，提交第二周汇报与实验表。",
    ]:
        paragraph(text)
    paragraph("六、未完成项与附件", "SectionCN")
    paragraph(
        "论文实验复现、完整预测特征、树/深度模型、融合解释性和最终 PPT 尚未完成。"
        + "不以已编写脚本代替训练证据。GitHub 发布以远端文件为准；助教接收渠道待提供。"
    )
    paragraph("仓库：https://github.com/sshwdh/douyin-user-behavior-analysis")
    paragraph(
        "附件：analysis_report.md、quality.json、结果图片、代码测试及四周执行计划。"
    )
    story.append(PageBreak())
    paragraph("关键结果图", "TitleCN")
    paragraph("图 1：每日活跃用户（全部行为用户按日去重）", "SectionCN")
    story.append(
        Image(str(root / "reports/figures/02_daily.png"), width=495, height=270)
    )
    paragraph(
        "12 月 12 日出现活跃峰值；是否由活动驱动仍需结合业务信息验证。", "CaptionCN"
    )
    story.append(Spacer(1, 12))
    paragraph("图 2：每日购买用户（行为码为 4 的去重用户）", "SectionCN")
    story.append(
        Image(str(root / "reports/figures/03_daily.png"), width=495, height=270)
    )
    paragraph("购买用户不等于订单数；完整八类图表及汇总 CSV 见附件目录。", "CaptionCN")
    document.build(story)


def main() -> None:
    """以当前目录为项目根目录生成 PDF。"""
    build(Path.cwd())


if __name__ == "__main__":
    main()
