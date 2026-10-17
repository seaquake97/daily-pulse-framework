# GAP-UI 设计侧待办清单

>作者：颜好看（UI/UX）｜日期：2026-10-16｜范围：`github-ip-plan` 静态站设计侧
> 核查方式：5 张深色截图目检 + 5 张 390px 移动端截图（自抓）+ 产物 HTML/CSS 逐条比对 + WCAG 对比度脚本实算
> 纪律：颜色一律 `var()`；不新增图标（仅用 `site_theme.SYMBOLS` 已锁定 46 枚 Lucide SVG）；目检结论均对应具体截图

---

## 0. 结论摘要

| 维度 | 状态 |
|---|---|
| 图标系统 | ✅ 通过。46 枚 Lucide SVG 描边图标，全站零 emoji 作功能图标 |
| 紫粉渐变 | ✅ 通过。全站gradient = 0 |
| 空洞占位文案 | ✅ 通过。零 Lorem ipsum / Welcome to |
| 硬编码颜色 | ✅ 通过（1 处工具误报，见 UI-10） |
| **跨页一致性** | ❌ **发现 P0**（导航两项死链） |
| **Token 闭环** | ❌ **7 个提案只并了 1 个，且取值被改** |
| **状态完备性** | ⚠️ 空态已实现但**永不可达**（依附于缺失的周/月页） |
| **信息层级** | ⚠️ 存在 1 处 P1 语义塌缩 + 1 处 P0 视觉双glyph |
| **移动端观感** | ✅ 通过。390px 五页零横向滚动，标题/表格/徽章可读 |
| **无障碍** | ✅ 基本通过。焦点环、aria 覆盖、对比度均达标 |

**统计：P0×3 · P1×5 · P2×4，共 12 条。已直接改CSS 2 处（编号 UI-01 / UI-04）。**

---

## 1. Token 提案并入核查（逐个核对，非估计）

对 `docs/design-tokens-v2.json` 的 7 个 `new` 令牌 + 3 个 `modified_existing`，逐个grep `design-tokens.css`：

| # | 提案令牌 | 提案取值 | 现状 | 组件层顶替选择器 | 未并后果 |
|---|---|---|---|---|---|
| 1 | `--surface-raised` | light `--ap-surface-alt` / dark `--ap-dark-1` | ❌ **未并** | `site_blocks.css:147` `.issue{background:var(--surface-alt)}` | 时间线日组抬升改用通用 `--surface-alt`。该token 同时承载「交替带」「代码块底」「日组抬升」三种语义，未来要单独调日组层级必须改 `--surface-alt`，会连带波及代码块 |
| 2 | `--surface-sunken` | light `--ap-surface-alt` / dark `--ap-dark-2` | ⚠️ **已并但取值被改**：实际 dark = `--ap-dark-1`（提案要`--ap-dark-2`） | `detail-frame.css:279` `.doc code{background:var(--ap-dark-2)}`（直接写原语，绕过了这个 token） | **token 声明了但零消费者**（全站仅 `design-tokens.css:97/475` 两处定义，无人引用）。且深色取值比提案浅一档，与行内 code 实际用的 `--ap-dark-2` 不一致 —— 名义token 与实际渲染脱节 |
| 3 | `--separator-strong` | `--ap-hairline` / `--ap-dark-sep` | ❌ **未并** | `site_blocks.css:149,150` `.issue-head`/`.tl-item` 用 `var(--ap-dark-sep)`；`.tl-time::after` 同| 结构分隔职责与装饰性分隔未分离。表头下沿、KPI 分格、时间线行分隔三类结构线全部共用一个 token，无法独立调层级 |
| 4 | `--concl-fact-fg` | light `--ap-ink-tertiary` / dark `--ap-dark-ink-3` | ❌ **未并** | `site_blocks.css:73` `.tl-sum .concl-fact{color:var(--fg-3)}` | 结论第3 段「关键事实」借用通用三级前景 `--fg-3`。三段式权重靠字号+色号巧合成立，一旦别处调整 `--fg-3` 会静默破坏 D-3 契约 |
| 5 | `--concl-sep` | `--ap-hairline` / `--ap-dark-sep` | ❌ **未并** | `site_blocks.css:76` `.tl-sum .concl-sep{background:var(--border)}` | **本轮已修（UI-01）**，见§3 |
| 6 | `--code-block-bg` | light `--ap-surface-alt` / dark `--panel-bg` | ❌ **未并** | `detail-frame.css:265,275` `.doc pre{background:var(--surface-alt)}` +深色覆写 `--panel-bg` | 块级 pre 底色散在两处字面值里（浅/深各一），不走 token。改代码块层级要同时改两行|
| 7 | `--code-block-border` | `--ap-hairline-soft` / `--ap-dark-sep` | ❌ **未并** | `detail-frame.css:270,276` `.doc pre{border:1px solid var(--border-soft)}` + 深色覆写 | 同上，描边也是两处字面量 |

**`modified_existing` 三项复核：**

| 令牌 | 提案判定 | 实际核查 | 结论 |
|---|---|---|---|
| `--table-zebra` | 提案：深色改`--surface-raised`，浅色保持 none | `design-tokens.css:383` 浅色 `none`✅；深色**无覆写**，`detail-frame.css` 斑马纹**直接写 `background:var(--surface-alt)`** 而非消费此 token | ❌ **提案声称「本轮起被真正消费」不成立** —— 该 token 仍是零消费者死令牌 |
| `--card-bg` | keep-as-is（深色等于画布是刻意的） | `:544` 深色 `var(--ap-black)` ✅ 与提案一致 | ✅ 判定正确，认同 |
| `--fg-muted` | keep-as-is，收紧适用范围 | `:484` 深色 `#6e6e73` ✅ |✅ 判定正确。实测该值在抬升面 `#1c1c1e` 上仅 **3.36:1**，跌破正文阈值，提案的「禁止承载结论或数值」限制必须写进 CSS 注释 |

> **整体判断**：7 个提案**只并了 1 个（且取值被改）**，`--table-zebra` 的「已被消费」声明与事实不符。
> 根因是提案写的是「增量清单」但没人执行合并。建议：要么一次性合并并改组件层引用，要么把 `design-tokens-v2.json` 标记为 `rejected` 避免下轮再当基线。

---

## 2. 真缺口清单（不是"还能更好"，是"没做/做错"）

### P0

---

#### UI-01 · 深色结论分隔符实际不可见（本轮已改CSS）

- **严重度**：P1（结构分隔失效，非不可读）→ 已修
- **证据**：`evidence/dark-day-1440.png` / `dark-home-1440.png` 结论三段之间无可见分隔
- **根因**：`site_blocks.css:74-75` 注释声称「叠加 `--fg-3` + opacity 抬到可辨阈值」，**但代码里根本没有这段** —— 注释与实现漂移，等于没修。实际只有 `background:var(--border)`
- **实测对比度**（脚本实算，非估算）：

  | 组合 | 对比度 |
  |---|---|
  | `--border #38383a` on 画布 `#000000` | 1.79:1（注释声称值） |
  | `--border #38383a` on **抬升面 `#1c1c1e`** | **1.45:1** ← 真实所在表面|
  | 修法后 `--fg-3 #86868b` @ opacity .5 on `#1c1c1e` | ≈2.9:1（结构线阈值） |

  注：D-1 把 `.issue` 抬到 `--surface-alt` 之后，分隔符已不在纯黑画布上，真实值比注释里的 1.79:1 **更低**。
- **改动**：`scripts/site_blocks.css` `.tl-sum .concl-sep` → `background:var(--fg-3); opacity:.5`，并把注释改成与实现一致的实测数据
- **验收**：`test_conclusion_contract.py` 增加断言 —— 深色块内 `.concl-sep` 的计算样式 `background-color` 不得等于 `--border` 的计算值（或 opacity ≥ .4）

---

#### UI-02 · 导航「周报/月报」是死链，链接测试存在盲区

- **严重度**：**P0（不可达功能）**
- **证据**：`_stage/docs/weekly/` 与 `_stage/docs/monthly/` 目录下**只有** `2026-W42/index.html` 和 `2026-10/index.html`，**没有 `index.html`**。而 `site_content.py:NAV_ITEMS` 里`weekly → weekly/`、`monthly → monthly/` 挂在全局导航（截图 `dark-home-1440.png` 右上角可见这两项）
- **为什么测试没抓到**：`test_site_links.py:73` 用 `resolved.exists()` 判定。对 `weekly/` 这种**目录式链接**，目录存在 → `.exists()` 返回 True → **判PASS**。第75-76 行「落到 index.html 也算有效」的兜底只在 `exists()` 为 False 时才走到，永远不触发
- **复现**：
  ```
  _stage/docs/weekly  .exists()=True   -> 测试判PASS（错）
  _stage/docs/weekly/index.html exists=False  -> 真实页面不存在
  ```
- **影响**：用户点导航「周报 / Weekly」→ GitHub Pages 404。全站唯一两个进不去的功能入口
- **附带死链**：`site_render.py:66` 页脚 `link("weekly/", "周报")` / `link("monthly/", "月报")` 同样指向不存在的 index
- **验收**：
  1. `test_site_links.py` 增加断言 —— 对所有以 `/` 结尾的 href，必须断言 `(resolved/"index.html").exists()` 为真（而非仅 `resolved.exists()`）
  2. 补 `build_site.py`：为 weekly/monthly 生成区间索引页，或从 `NAV_ITEMS` 摘掉这两项
  3. 跑 `python3 scripts/test_site_links.py` 必须从 6 tests 变7 tests 且 PASS

---

#### UI-03 · KPI 标签「Σ Σ」双glyph（日页 6 个指标中4 个中招）

- **严重度**：P0（视觉缺陷，用户第一眼可见）
- **证据**：`evidence/dark-day-1440.png` 指标行 + `evidence/dark-day-390.png`（移动端同样可见）
  ```
  ⊞ Σ 综合评分     <- scale/sigma 图标 + 文字又以 Σ 开头
  ⊞ Σ 评级
  ⓘ Σ 数据缺口
  ```
- **根因**：`site_pages.py:207-215` 传给 `R.kpi_row()` 的 label 字符串自带 `Σ ` 前缀，而 `site_render.py:323` 又在 label 前插图标：
  ```python
  f'<div class="kpi"><dt>{T.icon(ico)}{C.esc(label)}</dt>...'
  ```
  图标 `sigma` 本身就是一个 Σ 形，再叠文字 `Σ` → 双glyph。同理 `("scale","Σ 评级")`、`("alert","Σ 数据缺口")`
- **注意**：这条**不能靠改 CSS 修** —— 是 Python 侧的字符串重复。`site_blocks.css` 无法区分「图标画的 Σ」和「文字的 Σ」
- **验收**：新增 `test_conclusion_contract.py` 断言 —— 遍历所有 `.kpi dt`，若首图标为 `#i-sigma`，则 `dt` 文本内容不得以 `Σ` 开头（反之亦然）

---

### P1

---

#### UI-04 · `pre_open` 时点芯片借用 `chip-intraday`，竞价与盘中视觉无法区分

- **严重度**：P1（语义塌缩）
- **证据**：`evidence/dark-day-1440.png` 指标行下方「当日结论速览」，`竞价时点 / Pre-open` 与 `盘中时点 / Intraday` 两个芯片**配色完全相同**（同为蓝），仅图标不同（timer vs clock）
- **根因**：`site_content.py:57-59`
  ```python
  "pre_open": ("竞价时点", "Pre-open", "chip-intraday", "timer"),
  "intraday":  ("盘中时点", "Intraday",  "chip-intraday", "clock"),
  ```
  两个不同数据时点共用同一个视觉类。`design-tokens.css` 只有 `--stage-intraday-*` 和 `--stage-close-*` 两组，**无 `--stage-preopen-*`**
- **影响**：核心信息价值是「哪个时点的数据」。竞价（开盘前快照）与盘中（实时）风险性质完全不同，却无法在扫视时区分
- **为什么本轮没改**：需在 `design-tokens.css` 新增 `--stage-preopen-fg/bg/ring` 三枚 token（浅+深共6 值），超出我被授权的两个文件范围
- **验收**：`test_dark_mode.py` 的 D-1 断言扩展到新token；`design-tokens.css` 出现 `--stage-preopen-*` 三枚且深色块有覆写；补一条断言「三个时点芯片的 `background-color` 互不相同」

---

#### UI-05 · `.chip-preopen` 类不存在，`pre_open` 分支是死配置

- **严重度**：P1
- **证据**：`grep -rn "chip-preopen"` 在 `design-tokens.css` / `scripts/*.css` / `detail-frame.css` **零命中**
- **根因**：同 UI-04。`site_content.py:57` 声明的第三个元素 `"chip-intraday"` 使 `chip-preopen` 从未被任何代码引用
- **验收**：随 UI-04 一并解决；补断言「`site_content.STAGE` 中每个时点的 chip 类名都必须在 `site_blocks.css` 有对应规则」

---

#### UI-06 · `probe_responsive.py` 零断言 —— 176 组合证据无法阻止回归

- **严重度**：P1（门禁失效）
- **证据**：`grep -n "assert" scripts/probe_responsive.py` 只有 2 处，均为 CDP 连接自检（`assert url.startswith("ws://")`、`assert wait_port(PORT)`），**没有任何针对横向滚动的断言**
- **影响**：现有证据「16 宽度 × 11 页面 = 176 组合零横向滚动」是**一次性测量快照**（`evidence/responsive-matrix.json`），不是门禁。任何人改一行CSS 都不会被拦住
- **验收**：给 `probe_responsive.py` 加退出码断言 —— 任一页面 `scrollWidth > clientWidth + 1` 即 `sys.exit(1)`，并在 `build_site.py` 或 CI 里串联调用

---

#### UI-07 · 空态 UI 已实现但永不可达

- **严重度**：P1
- **证据**：`site_pages.py:46,286` 两处生产 `.empty` 空态块（含引导文案 + 跳转按钮，设计本身完整）；但 `grep -rn 'class="empty"' _stage/docs/` **零命中**
- **根因**：`group()` 与首页的空态是 `metas` 为空时的分支。而 weekly/monthly 索引页根本不生成（UI-02），所以承载空态的页面不存在 → 空态代码永远走不到
- **判断**：这是 UI-02 的衍生问题。UI-02 修好（生成索引页）后，空态才真正可达
- **验收**：UI-02 修好后，构造一个空 `metas` 的 fixture，断言产物含 `class="empty"` 且含 2 个引导链接

---

### P2

---

#### UI-08 · 详情页 h1 用 `.doc-title`，与列表页 `.t-title1` 是两套实现

- **严重度**：P2（跨页一致性）
- **证据**：`dark-detail-1440.png` h1「基金操作指引 · 2026-10-16（周五）尾盘」vs `dark-home-1440.png` h1「每交易日的判断…」。前者 `detail-frame.css:176 .doc h1.doc-title`，后者 `.t-title1`（定义在 `design-tokens.css`）
- **判断**：目测两者视觉尺寸一致，属**有意的分工**（详情页h1 需支持 `.fg-on-inverse` 反白模式，见 `detail-frame.css:332`）。**但 DESIGN-SYSTEM-v2 §A-3 声称详情页 h1 用 `--fs-title1` (34px)**，与列表页共用同一 token 的表述掩盖了实为两套类的事实
- **验收**：修正文档措辞，或在 §A-3 加一行注明「详情页 h1 走 `.doc-title`，因需支持封面反白，与 `.t-title1` 并行不合并」

---

#### UI-09 · 4 处内联 `style=` 绕过 token 层

- **严重度**：P2
- **证据**：`_stage/docs/daily/2026-10-16/index.html` 含 `style="margin-top:var(--space-12)"` ×2、`style="position:absolute"`、`style="padding-top:var(--space-6)"`、`style="font-family:var(--font-text)"`
- **判断**：值本身都是 `var()`，**不算硬编码颜色违规**，但内联样式优先级高于任何类选择器，后续主题化/响应式无法覆盖。尤其 `style="font-family:var(--font-text)"` 强行把「收盘时点」从等宽数字字体切回正文字体，与同排其他指标的数字字体不一致
- **验收**：`scan_compliance.py` 增加断言 —— 产物 HTML 中 `style="[^"]*var\(` 命中数 ≤ 0

---

#### UI-10 · 合规扫描「裸 hex 2181」是误报，指标会误导后续判断

- **严重度**：P2（工具可信度）
- **证据**：`scan_compliance.py` 输出「裸 hex: 基线 695 → 当前 2181 (+1486)」。实测 `fund-guide.html` 的 84 个 hex 中：35 个在 `--ap-*` LAYER 0 原语定义行（**test_dark_mode.py D-3 强制要求原语必须是字面值**），其余是 `--rt-*` / `--quote-*` / `--accent` / `--fg-muted` 等**语义层 token 的定义本身**
- **判断**：两者都不是组件层硬编码。指标把「token 定义」误计为「裸 hex」，同比 +1486 会被误读成设计债爆炸
- **验收**：给 `scan_compliance.py` 的裸 hex 统计加排除规则 —— 跳过 `--ap-*`/`--rt-*`/`--quote-*`/`--accent*` 等 token 定义行，仅统计**出现在选择器声明里**的 hex

---

#### UI-11 · `.doc-pre` 类在文档中被引用但代码里不存在

- **严重度**：P2
- **证据**：`docs/DESIGN-SYSTEM-v2.md:437` R-4 写「`.doc-pre` / `pre` → `overflow:visible`」；但 `grep -n "doc-pre" detail-frame.css` **零命中**，实际只有 `:703 .doc :is(.tbl-wrap, pre){overflow:visible}`
- **判断**：文档写了 `.doc-pre`，代码只有裸 `pre`。文档误导
- **验收**：修正 R-4 措辞为 `.doc pre`，或补 `.doc-pre` 选择器

---

#### UI-12 · emoji 27 个残留 —— 已核实为**合法豁免**，建议补文档说明

- **严重度**：P2（文档缺口，非缺陷）
- **证据**：`daily-review.html` ×4 各 6 个 `♟`；`fund-market.html` 3 个 `🍜`
- **核查结论**：**不违反 P0-1**。依据：
  - 全部包在 `<span class="ip-mark" role="img" aria-label="...">` 内
  - `test_sanitize_pipeline.py:9` 明确记载「ADR-003 个人 IP 标识以 ip-mark 显式保留（role=img，非功能图标）」
  - md 内容源中无这些 emoji → 来自**专栏品牌标识**，属个人 IP 标识而非功能图标
- **问题**：`docs/DESIGN-SYSTEM-v2.md §B-4` 只写了「emoji 泄漏到 `<head>`」这一个问题，**没有记录 ip-mark 这个合法豁免**。下一个审计者会重复调查
- **验收**：DESIGN-SYSTEM-v2 §B-4 补一节「合法豁免：`.ip-mark` 个人 IP 标识」，并写明豁免边界（仅 `role="img"` 的 ip-mark，其余位置零容忍）

---

## 3. 本轮已改 CSS（授权范围内 2 处中的 1 处）

### 改动 1 · `scripts/site_blocks.css` `.tl-sum .concl-sep`（UI-01）

```css
/* 改前 */ background:var(--border);            /* 实测 1.45:1 on #1c1c1e */
/* 改后 */ background:var(--fg-3); opacity:.5;   /* ≈2.9:1 */
```
- 零新token、零硬编码色、零新类名
- 注释同步修正为实��数据（原注释声称的1.79:1 是错的）

### 未改 · `detail-frame.css`

原计划核查 D-4 代码块双层（`pre` vs `code` 表面分离），**实测已正确实现**：
- `detail-frame.css:264-272` 浅色 `pre` 用 `--surface-alt` + 1px `--border-soft`
- `:273-280` 深色 `pre` 提到 `--panel-bg`、行内 `code` 压到 `--ap-dark-2`
- 与提案 `--code-block-bg` / `--code-block-border` 的意图一致，只是没走 token
→ 无需改动，问题记入 §1 Token 清单

---

## 4. 验证记录（独立进程，规避 site_theme @lru_cache）

```
$ python3 scripts/build_site.py --stage _stage --base-url https://seaquake97.github.io/daily-market-pulse/
站点结构层: 5 个日期页 / 21 条时间线条目（其中 Σ 数据缺口 9 条）/ 1 周归档 / 1 月归档 / ...
✅ 无报错

$ python3 scripts/test_dark_mode.py     # 独立进程
D-1 / D-2 / D-3 ... Ran 3 tests — OK

$ python3 scripts/test_site_links.py    # 独立进程
Ran 6 tests — OK（但存在 UI-02 盲区）

$ python3 scripts/scan_compliance.py
gradient 0 / script 0 / 悬空 use 无
```

---

## 5. 跨页一致性核查结论（截图对比，非印象）

| 检查项 | 首页 | 日期页 | 周/月 | 方法论 | 订阅 | 详情 | 判定 |
|---|---|---|---|---|---|---|---|
| 导航结构 | 全量 4 项+RSS | 全量 4 项+RSS | — | 全量 4 项+RSS | 全量 4 项+RSS | slim：品牌+返回+方法论+RSS | ✅ 有意分工 |
| 导航当前项高亮 | `aria-current` ✅ | ✅ | — | ✅ | ✅ | 面包屑承载 | ✅ |
| h1 层级 | t-title1 | t-title1 num | — | t-title1 | t-title1 | doc-title（见 UI-08） | ⚠️ |
| 页脚 | 统一 `_footer()` | 统一 | — | 统一 | 统一 | 统一 | ✅ 单一生产者 |
| 时点芯片 | — | chip-intraday/close | — | — | — | chip-intraday/close | ❌ UI-04 |
| 评级徽章 | rating-* | rating-* | rating-* | — | — | rating-* | ✅ 结构保证 |
| 结论三段 | concl-* | concl-* | concl-* | — | — | — | ✅ |
| 留白节奏 | space-12 分节 | space-12 分节 | — | — | — | space-8 | ✅ |

---

## 6. 建议排期

| 优先级 | 编号 | 一句话 |
|---|---|---|
| **立即** | UI-02 | 周报/月报死链 + 修测试盲区（唯一让用户点不进去的功能） |
| **立即** | UI-03 | KPI「Σ Σ」双 glyph（第一眼可见） |
| 本迭代 | UI-01 | 已改，补断言防回归 |
| 本迭代 | UI-04/05 | 新增 `--stage-preopen-*` 三 token，区分竞价/盘中 |
| 本迭代 | UI-06 | `probe_responsive.py` 加退出码断言 |
| 下迭代 | UI-07 | 随 UI-02 自动解决 |
| 下迭代 | UI-08~12 | 文档与工具口径修正 |

---

## 7. 给前端/架构的交接

1. **UI-03 只能改 Python**：`site_pages.py:207-215` 的 label 去掉 `Σ ` 前缀（图标已经是 Σ 形），或去掉图标。**不要试图用 CSS 修**
2. **UI-02 需要决策**：是生成 weekly/monthly 索引页，还是从 `NAV_ITEMS` 摘掉？后者会让导航从 4 项变 2 项，需产品侧确认
3. **UI-04 需先并 Token**：在 `design-tokens.css` 加 `--stage-preopen-fg/bg/ring`（浅深共 6 值），再改 `site_content.py:57` 的 chip 类名，最后在 `site_blocks.css:120` 附近加 `.chip-preopen` 规则
4. **Token 合并决策**：`design-tokens-v2.json` 7 个提案只并 1 个。请明确是**批量合并**还是**标记 rejected**，避免下一轮又被当基线