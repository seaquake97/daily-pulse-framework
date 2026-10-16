# FRAMEWORK-DESIGN — 统一任务框架与产品化资产设计 v2.0（架构师版）

> 日期：2026-10-16 19:30
> 作者：首席架构师高见远（RoleVerdict 回传全文，总监落盘）
> 状态：已确认为实现契约
> 基础：5 个任务书逐字 view + 3 份 md 全文结构实测 + 全部引擎脚本 code_stats.py/compute_signals.py 实读 + 现有设计规范三件套核对
> 取代：v1.0（总监版，2026-10-16 19:00）——v1.0 的 front-matter 强制假设被 v2.0 修正为「front-matter 可选 + meta 启发式兜底」

---

## 0. 核心诊断（一句话）

**上游任务既是内容生产者又是 HTML 生产者（五个任务五套审美，且 14:30 干脆不产 HTML），呈现层没有统一生产者。** 方案：上游退化成 Markdown 内容源，管线新增 render_md.py 作为唯一 HTML 生产者，上游 HTML 生成器全废。

---

## 1. 问题链（用户 8 项反馈 → 根因 → 方案）

| # | 用户反馈 | 根因（实锤） | 方案 |
|---|---------|-------------|------|
| P-1 | 14:30 推送是空的 | 任务书步骤 4 只要求 md，管线只搬已有文件，md-only 任务永远无详情页 | render_md.py 渲染 |
| P-2 | 15:05 缺源 | **任务书 bug**：股票复盘任务书通篇无任何发布/交付要求，无 present_files；14:30 同类任务书有步骤 5 交付。非当天执行事故 | 任务书补步骤 5 |
| P-3 | 标题风格不一致 | 各任务自由写 H1 | TASK_META 映射表 + 渲染器强制标题规范 |
| P-4 | 网页/维度/内容风格不一致 | 上游五套 HTML 生成器 + 五套标题风格（2 种带 emoji） | 渲染器唯一生产者 + 任务书三段式标题规范 |
| P-5 | 首页口径提示看不懂 | tag-warn 小徽章内部术语 | 前端重设计（在修） |
| P-6 | 响应式/缩放 | 未实测加固 | 前端实测加固（在修） |
| P-7 | RSS 裸 XML | feed item 质量差 + rss.xml 404 + 入口无引导 | 前端修复（在修） |
| P-8 | 产品化/复用/小程序 | 无系统设计 | §5-§7 |

---

## 2. render_md.py 契约（v2.0，含 v1.0 盲点修正）

### 2.1 标题统一规范（P-3 唯一正解）

各任务 H1 五花六门（实测：股票助手"股票助手 · 2026-10-16（周五）早盘集合竞价研判"、基金盘面"基金每日盘面分析与加权预估报告（11:00午盘版）"、基金指引"📊 基金每日操作指引（14:30）— daily-decision-engine v1.3…"、总复盘"基金股票每日复盘 - 2026年10月16日"）。管线 TASK_META 已有 TASK_NAMES，但 extract_entry 直接取 md 的 H1。

**规范**：`<TASK_NAMES[slug]> · YYYY-MM-DD（周X）<阶段标签>`

| slug | 渲染标题 | 依据 |
|------|---------|------|
| stock-assistant | 股票助手 · 2026-10-16（周五）早盘竞价 | data_stage=pre_open |
| fund-market | 基金盘面 · 2026-10-16（周五）午盘 | intraday |
| fund-guide | 基金指引 · 2026-10-16（周五）尾盘 | intraday |
| stock-review | 股票复盘 · 2026-10-16（周五）收盘 | close |
| daily-review | 每日总复盘 · 2026-10-16（周五）收盘 | close |

实施：extract_entry 的 title 字段改由 TASK_META 生成（不再取 H1 自由文本）；md 内 H1 保留为正文首行由渲染器降级为章节头。**兼容存量**：存量 5 个日期的 entries.json 标题已是 H1 提取，重渲染时统一刷新——可接受（修正不一致正是目标）。

### 2.2 渲染器管线位置（解决 P-1）

```
步骤4 落盘 md → render_md.py（md-only 任务生成 html）→ sanitize_body.py → frame_pass.py → build_site 框架页
```

接线规则：collect 后判断 `entry 有 md 无 html` → 渲染。**fund-guide/stock-review 立即受益；fund-market/stock-assistant/daily-review 保持原 HTML 链路**（任务书改造后自然切换）。渲染产物同样进 sanitize（渲染器输出已 Token 化，sanitizer 主要做 emoji→SVG 与兜底）。

### 2.3 meta 提取三级兜底（v1.0 盲点修正）

**实测真相**：3 份存量 md **均无 front-matter**（首行即 H1），但都带裸 meta 行：`评级：信号矛盾`、`数据时点：intraday`、`生成时点：…`。管线 extract_entry 已有 _META_LINE 正则先例。**front-matter 是新任务书的事，存量必须兼容**。

```
L1 front-matter（YAML 头，新任务书 md 才有）
   ↓ 无
L2 meta 启发式：正文前 50 行扫「评级[:：]\s*(进攻|均衡|信号矛盾|防守|回避)」+「数据时点[:：]\s*(pre_open|intraday|close)」
   ↓ 无
L3 market_data.json verdict（现有 load_market_data_for_slug，per-slug 已修）
   ↓ 无
诚实降级：rating=None → 渲染「数据缺口」tag-gap（复用现有机制，禁编造）
```

### 2.4 Markdown 渲染范围（v2.0 实测裁剪）

实测 3 份 md 全部只用了：ATX 标题/GFM 管道表格/任务列表/有序无序列表/嵌套列表/行内代码/粗斜体/分隔线/图片/链接/HTML 注释。**零数学公式**（v1.0 的 LaTeX 担忧不存在，已核对）。唯一图片引用在 daily_review.html（body_slice_*.jpg），md 内无 ![]()。

渲染清单：标题（h1→h3、h2→h4，与 sanitizer heading_pass 的 LEVEL_MAP 对齐）/ 段落 / GFM 表格→.tbl-wrap>table.tbl（tabular-nums，detail-frame.css 已有 .tbl-wrap）/ 列表（任务列表→状态徽章 check/ban）/ 粗斜体 / 行内代码 / 分隔线 / 链接 / 引用块 / 图片→figure。

**章节视觉统一（P-4 核心）**——通用结构映射：
- 「结论卡/核心决策卡」→ verdict-card 族
- 表格章节 → .tbl-wrap
- 「免责声明」→ footer-note
- 四态台账（TRIGGERED/NOT_TRIGGERED/UNEVALUABLE/MISSED_NEUTRAL）→ 状态徽章

**铁律**：章节级 md 正文 100% 保留（用户铁律：全量正文无损），只做视觉映射不改文字。

### 2.5 输出契约

```html
<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{规范标题} — 每日市场脉搏</title>
<style>{token 子集：detail-frame.css 已含全部，渲染器只引 var()}</style>
</head><body data-sb-h>
{渲染正文：h3/h4/表格/卡片/徽章，零 script/零渐变/零裸 hex}
</body></html>
```

- 样式策略：渲染器**不内联 CSS**，靠 frame_pass 注入的 detail-frame.css（已有 .doc h3/.tbl-wrap/verdict-card 全套）——单一 Token 源，避免两套 CSS 漂移
- sanitizer 对渲染产物：emoji→SVG、heading 校验、兜底消毒（正常应为零改动）

---

## 3. 任务书改造矩阵（5 本，逐字核对实况）

### 3.1 标题规范统一（每本加「标题铁律」段）

各本步骤 4 的生成指令加：
> **标题铁律**：md 首行 H1 必须用 `<任务名> · YYYY-MM-DD（周X）<阶段>` 格式，禁止 emoji、禁止版本号后缀、禁止破折号副标题（如「— daily-decision-engine v1.3」）。

同时（可选加强）要求 front-matter（task/stage/rating/sigma/data_date）——**但存量兼容靠 §2.3 L2，不强求**。

### 3.2 逐本改造点

> **执行状态（2026-10-16 收尾轮）**：9:28 / 11:00 / 14:30 / 15:05 四本已改完上线（标题铁律 + front-matter 两键契约 rating/stage + md-only 切换；11:00 为步骤 5.5 后删 html）。15:30 按 §3.4 纪律留待 15:05 新版稳定运行一日后再改（依赖链终点）。切换安全性证据：全部 5 日期 × 5 任务的存量 md 干跑渲染零失败。

| 任务书 | id | 现状 | 改造 | 状态 |
|--------|----|------|------|------|
| 股票助手 9:28 | automation-1784899435961 | 步骤4 生成 stock_assistant.md + .html，无标题规范 | 标题铁律；**删 fill_and_publish 直出 HTML 步骤**（改为「HTML 由发布管线渲染，任务书不产」） | ✅ 已改 |
| 基金盘面 11:00 | automation-1785247840681 | 同上有 html（generate_report.py 双产 md+html） | 同上（实现为步骤 5.5：核对 md 规范后删 html） | ✅ 已改 |
| 基金指引 14:30 | automation-1785247840781 | 只有 md，无标题规范 | 标题铁律 + front-matter 要求 + 落盘自检 | ✅ 已改 |
| 股票复盘 15:05 | automation-1785245996901 | 只有 md，**无步骤5 present_files、无任何发布要求**（P-2 根因） | 标题铁律 + **补步骤5 present_files**（对齐 14:30 模式）+ front-matter | ✅ 已改（4.1/5 为 10-16 上午补，front-matter 为 10-16 晚补） |
| 每日总复盘 15:30 | automation-1785332237194 | 只产 html，md 共享 stock_review.md | 标题铁律；**HTML 步骤废除以 stock_review.md 为源**（需先确认 15:05 已产该 md，时序上 15:05 先于 15:30，安全） | ⏳ 待 15:05 稳定后改 |

### 3.3 15:05 时序安全检查

15:05 股票复盘先产 stock_review.md → 15:30 总复盘消费它渲染——**时序安全**（25 分钟间隔）。总复盘任务书改为：读 stock_review.md 若不存在则静默失败告警（不渲染空页）。

### 3.4 执行纪律

逐本改、次日验证一本再改下一本。总复盘那本最后改（依赖链终点）。全部走 automation_update。

---

## 4. RSS + 响应式 + 首页文案（前端在修，验收标准）

### 4.1 RSS
- item=每日一条：title=总复盘规范标题、link=日期页、description=「Σ 评级【X】（值），覆盖 N 项任务，数据时点 Y」
- rss.xml 别名；首页入口「订阅更新」+ 引导
- feed.xml 日期倒序、pubDate 合法

### 4.2 响应式
- 断点 390/734/980/1280/1920/2560px + 缩放 67/80/100/125/150/200%
- 每档：scrollWidth<=clientWidth、表格不撑破、导航 sticky、文字可读

### 4.3 首页口径提示
- tag-warn 仅用于真缺口（无 market_data.json），文案「数据缺口 · 该任务无 Σ」+ 图标说明
- 时点说明改为时间线头部一句人话：「盘中数据为实时估值，收盘数据为全日定格，两者不可直接比较」
- Σ 值旁 chip 显示 data_stage（已有，保留）

---

## 5. 资产化结构（P-8）

### 5.1 双仓分工

| 仓库 | 角色 |
|------|------|
| daily-market-pulse | 内容站（用户数据产物） |
| **daily-pulse-framework**（新建 MIT） | 框架资产（零用户数据） |

### 5.2 框架仓结构

```
daily-pulse-framework/
├── README.md                     # 一键复用：clone→config→run→publish
├── config/
│   ├── holdings.example.yaml     # 持仓模板（股票+基金+网格）
│   └── site.example.yaml         # 站点配置
├── scripts/                      # render_md/sanitizer/site_*/publish/push
├── assets/design-tokens.css
└── docs/FRAMEWORK-DESIGN.md + MINIPROGRAM-MIGRATION.md
```

### 5.3 持仓配置化（一键复用前提）

现状：持仓写死用户 MEMORY.md（parse_holdings.py 按列位置解析）——不可复用。
目标：`config/holdings.yaml`（股票/基金/网格参数 schema 见 §5.4），parse_holdings.py 优先读 config，**缺失回落 MEMORY.md**（引擎零改动、向后兼容）。

### 5.4 一键复用流程

```
git clone framework → cp config/*.example.yaml config/ → 填持仓
→ 跑引擎（采集+compute_signals+validate）→ publish --date --push → Pages 上线
```

新用户不写一行代码；引擎侧唯一耦合点=parse_holdings 的 config 优先读取。

---

## 6. 小程序迁移评估（P-8）

| 资产 | 复用度 |
|------|--------|
| entries.json/market_data.json/viewpoint.json | 完全复用（小程序直接消费 JSON） |
| design-tokens | 完全复用（CSS 变量同构） |
| render_md 解析层 | 部分（md→WXML 输出层重写，解析层复用） |
| sanitizer | 不复用（数据源是 JSON 非 HTML） |
| 引擎 scripts | 完全复用（纯 Python 可跑云函数） |

**选型：Taro 4（React 语法）**——匹配前端技能栈，一套代码多端，JSON feed 驱动简单。

**路径**：Phase 1 只读展示（首页评级 Σ + 任务列表 + 详情，数据源=Pages JSON，零服务器，2-3 周）→ Phase 2 持仓管理+网格计算器+订阅消息提醒 → Phase 3 台账同步+个性化推送。

**风险**：① 审核定位「个人投资日志」规避投顾资质红线；② 类目选「工具-信息查询」；③ 数据来源标注+免责声明同站；④ Phase 1 静态托管零成本，Phase 2 起云开发按量付费。

---

## 7. 渐进路线图

| 阶段 | 内容 | 验收 |
|------|------|------|
| R0 止血 | 5 日期治愈重建+推送（data-origin+范围收窄已就位） | 线上 palette 字面值、深色正常 |
| R1 渲染器 | render_md.py + 接线 + ≥10 测试 | 14:30/15:05 有详情页、风格统一 |
| R2 前端 | 文案+RSS+响应式 | §4 验收 |
| R3 推送 R1+R2 | 全量重建推送 | 用户验收 |
| R4 任务书 | §3 矩阵逐本 | 次日运行验证 |
| R5 资产化 | 框架仓+config+README | 新 agent 复用演练 |
| R6 小程序 | Phase 1 | 上线 |

---

## 8. 汇报外的问题链备注（总监执行提示）

- 存量 entries.json 标题刷新（§2.1）会使 10-12~10-15 时间线标题变化——这是修正 P-3 的必要代价，R0/R3 推送时自然生效
- 15:05 任务书补 present_files 后，10-16 缺失的那天不会追溯（md 没写），但次日起有自检兜底
- 渲染器优先服务 fund-guide/stock-review（md-only），存量 html 任务链路不动，R4 任务书改造后自然切换——全链路无需一次性切换
