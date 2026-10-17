# UI-METHODOLOGY-SPEC: 方法论页面 Apple 风格双端设计规范

> **规范版本**：v2.0.0  
> **责任人**：颜好看（UI/UX 设计师） / 韦优（项目总监）  
> **归档日期**：2026-10-17  
> **适用范围**：`site/methodology/index.html` 及相关呈现层样式

---

## 一、视觉设计哲学与风格基准

本项目严格遵循 **Apple HIG（Human Interface Guidelines）** 视觉与交互哲学：
- **微质感、零彩色阴影、零粗暴渐变**；
- **排版建立层级**：通过字阶（Typography Scale）、字重（Font Weight）、微边框（Hairline Border）与留白节奏（Spacing Rhythm）建立自然阅读秩序；
- **深浅双模无缝自适应**：浅色下基于纯净浅灰与面底反差；深色下基于抬升面（Elevated Surfaces）与高对比度文字；
- **⛔ 团队三大 P0 绝对红线（不可妥协）**：
  1. **P0-1 严禁使用 emoji 作为功能图标**：全站一律使用统一描边（1.75~2px）的内联 SVG Symbol；
  2. **P0-2 严禁紫粉渐变主视觉**；
  3. **P0-3 严禁硬编码颜色字面量**（唯一例外 #fff/#000）：一切取值走 `design-tokens.css` 的 `var(--token)`。

---

## 二、双端版式与栅格系统规范

### 2.1 桌面端适配规范（Desktop `> 900px`）
1. **主容器宽幅优化**：
   - 废弃原先狭窄的 680px（`--container-prose`），升级为专门的 **`--container-methodology: 920px`**；
   - 在 1440px / 1920px 视口下居中呈现，两侧留白均匀舒展，阅读视线不压抑、不空洞。
2. **快速胶囊导航（TOC Segmented Capsule Bar）**：
   - 位于 Hero 下方，吸顶显示（`position: sticky; top: var(--nav-h); z-index: 10;`）；
   - 背景采用 Apple 标志性的毛玻璃效果：`background: var(--nav-bg); backdrop-filter: saturate(180%) blur(20px); -webkit-backdrop-filter: saturate(180%) blur(20px);`；
   - 包含 9 大模块锚点药丸：`流水线`、`信号量化`、`五档评级`、`技术指标`、`决策护栏`、`策略体系`、`多源容灾`、`基金穿透`、`反滥用`；
   - 各锚点设置平滑滚动与吸顶偏移（`scroll-margin-top: calc(var(--nav-h) + 64px);`）。
3. **七步流水线栅格（Step Flow Grid）**：
   - 桌面端采用 7 列等宽网格（`display: grid; grid-template-columns: repeat(7, 1fr); gap: var(--space-2);`）；
   - 每步包含等宽序号 `01~07` 与两行紧凑标题，形态连贯如工业级装配线。
4. **对比卡片（Dual-Card Comparison）**：
   - 双列并排（`display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4);`）；
   - 典型应用于“时相感知护栏 vs 市场环境护栏”、“主源采集 vs 备用容灾链”。

### 2.2 移动端适配规范（Mobile `<= 640px`，针对 375px/390px/414px）
1. **胶囊导航横向平滑滚动**：
   - 单行横排不换行（`white-space: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch;`）；
   - 隐藏滚动条，两端留有手势滑动余量，大拇指轻触即可直达目标章节；
   - 胶囊按钮高度设为 `34px`，单手触控轻松准确。
2. **流水线自适应重排**：
   - 在手机端折为 **2 列自适应网格** 或垂直步骤列表，文字不挤压、不换行截断。
3. **对比卡片自动折单列**：
   - 双列卡片在 `<=640px` 自动折为单列流，保持纵向阅读节奏。
4. **表格与宽内容保护**：
   - 全部表格包含在 `.tbl-wrap` 容器内，保留横向弹性滑动提示；
   - 移动端表格单元格紧凑内边距（`padding: var(--space-2) var(--space-3);`），数字列等宽。
5. **底部安全边距**：
   - 页面底部注入 `padding-bottom: max(var(--space-16), calc(env(safe-area-inset-bottom, 24px) + var(--space-8)))`。

---

## 三、组件级微质感设计细节

### 3.1 模块主卡片（`.mp-sec`）
- **浅色模式**：
  - 背景：`var(--surface)`；
  - 边框：`1px solid var(--border-soft)`；
  - 圆角：`border-radius: var(--panel-radius, 14px); corner-shape: squircle;`；
  - 内边距：桌面端 `var(--space-6) var(--space-8)`，移动端 `var(--space-4) var(--space-4)`。
- **深色模式**：
  - 背景：`var(--surface-alt)`；
  - 边框：`1px solid var(--ap-dark-sep)`；
  - 文字前景：主要文字 `var(--fg)`，次要解释 `var(--fg-2)`。

### 3.2 胶囊按钮（`.mp-pill`）
- 结构：`<a class="mp-pill" href="#mp-xxx">流水线</a>`；
- 样式：
  - 字体：`font-size: var(--fs-caption1); font-weight: var(--fw-medium);`；
  - 边框：`1px solid var(--border-soft)`；
  - 背景：`var(--surface-alt)`，悬浮为 `var(--accent-hover)`；
  - 圆角：`border-radius: var(--radius-pill);`。

### 3.3 规则高亮块（`.mp-callout` / `.mp-note`）
- 用于突出“强势趋势补偿 1.5 倍”、“有效权重封顶规则”、“L-4 降级态动作门禁”等硬核纪律；
- 背景：`var(--surface-alt)`，左侧配有弱对比度细线与内联 SVG 提示图标。

---

## 四、设计自检清单（Design Audit）

| 检查项 | 标准 | 状态 |
|---|---|:---:|
| **P0-1 图标纯洁度** | 100% 零 emoji 功能图标，统一采用内联 SVG | PASS |
| **P0-2 色彩纯洁度** | 零紫粉渐变，背景与文本明暗对比符合 WCAG AA (≥ 4.5:1) | PASS |
| **P0-3 Token 规范** | 无硬编码颜色字面量，全部引用系统 Token | PASS |
| **桌面端阅读舒适度** | 容器 920px，排版舒展，TOC 锚点吸顶正常响应 | PASS |
| **移动端触控与无横滚** | 胶囊栏水平平滑滑动，页面各宽度零水平溢出 | PASS |
| **深浅模式自适应** | 双模式下边框、文字、背景对比鲜明，无视觉融化 | PASS |
