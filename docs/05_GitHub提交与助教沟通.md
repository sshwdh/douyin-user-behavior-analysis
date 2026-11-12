# GitHub 提交与沟通

已核验 GitHub 账号为 sshwdh，项目私有仓库：https://github.com/sshwdh/douyin-user-behavior-analysis 。助教接收渠道和访问账号仍未提供，尚未代发。原始 CSV、原始 PDF/Excel、数据库、用户级特征及模型文件不纳入提交。

仓库使用 `douyin-user-behavior-analysis`，私有可见。拿到助教账号后再邀请其访问；仓库链接本身不会授予访问权限。

## 新仓库首次发布

以下为新环境的首次配置参考；本地 origin 已配置，不要重复添加：

```bash
git remote add origin https://github.com/sshwdh/douyin-user-behavior-analysis.git
git push -u origin main
git push -u origin dev
```

开发时从 dev 创建 `feature/任务名`，评审后合入 dev，再合 main。提交信息示例：`feat: add global behavior deduplication`、`test: cover invalid timestamps`。发布前运行 README 中所有质量检查；检查 `git ls-files` 没有数据、凭证或本地环境。

## 发给助教的文案（待真实链接后发送）

老师您好，这是第一周项目汇报。仓库链接：https://github.com/sshwdh/douyin-user-behavior-analysis ，首周版本 v0.1.0-week1。本次包含全量清洗、质量报告、SQL/SQLite、八类图表、方法说明和初步 LR 实验。实际数据为约 1226 万条行为、1 万用户；小时四元组去重折叠了 49.31% 记录，需请您确认去重口径和采样来源。下周重点完善特征、候选覆盖和模型对照。仓库为私有，请提供 GitHub 用户名以便开通查看权限。

发送时附上具体 commit 或 release 链接，避免老师看到持续变化的未完成分支。只有确实完成的内容才能保留在文案中。
