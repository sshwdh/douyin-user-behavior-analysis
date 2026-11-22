"""读取公开汇总结果，核验看板计数并构造固定窗口模型指标。"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"


def read_report(name: str) -> pd.DataFrame:
    """读取仓库内 CSV，拒绝越出 reports 目录的路径。

    Args:
        name: 相对于 reports 的 CSV 路径。

    Returns:
        未修改的汇总表。
    """
    path = (REPORTS / name).resolve()
    if not path.is_relative_to(REPORTS.resolve()) or path.suffix != ".csv":
        raise ValueError("仅允许读取 reports 内的 CSV")
    return pd.read_csv(path)


def overview() -> dict[str, int | str]:
    """读取质量报告并核对三个独立汇总表的事件总数。

    Returns:
        质量报告；不一致时拒绝展示过期数字。
    """
    result = json.loads((REPORTS / "quality.json").read_text(encoding="utf-8"))
    for name in ["daily.csv", "hourly.csv", "behavior.csv"]:
        if int(read_report(name)["events"].sum()) != result["clean_rows"]:
            raise ValueError(f"{name} 与清洗记录总数不一致，请重新生成汇总")
    return result


def select_days(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """按包含首尾日期的范围筛选每日汇总，不累加去重用户数。

    Args:
        frame: 含 day、events、dau、buyers 的每日汇总。
        start: 起始自然日。
        end: 结束自然日。

    Returns:
        按日期排序的独立副本。
    """
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    days = pd.to_datetime(frame["day"]).dt.date
    return frame.loc[days.between(start, end)].sort_values("day").copy()


def model_metrics() -> pd.DataFrame:
    """合并已有验证指标，不读取测试预测或执行训练。

    Returns:
        每个已运行模型一行，额外校验混淆矩阵计数。
    """
    records = []
    for experiment in ["lr_2026-11-17", "tree_validation_2026-11-17"]:
        path = REPORTS / "experiments" / experiment / "metrics.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, model in payload["models"].items():
            records.append({"model": name, **model["validation"]})
    path = REPORTS / "experiments/temporal_features_2026-11-18/metrics.json"
    extended = json.loads(path.read_text(encoding="utf-8"))["models"]["extended30"]
    records.append({"model": "hgb_31_extended30", **extended})
    frame = pd.DataFrame(records).set_index("model")
    frame["true_negative"] = (
        frame["rows"] - frame["positives"] - frame["false_positive"]
    )
    if not (frame.true_positive + frame.false_negative == frame.positives).all():
        raise ValueError("正例与混淆矩阵不一致")
    if (
        not (
            frame.true_positive + frame.false_positive == frame.predicted_positive
        ).all()
        or (frame.true_negative < 0).any()
    ):
        raise ValueError("预测计数与混淆矩阵不一致")
    if frame["rows"].nunique() != 1 or frame["positives"].nunique() != 1:
        raise ValueError("模型验证样本不一致，不能直接比较")
    return frame
