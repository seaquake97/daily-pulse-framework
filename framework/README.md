# daily-pulse-framework

持仓驱动的每日研判内容流水线。从**一份配置**到 Markdown、站点 HTML、JSON feed 全链路产出。

框架只做三件事：**校验你的持仓配置 → 跑决策协议 → 渲染发布**。
你只需要维护自己的股票、网格参数和基金。

---

## 3 步出报告

### 第 1 步：填配置

```bash
git clone <framework-repo> && cd daily-pulse-framework
cp config/holdings.example.yaml holdings.yaml
$EDITOR holdings.yaml
```

只改三段：`holdings.stocks`、`holdings.grid`、`holdings.funds`。

```yaml
holdings:
  stocks:
    - code: "600919"      # 6 位数字即可，市场前缀会自动补全
      name: "示例银行"
      shares: 100
      cost: 1.696
      note: "底仓收息"
  grid:
    - code: "600312"
      name: "示例电气"
      enabled: true        # 不跑网格写 false
      base_price: 20.40
      range_low: 18.50     # MEMORY 的「18.50 - 24.50」拆成两列
      range_high: 24.50
      step_pct: 2.5        # 注意：不带 % 号
      per_trade: 100
      min_position: 300
      max_position: 1000
  funds:
    - code: "000979"
      name: "示例沪港深A"
      asset_class: fund    # gold = 实物/积存金
      amount: 15080.21
      plan: smart
```

完整字段说明见 `config/holdings.example.yaml` 内的逐条注释。

### 第 2 步：校验

```bash
python3 scripts/validate_config.py --config holdings.yaml --strict
```

```
[ok] 配置校验通过 holdings.yaml
     股票 4 只 / 网格 3 启用（共 4）/ 基金 3 只
     纯基金 24643.27 元 / 黄金 3907.41 元（两者口径独立，不相加）
```

**校验不过就不要往下跑。** 退出码：`0` 通过 / `1` 校验失败 / `2` 文件或语法错误。

### 第 3 步：跑流水线

配置 `daily-pulse-framework` 技能，让 agent 执行流水线。
也可以手动跑渲染与发布：

```bash
export PULSE_CONFIG="$PWD/holdings.yaml"
export PULSE_WORK_ROOT="$HOME/pulse-work"
export PULSE_CONTENT_REPO="$HOME/pulse-content"

# 任务产出的 md → 站点 HTML
python3 scripts/render_md.py \
  --md "$PULSE_WORK_ROOT/2026-01-02/daily-review.md" \
  --slug daily-review --date 2026-01-02 \
  --out "$PULSE_WORK_ROOT/2026-01-02/daily-review.html"

# 站点结构层（首页/日期页/归档/feed）
python3 scripts/build_site.py \
  --stage "$PULSE_CONTENT_REPO/_stage" \
  --base-url "https://<user>.github.io/<repo>/"

# 发布到内容仓
python3 scripts/publish_to_github.py \
  --date 2026-01-02 \
  --source-root "$PULSE_WORK_ROOT" \
  --stage "$PULSE_CONTENT_REPO/_stage" \
  --repo <content-repo> --owner <user> --push
```

---

## 环境要求

| 项 | 要求 |
|----|------|
| Python | 3.10+（实测 3.13） |
| 第三方依赖 | **零**。校验器只用标准库 |
| 行情数据 | 需连接 `westock-mcp` 连接器并完成授权 |
| GitHub | 发布需 `GH_TOKEN_FILE` 指向 token 文件 |

Python 版本可用 `python3 -V` 自查。框架不要求特定虚拟环境。

## 路径参数化

**禁止在任何脚本或定时任务里写死绝对路径。** 统一用环境变量：

| 变量 | 含义 | 必填 |
|------|------|------|
| `PULSE_CONFIG` | `holdings.yaml` 路径 | 是 |
| `PULSE_WORK_ROOT` | 产物工作根目录 | 是 |
| `PULSE_CONTENT_REPO` | 内容仓路径 | 是 |
| `DECISION_ENGINE_MEMORY` | 回退用 MEMORY.md（迁移期） | 否 |
| `GH_TOKEN_FILE` | GitHub token 文件 | 发布时 |

CLI 参数优先级高于环境变量。

## 配置 vs 框架 vs 产物

| 类别 | 内容 | 进公开仓？ |
|------|------|-----------|
| 框架 | 校验器、渲染器、流水线、协议、合规门禁 | 是（MIT） |
| 配置 | `holdings.yaml` | **否**——绝不要提交持仓到公开仓 |
| 产物 | md / html / json / feed.json | 进你自己的内容仓 |

## 常见问题

**Q：`grid: []` 和不写 `grid` 一样吗？**
不一样。不写会被判「缺少必填段」。无内容请显式写 `[]`。

**Q：代码要写 `sh600919` 还是 `600919`？**
写 `600919`，解析器按规则自动补前缀。显式写错前缀（如 `sz600919`）会直接报错。

**Q：ETF 和基金怎么填？**
ETF 当股票填 `stocks`（6 位代码，如 `563230`）；场外基金填 `funds`。

**Q：黄金怎么填？**
`asset_class: gold`，`code` 可省略。金额单独统计，不并入纯基金。

**Q：从 MEMORY.md 迁移过来会破坏现有流程吗？**
不会。`parse_holdings.py` 行为保持不变，MEMORY.md 仍是有效回退通道。
详见 `ARCH-R5-FRAMEWORK.md` §4。

**Q：校验器为什么自己实现 YAML 解析？**
PyYAML 不是标准库。要求「clone 完就能跑」，就不能依赖用户先装依赖。
代价是只支持 YAML 子集（不支持锚点/别名/块标量/流式集合），
遇到会明确报行号，不会静默猜错。

## 自测

```bash
python3 scripts/test_validate_config.py              # 29 例（配置层）
python3 engine/collect/test_market_data_contract.py  # 19 例（取数契约层）
python3 engine/report/test_report_contract.py        # 27 例（报告契约层）
python3 engine/test_run_pipeline.py                  # 17 例（三步编排）
python3 engine/signals/test_signals.py               # 24 例（引擎四脚本，A-09 迁入）
python3 engine/signals/test_technical.py             # 13 例（技术指标库）
```

当前合计 **6 套件 129 例全绿**。一键总门禁：`python3 scripts/ci_verify.py`。

## 环境变量（全部路径可覆盖，零硬编码）

| 变量 | 含义 | 默认 |
|------|------|------|
| `PULSE_WORKBUDDY_ROOT` | 工作区根（含各任务日期目录） | `$HOME/WorkBuddy`（由 paths.py 推导，不写死用户名） |
| `PULSE_SITE_ROOT` | 站点根（含 `scripts/publish_to_github.py`） | framework 的上一级 |
| `PULSE_ENGINE_SCRIPTS` | 引擎脚本目录 | `~/.workbuddy/skills/daily-decision-engine/scripts` |
| `PULSE_PYTHON` | Python 解释器 | `sys.executable` |

## 采集三步的实际状态（2026-10-16）

| 步骤 | 状态 | 说明 |
|------|------|------|
| **采集** | 契约层已工程化 | MCP 调用与组装由 agent 执行；本仓提供**校验器**（基于 22 份真实产物统计的 schema）与**确定性规范化器** |
| **生成** | 契约层已工程化 | 报告撰写由 agent 执行；本仓提供**章节契约**与一致性校验（评级/Σ 必须与 market_data 一致） |
| **发布** | 已工程化 | `publish_to_github.py` 承担渲染→消毒→加框→构建→推送 |

**取舍说明**：把可确定性部分（校验/规范化/评分/发布）脚本化，把需要判断的部分
（MCP 调用/研判撰写）留给 agent 并用契约守住输出质量。硬把研判撰写脚本化只会
得到一个巨大的 if-evaluate。

## 代码结构

```
engine/
  signals/
    compute_signals.py       步骤5：S1-S6 信号评分与四档评级（代码计算，LLM 禁改）
    validate_market_data.py  步骤3：market_data.json 硬校验
    settle_viewpoints.py     步骤7：观点台账四态结算
    parse_holdings.py        步骤4：MEMORY.md 持仓解析（full_code 委托 codes.py，A-10）
    technical.py             个股技术指标库（MA/BIAS/Wilder RSI/MACD）
    test_signals.py          引擎四脚本回归（24 例）
    test_technical.py        技术指标库单测（13 例）
  collect/ report/ run_pipeline.py   取数 / 报告 / 三步编排
scripts/
  paths.py          路径唯一入口（所有 PULSE_* 环境变量在此定义一次）
  yaml_min.py       YAML 子集解析（无内部依赖）
  codes.py          证券代码规范化（前缀推断单一实现，parse_holdings 与之对齐）
  rules.py          校验规则集  -> codes
  validate_config.py  CLI 门面      -> codes / rules / yaml_min
  test_validate_config.py
```

依赖图无环，每层均 ≤300 行。若要修改市场前缀规则，**只改 `codes.py`**——
`parse_holdings.py` 的 `full_code()` 已委托 `normalize_code()`（A-10 收敛），
不再有第二份可漂移的实现。

引擎四脚本与 `daily-decision-engine` 仓的归属与同步方向，见
`engine/signals/README.md` 的单一事实源声明。

## 许可

MIT，见 `LICENSE`。

免责：本框架是内容生产工具，不构成投资建议。产出内容的合规校验责任在使用者。
