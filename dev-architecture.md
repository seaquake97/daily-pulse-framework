# dev-architecture.md — 每日产出 → GitHub 自动发布流水线 · 架构设计

> 角色：dev（软件开发）｜状态：**dry-run 全流程实测通过，待 team-lead 评审后启用真实推送**
> 配套：`scripts/publish_to_github.py`（编排器）、`scripts/build_site.py`（站点结构层）、
> `scripts/redline_hardening.py`（脱敏加固层）、`scripts/pipeline_selftest.py`（全量自测）、
> `site/methodology/index.html`（方法论页）、`evidence/`（实测证据包）

---

## 1. 总览

```
本地（每日定时任务产出）                本地工程目录                          公库
/Users/lianghaizhen/WorkBuddy/         github-ip-plan/
  基金每日盘面分析（11:00）/<date>/  →   scripts/  ──┐
  股票助手/<date>/                  →     ├─ desensitize.py（基础引擎）
  基金每日操作指引（14:30）/<date>/  →     ├─ redline_hardening.py（加固层）
  股票复盘/<date>/                  →     ├─ publish_to_github.py（编排器）
  每日总复盘（15:30）/<date>/        →     ├─ build_index.py（团队首页）
                                       └─ build_site.py（结构层）
                                            ↓ 脱敏+聚合+门禁
                                         _stage/（站点镜像 + manifest.json）
                                            ↓ manifest 契约（读取清单）
                                         【代理】mcp__github__push_files ──→ daily-market-pulse
                                                                              （GitHub Pages）
```

**核心边界**：本地无 SSH 密钥、无 gh CLI、无全局 git 身份、无 GITHUB_TOKEN——所有推送经
GitHub MCP 工具由代理侧执行。本地脚本的职责是「产出可推送的站点镜像 + 一份机器可读的
manifest 契约」；代理读取 manifest 后调用 `mcp__github__push_files` 完成推送。

---

## 2. 目录结构设计

### 2.1 本地工程目录（github-ip-plan/）

```
github-ip-plan/
├── scripts/
│   ├── desensitize.py          # 基础脱敏引擎（team-lead 维护，v3）
│   ├── redline_hardening.py    # 红线加固层（dev，第二道防线）
│   ├── publish_to_github.py    # 发布编排器（dev，七步流水线）
│   ├── build_index.py          # 聚合首页（team-lead 维护）
│   ├── build_site.py           # 站点结构层（dev：日期页/周月报/feed/sitemap/methodology）
│   └── pipeline_selftest.py    # 全量自测（dev，8 真实产出用例）
├── site/methodology/index.html # 方法论静态页源（dev，注入时间戳后发布）
├── _stage/                     # 站点镜像（推送前的完整快照）
│   ├── manifest.json           # 推送契约（清单/哈希/参数模板/pushed 状态）
│   └── docs/                   # ← 即仓库根目录内容
│       ├── index.html          # 聚合首页（build_index 生成）
│       ├── daily/<date>/       # 每期：meta.json + index.html + <slug>.md/.html
│       ├── weekly/<YYYY-Www>/  # 周归档
│       ├── monthly/<YYYY-MM>/  # 月归档
│       ├── methodology/        # 方法论页
│       ├── feed.xml            # RSS
│       └── sitemap.xml
└── evidence/                   # dry-run 实测证据包
```

### 2.2 仓库内结构（daily-market-pulse，Pages 根 = /docs）

```
docs/
├── index.html              # 首页：日报卡片列表（评级徽章/Σ/数据时点/链接）
├── daily/
│   └── 2026-10-14/
│       ├── index.html      # 日期导航页（当日全部产出入口）
│       ├── meta.json       # 期元数据（标题/评级/Σ/时点/任务清单）
│       ├── fund-market.md / .html      # 基金盘面分析
│       ├── stock-assistant.md / .html  # 股票助手
│       └── fund-guide.md               # 基金操作指引
├── weekly/2026-W42/index.html
├── monthly/2026-10/index.html
├── methodology/index.html  # 研判方法论（引擎七步/S1-S6/五档评级/红涨绿跌/免责声明）
├── feed.xml
└── sitemap.xml
```

发布路径约定 `docs/daily/<date>/<任务slug>.<ext>`（PM 策略 `/daily/YYYY-MM-DD/` 用户约定目录），
按日期天然隔离，幂等。

### 2.3 任务 slug 映射（与源文件名的差异处理）

| slug | 任务目录 | 源文件 | 发布名 |
|---|---|---|---|
| fund-market | 基金每日盘面分析（11:00） | fund_market_analysis.md/.html | fund-market.md/.html |
| stock-assistant | 股票助手 | stock_assistant.md/.html | stock-assistant.md/.html |
| fund-guide | 基金每日操作指引（14:30） | fund_operation_guide.md | fund-guide.md |
| stock-review | 股票复盘 | stock_review.md | stock-review.md |
| daily-review | 每日总复盘（15:30） | daily_review.html | daily-review.html |

> 总复盘目录下的 `stock_review.md` 与股票复盘目录同文件（MD5 一致），按 slug 去重只发布一次，
> 避免同日重复文件。总复盘无独立 md，只发布 html。

---

## 3. GitHub Pages 启用方案

首次上线（**待 team-lead 评审后执行，当前未创建仓库**）：

1. `mcp__github__create_repository(name="daily-market-pulse", description="每日市场脉搏 · 数据驱动的A股/基金每日研判档案", private=false, autoInit=true)`
   - private=false：公库（PM 决策：双公开仓库之一，内容主站）
   - autoInit=true：建立 main 分支与初始 README，Pages 有分支可指
2. 启用 Pages：仓库 Settings → Pages → Source: `main` 分支 / `/docs` 目录
   （MCP 工具集当前无 Pages 设置能力，需主理人在 GitHub 网页端一次性操作；或后续
   用 `mcp__github__create_or_update_file` 写入 `.github/workflows/pages.yml` 走
   Actions 部署——二选一，推荐前者，零配置）
3. 站点地址：`https://seaquake970623.github.io/daily-market-pulse/`
4. 验证：推送后访问首页 → 日期页 → methodology，检查 feed/sitemap 可读

备用通道（ Pages 网页端不可用时）：`mcp__github__create_or_update_file` 单文件写入，
适合热修单页；日常发布统一走 push_files 批量通道。

---

## 4. MCP push_files 调用时序

```
publish_to_github.py（本地）                代理（AI/定时任务）                GitHub
        │                                        │                            │
1. 收集+提取+双语 meta                          │                            │
2. 两段式脱敏 + 三重门禁                        │                            │
3. 站点镜像写入 _stage/docs/...                 │                            │
4. 写 _stage/manifest.json（含 pushed=false）    │                            │
5. --push：打印调用参数，退出                    │                            │
        │                                        │                            │
        │  6. 读取 manifest.json                 │                            │
        │───────────────────────────────────────>│                            │
        │                                        │  7. 读取 _stage/<path> 内容  │
        │<───────────────────────────────────────│                            │
        │                                        │  8. mcp__github__push_files │
        │                                        │  (owner, repo, branch,     │
        │                                        │   files=[{path,content}],  │
        │                                        │   message="daily: <date>") │
        │                                        │───────────────────────────>│
        │                                        │  9. commit SHA             │
        │                                        │<───────────────────────────│
        │  10. manifest.pushed=true + commit SHA │                            │
        │<───────────────────────────────────────│                            │
```

**push_files 参数要点**（dry-run 中已完整走查）：
- content 为明文字符串，无需 base64
- files 数组单次调用上限约 20+ 个文件（当前全量快照 22 个，实测一次调用可承载；
  如未来超限，按「daily 内容文件 / 站点文件」分两批）
- message 规范：`daily: <date> (<评级> Σ<分值>)`，便于仓库历史追溯

---

## 5. 每日增量发布流程

单一发布者：15:30 总复盘任务产出后一次性发布（PM 决策）。编排器七步：

| 步 | 动作 | 失败退出码 |
|---|---|---|
| 1 收集 | 从 5 个任务目录取 `<date>` 产出，按 slug 去重 | 2（无产出） |
| 2 提取 | market_data.json 的 verdict → Σ评级/时点；md 首行 → 标题 | — |
| 3 双语 | meta.json（title_zh/en、summary_zh/en、rating、sigma、data_stage、tasks） | — |
| 4 脱敏 | 两段式：desensitize.py → redline_hardening.py；三重门禁（check_residual / harden_verify / PM 红线 grep） | **1（个人数据残留，禁止推送）** |
| 5 聚合 | build_index.py（首页）+ build_site.py（日期页/周月报/feed/sitemap/methodology） | 3 |
| 6 清单 | manifest.json 全量快照（所有日期 daily 文件 + 站点文件 + sha256） | 4 |
| 7 推送 | --push 模式打印 MCP 调用参数；代理执行 | — |

用法：
```bash
PY=/Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3
$PY scripts/publish_to_github.py --date 2026-10-14            # dry-run（默认）
$PY scripts/publish_to_github.py --date 2026-10-14 --task fund-market   # 只发一个任务
$PY scripts/publish_to_github.py --date 2026-10-14 --push     # 输出 MCP 推送指令
```

退出码规范：`0` 成功｜`1` 脱敏门禁失败｜`2` 无产出/参数错误｜`3` 站点生成失败｜
`4` manifest 失败｜`5` 结构/幂等校验失败（pipeline_selftest 用）。

> **退出码唯一口径（team-lead 2026-10-14 裁决）**：以 `publish_to_github.py`
> 为准（0=成功/1=门禁失败/2=无产出或参数错误/3=站点生成失败/4=manifest 失败/
> 5=结构幂等失败）。`pipeline_selftest.py` 聚焦脱敏层验证，其退出码 2 在
> 自测语境下表示「误杀」；任务书与对外文档一律引用 publish_to_github.py 的定义。

---

## 6. 失败重试与断点

- **门禁失败（退出码 1）**：当日不推送，暂存区保留现场；修复规则后重跑同日期命令即可
  （暂存按日期目录隔离，不会污染其他日期）。
- **推送失败**：manifest.pushed 仍为 false，代理重读 manifest 重试；push_files 为
  upsert 语义，重推不产生重复文件——**幂等由三层保证**：①日期目录隔离 ②manifest
  全量快照 + sha256 比对 ③脱敏输出逐字节确定（同输入同输出，实测二次执行哈希一致）。
- **断点续跑**：_stage/ 是累积的站点镜像，任何一天重跑只会重算该日期文件与全局
  站点文件；已推送日期的内容文件哈希不变，代理可跳过未变文件（比对 manifest）。
- **非交易日**：任务静默不产出 → publish 收集为空 → 退出码 2，无副作用。

---

## 7. 与定时任务衔接点（草案，待 team-lead 评审后写入任务书）

> 以下为建议追加到各定时任务书末尾的「发布步骤」文本，**先评审、不直接改任务书**。

```text
## 发布步骤（产出落盘后执行）

1. 确认产出文件已写入 /Users/lianghaizhen/WorkBuddy/<任务名>/<YYYY-MM-DD>/
2. 执行 dry-run（默认，不推送）：
   /Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3 \
     /Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan/scripts/publish_to_github.py \
     --date <YYYY-MM-DD>
   - 退出码 0：门禁通过，进入推送
   - 退出码 1：脱敏门禁拦截（个人数据残留）→ 停止发布，报告残留明细
   - 退出码 2：当日无产出（非交易日）→ 静默结束
3. 推送（仅 15:30 总复盘任务执行；其他任务只跑到 dry-run）：
   同上命令加 --push，按输出的 manifest 契约调用
   mcp__github__push_files(owner=seaquake970623, repo=daily-market-pulse,
   branch=main, files=[{path,content}...], message='daily: <date>')
4. 推送成功后把 _stage/manifest.json 的 pushed 置 true
```

---

## 8. 模块分工与接口（与 team-lead 的模块边界）

| 模块 | 归属 | 接口 |
|---|---|---|
| desensitize.py | team-lead | `desensitize_text(raw) -> (text, stats)`；`check_residual(text) -> list` |
| redline_hardening.py | dev | `harden(text, fmt) -> (text, report)`；`harden_verify(text) -> list` |
| build_index.py | team-lead | CLI：`--daily-dir --out`；读 daily/*/meta.json，写 docs/index.html |
| build_site.py | dev | CLI：`--stage [--base-url]`；输出 SITE_FILE: 行协议 |
| publish_to_github.py | dev | 编排上述全部；退出码规范；manifest 契约 |
| pipeline_selftest.py | dev | 8 真实产出用例：泄漏/误杀/幂等/结构四维验证 |

两段式脱敏的数据流：`raw → desensitize_text → harden → 三门禁 → _stage`。
加固层设计为可叠加于任何基础引擎（幂等、幂格式），基础引擎升级不影响加固层。

---

## 9. 脱敏防线与实测结论

**两段式 + 三重门禁**（任一命中即中止发布，退出码 1）：
1. `check_residual`（基础引擎残留）
2. `harden_verify`（加固层：姓名/¥金额/元金额/股份份数/网格区间/个人价格语境/卡号/证件/手机）
3. PM 红线 grep（词面零命中：`\d+股`/`\d+份`/成本/浮盈/浮亏/收益率/市值/账户/持仓金额/
   姓名/金额/卡号/证件/手机/个人百分比词面/网格区间/个人价格语境）

加固层（redline_hardening.py）能力矩阵：
- H0 白名单保护（亿元资金流/Σ评分/规则阈值/日期先摘出，防误伤）
- H1 个人标识（姓名/券商名/「投资者：X」角色模式）
- H2 强规则（¥金额/元金额〔排除「元件」误报〕/N股/N份/网格区间/个人价格语境
  〔基准价强词允许整数、网格词限小数点价格、双向前后缀匹配〕/卡号/证件/手机）
- H2.5 HTML 注释脱敏 + 门禁词面中和（表头「持仓金额」→「持仓规模」；美债语境「收益率」→「利率」）
- H2.6 HTML/MD 表格敏感列整列脱敏（表头命中 网格区间/基准价/成本/盈亏/权重/暴露… 的列；
  MD 侧收窄关键词，保住「今日预估涨跌」等公开估值列）
- H2.7 市场语境豁免 `_is_market_line`（team-lead 2026-10-14 裁决）：含市场指标词
  且无个人标记的行/句/单元格，百分比与计数不掩不替换——修复宽度表/KPI
  「上涨占比」/板块资金流误杀
- H3 句子级处置（块级标签 + MD 行 + MD 表格单元格〔仅替换不掩百分比〕；整句替换
  保留 HTML 标签；P1 表格内 token 句不拖灭定性描述）
- H4 行级兜底（KPI 标签→值、条形图 width 样式；三态资格防跨卡误掩；MD 章节边界；
  市场行不触发不目标）
- PM 红线门禁 `redline_scan`（模式唯一定义于本模块，publish/selftest 共用；
  逐行按句扫描，市场语境句对数值模式豁免）

**实测证据**（evidence/pipeline-selftest.txt，8/8 PASS，退出码 0）：
- A 面（安全）：25 项个人数据跨文件扫描零残留——姓名/成本价/股份份数/持仓金额/
  组合暴露百分比/网格区间/基准价/买卖线/止盈止损线全部掩除
- B 面（不误杀）：公开数据逐文件全保留——指数点位/涨跌幅/成交额/Σ评分/信号分值/
  股息率/上涨占比/市场宽度/基金公开估值/板块资金流
- 幂等：二次执行逐字节一致（哈希比对通过）
- 结构：HTML 标签配平、MD 标题完整
- 覆盖：2026-10-13 五天任务产出 + 2026-10-14 三天任务产出，md/html 双格式
- P1 前后对比（占位句残留）：stock_assistant 18→0、fund_guide 10-14 98→18、
  fund_guide 10-13 60→9、stock_review 29→23，零新泄漏（开关 `P1_TABLE_NARROW`
  可回退旧行为）

---

## 10. 已知问题与待裁决项（请 team-lead 裁定）

1. ~~**仓库名分歧**~~ → **已裁决：daily-market-pulse**（team-lead 2026-10-14）。
   prepare_release.py 由 team-lead 移入 _archive/，本流水线为唯一实现。
2. **v3 引擎误杀公开数据（不影响安全，影响内容质量）**——经 raw/v3/hardened
   三级分流实测定位：
   - 基金 md 宽度表 上涨/下跌/平盘家数占比（38.6%/57.7%/3.7%）与「100%」：
     **v3 的句子级规则**所掩（非加固层，加固层修复管不到已替换文本）；
   - 「净流出TOP1 -18.30 亿」「板块涨跌幅 +2.95%」「架构类型 100%」：实测当前
     版本均未被掩（team-lead 的 diff harness 或基于旧暂存）；
   建议 v3 的句子级百分比规则增加「市场宽度/板块资金」语境白名单
   （加固层已有同款豁免 `_is_market_line` 可参考）。
3. ~~**首页未链接 methodology**~~ → team-lead 已在 build_index.py 加入口。
4. ~~**Pages 启用**~~ → 已确认：建库→推送→用户网页端一次性开启
   （Settings→Pages→main branch /docs）。
5. ~~**Task #9 重复**~~ → team-lead 已关闭并归档。
6. ~~**任务书草案退出码不一致**~~ → 已统一：以 publish_to_github.py 为准，
   pipeline_selftest.py 注释与草案均已对齐（2026-10-14）。
   方法论入口，建议在导航区加 `<a href="./methodology/">研判方法论</a>`。
4. **Pages 启用方式**：网页端 Settings 一次性开启（推荐）vs 写入 Actions workflow，
   需主理人操作，MCP 工具集无 Pages 设置能力。
5. **Task #9「主理人重建」与本任务重复**：如团队采纳本流水线，建议将 #9 关闭或
   合并；prepare_release.py 的六步编排已被 publish_to_github.py 取代（含其全部能力：
   日期页/周月报/feed/sitemap/methodology/--task/全量 manifest/三重门禁）。
6. **任务书发布步骤草案**（第 7 节）待评审后写入 6 个定时任务书。
