# Streamlit 双看板说明

更新：2026-11-22。首版已接入既有公开结果，不训练模型、不读取原始用户明细。参考《双看板大纲》分阶段实施。

## 启动

在仓库根目录的 Python 3.12 环境安装 `python -m pip install -e '.[dashboard]'`，运行 `python -m streamlit run scripts/run_dashboard.py --server.address 127.0.0.1 --browser.gatherUsageStats false`，浏览器打开终端提供的本机地址。需保留仓库内 reports 和 outputs；单独复制入口脚本不能运行。Streamlit 版本固定为 1.67.0。`requirements-dashboard-lock.txt` 保存此次运行环境；首批分析环境锁文件保持不变。中文路径在 ASCII 区域设置下，安装与启动命令前加 `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`。

首版只加载小型公开汇总；每次交互重新读取，避免缓存过期。目前不支持任意类别、日期下重算全量去重人数，也不提供用户级明细。

## 指标与筛选范围

| 展示 | 来源 | 分母与边界 | 首版交互 |
|---|---|---|---|
| 事件、用户、商品、类目 | reports/quality.json | 全观察期；实体去重；重复事件保留 | 固定全期 |
| 每日事件、日活跃、日行为码4用户 | reports/daily.csv | 每日独立去重；不可累加用户数作为区间人数 | 日期、指标切换，仅影响每日趋势 |
| 小时分布 | reports/hourly.csv | 所有日期按一天中小时合并；非精确会话 | 固定全期 |
| 类目排行 | reports/categories.csv | 按事件数排序；非曝光排行 | 展示前5至30项，不受日期筛选影响 |
| 特征目录 | reports/features/feature_catalog.csv | 24基础、6实验；3类目建议未实现 | 按层级筛选、Excel下载 |
| 样本正例率 | reports/features/sample_summary.csv | 正标签候选对 / 全部候选对 | 固定验证窗 |
| 候选覆盖率 | 同上 | 候选中未来码4对 / 未来全部码4对 | 固定验证窗 |
| AP、ROC AUC、Precision、Recall、F1 | 三次实验 metrics.json | 同一验证样本；Recall分母为候选内正例 | 模型对照 |
| 混淆矩阵 | 同上 | 原实验验证集选定阈值，计数单位为用户商品对 | 选择模型 |
| PR、固定预算命中 | 已保存结果图 | PR图仅含HGB15/HGB31；预算为全局Top-K | 首版展示静态结果图 |

模型对照包含 LR10、LR24、HGB15、HGB31、HGB31的30特征实验。模型比较只读验证指标。测试集已经用于早期 LR 评估，后续结果不可宣传为独立最终测试结论。

类别加权已用于训练，验证集保持自然正例率；尚缺加权与不加权独立对照。页面不将分数解释为已校准概率，也不将验证最大 F1 阈值认定为业务阈值。

## 数据一致性

入口核对 daily、hourly、behavior 三张汇总事件总数是否等于 quality 的保留行数。模型加载核对 TP+FN=正例、TP+FP=预测正例、TN非负及各模型验证样本数一致；错误时提示停止展示对应结果。这些是首版一致性检查，不能替代完整数据版本校验。

## 后续范围

1. 生成可按日期、行为和类目查询的聚合数据，补充星期×小时热力图、用户活跃分布、商品排行与长尾分布。
2. 增加交互式 PR/ROC 和误报漏报分组，注明阈值与候选覆盖的限制。每用户 Top-K 需新定义，不能复用现有全局预算冒充。
3. 核验后整理截图、周报及演示说明。SHAP、校准、真正冷启动评估尚未实现，不生成占位结果。

缺少曝光、金额、订单、会话及退出字段，不展示曝光CTR、GMV、实际停留时长或退出率。小时内并列事件不能还原准确顺序；收藏、加购不是强制串联漏斗。

技术参考：[Streamlit 页面导航](https://docs.streamlit.io/develop/api-reference/navigation/st.navigation)、[AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)。
