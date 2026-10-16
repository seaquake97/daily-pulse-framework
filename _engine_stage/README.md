# daily-decision-engine

**数据驱动的每日投资研判引擎 · A deterministic decision engine for daily market research**

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero Dependency](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#)

> 把「模棱两可的每日研判」变成「可复算、可结算、可审计」的工程系统。
> Turn vague daily market commentary into a reproducible, settleable, auditable pipeline.

---

## 为什么做这个项目 / Why

大多数自动化的每日研报都有三个通病：**数据写死**（模板套话）、**结论骑墙**（中性词堆砌）、**无法证伪**（说对说错都无法结算）。本项目用工程手段解决这三个问题：

1. **确定性信号评分**——市场信号由代码计算（S1-S6），LLM 只负责解读，无权改分；
2. **硬校验门禁**——行情数据不满足断言（时间戳、成交额交叉验证、涨跌平合计）直接拒绝出报告；
3. **观点台账结算**——每条观点带条件与评估时点，次日由代码裁定 TRIGGERED / NOT_TRIGGERED / UNEVALUABLE / MISSED_NEUTRAL，让研判质量可被量化。

## 七步流水线 / Pipeline

```
交易日判定 → MCP 数据采集 → 信号评分(代码) → 持仓解析 → 硬校验(代码) → 专家辩论 → 决策卡 + 观点台账
Trading-day check → MCP fetch → Signal scoring → Holdings parse → Hard validation → Expert debate → Verdict card + Ledger
```

> ⚠️ **顺序铁律**：信号评分必须在硬校验**之前**运行——校验器强制要求 verdict 存在，顺序颠倒将直接失败（fail-closed 设计）。

## 六信号体系 / Signal System

| 信号 | 权重 | 度量 | Signal | Weight | Measures |
|---|---|---|---|---|---|
| S1 量能 | 0.20 | 指数量比（同时段归一化） | Volume | 0.20 | Volume ratio vs. same-period baseline |
| S2 宽度 | 0.20 | 上涨占比 + 涨跌停结构 | Breadth | 0.20 | Advance ratio + limit-up/down structure |
| S3 动量 | 0.15 | 价格/MA5、价格/MA20、20日涨跌 | Momentum | 0.15 | Price vs MA5/MA20, 20-day change |
| S4 分化 | 0.15 | 成长指数 vs 蓝筹指数价差 | Dispersion | 0.15 | Growth vs. blue-chip spread |
| S5 资金 | 0.15 | 主力净流入极值差 | Fund flow | 0.15 | Net inflow extremes |
| S6 估值 | 0.15 | 指数 PE + 60日回撤 | Valuation | 0.15 | Index PE + 60-day drawdown |

**Σ 综合分 → 五档评级 / Five-tier verdict**：进攻 / 均衡 / 信号矛盾 / 防守 / 回避。
当有效权重 < 0.50（过半信号缺失）时**强制封顶为「信号矛盾」**并标记数据不足——单一信号永远无权给出方向性评级。

## 快速开始 / Quick Start

```bash
git clone https://github.com/seaquake97/daily-decision-engine.git
cd daily-decision-engine

# 1. 准备持仓记忆文件（Markdown，按 SKILL.md 约定的表格格式记录持仓与网格参数）
export DECISION_ENGINE_MEMORY=/path/to/your/holdings-memory.md

# 2. 解析持仓（唯一事实源，代码动态解析，禁止写死）
python3 scripts/parse_holdings.py -o holdings.json

# 3. 信号评分（需准备 market_data.json，schema 见 templates/）
python3 scripts/compute_signals.py market_data.json --kline index_kline.json -o market_data.json

# 4. 硬校验（fail-closed：不满足断言即拒绝出报告）
python3 scripts/validate_market_data.py market_data.json --expect-date 2026-01-01

# 5. 观点台账结算（次日由代码裁定每条观点的命中情况）
python3 scripts/settle_viewpoints.py --archive ./archive --today 2026-01-02 --market-data market_data.json
```

零第三方依赖，纯 Python 标准库。

## 设计哲学 / Design Principles

- **代码裁定，LLM 解读**：所有分数、阈值、断言由确定性代码执行；LLM 只做证据组织与文字表达，且受中性词禁令约束（密度 ≤1.5/千字）。
- **Fail-closed**：数据缺失、字段不符、时点错配一律显式失败或降级披露，绝不静默兜底——静默兜底是「假数据」的第一来源。
- **可结算**：研判的质量不靠修辞，靠台账命中率说话。

## 目录结构 / Layout

```
├── SKILL.md                        # 引擎协议全文（七步流水线 + 铁律）
├── references/
│   ├── signal-scoring.md           # S1-S6 公式与数据缺口处置
│   ├── decision-card.md            # 决策卡规范与五档评级动作
│   ├── expert-roundtable.md        # 专家团对抗辩论规范
│   └── forbidden-words.md          # 中性词禁令与 CI 检查口径
├── scripts/
│   ├── parse_holdings.py           # 持仓动态解析（唯一事实源）
│   ├── compute_signals.py          # 信号评分 + 有效权重封顶
│   ├── validate_market_data.py     # 硬校验（断言清单）
│   └── settle_viewpoints.py        # 观点台账四态结算
└── templates/market_data.schema.json
```

## 免责声明 / Disclaimer

本项目为开源工程工具，输出内容基于公开数据与量化分析，**仅供参考，不构成投资建议**。市场有风险，投资需谨慎。使用本项目产生的任何决策与后果由使用者自行承担。

This project is an open-source engineering tool. Its outputs are generated from public data and quantitative analysis, **for reference only, not investment advice**.

## 许可 / License

代码：[MIT](LICENSE) · 文档：CC BY 4.0

---

由「老北京的热干面」维护 · Maintained by *Laobei Beijing Hot Dry Noodles* · 配套内容站：[daily-market-pulse](https://github.com/seaquake97/daily-market-pulse)
