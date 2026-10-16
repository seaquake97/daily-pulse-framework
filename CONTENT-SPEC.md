# 统一内容契约（Unified Content Contract）

版本：1.0.0 ｜ 状态：生效中 ｜ 契约实现：`scripts/content_contract.py` + `scripts/content_dictionary.py`
适用范围：`/Users/lianghaizhen/WorkBuddy/` 下 6 个每日定时任务的全部 Markdown 产出

本文件是规范，不是选型报告。文中「必须」「禁止」为硬约束；技术栈由项目实际情况决定，不在本文锁定。

---

## 1. 背景与目标

### 1.1 问题陈述

同一交易日，6 个任务产出的研判在结构、命名、时点标注三个层面互不对齐。读者拿到 3 份报告，看到 3 个不同的 Σ 值与 2 种评级，无法判断这是盘中观点演进还是数据错误——因为呈现层没有任何区分。

### 1.2 实测证据（2026-10-14）

证据取自当日真实产出，非抽样估计。

| 编号 | 事实 | 证据位置 |
| --- | --- | --- |
| E1 | 章节编号四套并存：纯中文数字（股票助手）、中文数字带多余空格（11:00 盘面 `## 一、 全场…`）、emoji 前缀 + 中文数字（14:30 指引）、两位阿拉伯数字（15:05 复盘） | 四份 md 的 H2 标题 |
| E2 | emoji 残留：14:30 指引 13 处、15:05 复盘 4 处、11:00 盘面 1 处 | 正则扫描 |
| E3 | Σ 值三值：9:28 `+0.010`（信号矛盾）、14:30 `-0.263`（防守）、15:30 `-0.339`（防守） | 三份 `market_data.json` 的 `verdict` |
| E4 | 同一概念四种叫法：信号明细被称作「六信号明细」「六维确定性信号硬校验」「四层信号矩阵」「信号面」 | 四份 md 的章节标题 |
| E5 | 11:00 盘面无 `market_data.json`，其 Σ 值无法回溯校验 | 目录清单 |
| E6 | 三份 `market_data.json` 均缺 `snapshot_at`，Σ 无法回溯到具体时刻 | JSON 字段检查 |
| E7 | 宽度分母两个口径并存：5,574（含北交所）与 5,273（仅 A 股） | `market_breadth` 字段 |
| E8 | 发布层把收盘 Σ 挂到所有任务：`_stage/docs/daily/2026-10-14/entries.json` 中 5 个条目的 `sigma` 全为 `-0.339` | 见 §5.3 |

### 1.3 目标

1. 六任务共用一套章节骨架，结构差异只体现在「章节有无」，不体现在「章节怎么命名、怎么编号」。
2. 同一分析维度在全项目只有一个规范名，中英双语锁定。
3. 任何 Σ 值都必须携带自己的时点戳，读者可据此判断时点差异。
4. 违规可被机器检出，不依赖人工通读。

### 1.4 非目标（本次不做）

- 不改造 `daily-decision-engine` 的信号评分公式与四档阈值——那是计算层，本契约只管呈现。
- 不回溯整改 2026-10-14 之前的历史产出。历史文件保持原样，契约从生效日向后适用。
- 不重构 `build_site.py` / `publish_to_github.py`。发布层的 Σ 归属缺陷记为 ADR-002 待办，本次仅登记不修复。
- 不引入任何第三方依赖（图标库、校验框架等）。图标语义由本契约定义，实现方式由渲染层自选。
- 不为 `每日基金股票复盘-v2决策引擎`（当前为空目录）单独设计骨架——它复用 `stock-review` 骨架。

---

## 2. 统一章节骨架

### 2.1 骨架定义

骨架由 `content_contract.SECTIONS` 唯一定义。章节分三类：

- **必选**（`required=True`）：所有任务恒定包含，恒定位于首尾。
- **条件选**（`applies_to` 非空）：仅列出的任务包含。
- **任务生成时**：按 `build_skeleton(slug)` 取子集，**顺序恒为 `SECTIONS` 声明顺序**，不因任务而异。

### 2.2 章节表

| # | 键 | 规范中文名 | English | 类型 | 适用任务 |
| --- | --- | --- | --- | --- | --- |
| 1 | `verdict` | 结论卡 | Verdict Card | 必选 | 全部 |
| 2 | `sigma_timeline` | 日内 Σ 演进 | Intraday Sigma Timeline | 条件 | 复盘、总复盘、v2 |
| 3 | `market_snapshot` | 市场快照 | Market Snapshot | 条件 | 股票助手、盘面、复盘、总复盘 |
| 4 | `signal_detail` | 确定性信号明细 | Signal Detail | 条件 | 除 v2 外全部 |
| 5 | `bull_bear_evidence` | 多空证据清单 | Bull-Bear Evidence | 条件 | 股票助手、盘面 |
| 6 | `sector_moneyflow` | 板块资金流向 | Sector Money Flow | 条件 | 盘面、指引、复盘、总复盘 |
| 7 | `overseas_check` | 外盘联动校验 | Overseas Linkage Check | 条件 | 盘面、指引、复盘、总复盘 |
| 8 | `portfolio_attribution` | 组合加权归因 | Portfolio Attribution | 条件 | 盘面、指引、总复盘 |
| 9 | `fund_lookthrough` | 基金穿透诊断 | Fund Look-through | 条件 | 盘面、指引 |
| 10 | `position_action` | 持仓动作卡 | Position Action Card | 条件 | 股票助手、指引、复盘、总复盘 |
| 11 | `grid_order` | 网格委托指令 | Grid Order Instruction | 条件 | 指引 |
| 12 | `expert_roundtable` | 专家圆桌 | Expert Roundtable | 条件 | 复盘、总复盘、v2 |
| 13 | `viewpoint_ledger` | 观点台账 | Viewpoint Ledger | 条件 | 股票助手、指引、复盘、总复盘 |
| 14 | `data_gap` | 数据缺口 | Data Gap | 条件 | 全部（无缺口时写明「本时点无数据缺口」） |
| 15 | `watchlist` | 待验证信号 | Watch Signals | 必选 | 全部 |
| 16 | `disclaimer` | 免责声明 | Disclaimer | 必选 | 全部 |

各任务实际章节数（由 `build_skeleton` 计算）：

| 任务 slug | 章节数 | 条件章节差异 |
| --- | --- | --- |
| `stock-assistant` | 12 | 有多空证据清单，无组合归因 |
| `fund-market` | 14 | 有基金穿透，无持仓动作卡、无专家圆桌 |
| `fund-guide` | 14 | 有网格委托指令，无专家圆桌 |
| `stock-review` | 14 | 有专家圆桌、日内 Σ 演进，无网格委托 |
| `daily-review` | 16 | 全章节 |
| `v2-decision-engine` | 6 | 复用复盘骨架 |

### 2.3 裁剪规则（应对 73 行与 144 行的行数落差）

行数差异由**章节有无**吸收，不由**章节改名或重编号**吸收。三条硬规则：

1. **条件章节当日无数据时保留章节标题**，正文写明「本时点无数据」及原因。禁止删除章节——删除会让当日结构与次日不可比。
2. **禁止为迁就篇幅增删必选章节**，也禁止把一个章节拆成两个以凑编号。
3. **章节内长度自由**：9:28 任务允许「持仓动作卡」只有 9 行，15:30 任务允许「专家圆桌」写满 6 位专家。骨架约束的是「有哪些维度」，不是「每个维度写多长」。

### 2.4 章节编号规范

唯一编号体系：**两位阿拉伯数字 + 半角句点 + 半角空格**。

```
## 01. 结论卡
## 02. 确定性信号明细
```

禁止：中文数字（`一、`）、单位数字（`1.`）、三位数字（`001.`）、编号后紧跟全角标点。

标题文本必须命中 `SECTION_TITLES_ZH` 或 `SECTION_TITLES_EN`（由 `SECTIONS` 派生，不单独维护）。

---

## 3. 统一维度词典

### 3.1 规范维度名

同一概念在全项目只能使用下列名称。英文名用于 HTML `data-dimension` 属性与站点标签。

| 键 | 规范中文名 | English |
| --- | --- | --- |
| `verdict` | 结论卡 | Verdict Card |
| `sigma_timeline` | 日内 Σ 演进 | Intraday Sigma Timeline |
| `market_snapshot` | 市场快照 | Market Snapshot |
| `signal_detail` | 确定性信号明细 | Signal Detail |
| `bull_bear_evidence` | 多空证据清单 | Bull-Bear Evidence |
| `index_quote` | 指数行情 | Index Quotes |
| `sector_moneyflow` | 板块资金流向 | Sector Money Flow |
| `overseas_check` | 外盘联动校验 | Overseas Linkage Check |
| `portfolio_attribution` | 组合加权归因 | Portfolio Attribution |
| `fund_lookthrough` | 基金穿透诊断 | Fund Look-through |
| `concentration` | 板块集中度 | Sector Concentration |
| `position_action` | 持仓动作卡 | Position Action Card |
| `grid_order` | 网格委托指令 | Grid Order Instruction |
| `expert_roundtable` | 专家圆桌 | Expert Roundtable |
| `viewpoint_ledger` | 观点台账 | Viewpoint Ledger |
| `data_gap` | 数据缺口 | Data Gap |
| `watchlist` | 待验证信号 | Watch Signals |
| `disclaimer` | 免责声明 | Disclaimer |

### 3.2 废弃名对照（出现即判违规）

`content_dictionary.BANNED_DIMENSIONS` 收录 45 条废弃写法，全部来自 2026-10-14 实测。节选：

| 废弃写法 | 规范名 | 所属维度 |
| --- | --- | --- |
| 六信号明细 | 确定性信号明细 | `signal_detail` |
| 六维确定性信号硬校验结果 | 确定性信号明细 | `signal_detail` |
| 四层信号矩阵 | 确定性信号明细 | `signal_detail` |
| 子专家观点 | 专家圆桌 | `expert_roundtable` |
| 主持人札记 / 主持人 Q&A | 专家圆桌 | `expert_roundtable` |
| 全场 A股动态行情家数与结构统计 | 市场快照 | `market_snapshot` |
| 板块主力资金流向 | 板块资金流向 | `sector_moneyflow` |
| 外盘企稳联动校验红线评估 | 外盘联动校验 | `overseas_check` |
| 逐基金穿透诊断 | 基金穿透诊断 | `fund_lookthrough` |
| 持仓穿透与板块集中度深度分析 | 基金穿透诊断 | `fund_lookthrough` |
| 股票与场内 ETF 网格操作指引 | 网格委托指令 | `grid_order` |
| 持仓层：网格动作卡 / 观察卡 | 持仓动作卡 | `position_action` |
| 明日待验证信号 | 待验证信号 | `watchlist` |
| 关键变量观察台 | 待验证信号 | `watchlist` |

「确定性」一词保留在 `signal_detail`，因为 S1-S6 是代码硬算的确定性信号；其余维度不加限定词，避免修饰语堆叠。

---

## 4. 数据时点标注格式

### 4.1 字段与格式

| 字段 | 位置 | 格式 | 示例 | 缺失后果 |
| --- | --- | --- | --- | --- |
| `data_stage` | md 头部 + `market_data.json` | `pre_open` / `intraday` / `close` | `intraday` | 无法判断盘中还是收盘 |
| `snapshot_at` | md 头部 + `market_data.json` | `YYYY-MM-DD HH:MM` | `2026-10-14 14:30` | 无法回溯 Σ 对应时刻 |
| `breadth_scope` | md 头部 + `market_data.json` | `a_only` / `a_plus_bj` | `a_plus_bj` | 宽度分母口径不明，Σ 不可比 |
| `valid_weight` | md 头部 + `verdict` | `0.00`-`1.00` | `1.00` | 不知是否缺信号 |
| `rating` | md 头部 + `verdict` | 进攻/均衡/信号矛盾/防守/回避 | `防守` | — |
| `sigma` | md 头部 + `verdict` | 带符号三位小数 | `-0.263` | — |

### 4.2 md 头部标注块（固定格式）

由 `render_meta_block()` 生成，字段顺序恒定：

```
> Σ = -0.263 ｜ data_stage=`intraday` ｜ snapshot_at=`2026-10-14 14:30` ｜ rating=防守 ｜ valid_weight=1.00 ｜ breadth_scope=`a_plus_bj`
```

### 4.3 `market_data.json` 新增字段

现有 schema（`daily-decision-engine/templates/market_data.schema.json`）的 `required` 为 `["date","indices","total_amount_yi","market_breadth","holdings","verdict"]`，不含时点字段。必须补入：

```json
{
  "data_stage": "intraday",
  "snapshot_at": "2026-10-14 14:30",
  "breadth_scope": "a_plus_bj"
}
```

`data_stage` 当前实际已写入三份 JSON，但不在 schema 中，属于未声明字段——本次补入 schema 并列入 `required`。

### 4.4 宽度分母口径

`a_only` = 仅 A 股（不含北交所），分母 5,273；`a_plus_bj` = A 股 + 北交所，分母 5,574。

同一天内所有任务必须使用同一 `breadth_scope`。口径不同则 S2 宽度信号输入不同，Σ 之间不可直接比较——`comparable()` 会据此判定不可比并给出理由。

---

## 5. Σ 值呈现契约

这是本规范的核心。目标是让读者一眼区分「观点随行情演进」与「数据出错」。

### 5.1 三值合理性复核结论

**结论：认同「三个 Σ 值本身是对的」，但需补充一个前提。**

三个值对应三个不同时点的独立快照，各自内部自洽：

| 时点 | data_stage | Σ | 评级 | S2 宽度输入 |
| --- | --- | --- | --- | --- |
| 9:28 | `intraday` | `+0.010` | 信号矛盾 | 上涨占比 33.1% |
| 14:30 | `intraday` | `-0.263` | 防守 | 上涨占比 18.3% |
| 15:30 | `close` | `-0.339` | 防守 | 上涨占比 17.9% |

Σ 随日内行情单向走低，与 S2 宽度同步恶化，方向自洽。计算层没有问题。

**需补充的前提**：11:00 盘面正文引用了第四个值 `+0.125`（`signal-scoring.md` 判定为信号矛盾档），但该任务无 `market_data.json`，无法回溯。所以真实情况是三个可验证值加一个不可验证值，不是三个值。

**缺陷定位认同**：呈现层无区分，这确实是表达契约缺失。但要补一条更严重的——**发布层 actively 制造了错误呈现**，见 §5.3。

### 5.2 呈现规范（三条硬约束）

**约束一：Σ 值必须与时点戳同行出现。** 禁止报告任何位置出现裸 `Σ`。判定由 `SIGMA_SNAPSHOT_STAMP` 与 `SIGMA_STAGE_STAMP` 两条独立规则执行，缺一即报。

结论卡首行用 `render_sigma_line()`：

```
- Σ = **-0.263** ｜ data_stage=`intraday` ｜ snapshot_at=`2026-10-14 14:30` ｜ rating=**防守**
```

**约束二：15:05 与 15:30 两个任务必须输出「日内 Σ 演进」章节。** 用 `render_sigma_timeline()` 渲染，把当日全部快照并列，让演进关系显式化：

```
| 时点 | 快照时刻 | data_stage | Σ | 评级 | 驱动变化 |
| --- | --- | --- | --- | --- | --- |
| 09:28 | 2026-10-14 12:39 | `intraday` | +0.010 | 信号矛盾 | - |
| 14:30 | 2026-10-14 14:30 | `intraday` | -0.263 | 防守 | S2 宽度由 33.1% 降至 18.3% |
| 15:30 | 2026-10-14 15:31 | `close` | -0.339 | 防守 | S5 资金净流出扩大 |
```

末列「驱动变化」必须写明哪个信号翻转，不允许留空或写「行情变化」。

**约束三：Σ 值必须等于本任务自己的 `market_data.json`。** 禁止跨任务继承。校验由 `SIGMA_VALUE` 执行，比对容差 `5e-4`。

**可比性附加规则**：演进表下方必须调用 `comparable()` 判定并写出结论。若 `breadth_scope` 或 `valid_weight` 不一致，表格后必须显式写「口径不一致，Σ 跨时点不可比」，禁止让读者默认可比。

### 5.3 已识别的发布层缺陷（登记待修，见 ADR-002）

`publish_to_github.py:241` 的 `extract_entry()` 对所有任务使用同一份 `market_data`：

```python
verdict = (market_data or {}).get("verdict", {})
return {..., "rating": verdict.get("rating"), "sigma": verdict.get("sigma"), ...}
```

而 `load_market_data()` 按 `MARKET_DATA_DIRS = ["每日总复盘（15:30）", "股票助手"]` 优先级加载，恒定命中收盘数据。实测 `entries.json`：

| slug | 自身 Σ | 发布层挂载的 Σ |
| --- | --- | --- |
| `stock-assistant` | `+0.010` | `-0.339` |
| `fund-market` | `+0.125`（无 JSON 佐证） | `-0.339` |
| `fund-guide` | `-0.263` | `-0.339` |

后果：站点上 9:28 任务显示「收盘时点 `-0.339` 防守」，与其正文的「盘中 `+0.010` 信号矛盾」直接矛盾。这不是呈现缺失，是**呈现错误**，且比正文层缺陷更严重——正文至少自洽，站点层不自洽。

修复方向（不在本次范围）：`entries` 的 Σ 必须来自各任务自己的 `market_data.json`，`SLUG_STAGE` 已有 per-slug 时点映射可复用。

---

## 6. emoji 禁令与 SVG 图标语义映射

### 6.1 禁令

六任务全部产出（md 与 html）禁止使用 emoji 作为章节标记或装饰。

判定由 `EMOJI` 规则执行，码点白名单见 `content_contract.EMOJI_PATTERN`。

**刻意不覆盖 U+2600-U+27BF 整块**：U+2605 与 U+2606 属排版评分符号，U+25B2 / U+25BC / U+2194 是站点层 `RATING_ARROWS` 故意保留的色盲友好冗余编码。这些若一并禁掉会破坏既有可访问性设计。当前白名单对 15 个真实 emoji 全部命中，对 18 个排版/评级符号零误判。

### 6.2 SVG 图标语义映射

契约锁定「语义键 → 图标含义」，**不锁定图标库**。渲染层可自行决定 inline `<svg>` / `<img>` / CSS mask 实现，只要语义键一致。跨任务混用不同图标库视为违规。

图标风格约束：24x24 视框、线性描边、`stroke: currentColor`、随文字颜色变化。

| 语义键 | 中文语义 | 用于章节/维度 |
| --- | --- | --- |
| `verdict` | 裁定 | 结论卡 |
| `sigma` | 综合评分 | 结论卡内 Σ 行 |
| `timeline` | 时点演进 | 日内 Σ 演进 |
| `breadth` | 市场广度 | 市场快照 |
| `moneyflow` | 资金流向 | 板块资金流向 |
| `overseas` | 外盘联动 | 外盘联动校验 |
| `portfolio` | 组合归因 | 组合加权归因 |
| `fund` | 基金穿透 | 基金穿透诊断 |
| `position` | 持仓动作 | 持仓动作卡 |
| `grid` | 网格委托 | 网格委托指令 |
| `expert` | 专家圆桌 | 专家圆桌 |
| `ledger` | 观点台账 | 观点台账 |
| `gap` | 数据缺口 | 数据缺口 |
| `watch` | 待验证 | 待验证信号 |
| `shield` | 风险红线 | 底仓红线、禁止动作提示 |
| `doc` | 文档 | 免责声明 |

### 6.3 配色禁令

禁止紫色至粉色渐变（`purple` / `violet` / `magenta` / `pink` / `fuchsia` 系）。站点现有配色（`--accent:#b45309` 琥珀 + 中性灰）符合要求，保持不变。新增视觉一律在现有中性色板内取色。

---

## 7. 术语一致性检查清单

发布前逐项核对，每项对应一条可执行校验：

- [ ] 章节编号全为 `## NN. `，无中文数字、无 emoji 前缀
- [ ] 章节标题命中 `SECTION_TITLES_ZH` 或 `SECTION_TITLES_EN`
- [ ] 正文无 `BANNED_DIMENSIONS` 中的废弃写法
- [ ] 全文无 emoji（U+2605 / U+25B2 / U+25BC / U+2194 等符号不算）
- [ ] Σ 值出现处必定同行带 `data_stage` 与 `snapshot_at`
- [ ] Σ 值等于本任务 `market_data.json` 的 `verdict.sigma`
- [ ] `data_stage` 取值为 `pre_open` / `intraday` / `close`
- [ ] `breadth_scope` 取值为 `a_only` / `a_plus_bj`，且与同日其他任务一致
- [ ] 15:05 与 15:30 产出含「日内 Σ 演进」章节，且「驱动变化」列非空
- [ ] 条件章节无数据时保留标题并写明原因，未删除
- [ ] 必选章节（结论卡/待验证信号/免责声明）齐全且位于首尾
- [ ] `market_data.json` 含 `data_stage` / `snapshot_at` / `breadth_scope`
- [ ] 无紫粉渐变
- [ ] 免责声明显 present 且未被裁剪

一键校验：

```bash
cd /Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan/scripts
python3 test_content_contract.py && python3 test_real_outputs.py
```

---

## 8. 共享生成器接口

### 8.1 模块职责

| 模块 | 行数 | 职责 |
| --- | --- | --- |
| `content_contract.py` | 286 | 骨架定义、渲染函数、校验逻辑 |
| `content_dictionary.py` | 84 | 维度词典、SVG 语义映射（纯数据） |

依赖方向单向：`content_contract` → `content_dictionary`。拆分理由是词表与逻辑变更节奏不同，避免每次调校验逻辑都碰到大块常量。

### 8.2 生成侧接口

```python
build_skeleton(slug: str) -> list[Section]
render_skeleton_md(slug: str) -> str
render_meta_block(sigma, data_stage, snapshot_at, rating,
                  valid_weight=1.0, breadth_scope="") -> str
render_sigma_line(sigma, data_stage, snapshot_at, rating) -> str
render_sigma_timeline(rows: list[dict]) -> str
comparable(sigmas: list[dict]) -> tuple[bool, str]
```

### 8.3 校验侧接口

```python
validate_contract(path: Path, market_data: dict | None = None) -> list[Violation]
validate_json_artifact(path: Path) -> list[Violation]
Violation: {rule, line, message, severity}
```

`severity` 为 `error`（阻断发布）或 `warn`（提示）。当前唯一 `warn` 是 `BREADTH_SCOPE` 缺失。

### 8.4 校验规则表

| 规则 | 级别 | 触发条件 |
| --- | --- | --- |
| `EMOJI` | error | 命中 emoji 白名单 |
| `NUMBERING` | error | 二级标题未用 `NN. ` 格式 |
| `SECTION_NAME` | error | 章节标题不在骨架内 |
| `DIMENSION` | error | 命中废弃维度名 |
| `SIGMA_SNAPSHOT_STAMP` | error | 有 Σ 无 `snapshot_at` |
| `SIGMA_STAGE_STAMP` | error | 有 Σ 无 `data_stage` |
| `SIGMA_VALUE` | error | Σ 与本任务 JSON 不一致 |
| `SIGMA_SOURCE` | error | JSON 缺 `verdict.sigma` |
| `STAGE_ENUM` | error | `data_stage` 非法 |
| `BREADTH_SCOPE` | error / warn | 取值非法（error）/ 未声明（warn） |
| `SNAPSHOT_AT` | error | JSON 缺 `snapshot_at` |
| `JSON_INVALID` | error | JSON 无法解析 |

---

## 9. 验收标准

每条用可验收句式（EARS）表述：

1. 当且仅当六任务的章节编号全部符合 `## NN. ` 时，视为编号合规。
2. 当产出中不存在 `BANNED_DIMENSIONS` 任一成员时，视为维度命名合规。
3. 当产出中不存在 emoji 白名单任一码点时，视为图标合规；U+2605 / U+25B2 / U+25BC / U+2194 不在此列。
4. 当报告出现 Σ 值且同行带 `data_stage` 与 `snapshot_at` 时，视为时点标注合规。
5. 当报告 Σ 值与本任务 `market_data.json` 的 `verdict.sigma` 绝对差不超过 `5e-4` 时，视为数值一致。
6. 当 15:05 与 15:30 产出均含「日内 Σ 演进」章节且「驱动变化」列非空时，视为演进可读。
7. 当同一交易日全部任务的 `breadth_scope` 取值相同时，视为 Σ 跨时点可比；否则必须在演进表下方显式声明不可比。
8. 当产出无数据缺口时，`data_gap` 章节保留且正文写明「本时点无数据缺口」。

## 10. 端到端验证步骤

```bash
cd /Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan/scripts

# 1) 契约自身回归（12 用例：骨架/词表/渲染/枚举）
python3 test_content_contract.py

# 2) 真实产出回归（17 用例：fixture 指向 2026-10-14 实际文件）
python3 test_real_outputs.py

# 3) 对当日全部产出跑一次校验，打印违规清单
python3 -c "
import sys; sys.path.insert(0,'.')
import content_contract as cc
from pathlib import Path
B = Path('/Users/lianghaizhen/WorkBuddy')
for d, f in [('股票助手','stock_assistant.md'),
             ('基金每日盘面分析（11:00）','fund_market_analysis.md'),
             ('基金每日操作指引（14:30）','fund_operation_guide.md'),
             ('股票复盘','stock_review.md')]:
    v = cc.validate_contract(B / d / '2026-10-14' / f)
    errs = [x for x in v if x.severity == 'error']
    print(f'{d}: {len(errs)} 条')
"
```

**通过判据**：步骤 1、2 全绿；步骤 3 对当日历史产出**应当报出违规**（这些是契约生效前的产出，本就不合规）。若步骤 3 报 0 条，说明校验器失效——那是回归失败，不是产出合格。

**变异验证**（已执行）：对 9 条校验规则逐条注入失效（关闭判定条件），确认对应用例转红。全部 9 条均可被检出，无空转规则。

## 11. 已知坑（内嵌）

1. **emoji 白名单不可用区间写 `U+2600-U+27BF`**：会误判 U+2605 / U+25B2 / U+25BC / U+2714，破坏站点层色盲友好箭头。必须逐个枚举码点。
2. **`\U` 转义在字符串拼接中会被截断**：Python 中 `"\U0001F300" + "-x"` 若误写为非 raw 拼接会产生 `truncated \UXXXXXXXX escape` 语法错误。改用显式码点枚举可规避。
3. **发布层 `MARKET_DATA_DIRS` 优先级会让所有任务共享收盘 verdict**：这是 §5.3 的缺陷根因，改动 `extract_entry` 时勿沿用全局 `market_data`。
4. **`SECTION_TITLES` 必须从 `SECTIONS` 派生**：早期版本单独维护 `SECTION_ALIASES` 字典，两处定义会静默漂移。
5. **`--task` 单任务发布时 `market_data` 仍走全局加载**：`publish_to_github.py` 支持 `--task` 参数，但 `load_market_data()` 不区分 slug，单任务发布会带上收盘 Σ。修复 ADR-002 时须一并处理。
6. **`__pycache__` 会让变异测试结果失真**：连续注入-还原时需清理缓存，否则第二次运行的是旧字节码。本次已踩，测试脚本应避免依赖缓存状态。
7. **真实产出 fixture 缺失时应 skip 而非伪造样本**：本项目产出目录会随日期滚动，测试须能优雅降级。

## 12. 活规格维护

- 实现与本规范冲突时，**先改本规范再改代码**。
- 新增维度必须同时更新 `content_dictionary.DIMENSIONS` 与本文件 §3.1，两处缺一即视为未完成。
- 新增章节必须同步 `SECTIONS` 与本文件 §2.2。
- 决策与理由保留在 `docs/decisions/`，被证伪的约束显式标注废弃，不静默删除。
