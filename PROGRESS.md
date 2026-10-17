# 团队进度记录（PROGRESS.md）

> 用途：任务异常终止后快速重新拉起。每个任务的「落点文件」「验收命令」「重拉起提示」均记录于此。
> 最后更新：2026-10-16 22:40（GMT+8）
> 项目：github-ip-plan（daily-market-pulse 内容站 + daily-decision-engine 决策引擎）
> 工作区：/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan
> Python：/Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3

---

## 一、已闭环任务（验收命令实测通过）

### PM-07 — 清除 body 内 emoji 图标（P0，前端 贾思敏）
- 状态：✅ 完成
- 裁决：团队 P0-1 绝对规则凌驾 emoji_map 内部「🍜 个人 IP 形象」设计决策
- 落点文件：
  - `scripts/sanitizer/emoji_map.py`（IP_MARK 策略改为 SVG 输出 + 顶部裁决文档）
  - `scripts/sanitizer/emoji_inline.py`（`_upgrade_legacy_ip_marks` / `_ip_mark_span`）
  - `scripts/site_theme.py`（新增 chess-pawn / noodle-bowl 两个 symbol）
  - `scripts/scan_compliance.py`（P0 口径收紧：ip-mark 内 emoji 也计违规）
  - `scripts/test_emoji_body.py`（新建：body 全量 emoji 扫描，2 tests）
  - `_stage/docs/daily/*/*.html`（历史产物升级 ip-mark→SVG）
- 验收：`python3 scripts/scan_compliance.py` → emoji(P0)=0；`test_emoji_body.py` 全绿
- 重拉起：若 session 中断，重新 spawn 前端，附此条目即可，勿重复造轮子

### A-02 — token_map bg 角色缺陷（P0，前端 贾思敏）
- 状态：✅ 完成（294 行 ≤300）
- 落点：`scripts/sanitizer/token_map.py:294`（`_BG_WASH_FOR_TEXT_TOKEN`，bg #f59e0b→--rating-balanced-wash）
- 验收：`token_for_hex('#f59e0b',role='bg')` 不再以 --warn 开头；`grep -c "background[^;]*var(--warn)" _stage/docs/daily/*/*.html`==0

### A-03 — publish 缺任务退出码（P0，架构师 高见远）
- 状态：✅ 完成
- 落点：`scripts/publish_to_github.py`（缺失任务 exit≥2 + stdout 列任务名 + 区分部分/全部）；`docs/decisions/ADR-006.md`
- 验收：`python3 scripts/publish_to_github.py --date 2026-10-11` → exit=2 且列缺失任务名
- 支撑改动：3 个消毒集成测试加 `--task stock-assistant` 收敛合成 fixture（test_sanitize_pipeline/gate_pipeline/scope）

### A-04 — 路径参数化（P0，架构师 高见远）
- 状态：✅ 完成
- 落点：`framework/scripts/paths.py`（新建，PROJECT_ROOT=parents[1]，含 off-by-one 修正）；scripts/*.py 引用处改 import
- 验收：`grep -rn "/Users/lianghaizhen" scripts/ framework/ --include="*.py" | grep -v _archive` == 3（仅注释）；14 套测试全绿

### A-05 — parse_holdings 删 MEMORY 回退（P0，架构师 高见远）
- 状态：✅ 完成
- 落点：`_git_engine/scripts/parse_holdings.py`（删 MEMORY 绝对路径隐式默认，改显式 --memory 参数）
- 验收：无 --memory 且无 env 时直接报错退出（不再静默回退）

### A-19 — SLUG_STAGE 收敛（P1，架构师 高见远）
- 状态：✅ 完成
- 落点：`framework/config/slug_stage.json`（单一数据源）；`publish_to_github.py:_load_slug_stage()` + `md_render/meta.py:_load_slug_stage()`
- 验收：`grep -rn '"stock-assistant": "intraday"' scripts/` == 0；stock-assistant=pre_open

### PM-15 — scan_compliance 剥注释消假阳性（P1，QA 严过关）
- 状态：✅ 完成（OPEN-006）
- 落点：`scripts/scan_compliance.py`（增加 `strip_comments`，使用 `n_clean` 统计弹跳缓动）
- 验收：`python3 scripts/scan_compliance.py` → 弹跳缓动 11→0，紫粉渐变 0，emoji(P0) 0

### L-4 — 降级态 detail 页动作指令门禁与历史数据清洗（P0，QA 严过关）
- 状态：✅ 完成
- 落点：
  - `scripts/content_contract.py`：新增 `_validate_degraded_no_action` 门禁与 `RE_ACTION_CMD` 正则匹配
  - `scripts/test_content_contract.py`：新增 `TestDegradedActionGate` 测试用例（拦截违规指令、允许中性距离陈述、豁免历史观点回顾）
  - `/Users/lianghaizhen/WorkBuddy/股票助手/2026-10-16/stock_assistant.md` & `.html`：清洗可执行挂单指令为中性降级观察陈述
- 验收：`test_content_contract.py` 15 套测试全绿；`_stage/docs/daily/2026-10-16/stock-assistant.html` 中无任何违规交易指令

### A-21 & 重推站点 — 线上同步与漂移清零（P1，运维 卜宕机）
- 状态：✅ 完成
- 落点：`scripts/publish_to_github.py --date 2026-10-16 --push`
- 线上提交：`https://github.com/seaquake97/daily-market-pulse/commit/efc6d57`
- 验收：`python3 scripts/verify_published.py` → 文件数 stage 74 | pulse 74，漂移数 = 0，内容契约全过

### DEPLOY-GUIDE — GitHub 上传与部署完整指南（运维 卜宕机）
- 状态：✅ 完成
- 落点：`docs/DEPLOY-GUIDE.md`（面向新人完整指南，覆盖三仓结构、凭证、构建发布、CI门禁、故障排查与速查表）
- 验收：文档内全部 14 测试命令、scan_compliance、verify_published 实跑核对通过

### RESEARCH — ZhuLinsen/daily_stock_analysis 深度研报（PM 许清楚）
- 状态：✅ 完成
- 落点：`docs/RESEARCH-ZhuLinsen-daily_stock_analysis.md`
- 覆盖：12 种数据源容灾、YAML 声明式策略引擎（缠论/情绪周期/龙头/成长等）、Wilder RSI / MACD / BIAS 算法、时相与大盘护栏、ETF 穿透、5 项落地建议

### STRATEGIES — 声明式策略库与校验器（Phase A-1，PM 许清楚 / 前端 贾思敏）
- 状态：✅ 完成
- 落点文件：
  - `framework/config/strategies/six_networks.yaml`（十五五六张网战略配置策略）
  - `framework/config/strategies/grid_trading.yaml`（条件单智能网格做T策略）
  - `framework/config/strategies/dividend_defensive.yaml`（高股息防御与收息底仓策略）
  - `framework/scripts/strategies.py`（策略加载器与 Schema / P0 emoji 门禁校验 CLI）
  - `framework/scripts/test_strategies.py`（6 例单测）
- 验收：`python3 framework/scripts/strategies.py --dir framework/config/strategies/` 输出 3 个策略全通过；`test_strategies.py` 全绿。

### TECHNICAL — 纯标准库指标计算与动态 BIAS 补偿（Phase A-2，后端 贝洛奇 / 架构师 高见远）
- 状态：✅ 完成
- 算法原理：
  - 纯 Python 原生列表实现，零第三方依赖（无需 pandas / numpy）。
  - MA 均线序列（MA5/10/20/60）。
  - 动态 BIAS 强势趋势补偿：基础 5% 阈值；在 `strong_trend=True` 时自动放宽 1.5 倍至 7.5%，允许主升浪龙头顺势追踪，防止踏空。
  - Wilder's SMMA 平滑 RSI（6日/12日/14日/24日）。
  - 确定性 MACD（DIF, DEA, BAR）。
- 落点文件：
  - `framework/engine/signals/technical.py`（160行 ≤ 300 行红线）
  - `framework/engine/signals/test_technical.py`（13 例单测）
- 验收：`python3 framework/engine/signals/test_technical.py` 13 例全绿。

### METHODOLOGY — 研判方法论页内容扩充（总监 韦优 编排内处理）
- 状态：✅ 完成
- 问题根因：方法论页为静态源 `site/methodology/index.html`，此前仅含七步流水线、S1-S6 信号、五档评级、反滥用、隐私 5 节，**缺持仓级策略、个股技术指标与基金分析方法论**（三节空白 = 读者看不到本项目的策略深度，与研读报告脱节）。
- 落点：`site/methodology/index.html` 新增 3 节 + 数据来源节更新：
  1. 持仓级策略体系（六张网战略配置 / 智能网格做T / 高股息防御收息）
  2. 个股技术指标体系（MA 系统与 BIAS 强势补偿 1.5 倍 / Wilder RSI / MACD / 与 Σ 的分工）
  3. 基金分析方法论（持仓穿透 + 加权归因 + 缺口披露 + 板块集中度 + 资产分层 + 黄金单列）
  4. 数据来源节补充多源容灾与缺口纪律（主源 westock-mcp + 备用腾讯/新浪只读兜底）
- 验收：符合团队 P0-1（无 emoji），结构与既有 mp-sec 一致；构建后呈现在线上 /methodology/ 页。

### CI_VERIFY — 统一 CI 总调度器（QA 严过关 / 总监 韦优）
- 状态：✅ 完成
- 落点：
  - `scripts/ci_verify.py`（269行 ≤ 300 行红线，纯标准库，涵盖 23 套单元测试与 4 套校验器，共 27 项测试）
  - `scripts/test_ci_verify.py`（299行 ≤ 300 行红线，28 例单测全部 PASS，含 19 个变异测试全部被杀 + 假绿灯识别机制）
- 验收：`python3 scripts/ci_verify.py` → 27 项全 PASS，0 失败，耗时 7.29 秒。

### FALLBACK_FETCHER — 多源行情容灾与持仓批量抓取（Phase B，架构师 高见远）
- 状态：✅ 完成
- 落点：
  - `framework/engine/collect/quote_sources.py`（258行，腾讯/新浪 GBK 接口解析，纠正 f36=成交量手、f37=成交额万元，统一新浪单位，登记 9 只持仓代码 `HOLDING_CODES`）
  - `framework/engine/collect/fallback_fetcher.py`（175行，多源主备降级 + 连续 3 次失败熔断 + 300 秒冷却 + `fetch_batch` / `fetch_holdings` 批量抓取）
  - `framework/engine/collect/test_fallback_fetcher.py`（24 例全离线单测全部 PASS）
- 验收：单次 HTTP 批量获取 9 只持仓真实行情实跑成功，离线单测 24 例全绿。

### FALLBACK_INTEGRATION — 备用源合并与健康度自动判定（Phase B，后端 贝洛奇）
- 状态：✅ 完成
- 落点：
  - `framework/engine/collect/primary_health.py`（70行，只读体检，提供 `degradation_reasons` 与 `is_primary_degraded`）
  - `framework/engine/collect/merge_fallback.py`（230行，主源绝对优先、脏值即丢弃、缺口声明绝不填0、`positions_to_mapping` 保证 schema 必须为 mapping 对象）
  - `framework/engine/collect/fetch_fallback_data.py`（101行，一键自动编排：体检 → 批量取数 → 合并 → missing 贯通进 data_gaps）
  - 单测：`test_primary_health.py` (22例), `test_merge_fallback.py` (50例), `test_fetch_fallback_data.py` (5例) 全部 PASS。

### S4_MOMENTUM — 确定性动量确认信号升级（Phase A-3，后端 贝洛奇）
- 状态：✅ 完成
- 落点：
  - `_git_engine/scripts/compute_signals.py`（新增可选入参 `--rsi` / `--bias` / `--strong-trend`）
  - `_git_engine/scripts/signal_momentum.py`（119行，S4 = 0.6*分化 + 0.4*动量，复用 `technical.calculate_bias`）
  - `_git_engine/scripts/test_compute_signals.py`（24 例单测全部 PASS，含 v1.2 黄金副本回归：不传参时逐字节一致）
  - 文档同步：`_git_engine/references/signal-scoring.md`、`_git_engine/SKILL.md`、`_git_engine/README.md` 中英双语对齐。

### STRATEGY_UI — 声明式策略前端卡片渲染与构建集成（前端 贾思敏 / 总监 韦优）
- 状态：✅ 完成
- 落点：
  - `framework/scripts/render_strategies.py`（278行，纯标准库，生成符合 Apple 规范的卡片片段与样式）
  - `framework/scripts/inject_strategies.py`（150行，成对锚点区间替换，支持构建幂等）
  - `framework/scripts/test_render_strategies.py`（24 例单测全部 PASS）
  - `site/methodology/index.html` 成功注入 3 个策略卡片，通过 `publish_to_github.py --push` 同步至线上 Pages 站点。

### DEPLOY_AND_DOCS — 云端自动化与部署指引全套就位（DevOps 卜宕机 / PM 许清楚）
- 状态：✅ 完成
- 落点：
  - `.github/workflows/daily_pulse.yml`（428行，4个时点 UTC cron 编排、时点推断、令牌临时注入、结构自检、verify/publish 分层）
  - `docs/CLOUD-AUTOMATION.md`（252行，云端自动化配置与时区换算说明）
  - `docs/DEPLOY-GUIDE.md`（新人接手 SOP 与全量验证指南）
  - `docs/REPO-UPLOAD-GUIDE.md`（本地工具仓新建远端与首次推送详细指引）
  - `docs/SPEC-DATA-FALLBACK.md`（多源行情容灾与降级数据契约规范）
  - `docs/RESEARCH-ZhuLinsen-daily_stock_analysis.md`（外部开源标杆深度研究报告）

### MOBILE_OPTIMIZATION_V2 — 手机端三级手风琴折叠与极简降噪系统性重构（PM 许清楚 / 设计师 颜好看 / 前端 贾思敏 / 总监 韦优）
- 状态：✅ 完成（真机截图痛点 100% 根除）
- 真机实测痛点与系统性解法：
  1. **三级手风琴架构（Progressive Disclosure）**：
     - **Level 1（日期折叠）**：基于 `<details class="issue dp-card">` 实现日期折叠面板。当天（最新一期）默认展开（`default_open=True`），历史日期默认折叠收起！彻底避免长达数千像素的平铺瀑布流；
     - **Level 2（时点折叠）**：基于 `<details class="slot-accordion" open>` 实现每日时点折叠卡片。头部高度仅 48px，左右两端对齐，左侧为时间与任务名，右侧为核心状态与展开箭头；用户可单手轻点任意折叠收起；
     - **Level 3（详情呈现）**：展开后清晰展示核心操作指令、分析佐证与详情页直达大按钮。
  2. **标签大乱炖根除（单一状态药丸原则）**：
     - 彻底清除原截图 09:28 处同时堆叠 5 个同义标签（数据源降级、数据不可信、评级未标注、竞价时点、统计口径不同）的灾难；
     - 归一化为单一主状态徽章：降级态统一展示 `<span class="tag tag-degraded">⚠️ 数据降级</span>`，正常态展示评级徽章，未标注展示缺口；
     - 彻底从列表折叠层移除每个条目反复插入的 `统计口径不同 · 数值仅供参考` 大黄框膏药。
  3. **标题冗余废话彻底清除**：
     - 新增 `_clean_title` 纯函数，彻底剥离所有 `YYYY-MM-DD` 与 `（周X）`，标题精炼为 `股票助手 · 早盘竞价`、`基金盘面分析 · 午盘` 等，单行放得下，绝不折成多行。
  4. **微运行时间与底部遮挡消除**：
     - 列表折叠头部彻底清除秒级抓取微时点（`.tl-run`）；
     - 页面容器底部注入安全边距 `padding-bottom: max(var(--space-16), calc(env(safe-area-inset-bottom, 24px) + var(--space-8)))`，彻底解决 iOS Safari / 微信底栏遮挡。
- 落点：
  - `docs/PRD-MOBILE-OPTIMIZATION.md`（v2.0.0 三级手风琴与标签归一化 PRD）
  - `docs/UI-MOBILE-SPEC.md`（v2.0.0 移动端三级层级与交互规范）
  - `scripts/site_render.py`（三级手风琴 DOM 组装与 `_clean_title` 函数）
  - `scripts/site_pages.py`（最新一期 `default_open=True`，历史期默认折叠）
  - `scripts/site_blocks.css`（手风琴平滑旋转、48px 触控区、安全边距）
- 验收：
  - 运行全量 27 套 CI 测试通过（`python3 scripts/ci_verify.py`，耗时 8.06 秒，27 项 100% 全部 PASS，漂移为 0）；
  - `scan_compliance.py` 门禁全 0（零 emoji、零紫粉渐变、零硬编码颜色）；
  - `probe_responsive.py` 16 个宽度 × 12 个页面（192 组合）横向滚动组合数恒为 0；
  - 已推送至线上 GitHub Pages（commit `13d3a26`），即刻生效。

### 全量测试（2026-10-17 13:15 实测）
- 状态：✅ 27 项全绿（耗时 8.06 秒）
- 清单：19 套单元测试套件 + 4 套质量校验器全部 PASS，0 失败，0 告警，verify_published 漂移为 0。

---

## 一之补、2026-10-17 下午轮（GitHub 治理常态化 + 产品/框架债销账）

> 权威总账：`docs/BACKLOG-MASTER.md`（本文只记落点与验收，不复制总账）。

### M-01 框架仓上线（用户指令「上传 GitHub 整个引擎和页面的管理」）
- 落点：`seaquake97/daily-pulse-framework`（public/MIT），HEAD `0dc49b3`，tag `v1.0.0` + Release
- 内容：199+ 文件全量源码（scripts/ framework/ site/ docs/ _engine_stage/ + 门面四件套）
- 修复两处 .gitignore 静默失效（行内注释致 pattern 永不匹配；framework 下 *.json 误吞
  slug_stage.json 与 market_data.schema.json 两份契约文件）
- 补齐此前漏追踪 22 个源码文件；paths.py 默认值改 ~/WorkBuddy（clone 到任意路径可跑）
- 验收：全新克隆跑 25 套件全绿（test_render_md 补 A-07 skip 守卫）；本地 ci_verify 28/28

### M-02 引擎仓同步与发布
- `seaquake97/daily-decision-engine`：commit `c11d8ef`（v1.4.0），tag v1.3/v1.4.0 + Release
- S4 复合动量 + parse_holdings 路径参数化（A-05）进入仓，SKILL.md version 0→1.4.0

### M-03 GitHub 常见模式维护体系
- README.md（三仓架构/快速开始/仓库地图/环境变量/文档索引）/ CONTRIBUTING.md /
  CHANGELOG.md / MIT LICENSE / Issue 模板 ×2 / PR 模板 / ci.yml（单测层 + 假绿灯判定）
- ⚠️ 两个 workflow 文件（ci.yml / daily_pulse.yml）**暂存本地未入仓**：PAT 缺
  `workflow` scope。令牌升级后一条命令补入：`git add .github/workflows && git commit && git push`

### M-04 产品 P0 三项上线（前端 贾思敏，总监实测复核）
- P-1 首页「今日一屏」：`scripts/site_today.py`；P-2 RSS 条目级：`scripts/site_feed.py`
  （24 items == entries 总和）；P-3 PWA 三件套：`scripts/gen_app_icon.py`（纯标准库
  手写 PNG，字节确定）+ manifest + theme-color 双 meta
- 顺手修复 publish 管线二进制 bug（manifest read_bytes，P-13）

### M-05 P-6 历史路径泄漏清零
- 10-15 stock_review.md 源句按 PM-17 裁决改中性表述并重发布（commit e2c4f81）；
  三载体 `/Users/` 扫描 = 0

### M-06 P-4/F-3 周月报真聚合（后端 贝洛奇）
- `scripts/site_aggregate.py`：周/月 KPI 实算（迁移次数/Σ 方向/防守天数/矛盾天数/条目数）
- 总监裁决：废止「相似度 < 0.9」代理指标（被 58KB 共享 CSS 支配，详 BACKLOG §1.2）

### M-07 F-1 引擎四脚本迁入 framework/engine/signals/（架构师 高见远）
- compute_signals/parse_holdings/settle_viewpoints/validate_market_data + v1.4.0 回合
- A-10 前缀收敛：full_code 委托 codes.py 单一实现（3527 例语料零差异）
- README 声明单一事实源：framework canonical → _engine_stage → GitHub 单向同步
- ci_verify 27→28 项；字节级回归与引擎仓 v1.4.0 一致

### 本轮门禁实测（全部通过）
ci_verify 28/28 ｜ scan_compliance 全 0 ｜ probe_responsive 0/192 ｜ verify_published 漂移 0 ｜
连续两次构建字节一致 ｜ 发布三连推（10-15 修路径 / 10-16 ×2）

## 二、进行中任务（active）

*当前手机端排版与视觉减负专项已 100% 全部完成并推送上线！*

---

## 三、待办（仅保留需用户操作与确认项）

### 需用户确认 / 操作清单（涉及个人 GitHub 账号与生产环境，等待指示）：
1. **GitHub 工具仓建仓与首次 Push**（参考 `docs/REPO-UPLOAD-GUIDE.md`）：
   - 在 GitHub 新建名为 `daily-pulse-framework` 的私有或公开空仓库；
   - 关联本地 remote 并执行 `git push -u origin main`。
2. **仓库 Secrets 配置**（参考 `docs/CLOUD-AUTOMATION.md`）：
   - 在新工具仓的 Settings -> Secrets 中增加 `GH_PAT`（需具备 `seaquake97/daily-market-pulse` 仓的 Contents:write 权限）；
   - 配置后 GitHub Actions 云端定时任务即可自动按工作日时刻表（09:28 / 11:00 / 14:30 / 15:30）运行并发布。
3. **生产技能目录同步决策（A1）**：
   - 目前 S4 动量升级与校验器完整保留在 `_git_engine/` 中，是否将 `compute_signals.py` 同步到生产目录 `~/.workbuddy/skills/daily-decision-engine/scripts/`？由你最终确认后一键执行。

---

## 四、异常终止快速拉起手册

若 session 中断，按以下顺序重新拉起，无需从零：
1. 先读本文件 + `docs/GAP-*.md` 五份清单（PM/ARCH/UI/LEAD/A 缺口清单）
2. 已闭环任务（上方一）勿重做，仅用验收命令复核
3. 进行中任务（上方二）重新 spawn 对应专家，prompt 附该条目「落点文件 + 验收命令」
4. 当前未决根因 / 已知坑见 `scripts/pitfalls.jsonl`（如有）与本项目 MEMORY
5. Python 必须用托管 runtime：`/Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3`
