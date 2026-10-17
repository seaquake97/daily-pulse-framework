# COLLECTION.md — 五任务采集清单（GAP-A1 落地件）

> 用途：把「每次该调哪些 MCP 工具、抓哪些字段、什么单位、缺了怎么降级」
> 从任务书自然语言固化为可执行清单。**LLM 只负责调 MCP 与落原始响应，
> 不再手写 market_data.json**（那正是此前不可审计的根源）。

## 采集三段式（新的标准动作）

```
① MCP 采集   → 原始响应落盘 <任务目录>/<日期>/mcp_raw.json
② 脚本组装   → python3 assemble_market_data.py（按 schema 组装 + 校验）
③ 信号评分   → python3 compute_signals.py → validate_market_data.py
```

**为什么必须落原始响应**：只有原始响应可审计、可重放、可 diff。
组装是纯函数——同一份 mcp_raw.json 永远产出同一份 market_data.json，
这让「今天的取数是否有异常」变成可回放的问题，而不是不可复现的灵光一现。

---

## 各任务采集清单

### 9:28 股票助手（data_stage: pre_open）
| MCP 工具 | 采集内容 | 落到 market_data | 单位/注意 |
|----------|---------|----------------|-----------|
| `data_quote` 批量 | 6 大指数 + 持仓 9 只 | `indices` / `holdings` | 交易所代码前缀须规范化（sz563230 实为 sh563230） |
| `data_changedist` | 涨跌家数 | `market_breadth` | 记录 `scope`（含北交所/仅A股），不同口径 Σ 不可比 |
| `data_sector` | 板块涨跌排名 + 主力资金 | `sector_ranking` / `sector_flows` | `sector_ranking.gainers/losers[{sector,name,chg_pct}]` |
| `data_kline` | 沪指日K | `kline` | **升序**，须剔除当日行 |

降级：连接器未连接 → 必须写 `data_gaps`，且下游禁出可执行动作。

### 11:00 基金盘面（data_stage: intraday）
同 9:28 全部项，另加：
- 基金持仓穿透（持仓集中度）→ 报告层消费，不进 market_data
- **实测缺陷**：本任务曾漏写 `data_stage`，导致发布层需兜底。组装器已强制。

### 14:30 基金操作指引（data_stage: intraday）
**必须重新采集**，禁止复用 11:00 数据或 `/tmp` 缓存（该缓存已被明令禁用）。
采集项同 11:00。

### 15:05 股票复盘（data_stage: close）
- 全部指数 + 持仓 + 板块 + 沪指日K（收盘定格）
- 外盘：usIXIC / usNVDA → `foreign`

### 15:30 每日总复盘（data_stage: close）
- 同 15:05，另加 `settle_viewpoints.py` 结算昨日观点台账（eval_at 时点须对齐）

---

## 单位与口径契约（错单位 = 静默失败）

| 字段 | 单位 | 换算点 |
|------|------|--------|
| `amount` | **元**（原始） | 不换算 |
| `total_amount_yi` | **亿元** | `(sh000001.amount + sz399001.amount + bj899050.amount) / 1e8` |
| `change_percent` | **%**（带符号，如 `+1.07`） | 禁止写 `0.0107` |
| `sigma` / `signals` | 无量纲（-1 ~ +1） | 由 compute_signals 计算，**禁止手填** |
| `volume_ratio` | 倍（同时段归一） | 禁止用「半日成交额 / 全日均值」 |

## 缺口处理纪律（不可协商）

1. **拿不到就声明，不填 0**：`data_gaps` 追加说明，字段留 null/缺失。
2. **补零是 P0 事故**：站点会把「没数据」显示成「评分为零」（曾真实发生）。
3. **降级轮不出动作**：`data_gaps` 非空时，结论层强制输出
   「数据源降级 · 本轮结论不适用」，标准动作只在正文给。
4. **ETF 代码异常**须记录映射（历史：`sz563230` → `sh563230` 已在
   `data_gaps` 中留痕，属正确做法）。

## 强制自检（每次采集后必跑）

```bash
PY=/Users/lianghaizhen/.workbuddy/binaries/python/envs/default/bin/python3
COLLECT=<framework>/engine/collect

# 1) 组装 + 规范化 + 校验（一条命令）
$PY $COLLECT/normalize_market_data.py --in <任务目录>/<日期>/market_data.json \
    --task fund-market --write

# 2) 独立复核（必须 exit 0）
$PY $COLLECT/check_market_data.py --dir <任务目录>/<日期>

# 3) 信号评分与硬校验（顺序不可颠倒）
$PY <engine>/compute_signals.py <任务目录>/<日期>/market_data.json \
    --kline <任务目录>/<日期>/sh000001_kline.json
$PY <engine>/validate_market_data.py <任务目录>/<日期>/market_data.json \
    --expect-date <今日>
```

**顺序铁律**：先 compute_signals 后 validate_market_data —— validator 强制
verdict 存在，顺序颠倒必挂（已多次实证）。

## 禁用清单（历史教训）

| 禁用 | 原因 |
|------|------|
| `generate_today_*.py` / `generate_YYYYMMDD_*.py` | 日期写死，不可复现；历史遗留已死 |
| `/tmp/market_data_cache.json` | 会被系统清理，数据新鲜度不可控 |
| `fetch_data.py`（新浪 HTTP）/ 14:30 同名脚本（东财 HTTP） | 违反 MCP 直采铁律；已归档至 `_legacy_http/` |
| LLM 手写 market_data.json | 字段漂移（已实证 chg_pct 双写法），改为脚本组装 |
| 关闭 SSL 校验抓金融数据 | 中间人风险 + 数据不可信 |
| HTTP 直抓当**主链路** | 违反 MCP 直采铁律；历史 `fetch_data.py`（新浪）/ 14:30 东财脚本已归档 `_legacy_http/` |

> 例外：HTTP 直抓在**MCP 不可达作为降级源**时允许，见下节，且必须留降级痕迹。

---

## 备用抓取器 fallback_fetcher（仅限降级，非主链路）

2026-10-16 落地，解决「MCP 挂了就只拿到空快照 / 旧数据」的缺口。它不是上表禁用脚本的复活：
主链路仍是 MCP 直采，本模块**只在 MCP 不可达时**被调用，把「取不到数据」改成带证据的降级事件。

- 文件：`framework/engine/collect/fallback_fetcher.py`（编排 + CLI，163 行）、
  `quote_sources.py`（腾讯/新浪 GBK 方言解析，254 行），均为纯标准库零依赖
- 用法：`python3 fallback_fetcher.py --json` ／ `--code sh000001` ／ `--codes sh000001,sh000688`
- 退出码：0 成功｜2 全部源失败｜3 参数错误（部分缺失仍 0，消费方须检查 `missing`）
- 单位口径与本文一致：`amount` 元、`change_percent` %（带符号）、`volume` 手
- 容错：腾讯主 → 新浪备；单源连续失败 3 次熔断、冷却 300s；脏数据（现价<=0、
  \|涨跌幅\|>20%、源返回空记录）直接丢弃并告警；全部源失败抛 AllSourcesFailed（不静默返回空）
- **降级纪律**：即便备用源取到数据，也必须照常写 `data_gaps` 声明「本轮走备用源」，
  下游按「降级轮不出动作」执行；不声明 = 把降级数据冒充 MCP 数据，属 P0
- 测试：`python3 test_fallback_fetcher.py` 纯离线；联网用例仅在 `PULSE_NET_TEST=1` 时运行
