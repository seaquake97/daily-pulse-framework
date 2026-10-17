# 云端自动化说明（GitHub Actions）

> 配套文件：`.github/workflows/daily_pulse.yml`
> 配套文档：本地发布流程见 [DEPLOY-GUIDE.md](./DEPLOY-GUIDE.md)
> 面向「新人接手 / 从零恢复定时任务」：照着做即可，无需记忆。
> 本文所有命令与参数均核对自 `scripts/publish_to_github.py`、`scripts/push_repo.py`、
> `framework/scripts/paths.py`，不含臆造内容。

---

## 0. 一句话心智模型

云端 Actions 与本地发布**共用同一条产物链路**，只是「内容从哪来」不同：

```
本地：WorkBuddy 任务目录 --> publish_to_github.py --> _stage --> push_repo.py --> _git_pulse
云端：内容源（content/ 或内容仓）--> publish_to_github.py --> _stage --> push_repo.py --> _git_pulse
```

- 云端**不是**另一套发布器：同样是 `publish_to_github.py` 构建 `_stage`、写 `manifest.json`，
  再由 `push_repo.py` 把 `_stage/docs` 同步进 `_git_pulse` 并 `git push`。
- 云端**不产生内容**：5 个每日任务的原始产出仍由本地任务生成，必须上传到内容源后云端才能构建。
- 工具仓（含 `scripts/`、`framework/`）与 Pages 内容仓（`daily-market-pulse`）是**两个仓库**，
  本 workflow 只能放在工具仓。

---

## 1. 前置条件（三项，均需用户确认）

| 序号 | 事项 | 为什么 | 状态 |
|------|------|--------|------|
| 1 | 把工具仓推送到一个 GitHub 仓库（如 `seaquake97/daily-market-pulse-tools`） | Actions 只对 GitHub 上的仓库生效；当前 `github-ip-plan` 是本地仓，无 remote | **需用户确认** |
| 2 | 配置 Secret `GH_PAT` | 云端无本地 `~/.config/gh-ip/token`，推送必须注入令牌 | **需用户确认** |
| 3 | 选定内容源（工具仓 `content/` 目录 或 独立内容仓） | 云端读不到本机 WorkBuddy 任务目录 | **需用户确认** |

### 1.1 为什么本 workflow 不能放进 `daily-market-pulse`

`daily-market-pulse`（本地副本 `_git_pulse`）只有 `LICENSE`、`NOTICE`、`README.md`、`docs/`，
没有 `scripts/publish_to_github.py`。把 workflow 放进去会在第一步就失败。
workflow 内已内置「仓库结构自检」步骤：找不到 `scripts/publish_to_github.py` 立即报错并说明原因。

---

## 2. Secrets 与 Variables 配置（需用户操作）

路径：仓库 `Settings` -> `Secrets and variables` -> `Actions`。

### 2.1 Secrets（敏感，值不可回读）

| 名称 | 取值 | 说明 |
|------|------|------|
| `GH_PAT` | fine-grained PAT | 需对目标 Pages 仓具备 **Contents: Read and write**；若用内容仓方案，还需对该仓有 **Contents: Read** |

创建步骤：GitHub 右上角头像 -> `Settings` -> `Developer settings` ->
`Personal access tokens` -> `Fine-grained tokens` -> `Generate new token`：

1. Resource owner 选 `seaquake97`；
2. Repository access 选 `Only select repositories`，勾选 `daily-market-pulse`（以及内容仓，若使用）；
3. Permissions -> `Contents` 设为 `Read and write`（`Metadata` 会自动带出 Read）；
4. 生成后立刻复制，回到工具仓 `Settings -> Secrets and variables -> Actions -> New repository secret`，
   名称填 `GH_PAT`，粘贴保存。

> 到期后 Actions 会失败并提示「令牌校验失败 HTTP 401」。建议设置到期提醒，到期前按同样步骤换新值。
> 令牌只写到 runner 临时文件（权限 600），经环境变量 `GH_IP_TOKEN_PATH` 传给 `push_repo.py`，
> **不进命令行参数、不进 remote URL、不进 `.git/config`**，作业结束前清理。

### 2.2 Variables（非敏感配置，全部可留空走默认值）

| 名称 | 默认值 | 说明 |
|------|--------|------|
| `PUBLISH_OWNER` | `seaquake97` | Pages 内容仓 owner |
| `PUBLISH_REPO` | `daily-market-pulse` | Pages 内容仓名 |
| `PUBLISH_BRANCH` | `main` | 推送分支 |
| `CONTENT_REPO` | 空 | 内容仓 `owner/repo`；留空则回退到工具仓自带 `content/` 目录 |
| `MARKET_HOLIDAYS` | 空 | 休市日，逗号分隔，如 `2026-10-01,2026-10-02,2026-10-03` |
| `CI_EXCLUDE` | 空 | 门禁额外排除项，逗号分隔（相对路径子串），叠加在作业内置排除项之上 |
| `CI_MAX_SKIP` | 空 | 门禁跳过数硬闸。留空=只告警；给数字时跳过数超过它即判失败 |
| `CI_SKIP_NETWORK` | 空 | 设为 `true` 时给 ci_verify 传 `--skip-network`（当前清单无网络依赖项，开关预留） |

---

## 3. 时区与 cron 换算（重点）

**GitHub Actions 的 cron 一律按 UTC 解释**，界面上的运行时间、日志时间戳也都是 UTC。
北京时间 = UTC + 8，所以要把北京时间减 8 小时写成 cron。

| 北京时间 | 含义 | UTC 时间 | cron 表达式 |
|----------|------|----------|-------------|
| 09:28 | 竞价窗口 | 01:28 | `28 1 * * 1-5` |
| 11:00 | 午盘 | 03:00 | `0 3 * * 1-5` |
| 14:30 | 尾盘 | 06:30 | `30 6 * * 1-5` |
| 15:30 | 总复盘（当日完整发布） | 07:30 | `30 7 * * 1-5` |

字段含义：`分 时 日 月 周`。`1-5` 表示周一至周五（0 = 周日）。

### 3.1 为什么可以直接用北京日期当目标交易日

四个时点对应的 UTC 时刻是 01:28 / 03:00 / 06:30 / 07:30，**全部早于 UTC 16:00**。
北京时间比 UTC 快 8 小时，只有在 UTC 16:00 之后，北京才会跨到第二天。
因此这四个时刻的「UTC 日期」与「北京日期」恒为同一天，
workflow 直接取 `TZ=Asia/Shanghai date +%F` 作为目标交易日，无需任何跨日修正。

> 反例（不要照抄）：若把某时点设在北京 08:00（UTC 00:00），仍是同一天；
> 但若设在北京 07:00，对应 UTC 前一日 23:00，此时北京日期比 UTC 日期**快一天**，
> 直接用 UTC 日期就会打错日期。本项目没有这类时点。

### 3.2 时点如何影响发布范围

早于 15:30 的时点只发布该时刻的任务产物（`--task` 单任务），15:30 走全量：

| 时点 | 发布任务 | 说明 |
|------|----------|------|
| 09:28 | `stock-assistant` | 只发股票助手 |
| 11:00 | `fund-market` | 只发基金盘面 |
| 14:30 | `fund-guide` | 只发基金操作指引 |
| 15:30 / `all` | 全量 | 缺任一任务按 A-03 规则中止（退出码 2），不做「发 4 条看起来像成功」 |

### 3.3 cron 的两个已知限制

- **只有周一至周五，不懂法定休市**：cron 无法表达节假日。休市日请在仓库变量
  `MARKET_HOLIDAYS` 登记日期，workflow 命中后跳过构建与推送（输出说明后正常结束）。
- **不保证准点**：GitHub 在负载高时可能延后数分钟才启动，极端情况下会丢跑。
  因此 workflow 按 **UTC 小时**推断时点（01/03/06/07），而不是精确匹配分钟，避免抖动导致误判。
  若某次彻底未触发，用 `workflow_dispatch` 手动补跑即可（幂等）。

---

## 4. 内容源准备

`publish_to_github.py` 从 `--source-root` 读取原始产出，期望布局：

```
<content_root>/基金每日盘面分析（11:00）/2026-10-16/fund_market_analysis.md
<content_root>/股票助手/2026-10-16/stock_assistant.md
<content_root>/基金每日操作指引（14:30）/2026-10-16/fund_operation_guide.md
<content_root>/每日总复盘（15:30）/2026-10-16/stock_review.md
<content_root>/每日总复盘（15:30）/2026-10-16/daily_review.html
```

（任务目录名以 `scripts/publish_to_github.py` 的 `TASK_SOURCES` 为准。）

两种方案二选一：

- **方案 A（推荐）：独立内容仓** —— 本地任务跑完后把当日产出提交到内容仓，
  在工具仓设置变量 `CONTENT_REPO=seaquake97/daily-market-pulse-content`。
  workflow 会克隆该仓到 runner 临时目录作为 `--source-root`。
- **方案 B：随工具仓提交** —— 把产出放在工具仓的 `content/` 目录下一起推送。
  适合量小、无所谓仓库体积的场景（历史产出会一直累积）。

两者都没配置时，workflow 会在「准备内容源」步骤**明确报错并退出**，不会静默发布空站点。

---

## 5. 手动触发（workflow_dispatch）

路径：仓库 `Actions` -> `daily-pulse` -> `Run workflow`。

| 输入 | 取值 | 说明 |
|------|------|------|
| `target_date` | `YYYY-MM-DD`，留空取北京时间当天 | 补跑历史日期用 |
| `slot` | `15:30`（默认）/ `09:28` / `11:00` / `14:30` / `all` | 决定只发该时点任务还是全量 |
| `push` | 复选框，默认**不勾选** | 勾选才真实推送；默认只构建校验，安全优先 |

等价的本地命令（对照理解）：

```bash
# 云端 slot=15:30 且勾选 push，等价于：
python3 scripts/publish_to_github.py --date 2026-10-16 --source-root <内容源> --push

# 云端 slot=11:00，等价于：
python3 scripts/publish_to_github.py --date 2026-10-16 --source-root <内容源> --task fund-market --push
```

---

## 6. 作业与步骤说明

### 6.1 `verify`（PR / push 到 main 触发）

只校验、不发布、不推送，PR 必过：

1. 检出工具仓 -> 准备 Python 3.13 -> 声明零依赖（不执行 `pip install`）；
2. 仓库结构自检（防止 workflow 被误放进 Pages 仓）；
3. 运行 `scripts/ci_verify.py --json`（文件缺失则跳过，不判定失败）；
4. P0 文本自检：workflow 与本文件不得含 emoji。

**本作业排除 `scan_compliance.py` 与 `verify_published.py`**，原因见 6.3。

### 6.2 `publish`（schedule / workflow_dispatch 触发）

1. 检出工具仓；
2. 用 `GH_PAT` 检出 Pages 内容仓到 `_git_pulse`（`fetch-depth: 0`，必须带完整历史，
   否则首次提交后 `git push` 会因非快进被拒）；
3. 准备 Python 3.13，登记 `PULSE_MANAGED_PY` 指向当前解释器
   （`paths.MANAGED_PY` 的本地默认值是托管解释器路径，云端必须覆盖）；
4. 计算目标交易日与时点、判断休市；
5. 准备内容源；
6. **以线上 `docs/` 预填 `_stage`**：云端 `_stage` 每次都是空的，若不预填，
   `push_repo.sync_stage` 会把「`_stage` 里没有的线上文件」判定为已删除并删掉，等于清空历史站点；
7. 准备令牌文件（仅勾选 push 时）；
8. 构建 `_stage`（不带 `--push`，先在云端验证构建不报错）；
9. 运行 `scripts/ci_verify.py --json` 推送前门禁（缺失则跳过），**排除 `verify_published.py`**；
10. 通过后再跑一次 `publish_to_github.py --push` 完成推送；
11. `verify_published.py` 发布后一致性校验（捕捉「推送成功但内容漂移」）；
12. 输出产物清单（`manifest.json` 摘要）；
13. 清理令牌文件（`if: always()`）。

并发控制：`concurrency.group: daily-pulse-publish`，`cancel-in-progress: false`
—— 同一时刻只允许一个发布作业排队执行，且不会取消已在跑的作业。

### 6.3 门禁为什么分两处跑、各自排除什么

`ci_verify.py` 的清单里既有**源码级测试**（16 套 + 2 个预留位），也有**产物级校验器**
（`scan_compliance.py`、`verify_published.py`、`strategies.py`）。后者依赖 `_stage`，
而 `_stage` 在两种场景下的状态完全不同，所以门禁必须拆开，不能无脑跑全量：

| 场景 | `_stage` 状态 | 排除项 | 原因 |
|------|---------------|--------|------|
| `verify` 作业（PR / main） | 不存在（被 `.gitignore` 排除，新检出里不会有） | `scan_compliance.py`、`verify_published.py` | `scan_compliance.py` 直接打开 `_stage/docs/index.html`，缺失时抛错并被判「合规护栏失守 = FAIL」，在 PR 场景纯属误报；`verify_published.py` 比对 `_stage` 与 `_git_pulse`，两者皆空时反而 PASS，在 PR 场景无意义 |
| `publish` 作业（推送前） | 已构建，与 `_git_pulse` **必然不一致** | `verify_published.py` | 它的职责就是比对两者、发现漂移即 FAIL；放进推送前门禁，任何一次真实的新内容发布都会被自己拦死 |
| `publish` 作业（推送后） | 已与 `_git_pulse` 同步 | 无 | 此时比对才有意义，用于捕捉「推送成功但内容漂移」 |

实现手法：`ci_verify.py` 只提供正向关键字 `--only`，没有 `--exclude`。
workflow 先用 `--list` 取全量清单，再把「未排除项」逐个作为 `--only` 传入。
好处是 QA 往清单里加项时 CI 自动纳入，不用回来改 workflow。

### 6.4 不要只信退出码

`ci_verify.py` 的退出码只区分「有失败项」（1）与「全通过」（0），SKIP 不算失败。
但产物缺失时，某些套件会用 `self.skipTest` 把用例整包跳过，退出码仍是 0
——调度器会把这种项从 PASS 降级为 SKIP（detail 里写明「绿灯不可信」），
`Ran 0 tests` 则直接判 FAIL。

因此 workflow 除了看退出码，还把每个 SKIP 项打成 `::warning::` 注解、
把结果表格写进 `GITHUB_STEP_SUMMARY`。**某天 skipped 数突然涨上去，多半是构建产物没生成，
不要当绿灯放过。** 需要硬闸时给仓库变量 `CI_MAX_SKIP` 设一个数字，超过即判失败。

---

## 7. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 定时任务一次都没跑 | 仓库是 fork（默认禁用 schedule）；或默认分支上没有该 workflow 文件；或仓库 60 天无活动被 GitHub 暂停 schedule | 确认文件在**默认分支**上；在 Actions 页手动触发一次可重新激活；fork 需在 Actions 页启用 |
| 定时任务延迟几分钟才启动 | GitHub 负载调度，正常现象 | 无需处理；workflow 按小时分桶推断时点，不会因此判错时点。对时效极敏感时用手动触发兜底 |
| 报「未配置内容源」 | 未设 `CONTENT_REPO`，工具仓也没有 `content/` | 按第 4 节配置其一，确认布局为 `<content_root>/<任务目录>/<日期>/<文件>` |
| 构建退出码 2 | 当日产物缺失（对应 `--task` 的文件不存在） | 检查内容源是否上传了当日该任务产物；修复后用 `workflow_dispatch` 重跑（幂等） |
| 构建退出码 3 | 站点生成失败 / 消毒失败 / 时点护栏 B-8 阻断 | 看步骤日志中 `[sanitize]`、`SITE_FILE` 相关输出；通常是产物陈旧于消毒代码，重跑即可 |
| 「令牌校验失败 HTTP 401/403」 | PAT 过期、被撤销，或权限不足 | 重新生成 fine-grained PAT，确认 `Contents: Read and write` 且已勾选目标仓；更新 `GH_PAT` |
| 「令牌身份与 --owner 不符」 | PAT 属于别的账号 | 用 `seaquake97` 账号生成令牌 |
| 推送被拒（non-fast-forward） | `_git_pulse` 检出时没带历史，或线上有新提交 | workflow 已用 `fetch-depth: 0`；若仍报，确认 `PUBLISH_BRANCH` 与实际默认分支一致 |
| 发布后线上少了历史页面 | 跳过了「以线上 docs 预填 `_stage`」步骤 | 恢复该步骤；它的作用是保证增量语义，避免 `sync_stage` 误删 |
| 日期打错（差一天） | 误把 UTC 日期当北京日期 | 本项目四个时点 UTC 与北京同日，不要额外做 ±1 天修正；改时点前先按第 3.1 节核算 |
| 休市日仍构建 | 未登记休市日 | 在 `MARKET_HOLIDAYS` 补上日期，逗号分隔 |
| 日志里出现令牌明文 | 不可能：GitHub 会自动遮蔽 Secret | 若真出现，立即吊销该 PAT 并重新生成 |
| 门禁报「合规护栏失守：emoji(P0) 指标行缺失」 | `_stage/docs/index.html` 不存在，`scan_compliance.py` 打开即抛错 | PR 场景属误报，workflow 已排除该项（见 6.3）；若你在本地手动跑全量，先构建 `_stage` |
| 推送前门禁卡在「漂移 N 个文件 \| 内容违规 0 处」 | `verify_published.py` 被误放进推送前门禁 | 它只能在推送**之后**跑；推送前 `_stage` 与 `_git_pulse` 必然不一致，属预期 |
| 门禁全绿但 `skipped` 数很大 | 套件整包 `skipTest`（产物缺失时常见），退出码仍是 0 | 看 `GITHUB_STEP_SUMMARY` 里哪些项标了 SKIP 及原因；需要硬闸就设 `CI_MAX_SKIP` |
| 本地跑 `ci_verify.py` 大面积红，报 `SyntaxError: f-string expression part cannot include a backslash` | 用了 Python 3.11 或更低版本 | 项目代码（如 `scan_compliance.py`）用了 3.12+ 才允许的 f-string 反斜杠写法。**必须 3.12 及以上**，workflow 已锁 3.13 |

---

## 8. 与本地流程的边界

| 环节 | 本地 | 云端 |
|------|------|------|
| 内容来源 | WorkBuddy 任务目录（`paths.WORKBUDDY_ROOT/<任务目录>/<日期>/`） | 内容源目录，由 `--source-root` 显式指定 |
| 构建 | `python3 scripts/publish_to_github.py --date <日期>` | 同一命令，加 `--source-root`，可选 `--task` |
| 门禁 | `scripts/ci_verify.py` | 同一脚本（缺失则跳过） |
| 推送 | `python3 scripts/publish_to_github.py --date <日期> --push` | 同一命令 |
| 令牌 | `~/.config/gh-ip/token`（权限 600） | runner 临时文件 + `GH_IP_TOKEN_PATH` |
| 发布后校验 | `scripts/verify_published.py` | 同一脚本 |
| `_stage` 基线 | 本地 `_stage` 跨日累积 | 每次从线上 `docs/` 复制预填 |

因此：**本地能跑通的命令，云端就一定能跑通**；云端失败的绝大多数情况是内容与令牌这两项外部输入没就位。

---

## 9. 自检记录（本次交付时实跑）

- YAML 解析：`yaml.safe_load` 通过，两个作业、4 条 cron、3 个 dispatch 输入齐全；
- Shell 语法：全部 `run` 块 `bash -n` 通过；
- 计划逻辑实测：UTC 01/03/06/07 分别推断为 09:28 / 11:00 / 14:30 / 15:30，
  对应单任务 `stock-assistant` / `fund-market` / `fund-guide` / 全量；
- 休市命中、日期格式校验、手动触发三种分支实测通过；
- 产物清单脚本用真实 `_stage/manifest.json` 跑通（74 个文件，当日 12 个）；
- `ci_verify.py --json` 基线实跑（Python 3.13）：21 项全 PASS，0 失败、0 跳过，耗时 5.9s；
  两个预留位（`test_fallback_fetcher.py`、`test_compute_signals.py`）已自动纳入并 PASS；
- 门禁排除逻辑实测：`--list` 取清单后按排除项生成 `--only` 参数集，
  确认 PR 场景只剩源码级套件与 `strategies` 校验器，推送前场景只剩 `verify_published` 被排除；
- 推送前漂移场景实测：人为改动 `_stage` 一个文件后 `verify_published.py` 判 FAIL
  （「漂移 1 个文件」），已据此把它移出推送前门禁并移入推送后校验。

未做实跑的部分：真实推送（需要 `GH_PAT`，属于需用户确认事项）。

## 10. 版本要求

- **Python 3.12 及以上**（workflow 锁 3.13）。项目代码里有 3.12+ 才允许的
  f-string 反斜杠写法（PEP 701），用 3.11 或更低版本跑 `scripts/scan_compliance.py`
  会直接 `SyntaxError`。macOS 自带的 `/usr/bin/python3` 是 3.9，**不能用**。
- 零第三方依赖：全流程不执行 `pip install`，`setup-python` 只为锁定解释器版本。
