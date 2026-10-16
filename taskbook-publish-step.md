## 发布步骤（GitHub Pages 内容站 · 产出落盘后执行）

> 唯一推送者：仅「每日总复盘 15:30」执行推送（--push），其余任务只跑到 dry-run。
> 15:30 之后时点的产出（如 15:31 v2 引擎）顺延并入次日发布。
> 韧性条款：推送失败（如 GitHub 集成未授权/网络异常）时，记录失败原因并继续完成其余交付，**不得阻塞任务主产出**；内容站更新可顺延，脱敏门禁不过则绝不推送。

1. 确认产出已写入 /Users/lianghaizhen/WorkBuddy/<任务名>/<YYYY-MM-DD>/
2. dry-run（默认，不推送；双层脱敏门禁：个人数据零残留才放行，fail-closed）：
   /Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3 \
     /Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan/scripts/publish_to_github.py \
     --date <YYYY-MM-DD>
   退出码（以 publish_to_github.py 为准）：0=门禁通过｜1=脱敏门禁拦截（个人数据残留→停止发布并报告明细）｜2=当日无产出（非交易日→静默结束）｜3=站点生成失败｜4=manifest 失败｜5=结构幂等失败
3. 推送（仅 15:30 总复盘任务）：--push 模式输出 manifest 契约（_stage/manifest.json 全量快照含 sha256，乱序/首推不断链），按 manifest 调用
   mcp__github__push_files(owner=seaquake970623, repo=daily-market-pulse, branch=main,
   files=[{path, content}...], message='daily: <YYYY-MM-DD>')
4. 推送成功后核对 manifest pushed 标记；GitHub Pages 自动重建站点（首次需在仓库 Settings→Pages→Source 选 main branch /docs 开启一次）
