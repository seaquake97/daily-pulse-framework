---
name: daily-decision-engine
description: >-
  基金/股票每日定时任务的决策引擎协议：数据硬校验、确定性信号评分、决策卡七件套、
  中性词禁令、观点台账结算与专家团对抗辩论规范。当执行每日复盘、基金盘面分析、
  基金操作指引、股票助手等定时研判任务时必须加载本技能。触发词：每日决策引擎、
  每日复盘决策、基金每日操作、研判协议、决策卡、观点台账、信号评分。
agent_created: true
version: 1.0.0
display_name: "每日决策引擎"
display_name_en: "Daily Decision Engine"
description_zh: "基金股票每日研判的决策引擎：数据校验、信号评分、决策卡、观点台账与专家辩论协议。"
description_en: "Decision engine protocol for daily fund/stock review: data validation, signal scoring, decision cards, viewpoint ledger, and expert debate rules."
visibility: "public"
---

# 每日决策引擎（Daily Decision Engine）

## 定位

本技能是用户全部基金/股票每日定时任务的**唯一决策协议**。任何定时任务生成研判内容前
必须加载本技能，并按以下流水线执行。设计范式融合：

- **TradingAgents**（TauricResearch，74.5k★）：分析师→牛熊对抗辩论→风控→组合经理分层决策
- **openInvest**（longsizhuo）：信息隔离契约（防禀赋效应）+ Markdown-as-Database 审计轨迹 +
  二轮反驳交叉挑战 + CIO 结构化裁决（BUY/ACCUMULATE/HOLD/TRIM/SELL + 置信度）
- **NoFx**：滚动准确率评分 + 连续错误熔断

## 铁律（一票否决）

1. **数据只走 westock-mcp**：所有行情/板块/资金/涨跌分布/估值数据必须通过
   `mcp__westock-mcp__data_*` 工具实时获取。禁止 HTTP API 替代（新浪/同花顺/东财爬虫
   仅可作为交叉验证的第二来源，且必须标注"交叉源"）、禁止写死任何数值、禁止凭记忆填数。
2. **零编造**：数据缺失时明确标注"数据缺口"并降级，禁止用代理指标伪装成真实值
   （例：QDII 基金估值接口为 0 时，可标注"估值源缺失，参考标的指数昨收表现"，禁止
   把指数涨跌直接写成基金估值）。
3. **硬断言不过即停**：`scripts/validate_market_data.py` 任一断言失败 → 该任务输出
   "数据校验未通过 + 缺口清单"，禁止带着脏数据出报告。
4. **决策必须差异化**：同一天不同任务、不同日期的同类任务，结论必须由当日数据驱动。
   禁止出现"维持/保持既定"作为唯一结论。
5. **持仓只从记忆文件动态解析**：`scripts/parse_holdings.py` 从用户 MEMORY.md 提取
   持仓与网格参数。禁止在代码或提示词中写死持仓金额/份额/成本。
6. **免责声明**：所有产出末尾附 workbuddy-finance-skill 规定的固定免责声明文案。

## 执行流水线（七步）

```
步骤1 交易日判定  → 步骤2 数据采集(MCP) → 步骤3 信号评分(代码,合入verdict)
→ 步骤4 持仓解析 → 步骤5 硬校验(validate) → 步骤6 专家研判+对抗辩论 → 步骤7 决策卡+CI+台账落档
```

> **顺序铁律（v1.3，终验修复 P0-1）**：必须"先 compute_signals 合入 verdict，后 validate"——
> validate_market_data.py 断言 verdict 存在（compute_signals 未执行即校验失败）。
> 旧版流水线把硬校验排在信号评分之前，按字面执行必挂（2026-10-14 9:28 任务零产出实证）。

### 步骤 1：交易日判定

用 `mcp__westock-mcp__data_trade_calendar`（或 data_quote 返回的 time 字段）确认目标日为
A 股交易日。非交易日：静默结束，不产出、不推送。

### 步骤 2：数据采集（westock-mcp 唯一数据源）

| 数据 | 工具 | 必填字段 |
|------|------|---------|
| 六大指数行情 | `data_quote` codes=`sh000001,sz399001,sz399006,sh000300,sh000688,bj899050` | price, change_percent, amount, time |
| 涨跌分布 | `data_changedist` type=`hs` | upCount, downCount, upLimitCount, downLimitCount, totalAmount |
| 持仓个股/ETF | `data_quote` codes=parse_holdings.py 输出的代码清单 | 同上 |
| 板块资金 | `data_sector` / `data_fund_flow` | 主力净流入/流出 TOP 板块 |
| 外盘 | `data_quote` codes=`usIXIC,usNVDA`（SOX/HSTECH 无 MCP 覆盖时标注数据缺口） | change_percent |
| 估值 | `data_quote` 返回 pe_ratio / `data_macro` | pe_ratio |
| K线（动量/均线） | `data_kline` code=`sh000001` period=day limit=30 | close, amount |

采集完毕写入 `<任务目录>/<YYYY-MM-DD>/market_data.json`（schema 见
`templates/market_data.schema.json`）。**禁止创建 generate_today_*.py 之类日期脚本**——
LLM 直接写 JSON，历史日期脚本是脏数据源头。

### 步骤 3：信号评分（代码计算，LLM 禁止参与打分）

先用 Write 把采集结果落盘 `<任务目录>/<YYYY-MM-DD>/market_data.json`（schema 见
`templates/market_data.schema.json`；**禁止创建 generate_today_*.py 之类日期脚本**），然后：

```bash
python3 scripts/compute_signals.py <market_data.json路径> [--kline <sh000001 kline json>]
```

六个确定性信号（细则见 `references/signal-scoring.md`）：

| 信号 | 权重 | 输入 | 方向 |
|------|------|------|------|
| S1 量能 | 0.20 | 沪指量比 volume_ratio（同时段归一化） | 放量+缩量- |
| S2 宽度 | 0.20 | 上涨占比、涨停-跌停差 | 正 |
| S3 动量 | 0.15 | 上证 vs MA5/MA20、20日涨跌 | 正 |
| S4 分化 | 0.15 | 创业板+科创50 均值 - 沪深300 | 正 |
| S5 资金 | 0.15 | 板块主力净流入TOP1 - 净流出TOP1 | 正 |
| S6 估值 | 0.15 | 沪深300 PE + 60日涨跌代理 | 低估值正 |

Σ∈[-1,1]，评级：**Σ≥0.50 进攻 / 0.15~0.50 均衡 / -0.50~-0.15 防守 /
Σ≤-0.50 回避**；|Σ|<0.15 或有效权重<0.50 为"信号矛盾"（暂停主动买入；可挂低于现价
≥2%的吸买单；只列多空证据+明日待验证信号，禁止和稀泥式均衡）。
评级由代码输出，写入 market_data.json 的 `verdict` 字段。

### 步骤 4：持仓解析（唯一事实源）

```bash
python3 scripts/parse_holdings.py [--memory <MEMORY.md路径>] [-o holdings.json]
```

默认读取环境变量 `DECISION_ENGINE_MEMORY` 指定的持仓记忆文件（或 `--memory` 参数显式指定），
该文件按约定格式记录股票持仓、网格参数与基金持仓，
输出：股票持仓（代码/持仓/成本/市值）、网格参数（基准价/区间/步长/底仓/顶仓）、
基金持仓（代码/金额/收益/仓位）。解析失败 → 任务降级为"仅大盘研判，不含持仓诊断"，
禁止回退到写死数据。

### 步骤 5：硬校验（代码裁定，LLM 无权跳过；必须在 compute_signals 之后运行）

```bash
python3 scripts/validate_market_data.py <market_data.json路径> [--expect-date YYYY-MM-DD]
```

断言清单（任一失败 → rating=暂停，输出缺口清单）：

1. `indices[*].time == expect_date` 且 `amount > 0`
2. `|indices[*].change_percent| <= 10`（指数单日涨跌异常值）
3. `total_amount_yi`（指数成交额之和）与 `changedist.totalAmount/1e8` 偏差 < 2%
4. `upCount + downCount + flatCount` ∈ [4800, 5600]（全市场家数合理性）
5. 持仓行情全部命中（parse_holdings 清单中每只都有 price>0；holdings 为空时降级为
   "仅大盘研判"警告而非失败，见下降级链）
6. verdict 存在且由 compute_signals.py 合入（LLM 不得手填评级）

**有效权重封顶（v1.2）**：有效权重 < 0.50（过半信号缺失）时，无论 Σ 正负一律封顶为
"信号矛盾"，verdict 置 `data_insufficient=true`——禁止凭单一信号下方向性结论；
该档决策卡只列多空证据 + 数据缺口清单 + 明日待验证信号。

### 步骤 6：专家研判 + 对抗辩论（信息隔离）

需要深度研判时（股票复盘 15:05 / 总复盘 15:30 / 复杂情况），按
`references/expert-roundtable.md` 拉起专家团：

- **分析师层**（互不可见）：技术面 / 基本面 / 资金情绪 / 估值，各自只拿自己维度的数据
- **对抗层**：牛方研究员 vs 熊方研究员，强制对立举证，各至少 2 条可验证证据
- **裁决层**：CIO（组合经理）综合，输出结构化裁决 + 置信度（高/中/低）
- **信息隔离红线**：负责信号/技术的分析师禁止提前知道持仓盈亏（防禀赋效应），
  持仓诊断只在裁决后由 CIO 层注入
- 简单任务（股票助手 9:28、基金盘面 11:00）可不拉 full team，但必须完成步骤 5 的
  代码评级 + 决策卡

### 步骤 7：决策卡 + CI + 台账

**决策卡七件套**（每条研判缺一打回，格式见 `references/decision-card.md`）：

1. 四档方向（进攻/均衡/防守/回避，必须与 Σ 计算值一致，LLM 不得上调/下调）
2. 相对沪深300 的偏离幅度（百分点，代码计算）
3. 持有期（5-10 交易日，写明截止日期）
4. 触发条件（"若 X 验证则 Y"，X 限成交额/涨停家数/量能/两融/行业资金等读者可验证指标）
5. 失效条件（出现 Z 则撤销判断）
6. 赔率区间（同类信号历史前向收益分位，样本<20 显示"样本积累中"，LLM 禁止报赔率数字）
7. 数据日历 + 有效期（明日有什么数据、观点何时过期）

**CI 硬阻断**（任一不过 → 重写对应段落）：

1. 禁词扫描：`references/forbidden-words.md` 一级词 0 命中 + 双阈值联检
   （中性词密度 ≤1.5/千字 且 数值密度 ≥4/千字）
2. **硬编码数值扫描**：报告中出现的历史持仓收益数字（如"+¥1,046.86"）必须与当日
   parse_holdings.py 输出一致；出现模板脚本残留的写死数字 → 一票否决
3. **头/正文一致性**：报告头部状态标签必须与正文校验结论同向（禁"头部企稳/正文未企稳"）
4. 遮日期盲测（同市场状态配对相似度 ≤40%；方向与实际指数方向一致率 ≥60%）
5. 决策卡七件套完整性（失效条件强制非空）
6. 数据时点标注：每个关键数字带"来源+时点"
7. 合规：AI 标识 + 三层免责 + 无指令性动词裸奔（必须"条件→操作"框架）

**观点台账**（可追责、可结算）：

```bash
python3 scripts/settle_viewpoints.py --archive <任务目录> --today YYYY-MM-DD
```

- 每日决策卡的条件命题写入 `<任务目录>/<日期>/viewpoint.json`（append-only；
  每条含 eval_at 时点声明：close=收盘后评估。结算时若今日数据时点早于 eval_at，
  该条记 UNEVALUABLE，防止用盘中数据误触发收盘观点）
- 次日按 TRIGGERED / NOT_TRIGGERED / UNEVALUABLE / NEEDS_JUDGMENT（方向性观点）
  四态结算，条件触发即 HIT；昨日全中性/无实质观点且期间指数波动代理
  （|沪指|+|沪深300|）> 1.0pct → 追加 MISSED_NEUTRAL（漏报）记录
- 报告必须包含"昨日观点兑现"小节：命中/未触发/无法评估/漏报 + 命中率
- 滚动 20 日命中率 < 50% → 在报告头部标注"策略引擎校准中"，并对信号权重做人工审查提示

## 降级链

| 故障 | 处置 |
|------|------|
| MCP 数据部分失败 | rating=暂停 + 缺口清单（代码裁定，LLM 无权选择"带着缺口继续"） |
| MCP 全挂 | 只输出日期 + 昨日存档事实 + 任务状态 |
| 持仓解析失败 | 降级"仅大盘研判"，标注持仓缺口 |
| 专家团超时 | 跳过辩论走简化链（代码评级 + 决策卡仍必须完整） |
| 连续 2 日 rating=暂停 | 输出告警待人工审查 |

## 文件索引

| 用途 | 路径 |
|------|------|
| 市场数据 schema | `templates/market_data.schema.json` |
| 数据校验 | `scripts/validate_market_data.py` |
| 持仓解析 | `scripts/parse_holdings.py` |
| 信号评分 | `scripts/compute_signals.py` |
| 观点台账结算 | `scripts/settle_viewpoints.py` |
| 信号评分细则 | `references/signal-scoring.md` |
| 决策卡规范 | `references/decision-card.md` |
| 中性词禁令 | `references/forbidden-words.md` |
| 专家团协议 | `references/expert-roundtable.md` |
