---
name: daily-pulse-framework
description: >-
  持仓驱动的每日研判内容站一键流水线：从 holdings.yaml 出发，跑完「交易日判定 →
  数据采集 → 信号评分 → 持仓解析 → 硬校验 → 专家研判 → 决策卡/台账 → 渲染 →
  发布」全链路，产出 Markdown + 站点 HTML + JSON feed。当用户要求配置持仓、
  生成每日复盘/基金盘面/操作指引、发布研判站内容、或搭建可复用的投资研判
  内容流水线时必须加载此技能。触发词：一键出报告、持仓配置、每日复盘流水线、
  研判站、holdings.yaml、发布研判内容、复用决策引擎。
agent_created: true
version: 1.0.0
display_name: "研判流水线框架"
display_name_en: "Daily Pulse Framework"
description_zh: "持仓驱动的每日研判流水线：从一份配置到 Markdown、站点 HTML 与 JSON feed 全链路产出。"
description_en: "Holdings-driven daily research pipeline: one config to Markdown, site HTML, and JSON feed."
visibility: "public"
---

# 研判流水线框架（Daily Pulse Framework）

## 定位与继承关系

本技能**继承** `daily-decision-engine`，不替代它。两者的关系是明确的分层：

```
daily-pulse-framework（本技能）
  ├── 继承：决策协议、七步流水线、决策卡七件套、观点台账、禁词与合规门禁
  │   全部来自 daily-decision-engine v1.3.0（本技能不重述、不改写）
  └── 新增：配置契约（holdings.yaml）+ 渲染发布链路 + 站点产物
```

**硬规则**：

1. 加载本技能时，必须**同时加载** `daily-decision-engine`。跳过它等于放弃
   全部决策协议与合规门禁——本技能只做「输入输出与编排」，不做决策。
2. 本技能**不改写** `daily-decision-engine` 的任何铁律。若两者冲突，
   以 `daily-decision-engine` 为准，并上报冲突，不要自行裁决。
3. `parse_holdings.py` 保持**行为不变**。它是回退通道，见下文「三」。

## 一、资产边界（三分法）

这是本框架的地基，动手前必须先分清什么是能复用的、什么是用户填的、什么是产物。

| 类别 | 归属 | 举例 | 是否进 Git |
|------|------|------|-----------|
| **框架** | 复用别人的，随 skill 分发 | `scripts/validate_config.py`、`render_md.py`、`build_site.py`、`md_render/`、`sanitizer/`、七步流水线、禁词与合规门禁、design-tokens | 进公开仓（MIT） |
| **配置** | 每个用户自己填 | `holdings.yaml`（三段：stocks/grid/funds）、`profile` | **不进公开仓**，进本地或私有仓 |
| **产物** | 用户自己的输出 | `market_data.json`、`holdings.json`、`viewpoint.json`、`*.md`、站点 HTML、`feed.json` | 进用户内容仓，不进框架仓 |

铁律：**持仓永远只来自 `holdings.yaml`**（或迁移期回退到 MEMORY.md）。
禁止把持仓写进任何脚本、提示词、定时任务配置。

## 二、配置契约（v1）

单文件 `holdings.yaml`，三段结构，与 `daily-decision-engine` 的 MEMORY.md 三表一一对应：

| 配置段 | 对应 MEMORY.md 表 | 关键字段 |
|--------|-------------------|---------|
| `holdings.stocks` | 股票持仓 | `code` `name` `shares` `available` `cost` `note` |
| `holdings.grid` | 网格交易参数 | `code` `enabled` `base_price` `range_low` `range_high` `step_pct` `per_trade` `min_position` `max_position` `guide` |
| `holdings.funds` | 基金持仓 | `code` `name` `asset_class`(fund/gold) `amount` `plan` `note` |

完整 schema 见 `config/schema.json`，字段级注释见 `config/holdings.example.yaml`。

**校验是强制门禁**，且必须在任何取数之前：

```bash
python3 scripts/validate_config.py --config <path/to/holdings.yaml> --strict
```

退出码 0/1/2。`--strict` 下警告也算失败（CI 用）。校验未过 → **禁止继续流水线**。

## 三、持仓事实源：迁移期双轨（重要）

框架**不破坏**任何现有行为。迁移分三步，每步可独立回滚：

| 阶段 | 动作 | 回滚方式 |
|------|------|---------|
| A（并行期，默认） | MEMORY.md 仍为事实源，`parse_holdings.py` 不动 | 无需回滚，现状即回滚点 |
| B（切换期） | 新增 `holdings.yaml` 并校验通过；仍由 `parse_holdings.py` 出 `holdings.json` | 删掉 yaml，恢复 `--memory` 参数 |
| C（目标态） | 引擎读 `holdings.yaml`；`parse_holdings.py` 保留为迁移工具 | 把 `--config` 切回 `--memory` |

**为什么不直接改 `parse_holdings.py`**：它被 6 个生产定时任务依赖，且按列位置解析
MEMORY.md。改动会让「当天出报告」这条生产链存在风险。**迁移必须是加法，不能是减法。**

## 四、路径参数化（本技能所有命令）

**禁止在脚本、提示词、定时任务里写死任何绝对路径。** 统一用环境变量：

| 变量 | 含义 | 默认值 |
|------|------|--------|
| `PULSE_CONFIG` | `holdings.yaml` 路径 | 无（必填） |
| `PULSE_WORK_ROOT` | 产物工作根目录 | 无（必填） |
| `PULSE_CONTENT_REPO` | 用户内容仓路径 | 无（必填） |
| `DECISION_ENGINE_MEMORY` | 回退用的 MEMORY.md | 无 |
| `GH_TOKEN_FILE` | GitHub token 文件路径 | 无 |

所有脚本同时支持 CLI 覆盖：环境变量给默认值，CLI 参数优先级更高。

## 五、执行流水线

```
步骤 0 校验配置   → 步骤 1 交易日判定 → 步骤 2 数据采集(westock-mcp)
→ 步骤 3 信号评分 → 步骤 4 持仓解析 → 步骤 5 硬校验
→ 步骤 6 专家研判 + 对抗辩论 → 步骤 7 决策卡 + 观点台账
→ 步骤 8 渲染 Markdown → 步骤 9 渲染站点 HTML → 步骤 10 发布 + feed.json
```

步骤 1-7 **完全继承** `daily-decision-engine`，包括那条顺序铁律：
**必须先 `compute_signals` 合入 `verdict`，后 `validate_market_data`**。
反序执行必挂——2026-10-14 9:28 任务零产出已实证。

本技能新增的步骤 0、8、9、10：

| 步骤 | 命令 | 产物 |
|------|------|------|
| 0 配置校验 | `python3 scripts/validate_config.py --config $PULSE_CONFIG --strict` | 退出码 |
| 8 渲染 md | `python3 scripts/render_md.py --md <in.md> --slug <slug> --date <YYYY-MM-DD> --out <out.html> [--market-data <md.json>]` | HTML |
| 9 渲染站点 | `python3 scripts/build_site.py --stage <stage> --base-url <url>` | `SITE_FILE:` 协议行 |
| 10 发布 | `python3 scripts/publish_to_github.py --date <d> --source-root <root> --stage <stage> --repo <r> --owner <o> --push` | 推送产物 + `feed.json` |

## 六、降级链

| 故障 | 处置 |
|------|------|
| 配置校验失败 | 中止。不取数、不产出任何研判（**唯一硬阻断**） |
| 行情 MCP 部分失败 | `rating=暂停` + 缺口清单（代码裁定，LLM 无权跳过） |
| 行情 MCP 全挂 | 只输出日期 + 昨日存档 + 任务状态 |
| 持仓解析失败 | 降级「仅大盘研判」，标注持仓缺口 |
| 专家团超时 | 跳过辩论走简化链（代码评级 + 决策卡仍必须完整） |
| 连续 2 日 `rating=暂停` | 输出告警待人工审查 |

## 七、合规门禁（对外发布时强制）

`disclaimer_profile: investing` 时，下列每一条都是发布前置条件，
任一不过**禁止发布**：

1. AI 生成内容标识（`🤖 AI 研判点评`），禁止虚构具体人名
2. 三层免责声明齐全（风险等级 / 决策独立性 / 非投资建议）
3. 禁词扫描一级词 0 命中；中性词密度 ≤1.5/千字；数值密度 ≥4/千字
4. 硬编码数值扫描：报告中持仓数字必须与当日 `holdings.json` 一致
5. 条件→操作框架：无指令性动词裸奔（「买入」必须挂在条件下）
6. 每个关键数字带「来源 + 时点」

## 八、文件索引

| 用途 | 路径 |
|------|------|
| 配置 schema | `config/schema.json` |
| 配置示例（字段级注释） | `config/holdings.example.yaml` |
| 配置校验器 | `scripts/validate_config.py` |
| 校验器自测 | `scripts/test_validate_config.py` |
| 一键复用指南 | `README.md` |
| 决策协议（本技能继承） | 技能 `daily-decision-engine` |
