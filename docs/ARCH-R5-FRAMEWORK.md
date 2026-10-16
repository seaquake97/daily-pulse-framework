# ARCH-R5：一键复用框架资产化

> 状态：Draft 待评审
> 版本：1.0.0
> 前置事实核对：本文明所有「现状」描述基于对
> `.workbuddy/skills/daily-decision-engine/` 与
> `WorkBuddy/2026-10-14-10-29-45/github-ip-plan/` 的实际代码清点，非转述。

---

## 0. 事实核对：与初始假设不符的三处

架构不能建在错误事实上。以下三点与立项时的描述不一致，已逐一核实：

| # | 初始描述 | 实际情况 | 影响 |
|---|---------|---------|------|
| 1 | 引擎有 7 个脚本：`compute_signals / validate_market_data / parse_holdings / settle_viewpoints / fetch_data / generate_report / fill_and_publish` | **只有 4 个**：`compute_signals.py` `parse_holdings.py` `settle_viewpoints.py` `validate_market_data.py`。`fetch_data.py` `generate_report.py` `fill_and_publish.py` 在 skills 与站点目录下**均不存在** | 重大。「数据采集」「生成报告」「填充发布」三个环节目前是 **agent 在定时任务里用自然语言执行的**，不是代码。框架化时必须承认这个事实：这三步要么补成脚本，要么明确标为「LLM 步骤」 |
| 2 | 站点有「10 套测试」 | 实测 `scripts/test_*.py` 共 **10 个文件**，但 `test_real_outputs.py` / `test_sanitize_gate_visual.py` / `test_frame_fixed_point.py` 依赖 `BASE = Path("/Users/lianghaizhen/WorkBuddy")` 的**当日实际产物**，换机器必失败 | 迁移时必须区分「纯单元测试」与「依赖本机 fixture 的集成测试」，后者要么参数化要么降级为可选 |
| 3 | `config/` 目录已存在 | 存在但**是空目录**（0 文件） | 无影响，但说明「配置层」此前从未落地，本设计是首次实现 |

另有一处需修正的表述：`parse_holdings.py` **已经支持环境变量**
`DECISION_ENGINE_MEMORY`（第 18-24 行），只是默认值硬编码。这是好消息——
参数化改造的起点已经存在，不必从零做。

---

## 1. 资产边界（三分法，穷举）

这是整个 R5 的地基。判断标准只有一条：**换一个人接手，还需要改代码吗？**

### 1.1 框架资产（复用别人的，随 skill 分发，MIT）

| 类别 | 具体文件 | 数量 | 依赖 |
|------|---------|------|------|
| 决策协议 | `SKILL.md` + `references/{signal-scoring,decision-card,forbidden-words,expert-roundtable}.md` + `templates/market_data.schema.json` | 6 | 纯文档 |
| 决策脚本 | `compute_signals.py` `validate_market_data.py` `settle_viewpoints.py` | 3 | 纯标准库 |
| 配置层（新增） | `config/schema.json` `config/holdings.example.yaml` `scripts/validate_config.py` `scripts/{yaml_min,rules,codes}.py` `scripts/test_validate_config.py` | 7 | 纯标准库 |
| 渲染层 | `render_md.py` + `md_render/{__init__,blocks,document,inline,meta}.py` | 5 | 纯标准库 |
| 脱敏层 | `sanitizer/{__init__,core,emoji_inline,emoji_map,freshness,gradient_pass,heading_pass,html_utils,icon_pass,report,script_pass,style_pass,token_map,token_pass}.py` | 15 | 纯标准库 |
| 站点结构层 | `build_site.py` `site_pages.py` `site_render.py` `site_content.py` `site_theme.py` `site_blocks.css` `site_components.css` `content_contract.py` `content_dictionary.py` | 9 | 纯标准库 |
| 详情页框架 | `frame_pass.py` `detail-frame.css` | 2 | 纯标准库 |
| 设计 Token | `design-tokens.json`（10 组：primitive/semantic/typography/space/radius/shape/shadow/layout/meta）→ 生成 `design-tokens.css` | 2 | 纯标准库 |
| 静态页 | `site/methodology/index.html` | 1 | 占位符注入 |
| 校验工具 | `sanitize_body.py` `scan_compliance.py` `probe_responsive.py` `probe_layout.py` `build_body_css.py` | 5 | 纯标准库 |
| 发布器 | `publish_to_github.py` `push_repo.py` | 2 | git + gh |
| 骨架文档 | 本文档 + R6 文档 + ADR | 4 | — |

**合计约 62 个文件进入框架仓。**

配置层已按单一职责拆为四层，依赖图无环（每层均 ≤300 行）：

```
yaml_min.py   YAML 子集解析        无内部依赖
codes.py      证券代码规范化        无内部依赖（与 parse_holdings.py 对齐）
rules.py      校验规则集           -> codes
validate_config.py  CLI 门面       -> codes / rules / yaml_min
```

拆分的必要性不是洁癖：`normalize_code()` 被 CLI 摘要与校验规则共同依赖，
放在任一方都会让另一方反向导入。实测踩过一次循环导入，
导致整个测试套件 `ImportError`——29 个用例全部无法执行。

### 1.2 用户配置（每人自己填，不进公开仓）

| 文件 | 内容 | 分发方式 |
|------|------|---------|
| `holdings.yaml` | `version` / `profile` / `market_data` / `holdings.{stocks,grid,funds}` / `snapshot` | 本地文件或私有仓 |
| `.env` 或 shell profile | 5 个环境变量（见 §7.1） | 本地 |
| GitHub token | 发布凭证 | `GH_TOKEN_FILE` 指向的文件，权限最小化 |

**`holdings.yaml` 是本框架唯一的新增「用户输入面」。** 其他一切都是框架或产物。

### 1.3 用户产物（用户自己的输出，进内容仓）

| 产物 | 生成者 | 去向 |
|------|--------|------|
| `market_data.json` | agent 采集 + 人工/agent 写入 | 工作区，可选归档 |
| `holdings.json` | `parse_holdings.py` 或 `validate_config.py --export` | 工作区 |
| `viewpoint.json` | 步骤 7 写入，append-only | 工作区，**必须留档**（观点台账的可追责性依赖它） |
| `*.md` | agent 产出 | 工作区 → 渲染输入 |
| `*.html` | `render_md.py` | `_stage/docs/daily/<date>/` |
| `_stage/docs/**` | `build_site.py` | 中间态 |
| `index.html` / `feed.xml` / `rss.xml` / `sitemap.xml` / `subscribe/` / `weekly/` / `monthly/` | `build_site.py` | 内容仓 GitHub Pages |
| `api/feed.json` | 新增（见 R6 §3） | 内容仓，供小程序消费 |

---

## 2. 配置契约

### 2.1 为什么必须换掉 MEMORY.md

MEMORY.md 三表能跑，但作为「可复用框架的配置契约」有四个硬伤：

1. **按列位置解析**——`parse_holdings.py:96` 是 `code = full_code(r[1])`。用户调整列顺序（哪怕只调整一次）就静默错位：可能把「成本」当「代码」解析，且**不报错**。
2. **无法表达类型**——`2.5%` 与 `2.5` 都是字符串；`+638.12%` 与 `638.12` 语义不同但都要靠 `to_float` 剥壳；价格区间只能存 `"18.50 - 24.50"` 这种需二次正则拆分的字符串。
3. **人和框架混在一处**——MEMORY.md 同时装着个人画像、移民调研、协作铁律、品牌署名。别人 clone 框架仓不可能、也不应该拿到这些。
4. **不可校验**——没有任何东西能告诉用户「你的最小底仓大于最大顶仓」。

### 2.2 三段映射（与 MEMORY.md 逐列对齐）

| MEMORY.md 表 | 配置段 | 列 → 字段 | 不进配置的原因 |
|--------------|--------|-----------|--------------|
| 股票持仓 | `holdings.stocks` | 标的→`name` 代码→`code` 持仓→`shares` 可用→`available` 成本→`cost` 状态/方向→`note` | 现价/市值/盈亏额/盈亏率/当日盈亏**全部不填**——它们是取数实时计算的变量，写进配置必然过期 |
| 网格交易参数 | `holdings.grid` | 标的→`name` 证券代码→`code` 基准价→`base_price` **区间拆两列**→`range_low`+`range_high` 步长→`step_pct`（去 %） 单笔→`per_trade` 最小底仓→`min_position` 最大顶仓→`max_position` 指引→`guide` | **委托档位不填**——纯券商 UI 概念（卖二买二），与计算无关 |
| 基金持仓 | `holdings.funds` | 标的→`name` 代码→`code` 金额→`amount` 备注→`note` 在途→`plan`（枚举化） | 持有收益/昨日收益/占纯基金比**不填**——属于 `snapshot`，每日刷新 |

三处关键设计决策：

- **非网格标的用 `enabled: false`，不从数组删除。** MEMORY.md 里江苏银行/中国广核/上海金三行是区间/步长均为 `-` 的底仓形态。删掉就丢了底仓上下限的留档。
- **`step_pct` 存 `2.5` 而非 `2.5%`。** 百分号是展示层的事，配置层存纯数值。
- **`asset_class: gold` 显式化。** MEMORY.md 里黄金靠「代码列为 `-` 且名称含黄金」被启发式识别成 `GOLD`——这是隐式契约，配置里必须显式声明。

### 2.3 校验规则清单

完整 schema 见 `framework/config/schema.json`，实现见 `framework/scripts/validate_config.py`（29 个测试用例）。

**硬错误（阻断流水线，退出码 1）**

| 规则 | 位置 | 理由 |
|------|------|------|
| `version` 缺失或不等于 1 | `version` | 契约版本必须显式声明 |
| 未知顶层键 | 根 | 防拼写错误静默生效 |
| `base_currency != CNY` | `profile` | 当前只支持 CNY |
| `market_data.source != westock-mcp` | `market_data` | 框架铁律：行情只走 MCP |
| 股票/基金/网格段缺失 | `holdings.*` | 缺失与「空」语义不同，必须显式 `[]` |
| 股票缺 `code`/`name`/`shares`/`cost` | `holdings.stocks[]` | 事实源最小集 |
| 股票代码重复 | `holdings.stocks[]` | 同一标的只能一行 |
| 市场前缀与代码段冲突 | `holdings.*.code` | 如 `sz600919`——写错前缀会让行情请求打空 |
| `available > shares` | `holdings.stocks[]` | 可用不可能多于持仓 |
| 启用网格但缺区间/基准价/步长 | `holdings.grid[]` | 缺参数无法算触发价 |
| `range_low >= range_high` | `holdings.grid[]` | 区间反了 |
| `min_position > max_position` | `holdings.grid[]` | 底仓大于顶仓 |
| `asset_class=fund` 但缺 code | `holdings.funds[]` | 基金必须有 6 位代码 |
| `asset_class` 非 fund/gold | `holdings.funds[]` | 枚举封闭 |
| `plan` 非法枚举值 | `holdings.funds[]` | 同上 |
| 重复键 / Tab 缩进 / 不支持语法 | 解析期 | 带行号报错，退出码 2 |

**软警告（`--strict` 下也失败）**

| 规则 | 理由 |
|------|------|
| `shares == 0` | 已清仓应删除，否则白占行情请求配额 |
| `base_price` 不在区间内 | 参数未校准 |
| `min_position` 超过实际持仓 | 网格会立即停卖 |
| `enabled=false` 却仍设了区间 | 大概率漏改 `enabled` |
| 股票与基金全空 | 会降级为「仅大盘研判」 |

### 2.4 YAML 子集限制（重要，必须让用户知道）

`validate_config.py` **自带** YAML 解析器，因为 PyYAML 不是标准库，而框架的硬要求是
「别人 clone 完就能跑」。

| 支持 | 不支持（明确报错并给行号） |
|------|---------------------------|
| 块状映射 / 块状序列 / 缩进嵌套 | 锚点 `&`、别名 `*`、标签 `!!` |
| `#` 行内与行尾注释 | 多文档 `---`、文档结束符 `...` |
| 单双引号字符串 | 块标量 `|` `>` |
| int / float / bool / null | 非空流式集合 `[]` `{}`（空 `[]` 支持） |
| `- key: value` 序列项内联首键 | 复杂键 `?` |

**这是有意的取舍**：配置契约只需表达三段持仓结构，不值得为动态特性引入
「写法正确但解析结果不符预期」的风险面。遇到不支持的语法时脚本**显式报行号**，
不猜、不静默降级。

---

## 3. 仓库分工

### 3.1 两个仓库

| | `daily-pulse-framework` | 用户内容仓（如 `daily-market-pulse`） |
|---|---|---|
| 许可 | MIT | 私有（内容是个人持仓研判） |
| 内容 | 框架资产 62 个文件 + skill | 产物：HTML / feed.json / RSS |
| 谁维护 | 框架维护者（可多人） | 用户自己 |
| 敏感度 | 公开可读 | **含个人持仓，必须私有或至少不公开索引** |

### 3.2 依赖方向（单向，不可逆）

```
用户配置(holdings.yaml) ──┐
                          ├──> 框架资产 ──> 产物 ──> 用户内容仓
westock-mcp(行情) ────────┘                     │
                                                └──> (R6) 小程序只读消费
```

硬规则：

1. **框架仓永不引用用户仓路径**——框架不认识任何具体用户。
2. **内容仓不含任何框架代码**——它是纯产物，重建成本低（跑一次流水线即可）。
3. 框架 → 产物的编译发生在用户机器上，不发生在 GitHub CI（避免把持仓传到第三方）。

### 3.3 版本策略

| 对象 | 版本位 | 变更影响 |
|------|--------|---------|
| 框架仓 | 语义化版本 | `MAJOR` = 配置契约不兼容；`MINOR` = 新增可选字段；`PATCH` = 修 bug |
| `holdings.yaml` | `version` 字段（当前 `1`） | 校验器按此决定规则集；不匹配直接报错而非猜测 |
| 决策协议 | `daily-decision-engine` 自带 `version`（当前 1.0.0，SKILL.md 内文提及 v1.3 顺序铁律） | 两者**独立版本**，框架不锁死协议版本，只声明依赖范围 |

**破坏性变更清单**（改动任一项即为 MAJOR，必须提供迁移脚本）：

1. `holdings.yaml` 删除或改名任何 required 字段
2. 改变代码市场前缀推断规则（会让存量配置的行情请求打空）
3. 改变 `fund`/`gold` 的金额统计口径（影响站点展示的历史可比性）
4. 改变 `plan` 枚举值（下游按枚举渲染）
5. `snapshot` 从可选变必填
6. 移除 `--memory` 回退通道

---

## 4. 迁移路径与回退（不能破坏现有生产链）

### 4.1 为什么绝不能直接改 `parse_holdings.py`

它被 **6 个生产定时任务**依赖，且按列位置解析 MEMORY.md。
一旦改动，「当天出报告」这条链就存在风险，而用户每天 09:28/11:00/14:30/15:05/15:30
都要出内容。**迁移必须是加法。**

### 4.2 三阶段双轨

| 阶段 | 事实源 | 动作 | 回滚方式 |
|------|--------|------|---------|
| **A 并行期**（默认，现状） | MEMORY.md | 不动任何生产文件 | 无需回滚 |
| **B 切换期** | MEMORY.md 仍为事实源 | 新增 `holdings.yaml` 并跑通校验；新增 `parse_holdings.py --config` 只读分支（默认仍走 `--memory`） | 删除 yaml 即可，行为零变化 |
| **C 目标态** | `holdings.yaml` | 定时任务改传 `--config`；`parse_holdings.py` 保留为迁移工具 | 把 `--config` 换回 `--memory` |

### 4.3 `parse_holdings.py` 的改造边界（阶段 B/C）

只允许**新增**，不允许修改现有逻辑：

```python
# 允许新增：不改任何既有函数签名与行为
ap.add_argument("--config", default=None, help="YAML 配置路径（阶段 B 起可选）")
ap.add_argument("--export", default=None, help="导出标准化 JSON")

# 禁止改动：
#   - _default_memory_path() 的环境变量读取（已是好的）
#   - parse_stocks/parse_grid/parse_funds 的列位置逻辑
#   - classify_table 的表头匹配
#   - full_code 的前缀规则
```

**共用逻辑必须提取**：`normalize_code()` / `market_of()` 现在同时存在于
`parse_holdings.py` 与 `validate_config.py`。阶段 B 必须抽成共享模块并加一致性测试，
否则两边规则漂移（配置校验说 ok、实际解析打空）是必然的。

---

## 5. Skill 化

### 5.1 继承而非替代

`daily-pulse-framework` **继承** `daily-decision-engine`：

```
daily-pulse-framework（新）
  ├── 继承全部：七步流水线、决策卡七件套、观点台账、
  │            禁词与合规门禁、AI 标识、三层免责、数据硬校验
  └── 新增：步骤 0 配置校验 + 步骤 8/9/10 渲染发布 + 配置契约
```

三条硬规则：

1. 加载新 skill 时**必须同时加载** `daily-decision-engine`，跳过即放弃全部决策协议。
2. 新 skill **不改写**任何引擎铁律；冲突时以引擎为准并上报，不自行裁决。
3. 决策逻辑**不迁入**框架仓——它留在 `daily-decision-engine`，避免协议分叉。

### 5.2 流水线扩展

```
步骤 0 校验配置（新增，硬阻断）
→ 步骤 1-7 决策引擎七步（原样继承，含「先 compute_signals 后 validate」顺序铁律）
→ 步骤 8 渲染 md → 步骤 9 渲染站点 → 步骤 10 发布 + feed.json（新增）
```

### 5.3 SKILL.md 结构

已落盘 `framework/skills/daily-pulse-framework/SKILL.md`，含 8 节：
定位与继承关系 / 资产边界三分法 / 配置契约 / 事实源双轨 / 路径参数化 /
执行流水线 / 降级链 / 合规门禁 / 文件索引。

---

## 6. 一键复用流程（新用户从 0 到出报告）

| 步 | 操作 | 预计耗时 | 验证点 |
|----|------|---------|--------|
| 1 | `git clone` 框架仓 | 1 min | 目录含 `config/ scripts/ skills/ README.md LICENSE` |
| 2 | `cp config/holdings.example.yaml holdings.yaml` | 10 s | 文件存在 |
| 3 | 填三段持仓 | 10-20 min | 股票/基金 code 各 6 位；网格 `step_pct` 不带 % |
| 4 | `python3 scripts/validate_config.py --config holdings.yaml --strict` | 5 s | **退出码 0**；非 0 必须先修 |
| 5 | 连 `westock-mcp` 连接器并授权 | 2-5 min | 能取到 `sh000001` 行情 |
| 6 | 配 5 个环境变量 | 5 min | `PULSE_CONFIG` 等非空 |
| 7 | 装 `daily-decision-engine` skill | 1 min | skill 可被加载 |
| 8 | 建内容仓（**私有**） | 3 min | `gh repo create <name> --private` |
| 9 | 配 `GH_TOKEN_FILE` | 2 min | token 文件权限 600 |
| 10 | 跑一次完整流水线 | 10-15 min | 产出 md + html + `feed.json` |
| 11 | 配 Pages | 3 min | `https://<user>.github.io/<repo>/` 可访问 |
| 12 | 挂定时任务 | 10 min | 对齐 `automation_update`，且**必须同步**（MEMORY.md 纪律） |

**总计约 50-90 分钟**，其中填配置占一半。真正难的不是配置，是第 5 步和第 12 步。

**首次跑通的验收标准**（缺一不可）：

1. `validate_config.py --strict` 退出码 0
2. `holdings.json` 的股票数/基金数与配置一致（不是 0，也不是写死值）
3. 报告中出现的持仓数字与 `holdings.json` **逐一可对账**（CI 硬阻断第 2 条）
4. 产出 md / html / `feed.json` 三个文件齐全
5. 页面顶部有 AI 标识，底部有三层免责

---

## 7. 风险登记

### 7.1 路径硬编码（17 处，全部需参数化）

实测站点 `scripts/` 下 17 处硬编码，其中 14 处为 `/Users/lianghaizhen/...`。

| 类别 | 文件:行 | 目标 | 参数化方案 |
|------|---------|------|-----------|
| 发布根 | `publish_to_github.py:76` | `Path("/Users/lianghaizhen/WorkBuddy")` | `--source-root` 已有默认值 → 改环境变量 `PULSE_WORK_ROOT` |
| Python 解释器 | `publish_to_github.py:78` | `.../binaries/python/envs/default/bin/python3` | **必须删**。改为 `sys.executable`，框架不假设 WorkBuddy 内置 Python 存在 |
| 测试 fixture | `test_real_outputs.py:21` `test_content_contract.py:21` `test_render_md.py:22` `test_sanitize_pipeline.py:36` `test_frame_fixed_point.py:35` `test_sanitize_gate_visual.py:34` | 本机当日产物 | 加 `--fixtures` 参数，默认跳过（`skipUnless`），区分单元测试与集成测试 |
| 强制 chdir | `scan_compliance.py:24` | `os.chdir('/Users/.../github-ip-plan')` | **必须删**。改用 `Path(__file__).resolve().parent.parent` |
| push 根 | `push_repo.py:33` | `Path("/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45")` | `--work-root` / `PULSE_WORK_ROOT` |
| body css 源 | `build_body_css.py:40` | 同上绝对路径 | `Path(__file__).resolve().parent.parent` |
| 记忆文件 | `parse_holdings.py:23` | MEMORY.md 绝对路径 | **已有** `DECISION_ENGINE_MEMORY` 环境变量，仅默认值需删 |

**唯一已存在的环境变量**是 `GH_IP_TOKEN_FILE`（`publish_to_github.py`）与
`DECISION_ENGINE_MEMORY`（`parse_holdings.py`）。其余 15 处都是硬编码。

框架统一环境变量表（已在 SKILL.md §4 与 README 定义）：

```
PULSE_CONFIG           # holdings.yaml
PULSE_WORK_ROOT        # 产物根
PULSE_CONTENT_REPO     # 内容仓
DECISION_ENGINE_MEMORY # 迁移期回退
GH_TOKEN_FILE          # GitHub token
```

### 7.2 上游数据源依赖

| 风险 | 等级 | 现状 | 缓解 |
|------|------|------|------|
| `westock-mcp` 连接器未授权 | **高** | `entries.json` 2026-10-16 的 `stock-assistant` 明确记录「当前未连接腾讯自选股连接器（westock-mcp）…已降级」 | 降级链已定义但**必须显式告警**，不得静默用替代源 |
| 单点依赖，无备用源 | 高 | 铁律禁止 HTTP API 替代 | 交叉验证源只能标注「交叉源」，且需 `market_data.allow_cross_source: true` 显式开启 |
| 采集/报告/发布三步无代码 | **高** | §0 第 1 条 | 阶段 B 前，这三步是 agent 自然语言行为，**不可复现、不可审计**。补成脚本是框架化的最大工程债 |
| 基金估值接口返回 0 | 中 | 已在 SKILL.md 铁律 2 规定降级 | 保持 |

### 7.3 Python 环境

| 风险 | 等级 | 说明 |
|------|------|------|
| 版本下限 | 中 | 实测 3.13.12，未验证 3.9/3.10。建议在 README 声明 3.10+，理由：`X \| Y` 联合类型语法、`dataclasses`、`from __future__ import annotations` |
| 解释器路径绑定 WorkBuddy | **高** | `publish_to_github.py:78` 写死了 WorkBuddy 内置 Python 路径。**第三方机器上不存在该路径，发布必然失败** |
| PyYAML | 中 | 本机有 6.0.3，但非标准库。框架选择自带子集解析器（§2.4） |
| 第三方依赖 | 低 | 站点与引擎脚本实测纯标准库 |

### 7.4 其他

| 风险 | 等级 | 说明 |
|------|------|------|
| 规则漂移 | **高** | `normalize_code()` 现存两份（`parse_holdings.py:44` 与 `validate_config.py`）。必须抽共享模块 + 一致性测试 |
| 内容仓公开泄露持仓 | **高** | 内容站含个人持仓研判。仓必须私有；GitHub Pages 需注意搜索引擎收录 |
| 迁移期双源漂移 | 中 | 阶段 B/C 两份配置并存，必须约定 MEMORY.md 为准还是 yaml 为准，否则出报告用错持仓 |
| 时区与交易日历 | 中 | `meta.json` 用「当期数据日期」而非运行时刻以保幂等——此设计必须保留 |

---

## 8. 落地清单（阶段 B，按依赖顺序）

1. 把 `codes.py` 的 `normalize_code()` / `market_of()` 接入 `parse_holdings.py`（替换其 `full_code()`），加跨实现一致性测试——这是规则漂移的唯一根治办法
2. 删 15 处硬编码路径，其中 `publish_to_github.py:78` 与 `scan_compliance.py:24` 为**必删**
3. `parse_holdings.py` 加 `--config` 只读分支（不改动既有逻辑）
4. 建框架仓 `daily-pulse-framework`（MIT），迁入 §1.1 的 62 个文件
5. `build_site.py` 增加 `api/feed.json` 产出（详见 R6 §3）
6. 抽离 10 个测试为「单元」+「集成」两组，集成组参数化
7. 补 `fetch_data.py` / `generate_report.py` / `fill_and_publish.py` 三个脚本（工程债）
8. 内容仓转私有 + 确认 Pages 收录行为
9. 阶段 C：定时任务改传 `--config`

---

## 9. 未决问题（需产品/用户决策）

1. **采集三步补不补脚本？** 不补则框架不可复现（agent 行为随模型波动）；补则是主要工程量。倾向补。
2. **内容仓是否允许公开？** 涉及个人持仓与收益数据泄露，建议私有。若要公开，须先做持仓脱敏（代码→脱敏别名）。
3. **迁移期以谁为准？** 建议阶段 B/C 全程以 MEMORY.md 为准，yaml 只做校验与演练，避免双源打架。
4. **是否要 `holdings.yaml` 支持多账户？** 当前 schema 单账户。多账户需在 `profile` 下加 `accounts[]` 并让各段带 `account` 字段——是 MAJOR 变更。
