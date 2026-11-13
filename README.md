# 抖音商城用户行为数据分析

基于提供的历史行为样本，构建可复现的数据清洗、质量核查与探索分析流程。实习周期自 2026-11-06 开始；第一周提交日期为 2026-11-13。

[![quality](https://github.com/sshwdh/douyin-user-behavior-analysis/actions/workflows/quality.yml/badge.svg)](https://github.com/sshwdh/douyin-user-behavior-analysis/actions/workflows/quality.yml)

## 第一周交付

- [第一周 PDF 周报：六页，含八张结果图](output/pdf/2026-11-13_第一周项目汇报.pdf)
- [第一周工作记录](docs/weekly/2026-11-13_第一周汇报.md)
- [数据处理与分析报告](reports/analysis_report.md)
- [文献调研笔记](docs/04_文献阅读起点.md)
- [清洗口径核查与确认事项](docs/07_第一阶段清洗口径确认单.md)

已完成：全量数据校验、小时四元组去重、Parquet 导出、SQLite 结构化存储、八类探索图表、质量检查及三篇文献调研。

已开展的补充探索：[逻辑回归基线](reports/lr_baseline_report.md)。完整特征体系、树模型、深度模型与最终演示尚未完成，按[项目计划](docs/01_项目执行计划.md)推进。

## 数据与指标边界

原始记录 12,256,906 条，按当前去重口径保留 6,213,379 条，涉及 10,000 名用户。数据范围为 2025-11-18 至 2025-12-18。详细字段与统计定义见[口径说明](docs/02_口径与技术说明.md)。

49.31% 的记录被小时四元组规则合并，可能包含同小时真实重复行为，业务口径待确认。数据缺少订单号、金额与曝光字段，不能据此计算真实订单数、GMV 或曝光 CTR。样本结论不代表平台总体。

仓库为 Public，仅发布代码、说明和汇总结果。原始资料、用户明细、Parquet、数据库及环境文件不纳入 Git；复现需另行取得授权数据。

## 环境与复现

建议使用 Python 3.12。以下命令在仓库根目录运行；本地需放置原始文件 `../user_behavior.csv`，或修改 `--input` 指向实际位置。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e '.[dev,reports]'
.venv/bin/python -m douyin_analysis.pipeline --input ../user_behavior.csv
.venv/bin/python -m douyin_analysis.sqlite_store
.venv/bin/python -m douyin_analysis.plots
.venv/bin/python -m douyin_analysis.reporting
```

`requirements-lock.txt` 记录首批结果生成环境；`pyproject.toml` 声明直接依赖。清洗命令会重建指定项目目录中的工作表和派生文件，SQLite 命令会重建本地分析数据库。原始 CSV 只读。

可选基线运行：

```bash
.venv/bin/python -m douyin_analysis.modeling
```

该基线采用七日历史与七日标签窗，验证集选阈值后固定在测试集评估。运行结果及候选覆盖限制见基线报告；并非线上验证结果。

## 质量验证

```bash
.venv/bin/python scripts/run_checks.py
.venv/bin/python scripts/validate_outputs.py
```

第一条执行 Black、isort、flake8、mypy、pylint、自定义规范检查和 pytest；第二条需要已有 Parquet、SQLite 与原始画像汇总，执行跨格式一致性核验。结果分别保存在 `reports/quality_checks.txt` 和 `reports/output_validation.json`。CI 状态见页首徽章。

首周 PDF 可用 `.venv/bin/python scripts/build_weekly_pdf.py` 重建。该脚本是固定日期的首周报告排版入口，不用于自动生成后续周报；分析报告生成器不会覆盖已发布周报。

## 目录

| 路径 | 内容 |
|---|---|
| `src/douyin_analysis/` | 清洗、数据库、绘图、分析报告与基线模块 |
| `tests/` | 核心规则单元测试与流程集成测试 |
| `scripts/` | 质量检查、产物校验与首周 PDF 生成 |
| `sql/` | 参数化查询示例与分析 SQL |
| `docs/` | 项目计划、指标口径、特征字典、调研及周报 |
| `reports/` | 汇总结果、图表、指标与检查记录 |
| `output/pdf/` | 正式提交的 PDF |

## 开发约定

遵循项目提供的 Python 编码规范：4 空格、88 字符行宽、双引号、绝对导入、Google docstring、公共接口类型注解、参数化 SQL 和核心逻辑测试。详细核对见[规范审查记录](docs/08_编码规范审查记录.md)。

从 `dev` 创建 `feature/*` 或 `chore/*` 分支，提交遵循 Conventional Commits。合入前执行质量检查及代码审查；带教业务评审状态独立记录，不以自动检查代替。
