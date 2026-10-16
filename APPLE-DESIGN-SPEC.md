# 每日市场脉搏 · Apple 设计语言落地规范

> 版本 1.0 | 日期 2026-10-14 | 设计：颜好看
> 参照基准：Apple 官网（apple.com）2025-2026 设计语言实测规范
> 交付物：本 Spec + `design-tokens.css` + `design-tokens.json` + `apple-prototype.html`
>
> **三轴刻度**：DESIGN_VARIANCE = 4 / MOTION_INTENSITY = 2 / VISUAL_DENSITY = 6
> （低动效＝Apple 式克制；中高密度＝金融内容站的现实需要，用户可覆盖）

---

## 0. 设计寄存器判定

本站属于 **Brand 寄存器**（内容 IP / 长期归档站），不是后台仪表盘。

这个判定决定了三件事：

| 维度 | Brand 寄存器下的选择 | 本 Spec 的落地 |
|------|-------------------|---------------|
| 色彩策略 | 允许纯色大面积铺陈，但**不靠饱和度取胜** | 画布纯白 + `#f5f5f7` 交替带形成「场景切换」，蓝色只给交互元素 |
| 排版策略 | 字号/字重/留白驱动层级，不靠卡片堆叠 | 时间线**零卡片**，只用 hairline 分隔 + 92px 时间槽 |
| 动效策略 | 允许一次精心编排的转场，禁止散落微交互 | 全部动效收敛在 hover / 骨架脉冲，时长 ≤300ms |

Apple 官网本身是「零渐变、零卡片投影、零装饰动效」的极端形态。本 Spec 照此执行，但**为一类硬需求做了明确让步**：五档评级色阶与箭头冗余编码 —— 这是金融语义的必要复杂度，不是装饰。

---

## 1. 设计原则（5 条，来自 Apple HIG 三支柱）

### 1.1 Clarity 清晰 —— 文字即界面

Apple 的界面会「退后」，让内容站到前面。具体做法：

- **层级靠字号建立，不靠盒子**。34px 页面标题 → 20px 条目标题 → 17px 摘要 → 13px 元信息，四级足够，不引入卡片边框。
- **信息密度靠对齐建立**。时间线的 92px 左槽是刚性网格，调度时点、生成时刻、标题、徽章四条基线纵向对齐，扫读时眼睛不需要重新定位。
- **超长中文标题钳制两行**（`-webkit-line-clamp:2`）。真实数据里存在 40+ 字的报告标题（如「A股持仓每日投研诊断与网格交易操作指南（2026-10-13 周二 午后补跑全景研判）」），不钳制必然撑破布局。

### 1.2 Deference 顺从 —— UI 服务内容

- **零投影**。Apple 的卡片默认 `box-shadow: none`，深度来自背景明度分层：白画布 → `#f5f5f7` 交替带 → `#ffffff` 抬升面。本站沿用，投影仅保留给瞬态浮层（`--elev-overlay`）。
- **蓝色是稀缺资源**。`#0071e3` 只给链接、CTA、焦点环、选中态，每屏可见 ≤2 处。标题、正文、分隔线一律不用蓝色。
- **正文永远左对齐**。Apple 从不居中正文，本站时间线、摘要、方法论段落全部左对齐。

### 1.3 Depth 层次 —— 明度递进，不是投影堆叠

深色模式尤其关键：黑底上的黑色投影**完全不可见**，纯属浪费合成层。本 Spec 的处理：

```
浅色：#FFFFFF → #F5F5F7        （画布 → 交替带）
深色：#000000 → #1C1C1E → #2C2C2E  （画布 → 抬升 → 三级表面）
```

深色模式下 `--elev-overlay` 只保留给真正悬浮的浮层；常规元素**投影置空**。

### 1.4 一致性 —— 单一图标族，单一字体栈

- **图标锁定 Lucide**（见 §8），全站 35 个 symbol，禁止混用第二套。
- **字体栈单一**：`-apple-system` 在 macOS/iOS 直接解析为 SF Pro（Display 用于 ≥20px，Text 用于 <20px，符合 Apple 的光学尺寸边界），中文回退 PingFang SC → 微软雅黑。
- **数字一律等宽**：`font-variant-numeric: tabular-nums`。价格与 Σ 值在刷新时不跳动 —— 这是数据站点的基本尊重。

### 1.5 本站专属原则：金融语义的确定性

Apple 的设计哲学是「让界面消失」；本站多一条约束：**评级不能消失**。

一条评级结论必须同时具备**四重编码**：

```
颜色（#15803d）+ SVG 图标（arrow-down）+ 箭头（▼）+ 文字（防守）
```

任一维度失效（色觉障碍 / 灰度打印 / CSS 加载失败 / 字体缺失），其余三维仍能完整传达结论。这是「严谨」在视觉层的落地方式。

---

## 2. 色彩系统

### 2.1 Apple 中性色阶（实测值，非推测）

Apple 的灰阶**不是** `#333/#999/#eee` 这种粗分法，而是一套带蓝灰倾向的精确值：

| 角色 | Token | 浅色 | 深色 | 用途 | 对比度 |
|------|-------|------|------|------|--------|
| 画布 | `--bg` / `--surface` | `#FFFFFF` | `#000000` | 页面底 | — |
| 交替带 | `--surface-alt` | `#F5F5F7` | `#1C1C1E` | 分区、页脚 | — |
| 导航面 | `--surface-nav` | `#FAFAFC` | `#161617` | sticky 导航 | — |
| 正文 | `--fg` | `#1D1D1F` | `#F5F5F7` | 标题、正文 | 16.83:1 / 19.29:1 |
| 次级 | `--fg-2` | `#515154` | `#A1A1A6` | 摘要、说明 | 7.91:1 / 8.16:1 |
| 三级 | `--fg-3` | `#6E6E73` | `#86868B` | 元信息、表头 | 5.07:1 / 5.80:1 |
| 弱化 | `--fg-muted` | `#86868B` | `#6E6E73` | **仅 ≥17px 或纯装饰** | 3.62:1 注意 |
| 分隔线 | `--border` | `#D2D2D7` | `#38383A` | 1px hairline | — |
| 轻分隔 | `--separator` | `#E8E8ED` | `#2C2C2E` | 行内分隔 | — |

**关键决策：正文永不用纯黑 `#000`**

Apple 刻意用 `#1D1D1F`（近黑、极轻微暖调）而非 `#000`。纯黑在 retina 上会显得刺眼且过重，近黑保留了「印刷品」而非「屏幕像素」的观感。本 Spec 全文遵守，唯一例外是深色模式的**画布**（OLED 场景需要真黑省电，这是 Apple 的做法）。

**`--fg-muted` 的 3.62:1 是有意为之**：Apple 官网自己就这么用（免责声明、轮播控件指示点）。本 Spec 把它限制在「≥17px 或纯装饰」范围内，任何正文级用途必须用 `--fg-3`。

### 2.2 强调色（唯一）

| 角色 | Token | 浅色 | 深色 | 对比度 |
|------|-------|------|------|--------|
| 交互强调 | `--accent` | `#0071E3` | `#2997FF` | CTA 白字 4.70:1 / 6.96:1 |
| 正文链接 | `--link` | `#0066CC` | `#2997FF` | 5.57:1 / 6.96:1 |

Apple 不用 `#007AFF`（那是 iOS 系统蓝），官网交互蓝是 **`#0071E3`**，更沉稳。这个区别很多仿站会做错。

**每屏 ≤2 处强调色使用**。首页的强调色预算：导航选中项 + CTA 按钮。其余一律靠字号与留白。

### 2.3 五档评级色阶（金融语义扩展，不可替换）

用户已锁定色值，本 Spec 校验并补齐深色模式：

| 评级 | 浅色 | 白底对比度 | 深色 | 深底对比度 | 箭头 | SVG 图标 |
|------|------|-----------|------|-----------|------|---------|
| 进攻 Offensive | `#B91C1C` | 6.47:1 达标 | `#F87171` | 6.18:1 达标 | ▲▲ | `trending-up` |
| 均衡 Balanced | `#B45309` | 5.02:1 达标 | `#FBBF24` | 9.23:1 达标 | ▲ | `arrow-up` |
| 信号矛盾 Conflict | `#475569` | 7.58:1 达标 | `#94A3B8` | 6.09:1 达标 | ↔ | `shuffle` |
| 防守 Defensive | `#15803D` | 5.02:1 达标 | `#4ADE80` | 8.77:1 达标 | ▼ | `arrow-down` |
| 回避 Avoid | `#166534` | 7.13:1 达标 | `#22C55E` | 6.72:1 达标 | ▼▼ | `chevrons-down` |

**「信号矛盾」为何用中性石板灰 `#475569`**

这是全Spec 最重要的色彩决策。该档位意为「多空信号打架、无法定向」。若给它红色，读者会误读为「看涨」；给绿色，会误读为「看跌」。**中性灰是唯一不携带方向暗示的选择**，同时与红绿保持最大区分度。

**浅色/深色的徽章形态不同**

- 浅色：`背景 = 实色深块 + 白字`（5.02–7.58:1 全部达标）
- 深色：`背景 = 同色 16% 淡色 + 亮色字`（6.09–9.23:1 全部达标）

原因：高饱和大色块在纯黑底上会产生光晕（halation），长时间阅读刺眼。深色模式改为「淡底亮字」是Apple 在 iOS 组件里的标准做法。

### 2.4 行情涨跌色（中国惯例：红涨绿跌）

| 角色 | Token | 浅色 | 深色 | 对比度 |
|------|-------|------|------|--------|
| 涨 | `--quote-up` | `#B91C1C` | `#F87171` | 6.47:1 / 7.59:1 达标 |
| 跌 | `--quote-down` | `#15803D` | `#4ADE80` | 5.02:1 / 12.05:1 达标 |
| 平 | `--quote-flat` | `#6E6E73` | `#A1A1A6` | 5.07:1 / 8.16:1 达标 |

**与评级色的一致性**：涨色与「进攻」同色（`#B91C1C`），跌色与「防守」同色（`#15803D`）。这不是偷懒 —— 它保持了「红 = 向上/进攻，绿 = 向下/防守」的单一语义轴，用户不需要建立两套心智模型。

### 2.5 色彩配比（精规校验）

| 层级 | 占比 | 本站实际 |
|------|------|---------|
| 中性色 | 70–90% | ~88%（白 + 灰阶 + 深色系） |
| 强调色 | 5–10% | ~4%（蓝色克制使用） |
| 语义色 | 0–5% | ~6%（评级色 + 涨跌色，仅数据密集区出现） |
| 效果色 | <1% | ~0%（**零投影、零渐变**） |

---

## 3. 字体系统

### 3.1 字体栈

```css
--font-display: "SF Pro Display", -apple-system, BlinkMacSystemFont,
                "PingFang SC", "Hiragino Sans GB", "Noto Sans SC",
                "Microsoft YaHei", "Helvetica Neue", sans-serif;

--font-text:    "SF Pro Text", -apple-system, BlinkMacSystemFont,
                "PingFang SC", "Hiragino Sans GB", "Noto Sans SC",
                "Microsoft YaHei", "Helvetica Neue", sans-serif;

--font-mono:    "SF Mono", ui-monospace, SFMono-Regular, Menlo, Monaco,
                "Cascadia Mono", "Roboto Mono", monospace;
```

**中文站怎么落SF Pro**

SF Pro 是 Apple 商业字体，不可自托管。落法是「让操作系统去解析」：

1. `-apple-system` 写在首位 → macOS/iOS 自动返回 SF Pro（系统已授权，无需下载）
2. 非 Apple 平台落到 `Helvetica Neue`（macOS 旧版）/ `Microsoft YaHei`（Windows）
3. 中文由`PingFang SC`（macOS/iOS）→ `Hiragino Sans GB` → `Noto Sans SC` → `Microsoft YaHei` 依次回退

**SF Pro Display vs Text 的光学尺寸边界**：Apple 在 20px 处切换字体变体。`--font-display` 用于 ≥20px 的标题，`--font-text` 用于 <20px 的正文 —— 与Apple 官网行为一致。

**禁止默认系统字体直出**：不接受裸 `sans-serif`，必须显式列出完整回退链，否则Windows用户会拿到宋体。

### 3.2 字号阶梯（Apple HIG Dynamic Type 实测值）

| Token | px/rem | 行高 | 字重 | 用途 | 中文安全 tracking |
|-------|--------|------|------|------|----------------|
| `--fs-display` | 56 / 3.5rem | 60 (1.07) | 700 | 展示级（本站仅 Token 校验台演示） | 0 |
| `--fs-title1` | 34 / 2.125rem | 41 (1.206) | 700 | 页面主标题 | -0.010em |
| `--fs-title2` | 28 / 1.75rem | 34 (1.214) | 600 | 分区标题 | -0.012em |
| `--fs-title3` | 22 / 1.375rem | 28 (1.273) | 600 | 小节标题 | -0.014em |
| `--fs-title4` | 20 / 1.25rem | 25 (1.25) | 600 | **时间线条目标题** | -0.012em |
| `--fs-headline` | 17 / 1.0625rem | 22 (1.294) | 600 | 强调正文、归档项标题 | -0.010em |
| `--fs-body` | 17 / 1.0625rem | 25 (**1.47**) | 400 | 正文（Apple 标准） | -0.010em |
| `--fs-callout` | 16 / 1rem | 22 (1.35) | 400 | **时间线摘要** | -0.006em |
| `--fs-subhead` | 15 / 0.9375rem | 21 (1.4) | 400 | 次级说明 | 0 |
| `--fs-footnote` | 13 / 0.8125rem | 18 (1.385) | 400 | 元信息、时间戳 | +0.010em |
| `--fs-caption1` | 12 / 0.75rem | 16 (1.333) | 400 | 标签、表头 | +0.020em |
| `--fs-caption2` | 11 / 0.6875rem | 15 | 400 | 微标签 | +0.020em |

**行高规律**：标题 1.07–1.29（压缩），正文 1.47（Apple 标准，宽松）。这组对比形成Apple 标志性的「字距紧、行距松」的呼吸感。

**字重二元制**：Apple 实践中只用 400 和 600，700 仅用于页面主标题，800/900 近乎不用。本 Spec 遵循，禁用 800+。

### 3.3 字间距 —— CJK tracking 补偿（本Spec 的核心修正）

**Apple 的负 tracking 是为拉丁窄字形设计的**

Apple 官网实测：56px 用 -0.005em，34px 用 -0.022em，28px 用 -0.029em，22px 用 -0.032em，17px 用 -0.025em。这是因为拉丁小写字母的字身框两侧留白较多，负字距能让字形「咬合」得更紧，呈现机械加工般的精确感。

**直接套到中文会出事**

汉字是**全角字形**，字身框占满整个 em 方格，字形之间几乎没有天然留白。套用 -0.032em 的 tracking：

```
「每日市场脉搏」六个汉字，在 -0.032em 下相邻字形边界会贴合甚至重叠
「」《》（）等全角标点会互相挤压
```

这是中文仿 Apple 站最常见的翻车点。

**补偿方案**：保留 tracking 的**字面观感**，按约 **40%** 幅度补偿

```
17px  body   : Apple -0.025em →本站 -0.010em   （40%）
22px  title3 : Apple -0.032em → 本站 -0.014em   （44%）
28px  title2 : Apple -0.029em → 本站 -0.012em   （41%）
34px  title1 : Apple -0.022em → 本站 -0.010em   （45%）
13px  footnote: Apple +0.002em → 本站 +0.010em  （小字号反向补偿）
12px  caption: Apple +0.010em → 本站 +0.020em   （小字号反向补偿）
```

小字号方向相反：Apple 在 13px 以下把tracking 调正，因为字形太小，负字距会粘连。中文字形方正，小字号正字距同样有助于辨识，故补偿幅度加倍。

**Token 里两套值并存**：`--tracking-*`（CJK 安全，本站正文用）与 `--tracking-lat-*`（Apple 拉丁实测，英文版对照）。若日后出英文版，直接切后者。

### 3.4 字重

| Token | 值 | 用途 |
|-------|----|------|
| `--fw-regular` | 400 | 正文、说明 |
| `--fw-medium` | 500 | 导航、强调正文 |
| `--fw-semibold` | 600 | **全部分标题**（Apple 主力） |
| `--fw-bold` | 700 | 仅页面主标题 |

---

## 4. 间距系统

### 4.1 4px 基准网格

Apple 官网的基础单位是 8px，但编辑刻度含 4px。本 Spec 取 4px 网格（更细的呼吸控制），8px 为常用步长：

```
--space-1:  4px     图标与文字
--space-2:  8px     紧凑元素组
--space-3:  12px    标准内距
--space-4:  16px    舒适内距
--space-5:  20px    时间线行间距
--space-6:  24px    区块内距 / 时间线行上下padding
--space-8:  32px    大区块
--space-10: 40px
--space-12: 48px
--space-16: 64px
--space-20: 80px    节区间距（桌面）
--space-24: 96px
--space-32: 128px
```

### 4.2 节区节奏

| 断点 | 节区间距 | Token |
|------|---------|-------|
| 桌面 ≥1025px | 80px | `--section-y-desktop` |
| 平板 641–1024px | 48px | `--section-y-tablet` |
| 手机 ≤640px | 32px | `--section-y-phone` |

### 4.3 容器与栅格

| Token | 值 | 用途 |
|-------|-----|------|
| `--container-max` | **980px** | 全站主容器（Apple 栅格模块） |
| `--container-wide` | 1180px | 归档页宽表 |
| `--container-prose` | 680px | 长文行宽 |
| `--container-narrow` | 760px | 日期页窄栏 |

**980px 不是随便取的**：它与 Apple 胶囊按钮的 `980px` 圆角同源，是 Apple 官网的栅格模数本站时间线内容在 980px 容器下减去 92px 时间槽，正文摘要可用宽约 840px。

**行宽控制**：中文正文 `--container-prose: 680px`，在 17px 下约 **34–38 字/行**。Apple 英文 65–75 字符对应中文约 32–40 字，这是符合中文阅读习惯的等效区间。

### 4.4 页面留白原则

- 页面主标题块：上 48px / 下 40px
- 日期分组之间：64px（`.issue` margin-bottom）
- 时间线条目之间：24px 上下 padding，条目内元素间距 20px
- 时间线无卡片 —— 分隔靠 1px `#E8E8ED` hairline

---

## 5. 圆角与阴影

### 5.1 圆角阶梯

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-xs` | 4px | 徽章、标签 |
| `--radius-sm` | 8px | 芯片、输入框 |
| `--radius-md` | 12px | 卡片、时间线组 |
| `--radius-lg` | 18px | 大内容面板 |
| `--radius-xl` | 28px | 特性面板 |
| `--radius-pill` | 980px | **Apple 签名胶囊**（按钮） |

**卡片圆角上限 28px**，且仅用于大面板。普通卡片 12px。避免「一切都是大圆角」的 AI 观感。

### 5.2 连续圆角（squircle）—— Apple 签名观感的实现

Apple 的圆角不是标准 `border-radius`。标准 `border-radius` 在圆角与直线相接处存在**曲率突变**（视觉上能看到一个小折点）；Apple 用超椭圆（superellipse）实现**曲率连续渐变**，即 iOS 的 squircle。

**CSS 现状（2026年）**：`corner-shape` 属性已进入 Chrome 139+ / Edge，但 **Safari 与 Firefox 尚未支持**。因此采用渐进增强：

```css
/* 无条件：标准圆角，全平台兜底 */
.rating, .btn, .card { border-radius: 12px; }

/* Chrome/Edge 139+：还原 Apple 连续圆角 */
@supports (corner-shape: squircle) {
  .rating, .btn, .card { corner-shape: squircle; }  /* = superellipse(2) */
}
```

**决策**：Safari 用户拿到标准圆角，视觉差异在 12–28px 尺度上几乎不可辨。**不值得为此引入 clip-path 路径数据或 SVG mask** —— 那会增加维护成本和渲染开销，换取一个Safari 用户看不出差别的收益。这是「工程理性优先于像素洁癖」的例子。

`corner-shape` 与 `border-radius` 是协作关系：前者定义转角盒内的曲线，后者定义转角盒的大小。**只有 `border-radius` 非零时 `corner-shape` 才生效**。

### 5.3 阴影层级

| Token | 值 | 用途 |
|-------|-----|------|
| `--elev-flat` | `none` | **默认** —— 卡片、面板、时间线条目 |
| `--elev-hairline` | `inset 0 0 0 0.5px var(--border)` | 需要描边的面板 |
| `--elev-overlay` | `0 8px 28px rgba(0,0,0,0.12)` | **仅瞬态浮层**（菜单、弹窗） |

**Apple 官网几乎没有投影。** 它的深度来自三件事：

1. 背景明度分层（白 ↔ `#f5f5f7` 交替）
2. 大面积留白
3. 产品本身的自然投影（在照片里，不在 CSS 里）

本站对应落地：**时间线零投影、零边框**，只用 hairline 分隔。文档类内容（上游产出的 19 个 `h2`、19 个 `table`）也遵循同样策略，靠 `border-bottom` 而非阴影分层。

**深色模式投影处理**：黑底上的黑色投影完全不可见，纯属浪费 GPU 合成层。`--elev-overlay` 在深色模式改为 `0 8px 28px rgba(0,0,0,0.55)` 仅供真正悬浮的浮层使用，其余元素依靠明度递进（`#000000 → #1C1C1E → #2C2C2E`）。

---

## 6. 组件规范

### 6.1 导航（两级 sticky）

**全局导航**（Apple 实测 44px）

```
高度      44px
背景      rgba(250,250,252,0.72)   深色 rgba(22,22,23,0.72)
背景处理  backdrop-filter: saturate(180%) blur(20px)
边框      1px solid #D2D2D7       深色 #38383A
字号      13px（--fs-footnote）
默认色    #515154                深色 #A1A1A6
悬停      #1D1D1F                深色 #F5F5F7
选中      #1D1D1F + 2px 下划线#1D1D1F
z-index   1100
```

**二级导航（localnav）**：52px，吸顶于全局导航下方（`top: 44px`），同一套玻璃背景，选中项2px 下划线。

**Apple 的 `saturate(180%) blur(20px)` 是签名值**：高饱和度模糊让背后内容透出色彩，模拟磨砂玻璃。纯 `blur()` 会让透出的颜色发灰。

**移动端策略**：导航链接横向可滚动（`overflow-x:auto` +隐藏 scrollbar），不折叠为汉堡菜单 —— 本站导航仅 5 项，折叠反而增加操作成本。次要项在 ≤640px 隐藏。

### 6.2 面包屑

```
首页 /   2026-10-14
13px / --fg-3(#6E6E73)，分隔符用 --border 色
hover → --link (#0066CC)
顶部内距 24px
```

### 6.3 时间线条目（本 Spec 的核心组件）

**Apple 做法：不用卡片。** 用 92px 刚性左槽 + hairline 分隔 + 留白。

**栅格结构**：

```css
.tl-item{
  display:grid;
  grid-template-columns: 92px  1fr  auto;   /* 时间槽 | 内容 | 徽章组 */
  gap:20px;
  padding:24px 0;
  border-bottom:1px solid var(--separator);
}
```

**八项必备字段**（原型 17 个条目 100% 覆盖）：

| 字段 | 呈现 | Token |
|------|------|-------|
| 调度时点 | 6px 实心圆点 + `09:28` 等宽数字 | `--tl-time-fg` |
| 真实生成时刻 | 12px timer 图标 + `生成 12:39` | `--tl-run-fg`，`--fs-caption2` |
| 任务名 | 13px 图标 + 文字，`--tracking-caption` | `--tl-kicker-fg` |
| 真实报告标题 | 20px/600，两行钳制 | `--fs-title4` |
| 一句话摘要 | 16px，`--container-prose` 限宽 | `--tl-summary-fg` |
| 评级徽章 | SVG 图标 + 箭头 + 文字 | `.rating-*` |
| Σ 值 | sigma 图标 + 等宽数字 | `--fs-caption1` |
| 数据时点 | clock/calendar 图标 + 盘中/收盘 | `.chip-intraday` / `.chip-close` |

**调度时点 vs 生成时刻为何都要**

这是本站与其他行情站的区别：调度时点是**承诺**（09:28 应该出研判），生成时刻是**事实**（实际12:39 完成，晚了 3 小时）。两者的差值本身是内容 —— 它揭示了系统可靠性。把两者混为一谈，读者就看不到延迟。

**摘要中的涨跌必须带 SVG 箭头**（`arrow-up` / `arrow-down`，13px，stroke 2.2）。这是上游 `entries.json` 里 emoji（如 10-13 股票复盘摘要中的 U+1F53A 红色上三角）的**替代方案** —— 不能只删掉，必须换成矢量图标，否则方向信息丢失。

**响应式**：
- ≤900px：`92px 1fr` 两列，徽章组下移至第二行
- ≤640px：单列，时间与内容纵向堆叠，徽章组横向排列

### 6.4 评级徽章

**四重编码**（详见 §1.5）：

```
<span class="rating rating-defensive">
  <svg class="ic"><use href="#i-arrow-down"/></svg>   ← 图标
  <span class="arrow">▼</span>                ← 箭头
  防守                                              ← 文字
</span>
```

```css
.rating{
  display:inline-flex; align-items:center; gap:5px;
  font-size:12px; font-weight:600;
  padding:3px 10px; border-radius:4px;
  border:1px solid var(--rating-*-ring);
  background:var(--rating-*-bg);
  color:var(--rating-*-fg);
}
.rating-lg{ font-size:15px; padding:6px 14px; gap:7px; }  /* 分组头用 */
```

**`--rating-conflict` 的中性灰是刻意选择**，理由见 §2.3。

**链接标签禁令**：时间线标题即链接文案（`<h3 class="tl-title"><a>真实报告标题</a></h3>`）。

**禁止**「阅读网页版 / HTML」「阅读 Markdown 版 / Markdown」这类零信息量标签 —— 读者已经知道自己在读网页，点之前需要的是「这篇讲什么」的判断依据。报告标题本身就是答案。数据中 `html` 字段为 `null` 的条目（基金操作指引、股票复盘），标题渲染为不可点击文本，并挂`chip-pending`「网页版待补齐」如实说明状态 —— 这比给一个死链更诚实。

### 6.5 指标卡（KPI）

**无边框，靠 hairline 分隔**：

```css
.kpi-row{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
          border-top:1px solid var(--border); }
.kpi{ padding:20px 16px 20px 0; border-left:1px solid var(--separator); }
.kpi:first-child{ border-left:none; padding-left:0; }
```

数值用等宽字体 + `tabular-nums`，涨跌部分加语义色。标签上方可放 13px 图标。

### 6.6 数据表（Apple 表格规范）

**Apple 表格的三个特征**：无竖线、无斑马纹、表头用次级文字色。

```css
.tbl{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
.tbl th{ font-size:12px; font-weight:600; color:#6E6E73;      /* 次级色，非加粗黑 */
         padding:8px 16px; border-bottom:1px solid #D2D2D7; }
.tbl td{ padding:12px 16px; border-bottom:1px solid var(--separator); }
.tbl tbody tr:last-child td{ border-bottom:none; }
.tbl .num{ text-align:right; font-family:var(--font-mono); white-space:nowrap; }
.tbl .zebra{ none }        /* 禁用斑马纹 */
```

**数字右对齐 + 等宽**：这是数据表的基本尊重。右对齐让小数点成列，扫读时一眼看出量级差异。

### 6.7 按钮

| 变体 | 背景 | 边框 | 文字 | 圆角 |
|------|------|------|------|------|
| Primary | `--accent` | 无 | `--fg-on-accent` | 980px 胶囊 |
| Secondary | 透明 | 1px `--accent` | `--accent` | 980px 胶囊 |
| Quiet | 透明 | 无 | `--link` | 980px 胶囊 |

```css
.btn{ padding:11px 21px; min-height:44px;          /* WCAG 2.5.5 触摸目标 */
      transition:background 150ms var(--ease-out); }
.btn-primary:hover{ background:var(--accent-hover); }
.btn-primary:active{ background:var(--accent-active); }
```

**Apple 的按钮内距是 `11px 21px`，字号 17px。** 本站因导航密集，采用 15px 字号但保留 `11px 21px` 内距以维持胶囊的视觉平衡。

### 6.8 状态芯片

| 变体 | 用途 | 呈现 |
|------|------|------|
| `chip-intraday` | 盘中时点 | 蓝色淡底 + 蓝色字，`#0066CC` @ 8% |
| `chip-close` | 收盘时点 | 中性灰底 + `--fg-2` 字 |
| `chip-pending` | 网页版待补齐 | 透明底 + **虚线边框** |

`chip-pending` 用虚线边框是刻意的：虚线在视觉上表达「此处应有内容而暂缺」，与普通实线芯片区分。

### 6.9 空态 / 加载态 / 错误态

**5 态覆盖是硬要求，原型已全部实现**：

| 状态 | 实现 |
|------|------|
| **Empty** | 虚线边框块 + 24px inbox 图标 + 具体引导文案 + **2 个真实操作**（查看上一日/ 订阅 RSS）。零占位图、零 Lorem。 |
| **Loading** | 骨架屏，盒高与真实条目一致 → **CLS ≈ 0**。微光用明度脉冲（`skel-pulse`），**不用渐变**（守住零 gradient 约束） |
| **Error** | danger 色 alert 图标 + 说明「空数据不做补零，避免生成虚假结论」+ 重试按钮。**不暴露技术细节** |
| **Populated** | 正常渲染，17 个条目 8 字段全覆盖 |
| **Edge** | 标题两行钳制（`-webkit-line-clamp:2`）+ 表格横向滚动 + 长数字 `tabular-nums` 不换行 |

**错误文案的专业性**：「上游行情接口在 09:31 无响应，本日信号未参与计算 —— 空数据不做补零，避免生成虚假结论」。这句话同时说明了**发生了什么**、**数据怎么处理**、**为什么这样处理**。技术细节（HTTP 状态码、堆栈）不出现。

### 6.10 页脚

```
背景      --surface-alt (#F5F5F7)        深色 #1C1C1E
字号13px
上边框1px #D2D2D7
分三栏：品牌说明 / 归档 / 关于 / 来源
免责声明 13px --fg-3
```

---

## 7. 动效

### 7.1 缓动曲线

```css
--ease-out:      cubic-bezier(0.215, 0.61, 0.355, 1)   /* Apple 主曲线 */
--ease-standard: cubic-bezier(0.4, 0, 0.2, 1)
--ease-out-soft: cubic-bezier(0.25, 0.1, 0.25, 1)
```

**Apple 特征**：起步快、收尾稳的减速曲线。元素「出现」比「消失」快。

**绝对禁止**：`cubic-bezier(0.68, -0.55, 0.265, 1.55)`（弹跳/回弹曲线）。这是 AI 生成站点的典型标志 —— 物理弹跳在专业金融内容里显得轻浮。

### 7.2 时长

| Token | 值 | 场景 |
|-------|-----|------|
| `--motion-instant` | 80ms | 按下反馈 |
| `--motion-fast` | 150ms | 状态确认、hover 变色 |
| `--motion-base` | 200ms | 局部展开 |
| `--motion-slow` | 300ms | 跨屏过渡 |
| `--motion-slower` | 400ms | 复杂编排上限 |

**上限 400ms**。Apple 官网的动效几乎都在 150–200ms，读者不应等待动画。

### 7.3 降级

```css
@media (prefers-reduced-motion: reduce) {
  :root{ --motion-instant:.01ms; --motion-fast:.01ms; --motion-base:.01ms;
          --motion-slow:.01ms; --motion-slower:.01ms; }
  *,*::before,*::after{ animation-duration:.01ms!important;
    transition-duration:.01ms!important; scroll-behavior:auto!important; }
}
```

连 `scroll-behavior: smooth` 也要关掉 —— 平滑滚动本身也是一种动效，前庭功能障碍者会因此不适。

---

## 8. 图标方案锁定说明

### 8.1 锁定结论

**全站锁定 Lucide 图标库，单一家族，禁止混用。**

| 项 | 值 |
|----|----|
| 图标族 | **Lucide**（ISC 协议，可商用） |
| viewBox | `0 0 24 24` |
| stroke-width | **1.75**（Lucide 默认 2，本 Spec 降一档更贴近 Apple 纤细观感） |
| stroke-linecap | `round` |
| stroke-linejoin | `round` |
| fill | `none` |
| 尺寸档位 | 16px 行内 / 20px 按钮内 / 24px 独立 |
| 实现方式 | 内联 `<symbol>` + `<use>`（零额外请求） |

### 8.2 为什么选 Lucide 而不是 Feather

两者同源（Lucide 是 Feather 的社区延续），差异在于：

- **Lucide 更新更快**（活跃维护 vs Feather 事实上停更）
- Lucide 补充了更多语义图标（`sigma`、`shuffle`、`file-text`、`target` 等本站必需）
- 描边风格更适合高密度金融界面

**关键约束：全站只用一套。** 混用两套图标库会产生三种描边粗细、两种圆角端点、两种视觉重心 —— 这是「一眼 AI」的最强信号之一，比单个图标画错更致命。

### 8.3 emoji 迁移方案（强制）

**问题**：上游 `entries.json` 的 `summary` 字段含 emoji（例：10-13 股票复盘摘要含 U+1F53A 红色上三角）。文档 `fund_operation_guide.md` 亦含 U+1F6A6 / U+1F4CB / U+1F3AF 等章节标记。

**规则**：

| emoji 类型 | 替代方案 |
|-----------|---------|
| 涨跌方向（U+1F53A / U+1F53B / U+1F4C8 / U+1F4C9） | **SVG 箭头** `arrow-up` / `arrow-down`（13px，stroke 2.2）+ 语义色 |
| 文档类型（U+1F4C4 / U+1F4CB / U+1F4CA） | **SVG 文件图标** `file-text` / `file` |
| 章节标记（U+1F3AF / U+26A1 / U+1F4BC / U+1F30D） | **SVG 语义图标** `target` / `activity` / `bar-chart` / `globe` |
| 状态标记（达标禁止注意） | **SVG 状态图标** `check` / `x` / `alert` + 文字标签 |

**绝对禁止「只是删掉」** —— 删除会丢失信息（原「U+1F53A +0.10%」删掉 emoji 后变成「+0.10%」，方向虽在但视觉强调消失）。必须替换为矢量图标或文字标签。

**自查正则**（已应用于本 Spec 全部产出，命中数 = 0）：

```
[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}\x{2B00}-\x{2BFF}\x{FE00}-\x{FE0F}]
```

**唯一例外**：用户生成内容（UGC）中的 emoji 不做强制替换 —— 那属于用户表达。本站 `summary` 字段来自上游自动生成，归类为**系统产出**，必须清洗。

### 8.4 站点图标清单（35 个 symbol，原型已定义）

| 语义 | symbol id | 用于 |
|------|-----------|------|
| 调度/时间 | `i-clock` `i-timer` `i-history` `i-calendar` | 调度时点、生成时刻、日期 |
| 涨跌 | `i-arrow-up` `i-arrow-down` `i-trending-up` `i-trending-down` | 评级、行情 |
| 评级 | `i-shuffle` `i-chevrons-down` `i-chevrons-up` `i-scale` | 信号矛盾、回避、进攻 |
| 数据 | `i-sigma` `i-database` `i-bar-chart` `i-line-chart` `i-activity` | Σ 值、数据源、图表 |
| 任务 | `i-target` `i-inbox` `i-git-branch` `i-radio` | 决策、归档、流程 |
| 文档 | `i-file` `i-file-text` `i-book` `i-archive` | 报告、方法论、归档 |
| 导航 | `i-arrow-right` `i-chevron-right` `i-chevron-down` | 链接、展开 |
| 状态 | `i-check` `i-x` `i-alert` `i-circle-dot` `i-minus` `i-shield` | 成功、失败、警告 |
| 订阅 | `i-rss` | RSS |

---

## 9. 响应式断点与栅格

| 断点 | 宽度 | 布局策略 |
|------|------|---------|
| xs | ≤390px | 单列；导航隐藏次要项；指标卡 1列；色卡 1 列 |
| sm | 641–640px… | 单列；徽章组横排；节区 32px |
| sm+ | 641–900px | 时间线 76px 窄槽；徽章组下移第二行 |
| md | 901–1024px | 完整时间线 92px 槽；容器 24px 内距；节区 48px |
| lg | ≥1025px | 980px 容器；32px 内距；节区 80px |

**关键断点行为**：

```css
/* ≤900px：徽章组脱离第三列，下移至内容下方 */
@media (max-width:900px){
  .tl-item{ grid-template-columns:76px 1fr; gap:16px; }
  .tl-meta{ grid-column:2; justify-self:start; flex-direction:row; flex-wrap:wrap; }
}

/* ≤640px：完全单列 */
@media (max-width:640px){
  .tl-item{ grid-template-columns:1fr; gap:12px; }
  .tl-meta{ grid-column:1; }
}
```

**无横向滚动保证**：所有宽表格包在 `.tbl-wrap{ overflow-x:auto; }` 内；长数字 `white-space:nowrap` + 容器 min-width:0；`body{ overflow-x:hidden; }` 兜底。viewport meta 允许缩放（**不禁用**）。

**触摸目标**：所有可交互元素 ≥44×44px（`.btn` min-height 44px、`.archive-item .go` 44×44px 圆形）。次要文字链接通过 `padding` 扩展热区至 44px。

---

## 10. 深色模式

### 10.1 实现方式（零 JS）

```css
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){ /* 全部 token 覆盖 */ }
}
:root[data-theme="dark"]{ /* 手动覆盖钩子，供未来 JS 切换 */ }
```

- `<meta name="color-scheme" content="light dark">` — 让浏览器 UI（滚动条、表单控件）同步
- `color-scheme: light dark` 在 `:root` — 原生适配
- 预留 `data-theme` 属性钩子，前端接入主题切换器时零 Token 改动

### 10.2 深色模式不是「反色」

**Apple 的深色不是把浅色取反**，而是重新配色：

| 角色 | 浅色 | 深色 | 变化逻辑 |
|------|------|------|---------|
| 画布 | `#FFFFFF` | `#000000` | 真黑，OLED 省电 |
| 交替带 | `#F5F5F7` | `#1C1C1E` | 从「浅灰」变为「深灰」 |
| 正文 | `#1D1D1F` | `#F5F5F7` | 近黑 ↔ 近白，都**不用纯色** |
| 分隔线 | `#D2D2D7` | `#38383A` | 降低亮度避免眩光 |
| 强调色 | `#0071E3` | `#2997FF` | **提亮**，维持黑底对比度 |

**强调色必须提亮**：这是深色模式最容易漏掉的一条。`#0071E3` 在黑底上对比度仅 3.36:1，不达标；`#2997FF` 达6.96:1。

### 10.3 评级徽章的深色形态

浅色模式是「深色实块 + 白字」，深色模式改为「淡色底（16% 同色）+ 亮色字」：

```css
--rating-defensive-bg:  rgba(74,222,128,0.16);
--rating-defensive-fg:  #4ADE80;    /* 8.77:1 on #122a1c */
```

原因：高饱和大色块在纯黑底上产生光晕（halation），长时间阅读刺眼。这是 Apple 在 iOS 组件上的标准做法。

### 10.4 明度递进而非投影

```
#000000 (画布) → #161617 (导航) → #1C1C1E (抬升) → #2C2C2E (三级) → #38383A (分隔)
```

深色模式下**不使用投影表达深度** —— 黑底上的黑影不可见。唯一保留的 `--elev-overlay` 供真正悬浮的浮层使用。

---

## 11. 禁止清单（Do's & Don'ts）

### 11.1 必须做

- 达标 **用字号/字重/留白建层级**，不靠卡片堆叠
- 达标 **蓝色只给交互元素**，每屏可见 ≤2 处
- 达标 **评级四重编码**：颜色 + SVG 图标 + 箭头 + 文字
- 达标 **数字一律 tabular-nums**，价格与 Σ 值不跳动
- 达标 **零 JS 降级可用**：深色模式走 `prefers-color-scheme`，禁用 JS 后结构完整
- 达标 **深色模式重新配色**，不简单反色；强调色提亮至 6.96:1
- 达标 **长标题钳制两行**，40+ 字中文标题不撑破布局
- 达标 **错误文案说明「发生了什么 + 数据怎么处理」**，不暴露技术细节
- 达标 **所有交互元素 ≥44×44px**，`:focus-visible` 焦点环始终可见

### 11.2 禁止做

- 禁止 **emoji 作功能图标** —— 全部图标来自锁定的 Lucide SVG，16/20/24 三档，禁止混用
- 禁止 **紫粉渐变**（`#7C3AED → #A855F7 → #EC4899` 及任何 Indigo→Pink 组合）。本站**零 gradient token** —— Apple 官网本身也没有渐变 token
- 禁止 **弹跳缓动** `cubic-bezier(0.68,-0.55,0.265,1.55)`
- 禁止 **彩色左边框卡片**（`border-left:3px solid accent`）—— 用边框颜色或 hairline 区分，不用侧条纹强调
- 禁止 **重复同尺寸卡片网格**（同款卡片 + 图标 + 标题 + 文字无限重复）
- 禁止 **千篇一律 Hero**（大图 + 一句口号 + 两个按钮）。本站首页首屏直接是真实归档数据条（3 期 / 12 篇 / 最新 Σ 评级）
- 禁止 **无信息量链接标签** —— 「阅读网页版 / HTML」「阅读 Markdown 版 / Markdown」全部禁止，链接文案写报告标题本身
- 禁止 **硬编码颜色** —— 除 Token 定义处外，全部走 `var(--token)`
- 禁止 **字重 800+** —— Apple 实践上限 700（且仅主标题）
- 禁止 **斑马纹数据表**、**表格竖线** —— Apple 表格只用横向hairline
- 禁止 **居中正文** —— Apple 从不居中正文段落
- 禁止 **把 Apple 拉丁 tracking 直接套到汉字** —— 必须做 CJK 补偿（§3.3）

### 11.3 借鉴 Apple 但明确让渡的地方

诚实标注三处**未照搬** Apple 的决策及理由：

| 项 | Apple 做法 | 本站做法 | 理由 |
|----|-----------|---------|------|
| 颜色数量 | 黑白灰 + 唯一蓝 | 增加五档评级色 + 涨跌色 | 金融语义必需。且已限制「每屏≤2 处强调色」，评级色仅出现在数据密集区 |
| 投影 | 几乎为零 | 同样为零 | **完全一致**，无让渡 |
| 渐变 | 零渐变 token | 零渐变 token | **完全一致**。骨架屏微光改用明度脉冲而非渐变以守住此约束 |

---

## 12. 三轴刻度记录

| 参数 | 值 | 依据 |
|------|-----|------|
| DESIGN_VARIANCE | **4/10** | Apple 官网本身高度可预测（严格栅格、左对齐、单栏为主）。取 4 而非更低，因为时间线的 92px 刚性槽 + 徽章组右对齐构成一定非对称感；不追求艺术性混沌 |
| MOTION_INTENSITY | **2/10** | Apple 官网动效极少（仅 hover 与产品切换淡入）。取 2，低于默认 5。仅保留：hover 变色 150ms、骨架脉冲、链接箭头位移 3px。**零滚动驱动动效** |
| VISUAL_DENSITY | **6/10** | 金融内容站，用户是专业投资者，需要高信息密度（每条目 8 个字段）。取 6（日常应用模式），未达 7+ 的「驾驶舱模式」—— 因为本站读者需要**阅读**摘要文本，不是扫读仪表盘；行高 1.47 与 16px 摘要保证了可读性 |

用户可覆盖以上任一参数。

---

## 13. 交付物与接入

| 文件 | 用途 | 接入方式 |
|------|------|---------|
| `design-tokens.css` | CSS 变量源文件 | `<link rel="stylesheet" href="design-tokens.css">` |
| `design-tokens.json` | 机器可读 Token | `import tokens from './design-tokens.json'` |
| `apple-prototype.html` | 高保真原型（单文件自包含） | 直接打开即见效果 |
| `APPLE-DESIGN-SPEC.md` | 本文档 | 团队对齐依据 |

### 13.1 上游正文 HTML 的容纳

本站 `daily/<date>/*.html` 共 19 个 `h2`、19 个 `table`、19 个 `h3`、12 个 `blockquote`，由上游任务产出，**不由本次重设计覆盖**。本 Spec 已为其预留容纳能力：

- 表格 → `.tbl` 规范（无竖线、hairline、数字等宽右对齐）
- 章节标题 → `--fs-title3`/`--fs-title4` 阶梯，靠字号建层级
- 评级块 → `.rating-*` 四重编码
- 长文行宽 → `--container-prose: 680px`

上游 HTML 当前使用硬编码色值与 `border-left:4px solid`（侧条纹），建议后续接入本 Token 替换。

### 13.3 上游详情页阅读框架（2026-10-15 增补）

§13.1 的「容纳能力」已工程化为独立规范：**`detail-frame-spec.md`**（配套 `detail-frame.css`）。要点：

- 由 `frame_pass.py` 在 sanitize 之后注入：slim 导航（同 `.nav` 同 Token）+ 面包屑 + kicker + 元信息行（与时间线条目同字段同组件）+ 标题提升（上游首标题升为 h1）+ 站点页脚（同源 + 「本页信息」行，字段全取 entries.json，保幂等）；
- 阅读容器裁定 **680px prose + 数据宽元素探出至 980px**（≤900px 收回），上游页面级容器（`.wrap` / Tailwind `max-w-*`）一律让位；
- sanitizer 共存：h3/h4 + `data-sb-h` 标记（借标记还原子节降档）、`.ic-wrap` / `.ip-mark` / `.viz-*` 类契约、sprite 注入、外链 Google Fonts 剥离；
- 反色表面（上游深色封面/hero）统一走 `--surface-inverse` / `--fg-on-inverse`，深色模式为抬升深灰而非反色；
- P0 三决策（IP 形象保留受约束、警告映射够用补 `.ic-wrap.warn`、emoji-kept 收紧为 K-1/K-2/K-3 判定规则）详见该规范 §8。

### 13.2 反AI 模板味自查

| 检查项 | 结果 |
|--------|------|
| emoji 作为功能图标 | 0 处（正则扫描验证） |
| 紫粉渐变 | 0 处 |
| 渐变 token（任意） | 0 处 |
| 弹跳缓动 | 0 处（仅在「禁止清单」文档描述中出现） |
| Lorem ipsum / Welcome to 等空洞占位 | 0 处 |
| 无信息量链接标签 | 0 处 |
| 硬编码颜色（style 属性裸 hex） | 0 处（`#fff`/`#000` 白名单外） |
| 虚构指标 | 0 处 —— 所有数字来自真实 `entries.json` |
| 通用 Hero 模板 | 未使用 —— 首屏为真实数据条 |
| 正文字号 <12px | 0 处（最小 11px 仅用于微标签，非正文） |

---

## 14. 变更记录

| 日期 | 变更 | 原因 | 影响范围 |
|------|------|------|---------|
| 2026-10-14 | 初版建立。Apple 设计语言落地，五档评级色阶校验通过，深色模式明度递进，图标锁定 Lucide | 用户明确要求「严格参考苹果公司网页风格」；替换原 emoji 章节标记 | 全站 |
| 2026-10-15 | 新增 §13.3 上游详情页阅读框架（detail-frame-spec.md + detail-frame.css）；新增 Token `--surface-inverse` / `--fg-on-inverse`（反色表面，承载上游深色封面/hero，修复 fg-on-fg 不可见文本风险）；框架页门禁发现两处构建 bug（rating-lg 类名优先级、日期页 li 无 ul 包裹），已列阻塞项交前端 | 上游详情页（daily/<date>/*.html）无站点级一致性；sanitizer 接线后暴露深渐变收敛与自定义属性两类 Token 漏洞 | 详情页 + Token 层 |