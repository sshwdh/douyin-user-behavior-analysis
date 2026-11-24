"""双看板的视觉层级、页面标题和通用图形样式。"""

from html import escape

import altair as alt
import streamlit as st

TEAL = "#147D92"
ORANGE = "#D98A39"


def style_page() -> None:
    """应用页面层级、主题卡片与响应式布局。"""
    st.markdown(
        """<style>
    .block-container{max-width:1440px;padding-top:1.8rem;padding-bottom:3rem;}
    [data-testid="stAppViewContainer"]{background:#F4F6FA;}
    [data-testid="stHeader"]{background:rgba(244,246,250,.94);}
    h1,h2,h3{letter-spacing:-.025em;color:#142D44;}
    h3{font-size:1.15rem!important;padding-top:.35rem!important;}
    [data-testid="stMetric"]{background:#FFF;border:1px solid #DFE7EE;
        border-radius:16px;padding:18px 20px;border-top:3px solid #208698;}
    [data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;font-weight:650;}
    [data-testid="stMetricLabel"]{color:#607184;font-size:.85rem;}
    [data-testid="stTabs"] [role="tablist"]{gap:12px;margin:12px 0 20px;}
    [data-testid="stTabs"] [role="tab"]{border-radius:8px 8px 0 0;padding:10px 18px;}
    [data-testid="stTabs"] [aria-selected="true"]{background:#E6F1F4;font-weight:650;}
    [data-testid="stVerticalBlockBorderWrapper"]{background:#FFF;border-radius:16px;}
    .hero{background:linear-gradient(115deg,#142D44 0%,#1B4E60 78%,#236F78 100%);
        border-radius:22px;padding:22px 28px;margin-bottom:16px;color:#FFF;}
    .hero .eyebrow{font-size:11px;letter-spacing:.16em;color:#9BD6D9;font-weight:650;}
    .hero h1{font-size:30px!important;color:#FFF;margin:6px 0!important;
        padding:0!important;line-height:1.3;}
    .hero p{font-size:14px;color:#D4E4ED;margin:0!important;
        line-height:1.8;max-width:950px;}
    .hero .badge{display:inline-block;margin-top:10px;padding:4px 10px;
        border:1px solid #6495A2;border-radius:20px;font-size:11px;color:#E2F0F4;}
    @media(max-width:700px){.hero{padding:23px}.hero h1{font-size:26px}
        .block-container{padding:4rem 1rem 1rem}.hero .eyebrow{font-size:10px}}
    </style>""",
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, label: str) -> None:
    """显示页面标题和范围说明，动态文本先转义。

    Args:
        title: 中文标题。
        subtitle: 业务阅读说明。
        label: 英文专题标签。
    """
    st.markdown(
        '<section class="hero"><div class="eyebrow">DOUYIN COMMERCE / '
        + f"{escape(label)}</div>"
        + f"<h1>{escape(title)}</h1><p>{escape(subtitle)}</p>"
        + '<span class="badge">离线研究 · 2025/11/18—12/18 观测样本</span></section>',
        unsafe_allow_html=True,
    )


def polish(chart: alt.Chart | alt.LayerChart) -> alt.Chart | alt.LayerChart:
    """统一图表文字、网格和视图边框。

    Args:
        chart: 已定义编码的单图或图层。

    Returns:
        配置为白底轻网格的图表。
    """
    return (
        chart.configure_view(strokeWidth=0)
        .configure_axis(
            gridColor="#EBF0F4",
            domain=False,
            tickSize=0,
            labelColor="#637587",
            titleColor="#42576B",
            labelFontSize=11,
            titleFontSize=12,
            titlePadding=12,
        )
        .configure_legend(orient="bottom", title=None, labelColor="#42576B", padding=12)
        .configure(background="transparent")
    )
