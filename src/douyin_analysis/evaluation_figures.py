"""从已保存的汇总生成评估图，不重新访问样本或拟合模型。"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.font_manager import FontProperties

from douyin_analysis.evaluation_supplement import OUTPUT

NAMES = {"lr_24": "LR24 加权", "lr_24_unweighted": "LR24 未加权", "hgb_31": "HGB31"}
COLORS = {"lr_24": "#DDA147", "lr_24_unweighted": "#55A3AC", "hgb_31": "#15667A"}


def finish(figure: plt.Figure, output: Path, name: str) -> None:
    """统一保存清晰的结果图并释放资源。"""
    figure.tight_layout(pad=2)
    figure.savefig(output / name, dpi=180, facecolor="white")
    plt.close(figure)


def plot_curves(root: Path, output: Path) -> None:
    """复用已有抽点曲线；图例指标来自全量分数计算结果。"""
    curves = pd.read_csv(root / "reports/dashboard/research/curves.csv")
    metrics = pd.read_csv(root / "reports/dashboard/research/metrics.csv").set_index(
        "model"
    )
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for name, label in NAMES.items():
        for axis, kind, metric in zip(
            axes, ["roc", "pr"], ["roc_auc", "pr_auc_average_precision"]
        ):
            frame = curves[(curves.model == name) & (curves.kind == kind)].sort_values(
                "order"
            )
            axis.plot(
                frame.x,
                frame.y,
                color=COLORS[name],
                label=f"{label}: {metrics.loc[name, metric]:.4f}",
            )
    axes[0].plot([0, 1], [0, 1], "--", color="#999999", linewidth=1)
    axes[0].set(
        title="ROC / 全范围",
        xlabel="假阳性率",
        ylabel="真阳性率",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    axes[1].axhline(2525 / 1061515, color="#999999", linestyle="--")
    axes[1].set(
        title="PR / 精确率放大至 0.15",
        xlabel="召回率",
        ylabel="精确率",
        xlim=(0, 1),
        ylim=(0, 0.15),
    )
    for axis in axes:
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
    finish(figure, output, "roc_pr_reused.png")


def plot_learning(output: Path) -> None:
    """展示训练规模曲线，不用视觉曲线替代数值评价。"""
    table = pd.read_csv(output / "learning_curves.csv")
    figure, axes = plt.subplots(1, 3, figsize=(12, 4))
    for axis, (name, label) in zip(axes, NAMES.items()):
        frame = table[table.model == name]
        axis.plot(
            frame.fraction * 100,
            frame.train_ap,
            "o--",
            color="#97A7AE",
            label="训练子集 AP",
        )
        axis.plot(
            frame.fraction * 100,
            frame.validation_ap,
            "o-",
            color=COLORS[name],
            label="固定验证集 AP",
        )
        axis.set(
            title=label,
            xlabel="训练样本比例 (%)",
            ylabel="Average Precision",
            xticks=[10, 30, 60, 100],
        )
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    finish(figure, output, "learning_curves.png")


def summarize_benchmarks(output: Path) -> pd.DataFrame:
    """汇总实际测量重复的分位耗时、CPU 时间及进程高水位内存。"""
    raw = pd.concat([pd.read_csv(output / f"benchmark_{name}.csv") for name in NAMES])
    result = (
        raw.groupby(["model", "batch_size"])
        .agg(
            repeats=("wall_ms", "size"),
            median_ms=("wall_ms", "median"),
            p95_ms=("wall_ms", lambda values: values.quantile(0.95)),
            median_cpu_ms=("cpu_ms", "median"),
            peak_rss_mib=("process_peak_rss_mib", "max"),
            model_bytes=("model_file_bytes", "first"),
        )
        .reset_index()
    )
    result["rows_per_second"] = result.batch_size / (result.median_ms / 1000)
    result.to_csv(output / "benchmark_summary.csv", index=False)
    return result


def plot_benchmarks(output: Path) -> None:
    """画批量推理中位耗时和存档文件大小，两者均为本机实测。"""
    table = summarize_benchmarks(output)
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    for name, label in NAMES.items():
        frame = table[table.model == name].sort_values("batch_size")
        axes[0].plot(
            frame.batch_size, frame.median_ms, "o-", color=COLORS[name], label=label
        )
        axes[1].bar(label, frame.model_bytes.iloc[0] / 1024, color=COLORS[name])
    axes[0].set(
        xscale="log",
        yscale="log",
        xlabel="批大小（对数轴）",
        ylabel="中位耗时 ms（对数轴）",
        title="预处理 + predict_proba / 单线程",
    )
    axes[0].legend(fontsize=8)
    axes[1].set(ylabel="KiB（未压缩 joblib 包）", title="模型文件大小")
    finish(figure, output, "inference_benchmark.png")


def plot_confusion(root: Path, output: Path) -> None:
    """复用固定阈值的计数，按行归一化配色并显示原计数。"""
    metrics = pd.read_csv(root / "reports/dashboard/research/metrics.csv").set_index(
        "model"
    )
    figure, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    for axis, (name, label) in zip(axes, NAMES.items()):
        row = metrics.loc[name]
        true_negative = row.rows - row.positives - row.false_positive
        counts = np.array(
            [
                [true_negative, row.false_positive],
                [row.false_negative, row.true_positive],
            ]
        )
        rates = counts / counts.sum(axis=1, keepdims=True)
        axis.imshow(rates, cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2):
                axis.text(
                    j,
                    i,
                    f"{int(counts[i, j]):,}\n{rates[i, j]:.2%}",
                    ha="center",
                    va="center",
                    color="white" if rates[i, j] > 0.5 else "#193B4B",
                )
        axis.set(
            title=label,
            xlabel="预测标签",
            ylabel="实际标签",
            xticks=[0, 1],
            yticks=[0, 1],
        )
    finish(figure, output, "confusion_reused.png")


def run(root: Path) -> None:
    """按已有 CSV 生成报告图，中文字体使用本机可用字体。"""
    plt.switch_backend("Agg")
    font = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    if font.exists():
        plt.rcParams["font.family"] = FontProperties(fname=font).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    output = root / OUTPUT
    plot_curves(root, output)
    plot_learning(output)
    plot_benchmarks(output)
    plot_confusion(root, output)


if __name__ == "__main__":
    run(Path.cwd())
