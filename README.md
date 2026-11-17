# 抖音商城用户行为数据分析

基于提供的历史行为样本，构建可复现的数据清洗、质量核查与探索分析流程。实习周期自 2026-11-06 开始；第一周提交日期为 2026-11-13。

[![quality](https://github.com/sshwdh/douyin-user-behavior-analysis/actions/workflows/quality.yml/badge.svg)](https://github.com/sshwdh/douyin-user-behavior-analysis/actions/workflows/quality.yml)

## 2026-11-17 口径确认

带教通过用户确认采用 **用户＋商品＋行为＋自然小时** 分组。本批最大频次为 22，没有超过 100 次的组：**全部 12,256,906 条有效记录保留，不去重、不隔离**。此前跨商品暂行隔离的 1,316,083 条已恢复。详见[本次确认与核验记录](docs/daily/2026-11-17_清洗口径确认与全量重跑.md)。

行为码语义、时区、采样与采集完整性仍待确认；有记录覆盖全部 744 小时不等于证明完整采集。11/13 去重结果与 11/15 跨商品暂行结果仅供历史追溯，不作为当前分析依据。

## 第二周进展：窗口特征与 LR 对照

已在确认的全量保留数据上完成 **24 项窗口特征**、三个时间窗口样本、候选覆盖与防泄漏测试。详见[样本核验报告](docs/10_窗口特征与样本核验.md)及[特征字典](docs/03_特征字典.md)。测试窗口候选覆盖未来行为码 4 用户商品对的 16.39%，不能将后续候选内模型指标解释为全站推荐效果。

```bash
.venv/bin/python -m douyin_analysis.feature_audit --snapshot reports/audits/2026-11-17/data_snapshot.json
```

样本明细留本地；公开汇总及两张图见 `reports/features/`。已完成固定样本上的 LR 10/24 项特征对照，详见[实验报告与结果图](reports/lr_baseline_report.md)。24 项特征的测试 AP 仅略升，Recall 与 F1 下降，不能宣称明显改善；行为语义仍待确认。

## 第一周交付

- [第一周口径确认 PDF：含八张重跑结果图](output/pdf/2026-11-17_第一周项目汇报_口径确认版.pdf)
- [本次修订记录](docs/daily/2026-11-17_清洗口径确认与全量重跑.md)
- [数据处理与分析报告](reports/analysis_report.md)
- [文献调研笔记](docs/04_文献阅读起点.md)
- [清洗口径核查与确认事项](docs/07_第一阶段清洗口径确认单.md)

已完成：全量数据校验、保留重复交互与小时频次筛查、Parquet 导出、SQLite 结构化存储、八类探索图表、质量检查及三篇文献调研。

旧去重口径的逻辑回归指标已失效；[当前 LR 对照](reports/lr_baseline_report.md)已在全量保留版本上完成。已实现 24 项基础窗口特征；完整特征体系、树模型、深度模型与最终演示尚未完成，按[项目计划](docs/01_项目执行计划.md)推进。

## 数据与指标边界

原始记录 12,256,906 条，按确认分组保留 12,256,906 条，隔离 0 条，涉及 10,000 名用户。数据范围为 2025-11-18 至 2025-12-18。详细字段与统计定义见[口径说明](docs/02_口径与技术说明.md)。

正常重复交互全部保留。频次阈值仅作筛查，不证明恶意行为；当前未触发超阈值处置。未来新数据若触发，整组隔离策略仍须单独确认。数据缺少订单号、金额与曝光字段，事件次数不能替代订单数、GMV 或曝光 CTR。

仓库为 Public，仅发布代码、说明和汇总结果。原始资料、用户明细、Parquet、数据库及环境文件不纳入 Git；复现需另行取得授权数据。

## 环境与复现

建议使用 Python 3.12。以下命令在仓库根目录运行；本地需放置原始文件 `../user_behavior.csv`，或修改 `--input` 指向实际位置。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e '.[dev,reports]'
.venv/bin/python -m douyin_analysis.pipeline --input ../user_behavior.csv --threshold 100 --scope user_item_behavior_hour
.venv/bin/python scripts/analyze_hourly_frequency.py
.venv/bin/python -m douyin_analysis.sqlite_store
.venv/bin/python -m douyin_analysis.plots
.venv/bin/python -m douyin_analysis.reporting
.venv/bin/python -m douyin_analysis.data_audit --input ../user_behavior.csv --date 2026-11-17 --scope-confirmed
```

`requirements-lock.txt` 记录首批结果生成环境；`pyproject.toml` 声明直接依赖。清洗命令会重建指定项目目录中的工作表和派生文件，SQLite 命令会重建本地分析数据库。原始 CSV 只读。

固定窗口 LR 对照与报告：

```bash
.venv/bin/python -m douyin_analysis.lr_experiment
.venv/bin/python -m douyin_analysis.experiment_report
```

该基线采用七日历史与七日标签窗，验证集选阈值后固定在测试集评估。运行结果及候选覆盖限制见基线报告；并非线上验证结果。

## 质量验证

```bash
.venv/bin/python scripts/run_checks.py
.venv/bin/python scripts/validate_outputs.py
```

第一条执行 Black、isort、flake8、mypy、pylint、自定义规范检查和 pytest；第二条需要已有 Parquet、SQLite 与原始画像汇总，执行跨格式一致性核验。结果分别保存在 `reports/quality_checks.txt` 和 `reports/output_validation.json`。CI 状态见页首徽章。

口径确认 PDF 可用 `.venv/bin/python scripts/build_weekly_pdf.py` 重建。该脚本是固定修订日期的首周报告排版入口，不用于自动生成后续周报；分析报告生成器不会覆盖已发布周报。

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
