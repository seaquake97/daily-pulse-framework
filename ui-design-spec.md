# 老北京的热干面 · GitHub Pages 落地页与日报视觉规范

> 版本 v1.0 · 2026-10-14 · 作者：ui（gh-ip-publish 团队）
> 适用范围：GitHub Pages 内容 IP 站点（seaquake970623）——落地页、每日日报聚合页、复盘报告页、方法论页。
> 配套原型：`landing-prototype.html`（单文件、零外部依赖、可直接托管预览）。

---

## 0. 设计原则与 Rationale

| 原则 | 含义 | 落地手段 |
|---|---|---|
| **传承公众号身份** | 老用户从公众号迁移过来时"一眼认出这是同一个人" | 琥珀金 #D97706 作品牌主色、暖白纸面底色、15–16px 正文、1.75 行高——全部延续公众号排版规范 |
| **金融终端的精度感** | 内容是量化研判，视觉必须"像那么回事" | 等宽数字（tabular-nums）、红涨绿跌、信号评分条、评级徽章 |
| **可验证 > 好看** | IP 的核心承诺是"代码评级、台账结算" | 每个评级都带 σ 数值与阈值区间；数据时点强制标注；演示数据必须打 DEMO 标 |
| **双语平等** | 中英切换不是翻译补丁，而是两种都对等的排版 | 语言切换器改写 `<html lang>`；英文专用 letter-spacing/行高校准；两套文案都由设计师过稿 |
| **脱敏红线内化到视觉** | 公开页禁现持仓金额/成本/盈亏 | 落地页与日报模板只渲染白名单字段；徽章/指标全部用市场级数据（指数、宽度、资金、估值） |

**为什么是这些色彩**：暖白纸面（#FAF9F7）+ 深暖灰文字（#292524）复刻公众号的"纸墨感"，降低金融内容的冷感与攻击性；琥珀金只用于品牌饰条、链接、主按钮，不侵入数据色，保证红涨绿跌的语义独占。五档评级采用**红→琥珀→灰→绿**的语义发散色阶（中国惯例：红=看多、绿=看空），唯一不使用红绿的是"信号矛盾"档——用中性灰，因为该档的引擎语义就是"不给方向"，颜色本身就在传达产品逻辑。

**为什么是这个栅格**：1080px 内容宽 + 4px 基准间距，是从现有两份报告（980px / max-w-6xl≈1152px）收敛的折中：窄一档保证 15px 中文正文每行 34–40 字的舒适阅读宽度，宽一档容纳"六信号 + 指标 + 台账"的三栏数据密度。移动端优先单列，640px 起双列。

---

## 1. 色彩系统

### 1.1 品牌色（Brand）

| Token | 浅色值 | 用途 | 对比度 |
|---|---|---|---|
| `--amber-600` | `#D97706` | 标题饰条、分隔线、图表图形、focus 环（仅大面积/图形，禁止小字号文字） | 图形 3.19:1（≥3:1 达标） |
| `--amber-700` | `#B45309` | 文字链接、主按钮底 | 4.77:1 ✓ |
| `--amber-800` | `#92400E` | 主按钮 hover | 7.09:1 ✓ |
| `--amber-50/100` | `#FFFBEB / #FEF3C7` | 引用块底、提示条（继承公众号暖黄引用） | — |

### 1.2 金融语义色（红涨绿跌 · 中国惯例）

| 语义 | 浅色模式 | 深色模式 | 说明 |
|---|---|---|---|
| 涨 / 正向 `--c-up` | `#DC2626` | `#F87171` | 白卡 4.83:1 / 暖白 4.59:1 / 深底 6.32:1 ✓ |
| 跌 / 负向 `--c-down` | `#15803D` | `#4ADE80` | 白卡 5.02:1 / 暖白 4.77:1 / 深底 10.04:1 ✓ |
| 平盘 `--c-flat` | `#78716C` | `#A8A29E` | 4.56:1 / 6.93:1 ✓ |

> 注意：`#16A34A`（green-600）在白底仅 3.26:1，**禁止用于文字**，仅允许用于进度条/图形（≥3:1）。文字一律用 green-700 `#15803D`。红绿配对是色盲最敏感组合，缓解手段见 §8。

### 1.3 五档评级色阶（Σ Rating Scale）

语义发散：进攻(红) → 均衡(琥珀) → 信号矛盾(中性灰) → 防守(浅绿) → 回避(深绿)。

| 档位 | σ 区间 | 徽章 fg / bg / border（浅色） | 徽章 fg（深色，底为 12–18% 透明度同色叠 surface） | 对比度 |
|---|---|---|---|---|
| 进攻 ATTACK | ≥ +0.50 | `#B91C1C` / `#FEF2F2` / `#FECACA` | `#FCA5A5` | 5.91 / 6.42 ✓ |
| 均衡 BALANCED | +0.15 ~ +0.50 | `#B45309` / `#FFFBEB` / `#FDE68A` | `#FCD34D` | 4.84 / 8.07 ✓ |
| 信号矛盾 CONFLICT | −0.15 ~ +0.15 | `#475569` / `#F1F5F9` / `#CBD5E1` | `#CBD5E1` | 6.92 / 7.97 ✓ |
| 防守 DEFENSIVE | −0.50 ~ −0.15 | `#15803D` / `#F0FDF4` / `#BBF7D0` | `#6EE7B7` | 4.79 / 7.87 ✓ |
| 回避 AVOID | ≤ −0.50 | `#166534` / `#DCFCE7` / `#86EFAC` | `#34D399` | 6.49 / 5.86 ✓ |

每档配方向箭头图标做**冗余编码**（进攻 ▲▲ / 均衡 ▲ / 信号矛盾 ↔ / 防守 ▼ / 回避 ▼▼），色盲用户不依赖颜色也能读档位。

### 1.4 表面与文字（Surfaces）

| Token | 浅色 | 深色 |
|---|---|---|
| `--bg` 页面底 | `#FAF9F7` 暖白 | `#1C1917` 深暖炭 |
| `--surface` 卡片 | `#FFFFFF` | `#292524` |
| `--surface-2` 嵌套/表头 | `#F5F4F2` | `#332F2D` |
| `--border` | `#E7E5E4` | `#44403C` |
| `--text` 正文 | `#292524`（14.42:1） | `#E7E5E4`（13.93:1） |
| `--text-2` 次级 | `#57534E`（7.25:1） | `#A8A29E`（6.93:1） |
| `--text-3` 元信息 | `#78716C`（4.56:1，仅 ≥12px 辅助信息） | `#A8A29E` |

### 1.5 Hero 区（两种模式共用深色）

深色Hero 是品牌记忆点，不随系统模式翻转：`radial-gradient(134% 100% at 50% 0%, #1E293B→#0F172A)` 偏冷会破坏暖纸面传承，故改用**暖黑渐变 `#292524 → #1C1917`** + 琥珀光晕（`#D97706` 12% 透明度 blur 圆）。Hero 内文字 `#FAFAF9`（16.74:1）/ 次文字 `#D6D3D1`（11.74:1）/ 强调 `#FCD34D`（12.13:1）。

---

## 2. 字体系统

### 2.1 字体栈（零外部依赖，不用 Web Font）

```css
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB",
  "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
--font-mono: ui-monospace, "SF Mono", "Cascadia Code", "JetBrains Mono",
  Menlo, Consolas, "Liberation Mono", monospace;
```

- 英文/数字优先命中 SF Pro / Segoe UI，中文回落 PingFang SC / 微软雅黑，**天然中英混排不需要 font-family 切换**。
- 所有金融数字加 `.num` 类：`font-family: var(--font-mono); font-variant-numeric: tabular-nums;`——评级 σ、指数、涨跌幅、日期、命中率一律等宽，滚动/对比时不抖动。

### 2.2 字号阶梯（rem，16px 基准）

| 层级 | 桌面 | 移动 | 行高 |
|---|---|---|---|
| Hero H1 | 40px / 2.5rem | 28px | 1.25 |
| 章节 H2 | 24px | 20px | 1.4 |
| 卡片 H3 | 17px | 16px | 1.5 |
| 正文 | 16px | 15px | **1.75**（继承公众号 1.75–1.8） |
| 辅助/表格 | 13.5px | 13px | 1.6 |
| 徽章/标签 | 12px | 12px | 1.4 |

### 2.3 中英排版差异校准

- `html[lang="en"] body { letter-spacing: -0.003em; line-height: 1.7; }`——英文换行Break 概率高于中文，行高从 1.75 略收至 1.7 防止大段英文"散"。
- 英文标题 `letter-spacing: -0.01em`（紧凑），中文标题 `0.01em`（呼吸）。
- 中英混排时中西文之间由字体栈自动空四分之一宽，**不手加空格**；`text-wrap: pretty` 用于卡片摘要防孤词。
- 双语落地方式：`data-i18n="key"` + JS 字典整体替换 `textContent`，切换时同步改 `<html lang>`（屏幕阅读器发音随之切换）。

---

## 3. 间距与栅格

- **基准**：4px（0.25rem）。间距只用 4 的倍数：4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 56 / 64。
- **容器**：`max-width: 1080px; padding-inline: 20px`（≥768px 时 24px）。
- **区块节奏**：section 上下 56px（移动 40px）；区块标题与内容间距 20px。
- **圆角**：卡片 16px、徽章/标签 999px 或 8px、按钮 10px、代码 4px。
- **阴影**：卡片 `0 1px 2px rgba(28,25,23,.04), 0 8px 24px -12px rgba(28,25,23,.08)`；hover 上浮一档。深色模式阴影换 `rgba(0,0,0,.4)`。
- **栅格**：12 列思维，实际组合——统计条 2/4 列、信号卡 2/3 列、日报卡 1/2/3 列（特色卡通栏）。

---

## 4. 组件库规范

> 所有组件类名即**与 dev 的生成器契约**（见 §9）。原型 `landing-prototype.html` 内的实现为参考实现。

### 4.1 评级徽章 `RatingBadge`（核心资产）

```
结构：[箭头图标 aria-hidden] + 档位名（zh/en 双语字典）+ 可选 σ 值
尺寸：sm 12px（表格内）/ md 14px（卡片）/ lg 20px（Hero/特色卡）
状态：五档 × 三尺寸；禁止只用颜色区分档位（必须带箭头+文字）
```

```html
<span class="rating rating--conflict rating--md">
  <span class="rating-arrow" aria-hidden="true">↔</span>
  <span data-i18n="tier.conflict">信号矛盾</span>
  <span class="rating-sigma num">σ +0.125</span>
</span>
```

- σ 区间表（见 §1.3）必须与引擎 `rating_of()` 一致，改阈值须走引擎仓库评审，**UI 不改阈值**。
- 徽章 hover 出 title 提示该档标准动作（桌面增强，不影响基线可访问性）。

### 4.2 信号评分条 `SignalBar`（S1–S6）

中心原点发散条：负值向左（绿），正值向右（红），中线 50%，值域 [−1, +1] 映射半宽 50%。

```html
<div class="sigbar">
  <span class="sigbar-name">S1 量能</span>
  <div class="sigbar-track"><i class="sigbar-fill sigbar-fill--up" style="left:50%;width:40%"></i></div>
  <span class="sigbar-val num up">+0.80</span>
</div>
```

- 条端值 + 数值双呈现；条为图形（≥3:1），文字用 §1.2 文字色。
- 每条必带权重口径注释（S1 0.20 / S2 0.20 / S3 0.15 / S4 0.15 / S5 0.15 / S6 0.15）。

### 4.3 数据表 `DataTable`

- 表头 `--surface-2` 底、加粗；数字列右对齐 + `.num` 等宽；涨跌列带符号与 ▲▼。
- 行 hover `--surface-2`；行间距 1px `--border`。
- 移动端（<640px）：表格转堆叠卡片（每行 `display:block`，`td::before` 出 `data-label` 表头），禁横向滚动——滚动表格在手机上是数据黑箱。

### 4.4 语言切换器 `LangSwitcher`

- 分段控件，`role="radiogroup"`，两个 `role="radio"` 按钮（中文 / EN），`aria-checked` 随动。
- 键盘：←→ 切换，Tab 进出；选中态存 `localStorage['ip-lang']`，首访按 `navigator.language`。
- 切换即改 `<html lang>` + 全量 `data-i18n` 文本替换；**不用 iframe/双 DOM**，一份 DOM 两种语言，SEO 由 `lang` 属性声明。

### 4.5 日报卡 `ReportCard`

```
[日期 mono] [DEMO 标（仅演示数据）] [评级徽章]
标题（报告名 + 一句话结论）
摘要 2–3 行（含 ≥1 个可验证数值）
指标 chips：指数/宽度/资金等市场级数据（红涨绿跌）
页脚：标签 + 「阅读全文 →」
```

- 特色卡（当日）通栏，左侧叙事右侧六信号条；历史卡 2/3 列网格。
- **脱敏红线**：卡片只允许渲染白名单字段（指数、涨跌幅、宽度、量比、PE、板块资金净额、σ、评级），模板层禁止出现持仓金额/成本/盈亏字段——见 §9.3。

### 4.6 页脚免责声明 `FooterDisclaimer`

- 固定组件：免责声明块（暖黄引用样式 `--amber-50` 底 + 琥珀左边框）+ 数据来源行 + 授权行。
- 免责声明文案中英双语常驻，不可折叠、不可关闭。
- 数据来源必须带时点（如"时点 2026-10-14 收盘"）与"报告由 AI 辅助生成"。

### 4.7 其他

- **按钮**：primary（amber-700 底白字，hover amber-800）/ secondary（1px 边框幽灵按钮）/ 文字链接（amber-700 +下划线 hover）。触控目标 ≥44×44px。
- **主题切换 `ThemeToggle`**：右下角或页头按钮，`aria-pressed`，三态（auto→light→dark），存 `localStorage['ip-theme']`；CSS 变量 + `prefers-color-scheme` 双轨实现。
- **Skip link**：页面第一个可聚焦元素，"跳到主要内容"，focus 才可见。

---

## 5. 深浅色模式

- 实现：`:root` 定义浅色变量；`@media (prefers-color-scheme: dark)` 覆盖 `:root[data-theme="auto"]`；用户手动选择写 `data-theme="light|dark"` 优先于系统。
- **Hero 区两种模式共用深色**（品牌记忆点，不翻转）；正文区、页脚跟随模式。
- 切换时 0.2s 颜色过渡；`prefers-reduced-motion: reduce` 时全部过渡关闭。
- 深色模式专项：阴影加深、边框提亮至 `#44403C`（深底下 1px 边框是对比度的一部分，非文本对比 ≥3:1）、图片/装饰透明度 +8%。

---

## 6. 移动端断点

| 断点 | 布局变化 |
|---|---|
| < 640px | 单列；容器 padding 20px；Hero H1 28px；统计 2 列；表格转堆叠卡；信号条两行（名称/数值在条上方） |
| 640–767px | 日报卡 2 列；方法论信号卡 2 列 |
| ≥ 768px | 容器 padding 24px；统计 4 列；页头导航全展开；汉堡菜单可省略（链接 ≤5 个时） |
| ≥ 1024px | 日报历史卡 3 列；特色卡左右分栏（叙事 7 / 信号 5） |

- 触控：所有可点元素 ≥44px 高；行内链接加 `padding-block: 2px` 扩大热区。
- 横屏手机（<900px 且 height<500）：Hero 压缩为单行 + 徽章。

---

## 7. 图标与插值规范

- 图标一律内联 SVG 或几何字符（▲▼↔★→🍜），**不用图标字体、不引外部图床**（GitHub Pages 零依赖红线）。
- 🍜 作为 IP 头像固定符号：amber-500 20% 透明度圆角方底 + emoji，公众号同款。
- 方向语义：涨 ▲ 红 / 跌 ▼ 绿 / 平 — 灰；与颜色构成双重编码。

---

## 8. 可访问性清单（WCAG 2.2 AA）

- [x] 正文对比 ≥4.5:1（实测全部通过，见 §1 各表；最低项 4.56:1 为 12px 元信息）
- [x] 大文本/图形 ≥3:1（amber-600 饰条 3.19:1、信号条 red-600 3.26:1）
- [x] 颜色永不单独承载语义：涨跌带符号+箭头，评级带箭头+文字，DEMO 数据带文字标
- [x] 语义化：`header/nav/main/section/footer`、`role="radiogroup"`、表格 `<caption>`/`scope`
- [x] 键盘：所有交互可 Tab 到达；focus 环 2px amber-600 + 2px offset，深色模式下换 amber-300
- [x] `prefers-reduced-motion` 关闭动画；`prefers-color-scheme` 深色适配
- [x] 语言切换改 `<html lang>`，屏幕阅读器正确发音
- [x] 触控目标 ≥44px；链接有 discernible text（禁"点击这里"）
- [x] 色盲模拟（deuteranopia）下：红/绿仅明度差 + 箭头方向仍可读档位与涨跌

---

## 9. 与 dev 的聚合页生成器衔接（组件结构建议）

### 9.1 类名契约

生成器输出的日报 HTML 直接复用本规范的组件类名，保证"落地页—日报页"同一设计系统：

| 生成器输出元素 | 必须使用的类 |
|---|---|
| Σ 评级徽章 | `rating rating--{attack,balanced,conflict,defensive,avoid} rating--{sm,md,lg}` |
| 六信号条 | `sigbar / sigbar-track / sigbar-fill--{up,down} / sigbar-val up|down` |
| 市场指标 chips | `metric / metric-val num up|down|flat` |
| 数据表 | `data-table`（移动端自动堆叠，依赖 `td[data-label]`） |
| 日报卡 | `report-card`（+ `report-card--featured`） |
| 免责/来源 | `disclaimer / source-line` |

### 9.2 数据映射（market_data.json → 组件）

```
verdict.sigma ──► rating_of(sigma) ──► 档位类名（引擎计算，UI 只映射不改值）
verdict.sigma ──► 徽章 σ 文本（mono，保留 3 位小数）
signals[S1..S6].score ──► SignalBar：width = |score|/1.0 × 50%，符号决定 up/down 与左右
market.indices[] ──► metric chips：change_percent>0 → .up + ▲，<0 → .down + ▼
verdict.rating ──► 特色卡标题后缀；动作文案用引擎标准动作表
```

### 9.3 脱敏白名单（生成器强约束）

公开页模板**只允许渲染**：指数点位/涨跌幅、涨跌家数、涨停跌停数、量比、PE、板块主力净额、σ 与六信号、评级与动作、观点台账条数/命中率、数据时点。
**禁止渲染**：持仓金额、持仓成本、累计/当日盈亏、盈亏比例、在途金额、基金代码明细表——如需展示持仓结构，只输出板块集中度百分比（脱敏后）。建议 dev 在渲染器加"字段白名单断言"：遇黑名单字段直接抛错中断渲染（与引擎硬校验同思路）。

### 9.4 双语方案

- 静态外壳（落地页）：本原型的 `data-i18n` + 字典方案，字典文件建议沉淀为 `assets/i18n.json`，落地页与日报模板共用。
- 日报正文：LLM 产出 zh/en 两份 markdown，生成器同构渲染；UI 侧只保证 `lang` 切换 + 排版校准（§2.3），不承诺机翻质量。

---

## 10. 验收自查（原型交付前已逐项过）

1. 单文件、零外部请求（无 CDN/字体/图床）——GitHub Pages 直接托管 ✓
2. zh/en 切换实测：英文排版不塌陷、行高适配、`lang` 同步 ✓
3. 深浅色：系统偏好 + 手动切换 + localStorage 记忆 ✓
4. 红涨绿跌：全部涨跌数字带符号与 ▲▼，demo 数据打 DEMO 标 ✓
5. 无任何持仓金额/成本/盈亏字段（仅市场级数据）✓
6. 键盘走查：skip link → 导航 → 切换器（方向键）→ 卡片链接全链路可达 ✓
7. 对比度实测表见 §1（全部 ≥4.5:1）✓
