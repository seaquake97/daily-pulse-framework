# 上游详情页阅读框架规范 · detail-frame-spec

> 版本 1.1 | 日期 2026-10-15 | 设计：颜好看 | 状态：待前端/后端接线
> 配套文件：`detail-frame.css`（框架扩展层 CSS，v1.1）、`design-tokens.css`（本次新增 `--surface-inverse` / `--fg-on-inverse`）
> 上位规范：`APPLE-DESIGN-SPEC.md`（Apple 设计语言落地规范 v1.0）—— 本规范是其 §13.1「上游正文 HTML 的容纳」的工程化落地
> 适用对象：`daily/<date>/stock-assistant.html`、`fund-market.html`、`daily-review.html`、`stock-review.html` 等上游任务自产 HTML（sanitizer 净化后、frame_pass 注入框架后）
> v1.1 变更：依据 10-15 stock-review.html 与四页 masthead 结构实测，补标题移出封面硬约束、反色面段落收复、body 工具类回补、icon-subsprite 共存、白名单扩至 v1.1；新增阻塞项 B-6/B-7。变更明细见 §13。

---

## 0. 结论摘要

上游详情页当前是「外来户」：无站点导航、无返回路径、容器宽度各自为政（720/860/Tailwind 72rem）、页脚缺失或带原始声明、深色模式不继承、移动端字号失控（实测正文 32px、封面字 72px）。

本规范裁定一套**读取框架（reading frame）**，由新增的 `frame_pass.py` 在发布链路中注入：

1. **slim 顶部导航** —— 复用框架页同一套 `.nav`（44px sticky 毛玻璃、同 Token），左侧站点名，右侧「返回当日时间线」+ 方法论 + RSS；
2. **阅读容器 680px prose 度量 + 数据宽元素探出** —— 正文 `--container-prose`，表格/KPI/静态图/双栏证据向两侧探出至 `--container-max`（980px），≤900px 收回；
3. **站点页脚** —— 与方法论页同源同 Token，新增「本页信息」行（数据日期/生成时点/数据时点，全部来自 `entries.json`，不含墙钟时间，保幂等）；
4. **深色模式零 JS 继承** —— 完整 Token 栈注入 + `prefers-color-scheme`，反色表面走新增的 `--surface-inverse` / `--fg-on-inverse`；
5. **移动端适配** —— 探出收回、栅格降列、导航横向滚动（复用框架既有行为）；
6. **与 sanitizer 输出共存** —— h3/h4 层级与 `data-sb-h` 标记、`.ic-wrap` / `.ip-mark` / `.viz-*` 类契约、反色 Token、后端最小 sprite（`<!-- icon-subsprite:v1 -->`）与全量 sprite 的去重、外链剥离，逐条有约束。
7. **封面标题移出（v1.1 新增硬约束）** —— 四页实测 masthead 形态各异（stock-assistant `.top` / daily-review `.cover` / fund-market 与 stock-review `<header>`），标题若留在封面内，`.doc h1.doc-title` 的 `color:var(--fg)` 特异性 (0,2,1) 会压过反色面容器色 (0,1,1)，出现 fg-on-fg 隐形标题。frame_pass 必须把提升后的标题节点移出 masthead（A-7）。

框架只做**换皮与补全，不做删改**：可见文本一字不删（唯一例外是 §3.5 的结构化去重，信息完整迁移）。上游 `<style>` 块保留（sanitizer 已将其色值收敛到 Token），框架 CSS 以级联次序 + 特异性胜出。

---

## 1. 架构与注入点

### 1.1 发布链路位置

```
上游任务产出 HTML
  → sanitize_body.py（已有：颜色→Token、emoji→SVG、script 摘除、heading 对齐）
  → frame_pass.py（新增：注入读取框架）        ← 本规范
  → build_site.py（框架页，不动详情页）
  → publish_to_github.py
```

**顺序是设计约束**：frame_pass 依赖 sanitizer 的产出形态（h3/h4 + `data-sb-h` 标记、`.ic-wrap`、`.viz-static`、收敛后的 Token 色值）。两者均幂等，任一再跑一次不产生变化（sanitizer 靠 `data-sb-h` 与 `var(` 跳过，frame 靠 `<body data-df="v1">` 整文件跳过）。

### 1.2 frame_pass.py 接口（与 sanitize_body.py 同构）

```bash
python3 scripts/frame_pass.py --dir _stage/docs/daily [--in-place] [--dry-run] [--report PATH]
```

- 处理对象 = 所有 `daily/<date>/entries.json` 中 `html` 字段非 null 的文件（**以 entries.json 为唯一事实源**，不扫目录、不碰 `index.html` 框架页）；
- 每文件读取同目录 `entries.json`，按文件名匹配 entry，取得 `slug / name / time / run_time / rating / sigma / stage / comparable / date`；
- `depth` = 文件相对 `docs/` 根的层数（详情页恒为 `../../`）；
- 原子写（临时文件 + rename），崩溃不留下半框架页面；
- 退出码约定与 sanitize_body 一致：0 干净 / 2 有 needs-manual-review（本规范内不产生该项）。

### 1.3 动作清单（A-1 ~ A-10，按序执行）

| # | 动作 | 幂等机制 |
|---|------|---------|
| A-1 | `<head>` 末尾注入四层 CSS：`design-tokens.css` + `site_components.css` + `site_blocks.css` + `detail-frame.css`（经 `site_theme.inject_tokens(detail_frame_css)` 装配） | body 标记整体跳过 |
| A-2 | `<head>` 补 `<meta name="color-scheme" content="light dark">`（缺失才补） | 存在性检查 |
| A-3 | 剥离上游外链 `<link rel="stylesheet" href="https://fonts.googleapis.com/…">`（Google Fonts 在大陆不可达，且与站点字体栈冲突；字体由 `--font-text` 接管） | 存在性检查 |
| A-4 | `<title>` 追加 ` — 每日市场脉搏`（无则加）；补 `<meta name="description">` 与 `og:title/og:description/og:type`（取 entry 的 title/summary，缺则跳过） | 存在性检查 |
| A-5 | `<body>` 后注入**全量** SVG symbol sprite（`site_theme.icon_sprite()`）；若文档已含后端最小 sprite（`<!-- icon-subsprite:v1 -->` 标记 + 紧随的 `<svg …><defs>` 块），**摘除该最小 sprite**（全量 sprite 位置更靠前、symbol 全集覆盖，去重同时消除重复 id）—— sanitizer 产出的 `<use href="#i-*">` 与导航/页脚图标都依赖它 | body 标记整体跳过 |
| A-6 | 注入 slim 导航（§3.1）与 `<main id="main" class="frame">` 骨架；上游 `<body>` 原有内容包进 `<div class="doc">`；**过滤 `<body>` class 列表**里的 Tailwind 布局工具类（`p*`/`m*`/`max-w-*`/`mx-auto`/`space-[xy]-*`，口径见 §3.7） | body 标记整体跳过 |
| A-7 | **标题提升与移出**：取 `.doc` 内首个标题元素（sanitize 后通常是 h3（原 h1）或 h4（原 h2）），改标签为 `<h1 class="doc-title">`，保留原文与 `data-sb-h` 标记，加 `data-df-title="1"`；**若其父元素是 masthead 容器（`header` / `.cover` / `.top` / `.hero`），把标题节点移动到该容器之前**（§3.3，防 fg-on-fg 隐形标题）；无标题则用 entry title 生成并标 `data-df-title="gen"` | 见 C-3 |
| A-8 | 在提升后的 h1 后插入 `.doc-meta` 元信息行（§3.4）；若 entry 的 `run_time` 与 `time` 不同，两者都呈现（承诺 vs 事实，SPEC §6.3） | body 标记整体跳过 |
| A-9 | 结构化去重与增强：所有 `<table>` 包 `<div class="tbl-wrap">` 并加 `class="tbl"`（已有则跳过）；`.doc` 内 class 含 `rating`、**不含** `rating-*` 变体类、**非 `.doc-meta` 后代**、且文字去【】后等于 entry rating 的元素，升级为四重编码徽章（`site_render.rating_badge`，文字不变，§3.5）；`.top .meta` 在 `.doc-meta` 已呈现时摘除（信息已完整迁移）；masthead 经摘除后无元素子节点且无可见文本时，移除该空容器（stock-assistant 的 `.top` 即此形态） | 各自存在性/标记检查 |
| A-10 | `</body>` 前注入站点页脚（§3.6） | body 标记整体跳过 |

### 1.4 body 标记

`<body data-df="v1" data-date="2026-10-14" data-slug="stock-assistant">`。整文件级幂等：标记存在即跳过。`data-date` / `data-slug` 供调试与后续门禁检索。

---

## 2. HTML 骨架（frame_pass 产出形态）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  …上游 head 原样（meta / title / <style>，title 已追加站点名）…
  <meta name="color-scheme" content="light dark">      <!-- A-2，缺失才补 -->
  <style>/* A-1：tokens + components + blocks + detail-frame 四层 */</style>
</head>
<body data-df="v1" data-date="2026-10-14" data-slug="stock-assistant">
  <svg width="0" height="0" …><defs>…35 个 symbol…</defs></svg>   <!-- A-5 -->
  <a class="skip-link" href="#main">跳到主要内容</a>
  <nav class="nav" aria-label="全局导航">                          <!-- A-6，§3.1 -->
    <div class="nav-in">
      <a class="nav-brand" href="../../index.html"><svg class="ic mark"><use href="#i-line-chart"/></svg>每日市场脉搏</a>
      <div class="nav-links">
        <a class="df-back" href="index.html"><svg class="ic"><use href="#i-arrow-left"/></svg>返回 2026-10-14 时间线</a>
        <a href="../../methodology/">方法论 / Method</a>
        <a href="../../feed.xml"><svg class="ic"><use href="#i-rss"/></svg><span class="sr">RSS 订阅</span></a>
      </div>
    </div>
  </nav>
  <main id="main" class="frame">
    <div class="doc">
      <nav class="crumb" aria-label="面包屑">
        <a href="../../index.html"><svg class="ic"><use href="#i-chevron-right"/></svg>全部归档</a>
        <span class="sep" aria-hidden="true">/</span>
        <a href="index.html">2026-10-14</a>
        <span class="sep" aria-hidden="true">/</span>
        <span aria-current="page">股票助手</span>
      </nav>
      <p class="df-kicker"><svg class="ic"><use href="#i-bar-chart"/></svg>股票助手</p>
      <h1 class="doc-title" data-df-title="1" data-sb-h="1->3">股票助手 · 2026-10-14（周三）盘中研判</h1>
      <div class="doc-meta">                                      <!-- A-8，§3.4 -->
        <span class="df-time"><svg class="ic"><use href="#i-clock"/></svg>调度 <b>09:28</b></span>
        <span class="df-time"><svg class="ic"><use href="#i-timer"/></svg>生成 <b>12:39</b></span>
        <span class="chip chip-intraday"><svg class="ic"><use href="#i-clock"/></svg>盘中时点 / Intraday</span>
        <span class="rating rating-conflict"><svg class="ic"><use href="#i-shuffle"/></svg><span class="arrow">↔</span>信号矛盾</span>
        <span class="tl-sigma"><svg class="ic"><use href="#i-sigma"/></svg>+0.010</span>
        <span class="tag tag-warn"><svg class="ic"><use href="#i-alert"/></svg>口径未标注 · Σ 不可跨时点比较</span>
      </div>
      …上游正文（table 已包 .tbl-wrap、评级已升级徽章、.top .meta 已摘除、标题已移出 masthead）…
    </div>
  </main>
  <footer class="foot">                                          <!-- A-10，§3.6 -->
    <div class="foot-in">
      <div class="foot-top">
        <div class="foot-brand">…品牌 + 一句话…</div>
        <nav class="foot-cols" aria-label="页脚导航">…归档 / 关于 / 来源 三栏…</nav>
      </div>
      <div class="foot-legal">
        <p>免责声明：…</p><p>Disclaimer: …</p>
        <p>数据来源：腾讯自选股 MCP 实时采集 · 信号评分由 daily-decision-engine 确定性计算</p>
        <p>本页信息：数据日期 2026-10-14 · 生成时点 12:39 · 数据时点 收盘时点 · 报告由 AI 生成</p>
      </div>
    </div>
  </footer>
</body>
</html>
```

### 2.1 masthead 实测形态（A-7 抽取的输入，四页逐一核对）

| 页面 | masthead 容器 | 标题位置（净化后） | 抽取后遗留内容 | 处置 |
|------|--------------|-------------------|---------------|------|
| stock-assistant | `div.top` | `.top > h3[data-sb-h="1->3"]` | `.meta` 一行 | `.meta` 摘除（§3.5-3）→ `.top` 空容器移除（§3.5-4） |
| daily-review | `div.cover` | `.cover > h4[data-sb-h="2->4"]` | date-label / sub / cover-visual / stats-row / team | 全部保留，反色面呈现（detail-frame §3） |
| fund-market | `header.gradient-hero` | `header > h3[data-sb-h="1->3"]`（残留 Tailwind `text-2xl sm:text-3xl font-extrabold text-white`） | 徽章行 / meta p / 持仓诊断卡 | 保留；光斑与脉冲点摘除、诊断卡去玻璃化（§3.8） |
| stock-review | `header` | `header > h3[data-sb-h="1->3"]` | meta p（交易日 / 数据时点 / 决策引擎版本号） | 保留，反色二级墨色（§3.8） |

抽取后阅读次序：面包屑 → kicker → h1 → doc-meta → 封面视觉 → 正文，与 Apple Newsroom 文章页一致。

---

## 3. 组件裁定

### 3.1 slim 顶部导航

复用框架页 `.nav` / `.nav-in` / `.nav-brand` / `.nav-links` 全部既有类（同 Token、同 44px、同 `saturate(180%) blur(20px)`），**不写新导航 CSS**。slim 体现在链接数：品牌 + `df-back` + 方法论 + RSS 四项。

- 返回链接（`.df-back`，detail-frame.css §5）：`href="index.html"`（同日录的日期页，显式文件名不依赖目录 URL）；文案 `返回 {date} 时间线`；图标 `i-arrow-left`。
- **前置依赖**：`site_theme.SYMBOLS` 当前无 `arrow-left`（P0：图标必须来自锁定 symbol 表，禁止临时手绘）。需前端在 `SYMBOLS` 追加 Lucide 原 path：`<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>`。这是唯一的图标表增量。
- 移动端：`.nav-links` 横向滚动（框架既有），`df-back` 的 `white-space:nowrap` 保证不被截断。

### 3.2 面包屑与 kicker

`.crumb` 三段：全部归档（`../../index.html`）/ 日期（`index.html`，日期页）/ 当前任务名（`aria-current="page"`，纯文本）。kicker（`.df-kicker`）= 任务名 + 该任务在时间线同款图标（`site_content.TASK_META` 的 ico 字段）——从时间线点到详情页，图标与文案连续，不做二次翻译。

### 3.3 标题提升与移出 masthead（A-7）

- 取 `.doc` 内**文档序第一个标题元素**。四页上游提升后首标题均为报告真实标题：stock-assistant（h1→h3）、fund-market（h1→h3）、daily-review（封面 h2→h4，其文无 h1）、stock-review（h1→h3）。
- 只改标签与加类，**文字与 `data-sb-h` 标记原样保留**（标记保证 sanitizer 再跑时不会把它降回 h3）。
- **移出是硬约束，不是优化项**：若标题的父元素是 `header` / `.cover` / `.top` / `.hero`，把标题节点 `insertBefore` 到该容器之前。不移的后果可证：`.doc h1.doc-title` 的 `color:var(--fg)`（特异性 (0,2,1)）会压过 detail-frame §3 反色面容器色（(0,1,1)），浅色模式下近黑标题落在近黑封面上 = 隐形标题。CSS 侧另有一条 `.doc :is(header,.cover) h1.doc-title{color:var(--fg-on-inverse)}` 防回归兜底（保证万一抽取失败也只是配色错、不隐形），但兜底不替代抽取——位置校验由门禁 G-1 独立核查（h1 不得是 header/.cover 的后代）。
- 样式 `.doc h1.doc-title`：`--fs-title1` / `--fw-bold` / `--tracking-title1`，特异性 (0,2,1) 稳赢上游 `.cover h2`、`.head h1`、Tailwind `text-2xl sm:text-3xl font-extrabold tracking-tight`（fund-market 实测残留类名，全部单类 (0,1,0)，必输；无需逐个剥类名）。
- 标题之后的上游块（封面、hero、`.top`）保留其余内容，标题不在其内部——阅读次序为「标题 → 元信息 → 封面视觉 → 正文」，与 Apple Newsroom 文章页一致。

### 3.4 元信息行 `.doc-meta`（A-8）

字段与时间线条目 meta 区**完全同源**（entries.json 同一记录），组件复用 `.chip` / `.rating` / `.tl-sigma` / `.tag`：

| 字段 | 组件 | 来源 | 条件 |
|------|------|------|------|
| 调度时点 | `.df-time` + `i-clock` | `entry.time` | 恒渲染 |
| 生成时刻 | `.df-time` + `i-timer` | `entry.run_time` | 与 time 不同才渲染（相同则信息冗余） |
| 数据时点 | `.chip-intraday` / `.chip-close` | `entry.stage` | 恒渲染 |
| 评级 | `.rating-*` 四重编码 | `entry.rating` | 非 null |
| Σ 值 | `.tl-sigma` | `entry.sigma` | 非 null；null 时渲染 `tag-gap`「Σ 数据缺口」，**严禁回落 0.000** |
| 口径提示 | `.tag-warn` | `entry.comparable == false` | 同时间线规则 |

entries.json 缺失或无匹配 entry：只渲染面包屑日期 + 页脚「数据日期」，**不得编造任何字段**。

### 3.5 结构化去重与增强（A-9）

1. **表格**：每个 `<table>` 包 `<div class="tbl-wrap">`（框架既有类，`overflow-x:auto`）并加 `class="tbl"`（框架 Apple 表格规范：无竖线、hairline、表头次级色、数字右对齐等宽）。上游 `table/th/td` 元素级样式被 `.tbl` 类规则 (0,1,0) 与 `.doc table` (0,1,1) 压制。
2. **评级徽章升级**：匹配条件 = `.doc` 内 class 列表含 `rating`、**不含**任何 `rating-*` 变体类、**不是 `.doc-meta` 的后代**、且元素文字去【】后与 `entry.rating` 相等 → 用 `site_render.rating_badge(rating)` 重写为「SVG 图标 + 箭头 + 文字」四重编码（文字不变，只增冗余编码维度）。这是站点签名组件，详情页不得降级成纯文字。三条排除条件分别防：A-8 注入的 doc-meta 徽章被二次升级、已是徽章形态的重复处理。选择器不限定 `.verdict` 后代——覆盖 stock-assistant 的 `.verdict .rating` 与 stock-review 的 `.verdict-card .verdict-header .rating` 两种上游形态。
3. **`.top .meta` 摘除**：股票助手头部那行 `2026-10-14（周三）12:39 盘中快照 · data_stage: intraday · 腾讯自选股 MCP 实时采集` 的每个信息点都已在 `.doc-meta` 与页脚结构化呈现（含术语翻译：`data_stage: intraday` → 「盘中时点 / Intraday」），摘除它属于**信息迁移不是删内容**；仅当 `.doc-meta` 已渲染时执行。上游 `.foot` / `.disclaimer` / `.cta` **不摘除**，按 §4 白名单改样式为小字区（文章级声明与站点级声明并存，金融出版惯例）。
4. **空 masthead 移除**：`.top` 经「标题移出 + `.meta` 摘除」后无元素子节点且无可见文本（stock-assistant 实测即此形态）→ 移除该空容器，防止上游 padding/margin 留下幽灵间距。有可见内容遗留的 masthead（daily-review 封面视觉、fund-market 徽章行、stock-review meta p）一律保留。
5. **上游 meta p 默认保留**：`header/.cover > p`（fund-market 的「分析日期 / 养基宝透视架构 / 投资者：海震」行、stock-review 的「交易日 / 数据时点 / 决策引擎 v1.3」行）含有 `.doc-meta` 未承载的信息点（架构名、投资者、引擎版本号），按 §3.8 反色面规则以二级墨色 `--ap-dark-ink-2` 呈现，**不删**。仅当其文本经日期/时间/来源词剥离后为空（全部信息点已被 `.doc-meta` + 页脚承载）时，才可按第 3 条同规则摘除。

### 3.6 站点页脚（A-10）

与方法论页/框架页**同一结构同一 Token**（`.foot` / `.foot-in` / `.foot-top` / `.foot-brand` / `.foot-cols` / `.foot-legal`），链接按 `depth` 前缀调整。`foot-legal` 四段：

1. 免责声明（与方法论页逐字相同）；
2. Disclaimer 英文行（同上）；
3. 数据来源行（同上）；
4. **本页信息行**（详情页新增）：`数据日期 {date} · 生成时点 {run_time} · 数据时点 {stage_zh} · 报告由 AI 生成`。全部取自 entries.json / 路径，**不取墙钟**——守住 PUBLISH-CONVENTION 的幂等铁律（同一天重跑字节一致）。

### 3.7 `<body>` 工具类过滤（A-6）

fund-market 实测 `<body class="p-3 sm:p-6 md:p-8 max-w-6xl mx-auto space-y-6">`；stock-review 实测 `<style>` 内 `body{padding:24px 16px 48px}`。两类处置：

1. **class 过滤（主路径）**：对 `<body>` 的 class 列表逐项匹配正则 `^(p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|max-w-.*|mx-auto|my-auto|space-[xy]-.*|container|w-.*)$`，移除命中项。`space-y-*` **必须**走这条：内联产物是 `.space-y-6 > :not([hidden]) ~ :not([hidden]){margin-top:…}`，特异性 (0,3,0)（双 `:not` 伪类叠加），任何常规 CSS 选择器打不过。
2. **CSS 回补（兜底）**：detail-frame §0 `body[data-df]{padding:0;margin:0;max-width:none}`，属性选择器把特异性抬到 (0,1,1)，稳赢工具类 (0,1,0)；上游元素级 `body{padding:…}`（(0,0,1)）更不在话下。A-6 写下的 `data-df` 属性即为此服务。

只动 `<body>` 上的类；正文内元素的 Tailwind 类一律不动——那里的特异性战役由 §5.2 的既有策略打，不新增解析面。

### 3.8 反色面与封面装饰管辖（detail-frame §3）

上游 masthead 经 B-2 修复后统一落在 `--surface-inverse` 深底上。四条管辖规则（全部已在 detail-frame.css §3 实装）：

1. **段落收复**：`.doc :is(header,.cover,.weixin-cover-card) p{color:var(--ap-dark-ink-2)}`，(0,1,2) 压过 `.doc p` 的 `--fg`（(0,1,1)）——否则 fund-market 的 `text-slate-400`、stock-review 的 `header p{color:var(--fg-3)}` 都会被拖成 fg-on-fg。`strong/b/a` 提回 `--fg-on-inverse` 全亮。
2. **装饰摘除**：`.blur-3xl` / `.blur-2xl` 光斑 `display:none`（fund-market 双圆斑，纯装饰、零信息）；`.animate-pulse` `animation:none`（站点 MOTION_INTENSITY=2，零环境动画）。
3. **去玻璃化**：`.backdrop-blur-*` 状态卡（fund-market 账户持仓诊断卡）`backdrop-filter:none` + `color-mix` 8% 提亮面 + 16% 内线——内容保留，形态换成站点的「线条表达层级」语言，不用默认毛玻璃三件套。
4. **投影清零**：封面容器 `box-shadow:none`（stock-review `0 10px 25px -5px` 实证）。

---

## 4. 阅读容器宽度裁定

**裁定：正文 680px（`--container-prose`），数据宽元素探出至 980px（`--container-max`），≤900px 收回。**

| 元素类 | 度量 | 机制 |
|--------|------|------|
| 正文文本（p/li/blockquote/h*） | 680px | `.doc { width: min(calc(100% - 2*var(--gutter-phone)), var(--doc-measure)) }` |
| 表格（`.tbl-wrap`）、KPI 看板（`.kpis`）、静态图（`.viz-static`）、双栏证据（`.two`）、圆桌快照（`.cc-snap-grid`） | 探出至 980px | `--doc-breakout`：桌面 150px / 平板 48px / ≤900px 0；负 margin 居中探出 |
| 上游页面级容器（`.wrap` 720/860px、Tailwind `.max-w-6xl` 等） | 让位 | `.doc :is(.wrap,.container,.max-w-*)` 全部 `max-width:none`，度量交还 `.doc` |

理由：中文 17px 正文 680px ≈ 34–38 字/行（SPEC §4.3 等效区间），长文可读；但上游产出含 5–7 列数据表与 KPI 看板，锁死 680px 会逼出表格内部横滚（信息密度浪费）。探出方案让「读」用窄度量、「扫」用宽度量，两者同一容器内共存。≤900px 收回是因为探出量会超过视口侧余量，此时表格走 `.tbl-wrap` 内部横滚（框架既有行为），页面级无横向滚动（`body{overflow-x:hidden}` 兜底 + `min()` 宽度双保险）。

**为什么不是 860px 单栏**（上游 stock-assistant 的方案）：860px 下文行 43+ 字，超出中文舒适区；且与框架页 980px 容器、日期页 760px 窄栏都不接轨。**为什么不是 980px 通吃**：方法论长文与总复盘长文在 980px 下行宽 50 字，阅读疲劳度高，且失去「文章感」。

---

## 5. CSS 分层与类参考

注入次序（A-1）：`design-tokens.css` → `site_components.css` → `site_blocks.css` → `detail-frame.css`。前三层与框架页**逐字节相同**（同 Token 同组件的保证），`detail-frame.css` 只含扩展层（v1.1 约 660 行，零颜色字面量、零 gradient、零弹跳缓动，全部 `var(--token)`）。

### 5.1 detail-frame.css 章节索引

| 章 | 内容 | 关键选择器 |
|----|------|-----------|
| §0 | 度量与探出 | `.doc`、`.doc :is(.tbl-wrap,.viz-static,.kpis,.kpi-row,.two,.grid-2,.cc-snap-grid)`、`.doc :is(.wrap,.container,.max-w-*)`、`body[data-df]` 回补 |
| §1 | sanitizer 产物类 | `.ic-wrap(+.up/.down/.warn)`、`.ip-mark`、`.viz-static/.viz-row/.viz-lb/.viz-track/.viz-fill/.viz-cap` |
| §2 | 阅读排版归一化（元素级全量） | `.doc h1.doc-title`、`.doc :is(h3,h4)`（含 `[data-sb-h="3->4"]` 子节降档）、`.doc p/ul/ol/li/blockquote/a/strong/em/code/pre/figure/hr`、`.doc section`（hairline 分带）、字重归一 `:not(:is(.rating,.btn))`、涨跌色收敛 `.up/.pos/.down/.neg/.flat` |
| §3 | 反色表面 | `.doc :is(header,.cover,.weixin-cover-card)`（投影清零）+ 内部 `-dk` 亮变体涨跌色 + `.text-white` 收敛 + 段落/strong/a 收复 + `h1.doc-title` 防回归兜底 + 光斑脉冲摘除 + 去玻璃化 |
| §4 | 上游白名单再皮肤 **v1.1** | `.verdict/.verdict-card` 族、`.kpis/.kpi/.kpi-card` 族、`.evi(.bull/.bear)`、`.gap-note`、`.tag(.watch/.gap)`、`.sig`、`.cc-snap-*`、`.mhead/.mnum/.mtitle/.mlede`、`.cta/.cta-title/.cta-btn`、`.disclaimer/.foot`、`.voice-avatar`、`.card/.experts-box/.card-title`、`.expert-*` 族、`.grid-2`、`.footer-note` |
| §5 | 框架头/元信息/页脚 detail 变体 | `.df-back`、`.df-kicker`、`.doc-meta`、`.df-time`、`.doc .top .meta` |
| §6 | 响应式 | ≤900px 探出收回 + 快照降 2 列；≤640px KPI/KPI-Card 2 列、双栏收单列、封面内距收敛；`.grid-2` 默认单列、≥901px 双列 |
| §7 | 打印 | 容器放开、反色块（含段落）转白底黑字 |

### 5.2 特异性策略（为什么框架必胜）

| 对手 | 特异性 | 框架对策 |
|------|--------|---------|
| 上游元素选择器 `section{…}` | (0,0,1) | `.doc section` (0,1,1) 胜 |
| Tailwind 单类 `.text-base` | (0,1,0) | `.doc h4` (0,1,1) 胜 |
| 上游后代 `.cover h2` | (0,1,1) | `.doc h1.doc-title` (0,2,1) 胜 |
| 上游双类 `.evi.bull h3` | (0,2,1) | `.doc .evi.bull :is(h3,h4)` (0,3,0)+h3 → (0,3,1) 胜（白名单收口） |
| 上游同特异性 `.dek` vs `.doc p` | (0,1,0) vs (0,1,1) | 框架胜 |
| **框架自身误伤**：`.doc p` 的 `--fg` 把封面段落拖成 fg-on-fg | (0,1,1) | `.doc :is(header,.cover) p` (0,1,2) 收复（§3.8-1，v1.1 新增） |
| Tailwind body 布局类 `p-6` / `max-w-6xl` | (0,1,0) | `body[data-df]` (0,1,1) CSS 回补 + A-6 class 过滤双路径（§3.7） |
| Tailwind `space-y-6` | (0,3,0)（双 `:not` 叠加） | **CSS 打不过** —— A-6 类名过滤是唯一路径，故列为硬约束而非兜底 |
| 上游 `.verdict-card` 6px 侧条纹（P0 禁令） | (0,1,0) | `.doc :is(.verdict,.verdict-card)` (0,1,1) `border:none` + `border-left-width:0` 双清零 |
| 上游 class 级字重 700/800（`.kpi-val` / `.expert-badge` 等） | (0,1,0) | `.doc :is(div,span,li,td):not(:is(.rating,.btn))` (0,2,0) 归一 |
| 上游 `<style>` 内声明级裸 hex（`.expert-badge` `#e0f2fe`） | (0,1,0) | 白名单 `.doc .expert-badge` (0,1,1) 整体接管（B-3 修复前的中转方案） |
| 框架自身组件 `.rating` (0,1,0) vs 字重归一 (0,2,0) | — | 归一规则用 `:not(:is(.rating,.btn))` 豁免，且白名单章节排在归一之后 |

级联次序：框架四层在 `</head>` 前最后注入，与上游 `<style>` 同特异性时后置胜。后端 `<style data-origin="icon-subsprite">` 同样位于 `</head>` 末端，但 sanitizer 先于 frame_pass 运行（§1.1 顺序约束），A-1 的注入天然排在它之后——`.ic-wrap` 等同类名同特异性 (0,1,0) 时后置胜，框架定义生效。

---

## 6. 与 sanitizer 输出的共存约束

| # | sanitizer 产出形态 | 框架约束 |
|---|-------------------|---------|
| S-1 | `h1→h3`、`h2→h4`、`h3→h4`，变更元素带 `data-sb-h="原->新"` | 标题提升只改首个标题的标签；`.doc :is(h3,h4)[data-sb-h="3->4"]` 借标记还原子节降档（原生 h4 无标记，按章节级） |
| S-2 | emoji→`<span class="ic-wrap {up/down/warn}"><svg class="ic"><use href="#i-*"/></svg></span>` | A-5 必须注入**全量** sprite（否则图标全不渲染）；`.ic-wrap` 语义色由 detail-frame §1 定义（站点此前无此类）；`.ic` 基础尺寸（16px/stroke 1.75）由后端 `<style data-origin="icon-subsprite">` 与框架 components 层双重定义，保留不删 |
| S-3 | IP 标识保留为 `<span class="ip-mark" title aria-label role="img">` | `.ip-mark` 固定 20px 盒 + 15px 字，防上游 32px 正文带大；处置策略签收见 §8 |
| S-4 | Chart.js 环形图降级为 `<figure class="viz-static">` 静态条形图 | `.viz-*` 全套样式由 detail-frame §1 提供（中性条 `--fg-2`，不花强调色预算） |
| S-5 | Tailwind CDN → 内联 `body-utilities.css`（注入在 `<head>` 首位） | 框架四层在其后注入，级联次序压过 Tailwind 工具类；`space-y-*` 等 (0,3,0) 例外走 A-6 类名过滤（§3.7） |
| S-6 | 色值收敛为 `var(--token)` | 上游自定义属性（`--up:#dc2626` 等）**不在** style_pass 管辖范围，由 detail-frame §2 的 `.up/.pos/.down/.neg/.flat` 收敛规则收口 |
| S-7 | 渐变收敛为纯色 Token | **前置阻塞项 B-2**：深渐变必须落 `--surface-inverse`（禁止落 `--fg`），否则封面/hero 出现 fg-on-fg 不可见文本 |
| S-8 | `<style>` 块保留 | 框架不删上游样式，只以特异性+次序压过；白名单 §4 是唯一显式再皮肤面 |
| S-9 | 后端最小 sprite：`<style data-origin="icon-subsprite">.ic{…}</style>`（`</head>` 末端）+ `<!-- icon-subsprite:v1 --><svg …><defs><symbol id="i-*">…</symbol></defs></svg>`（`</body>` 前，仅含本页 emoji 用到的 symbol——实测 stock-review 仅 1 个 `i-alert-triangle`） | A-5 检测到 `<!-- icon-subsprite:v1 -->` 标记即**摘除该最小 sprite**：全量 sprite 位置更靠前（`<body>` 后），`<use>` 按文档序解析到全量定义，symbol 同表同 path 无分歧；摘除同时消除「同一 id 两个 symbol」的重复 id 失效 HTML。样式块不删（与 S-8 同理）；symbol 覆盖校验见 G-7 |

---

## 7. 深色模式 / 移动端 / 打印 / 降级

- **深色**：零 JS。Token 栈含完整 `prefers-color-scheme: dark` 覆盖 + `color-scheme: light dark`；反色表面在深色下为 `--ap-dark-2`（#2C2C2E，比画布亮一档的明度递进，不是反色）。上游存活的原生色值（Tailwind 空格分隔 rgb 等）不随 scheme 翻转——已知方差，记入 §9 风险。
- **移动端**：断点沿用框架 640/900/1024；探出 ≤900px 收回；`.cc-snap-grid` 降 2 列；`.kpis` / `.kpi-card` 降 2 列；`.two` 收单列；`.grid-2` 默认单列、≥901px 才双列（上游 `minmax(480px,1fr)` 在 680px 容器里必溢出，v1.1 修正）；触摸目标沿用框架 ≥44×44px（`.btn`、`.archive-item .go`）；详情页无底部 TabBar（阅读型页面，顶部 slim 导航 + 返回链接即导航全量）。
- **打印**：框架层已有打印块（隐藏 `.nav`、白底黑字）；detail-frame §7 放开阅读容器与表格横滚，反色块转白底黑字。
- **动效降级**：框架层 `prefers-reduced-motion` 全局块随栈注入，详情页零额外动效（MOTION_INTENSITY=2：仅 hover 变色 150ms 与骨架脉冲，本页无骨架）。
- **无障碍**：skip-link、`:focus-visible` 焦点环、`aria-current`、`role="img"`+`aria-label`（viz-static）、徽章四重编码均随框架栈注入；标题提升保证每页有且仅有一个 h1。

---

## 8. P0 决策签收（本次门禁结论）

### 8.1 个人 IP 形象（U+1F35C / U+265F）在上游正文中的处理 —— **保留，受约束**

**结论：接受 IP_MARK 保留策略，但附加三条约束。**

1. 定位是**身份标识不是功能图标**：锁定 symbol 表无面/餐/棋类图标，强行补绘等于手绘第二套图标库（违反 P0-1 的「全站唯一样式」更甚）；删除则丢品牌标识（违反「换皮不阉割」）。保留原字符 + `ip-mark` 包裹是两害相权下的最优解。
2. **允许位置**：署名/落款（fund-market 投资者署名「投资者：海震」旁的账户头像位）、栏目标识（daily-review 封面脚标「股市棋手 · 投研圆桌复盘专栏」的棋子前缀）、CTA 装饰前缀。**禁止位置**：导航、按钮、表头、任何承担「点击后发生什么」的功能位——功能位出现即 P0 违规，要求上游整改或改映射。
3. **样式约束**（detail-frame §1 `.ip-mark`）：固定 20px 盒 + 15px 字，防上游 32px 正文带大；平台间emoji 字形差异由固定盒吸收，不参与布局跳动。

### 8.2 警告符 SVG 映射（U+26A0 → `alert-triangle` + `warn`） —— **够用，补一个洞**

当前 `emoji_map.py` 对 U+26A0（含 VS16 变体，查表前统一剥离）映射 `("alert-triangle", "warn")`，方向/章节/CTA 四组共 16 个语义映射覆盖 2026-10-12~15 全部实测产出。**洞**：`warn` class 落在 `<span class="ic-wrap warn">` 上，而站点 CSS 此前没有 `.ic-wrap.warn` 定义——图标会回落 currentColor，警示语义褪色。本次由 detail-frame.css §1 补齐（`.ic-wrap.warn{color:var(--warn)}`），映射表本身无需改。

同时签收一个**映射语义修正**：`U+1F44D（大拇指）→ check` 是错的（点赞不是确认）。原文同句已有「点赞」文字，图形语义重复，应改为 Lucide `thumbs-up`。需前端在 `SYMBOLS` 追加 `<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>` 并把 emoji_map 该项改为 `("thumbs-up", "")`。非阻塞（图标已呈现，仅语义不准），但应在下次映射表变更时一并修正。

### 8.3 emoji-kept 保留策略 —— **现行策略过宽，收紧为三条判定规则**

实测 2026-10-14：daily-review kept 2（U+265F 棋子 ×2）、fund-market kept 1（U+1F35C 面碗 ×1）、stock-assistant kept 0——全部命中规则 K-1，可接受。但现行代码的兜底是「查不到 → IP_MARK 保留原字符」，**未登记的功能性 emoji 会静默混过门禁**（如上游某天用了 U+1F680 火箭当章节标记，查表未命中 → 原样保留 → P0 违规输出）。

**判定规则（三者穷尽，第四条不允许存在）**：

| 规则 | 语境 | 处置 |
|------|------|------|
| K-1 身份标识 | 个人 IP / 栏目标识（U+1F35C 面碗、U+265F 棋子），出现在署名/落款/栏目标识位 | 保留原字符 + `ip-mark` 包裹 + title/aria-label |
| K-2 方向冗余编码 | ▲▼↔ 及 ▲▲▼▼（ADR-003 色盲友好，评级四重编码的箭头维度） | 保留原样（这些码点本就不在 EMOJI_PATTERN 枚举内，天然不命中） |
| K-3 UGC / 通讯语境 | 用户评论、聊天引用、社群截图转录 | 保留原样 |
| —— 其余一切 | 功能图标、章节标记、状态标记、装饰符号 | **必须**命中 EMOJI_TO_SYMBOL 映射为 SVG；未命中 → 报告 `needs-manual-review` 并退出码 2 交人工判断，**禁止静默保留** |

**需后端修正**：`emoji_inline.replace_emoji` 的兜底分支，对 `is_ip_mark(token)` 为 False 的未命中 emoji，从「保留 + ip-mark」改为「保留 + `needs-manual-review` 报告」。这是发布门禁的最后一类 P0 漏口，列为阻塞项 B-4。

**2026-10-15 追加实证（B-7）**：stock-review.html:385/391 的 U+2705/U+274C 状态标记并非「未命中兜底保留」，而是构建时点（19:00:19）早于模式扩展（emoji_inline.py 19:27:27）——代码修好了、产物没重建。这证明 P0 漏口有两条独立的时间路径：**规则路径**（K-3 收紧兜底）与**产物路径**（发布前强制重建 + 时点断言）。只修一条，另一条照样放毒。

---

## 9. 已知方差与风险（接受，不阻塞）

| # | 方差 | 影响 | 处置 |
|---|------|------|------|
| R-1 | Tailwind 空格分隔 rgb（`rgb(255 255 255/1)`）不被 style_pass 匹配，原样存活 | 深色 hero 内文字色不随 scheme 翻转（hero 恒为深底，可读） | 接受；后端可将 style_pass 的 `_FUNC_COLOR` 扩展空格/斜杠语法（advisory） |
| R-2 | 圆桌头像内联 SVG 含 `linearGradient` + 裸 hex（4 个 64px  persona 插图） | 非 UI 功能图标、非主视觉、无粉紫搭配；与站点零渐变基调有张力 | 接受为内容插图（同 UGC 例外）；advisory：上游后续生成改单色填充 + Token 色 |
| R-3 | 上游 div 级字号（`.cc-headline` 22px 等）不在框架元素级管辖内 | 文章内出现少量非阶梯字号 | 接受（方差有界）；若某页明显失衡，把类名加入白名单 v2 |
| R-4 | `body-utilities.css` preflight 的 `border:0 solid #e5e7eb` 裸 hex | border-width 为 0，不可见，零视觉影响 | 接受；advisory：build_body_css.py 生成后过一遍 Token 收敛 |
| R-5 | 上游 800/900 字重定义在 class 级 div 上，CSS 无法按值选择器剥离 | 个别标题超 Apple 二元制上限 | 接受（元素级已归一）；advisory：style_pass 增加 `font-weight ≥ 700 → var(--fw-semibold)` 声明级钳制 |
| R-6 | Google Fonts 外链被 A-3 剥离后，`Noto Serif SC` 衬线观感让位站点 sans 栈 | 总复盘页失去「投研报告」衬线气质 | 刻意为之：外链在大陆不可达 + 全站字体栈统一（SPEC §3.1） |
| R-7 | 内联 `style=""` 属性的非颜色声明存活 | style_pass 的 `map_inline_styles` 只收敛 color/background-color/border-color/fill/stroke 族；`font-size`/`margin`/`opacity` 等原样存活（实测：stock-assistant `.v style="font-size:15px"`、stock-review `div style="margin-top:10px;font-size:13.5px;color:var(--sub)"`、daily-review `.date-label span style="font-size:16px;opacity:.85"`）。内联样式特异性 (1,0,0,0)，任何类选择器打不过 | 接受（方差有界且 color 族已 Token 化）；advisory：style_pass 后续对 inline `font-size` 做阶梯钳制需评估破坏上游布局的风险，不列为阻塞 |

---

## 10. 实现约束清单（交接前端/后端）

**frame_pass.py（后端）**

- C-1 处理对象以 entries.json `html` 字段为唯一事实源；不扫目录、不碰 `index.html`。
- C-2 `<body data-df="v1">` 整文件幂等；临时文件 + rename 原子写。
- C-3 标题提升条件：`.doc` 内文档序首个 `h1-h6`；已有 `data-df-title` 则跳过；无标题才用 entry title 生成（标 `data-df-title="gen"`）。**父元素为 `header`/`.cover`/`.top`/`.hero` 时，标题节点必须移出到该容器之前**（§3.3 硬约束）；G-1 门禁独立核查 h1 不得是 header/.cover 后代。
- C-4 `.doc-meta` 字段表见 §3.4；Σ 为 null 渲染 `tag-gap`，**严禁 0.000 兜底**；`comparable == false` 必须带 `tag-warn`。
- C-5 页脚「本页信息」行只取 entries.json / 路径字段，**禁止墙钟时间**（幂等铁律）。
- C-6 表格包裹幂等：`<table>` 无 `.tbl-wrap` 父级才包；`class` 已含 `tbl` 才加。
- C-7 探出宽度公式见 detail-frame §0；禁止把裸 `<table>` 加进探出选择器列表（与 `.tbl-wrap` 负 margin 双重叠加）。
- C-8 A-3 剥离外链 stylesheet 时保留其余 `<link>`（若有 canonical 等）。
- C-9 每文件输出审计行（改动摘要），汇总退出码 0/2。
- C-10 与 sanitize_body 的顺序固定：sanitize → frame；两者可各自重跑（标记幂等），但**不要**把 frame 嵌套进 sanitizer 包（关注点分离：sanitize 改呈现，frame 补结构）。

**前端（贾思敏）**

- C-11 `site_theme.SYMBOLS` 追加 `arrow-left`（path 见 §3.1）与 `thumbs-up`（path 见 §8.2）；`REQUIRED_TOKENS` 追加 `--surface-inverse`、`--fg-on-inverse`。
- C-12 修 `site_render.py:109` 优先级 bug（见交付报告阻塞项 1）后重建全部页面。
- C-13 `<body>` class 过滤按 §3.7 正则执行；`space-[xy]-*` 命中项**必须**移除（CSS 无解），其余命中项移除后由 `body[data-df]` 兜底；过滤完成后 body class 不应再有布局类残留（审计行自检）。
- C-14 类名冲突门禁：frame_pass 构建时输出「上游 class × 框架组件类」交叉清单（与 `site_components.css` / `site_blocks.css` 的类名集合逐一比对）。交叉类只有两种合法结局——已在 §4 白名单收录（如 `.card` / `.rating` / `.tag`），或在审计报告显式记名为接受方差；两者都不占的交叉类 = 构建失败。防止上游某天新增 `.btn` / `.chip` 同名类把框架组件带偏。

**验收门禁（QA 可执行）**

- G-1 四个详情页各含：1 个 h1（`data-df-title`）且该 h1 **不是** `header`/`.cover` 的后代（A-7 移出校验）；sprite（`<symbol id="i-arrow-left"`）、`.nav`、`.doc-meta`、`.foot`；`<table>` 100% 有 `.tbl-wrap` 父级。
- G-2 扫描详情页：emoji 仅存在于 `.ip-mark` 内（正则对 `<span class="ip-mark"…>…</span>` 段外扫描为 0）；裸 hex 为 0（`var(--` 外，注释豁免需先剥注释）；gradient 为 0；`<script` 为 0。
- G-3 深色模式（`prefers-color-scheme: dark` 模拟）下：封面/hero 为 `--surface-inverse` 深灰、其内文字 `--fg-on-inverse` 亮色，对比度 ≥ 4.5:1；无 fg-on-fg 组合。
- G-4 390px 视口无页面级横向滚动；表格在 `.tbl-wrap` 内横滚。
- G-5 幂等：连续两次 `frame_pass --in-place`，文件 shasum 不变。
- G-6 `prefers-reduced-motion: reduce` 下无过渡动画（随框架栈）。
- G-7 sprite 完整性：页面内全部 `<use href="#i-*">` 引用的 symbol 均存在于全量 sprite；全文 `<symbol id=` 无重复 id（最小 sprite 已摘除的判据）；`<!-- icon-subsprite:v1 -->` 标记不残留（连同其 svg 一并摘除）。

---

## 11. 前置阻塞项（本规范落地的前置依赖）

| # | 阻塞项 | 归属 | 详情 |
|---|--------|------|------|
| B-1 | 框架页 `rating-lg` 类名优先级 bug | 前端 | `site_render.py:109`，见交付报告阻塞项 1 |
| B-2 | sanitizer `gradient_pass` 深渐变落 `--fg` 造成 fg-on-fg 不可见文本 | 后端 | 深渐变（均亮度 < 0.2）必须落 `--surface-inverse`；配套 `token_map` 浅色字（亮度 > 0.75、role=text）按色相族映射 `-dk` 亮变体、中性浅色映射 `--fg-on-inverse`，**禁止映射到 `--rating-*-wash` 当文字色**（8% alpha 淡底 token 做前景 = 隐形文字） |
| B-3 | sanitizer `style_pass` 不收敛 `<style>` 内自定义属性定义 | 后端 | `--up:#dc2626` 类定义原样存活；按属性名词义角色（bg/surface→bg；fg/text/ink→text；border/line→border）收敛，未知名保留 + unmapped 报告 |
| B-4 | emoji 兜底保留过宽 | 后端 | §8.3 规则化：非 IP 标识的未命中 emoji → `needs-manual-review`，禁止静默保留 |
| B-5 | `_CHART_CDN` 误报 | 后端 | 「Chart.js」字样出现在正文/figcaption 即触发 `needs-manual-review`（退出码 2）；CDN 指纹只应在 `<script>` 上下文匹配（`live_ref` 改为只在 `_SCRIPT_BLOCK` 匹配结果内检索） |
| B-6 | `script_pass` 无 ECharts 指纹 | 后端 | `_CHART_CDN`（`chart.umd.js\|chart.min.js\|Chart.js`）与 `_CHART_NEW`（`new Chart(`）都不覆盖 echarts：`_stage/docs/daily/2026-10-15/stock-review.html:7` 的 `echarts@5.4.3` CDN script 原样存活（外部请求 + G-2 的「`<script` 为 0」判据直接失败）。实测本页无 `echarts.init` 调用（死引用，删掉即净）。修法：补 `_ECHARTS_CDN = echarts(\.min)?\.js\|echarts@` 与 `_ECHARTS_NEW = echarts\.init\|new\s+echarts`，纳入既有图表脚本处置分支；若某页真有存活 `echarts.init`，按 Chart.js 同路径静态化 + 数据冗余校验 |
| B-7 | stage 产出物陈旧于 sanitizer 代码 | 后端（发布链路） | `emoji_inline.py`（mtime 19:27:27）/ `emoji_map.py`（19:27:47）的 U+2705/U+274C 映射与 U+2700-27BF 模式扩展，晚于 `_stage/docs/daily/2026-10-15/stock-review.html`（19:00:19）的构建时点 → 该页 L385/L391 的 U+2705/U+274C 状态标记原样漏过消毒（P0「emoji 作功能图标」）。全库扫描实测：19 个 HTML 中仅此 2 处（清单见交付报告）。修法：B-4/B-6 修复后**重建全部 stage 产出**，合规门禁只对重建后产物放行；发布流水线增加「代码时点 vs 产物时点」断言，代码新于产物即拒绝发布 |

B-1 不修，框架页徽章四重编码缺色；B-2/B-3 不修，总复盘页封面与结论块仍会文本不可见/裸 hex 外露；B-4 不修，P0 门禁存在静默漏口；B-5 不修，正文提到图表库名即假阳性报警；B-6 不修，echarts 页带外部 script 发布；B-7 不修，陈旧产物绕过修复直接上线。**本规范的验收以 B-1 ~ B-7 修复为前提。**

---

## 12. 白名单增长规则

§4 白名单按「承载数据/结论的块」收录，当前 **v1.1** 覆盖四页实测类名（stock-assistant / fund-market / daily-review / stock-review）。增长规则：

1. 新上游类名出现且**承载数据语义**（看板/证据/图表/快照/评级/专家观点）→ 加入白名单，版本号 +0.1，在 detail-frame.css §4 增补规则，同步更新本规范 §5.1 索引；
2. 新上游类名仅为装饰（配色/圆角/间距微调）→ 不收，接受方差（R-3）；
3. 新上游类名违反 P0（渐变/侧条纹/emoji 图标）→ 不收样式，退回上游整改或补 sanitizer 规则；
4. 新上游类名与框架组件类**同名**（`.card`/`.rating`/`.tag` 已在此列）→ 必须显式收录并注释冲突来源，走 C-14 门禁登记，不允许静默依靠级联次序；
5. **禁止通配符大扫除**（`.doc div{…}` 式全局重写）——那会制造第二次「两套设计语言打架」，只是换方方向。

---

## 13. 变更记录

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-10-15 | 初版建立。裁定 680px prose + 数据探出、slim 导航、同源页脚、反色 Token、sanitizer 共存八条、P0 三决策 | 上游详情页无站点一致性；框架页门禁发现两处构建 bug 与 sanitizer 五处阻塞项 |
| 2026-10-15 | v1.1：标题移出 masthead 升为硬约束（A-7/C-3/G-1）；反色面段落收复与封面装饰管辖（§3.8）；`body[data-df]` 回补 + A-6 类名过滤（§3.7/C-13）；icon-subsprite 去重与 G-7（S-9）；评级升级选择器泛化（§3.5-2）；白名单扩 v1.1（verdict-card / kpi-card / card / expert-* / grid-2 / footer-note）；类名冲突门禁（C-14）；新增阻塞项 B-6（ECharts）、B-7（stage 产物陈旧）；风险 R-7（inline 样式） | 10-15 stock-review.html 与四页 masthead 结构实测：发现 `.doc p` 会拖黑封面段落（fg-on-fg）、fund-market body 带 Tailwind 布局类、后端已实装最小 sprite、U+2705/U+274C 陈旧产物 2 处、echarts CDN 存活 |
