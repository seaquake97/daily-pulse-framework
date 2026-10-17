# daily-pulse-framework

**把每日市场研判变成可复算、可结算、可审计的工程系统 · A reproducible, settleable, auditable pipeline for daily market research**

[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#零依赖)
[![CI](https://github.com/seaquake97/daily-pulse-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/seaquake97/daily-pulse-framework/actions/workflows/ci.yml)

---

## 这是什么 / What

大多数人看的「每日研报」有三个通病：**数据写死**（模板套话）、**结论骑墙**（中性词堆砌）、**无法证伪**（说对说错都无法结算）。

本框架用工程手段解决这三个问题，并把「研判 → 呈现 → 发布」整条链路产品化：

```
市场数据 → 硬校验 → 代码化信号评分 → Σ 评级 → 专家对抗辩论 → 决策卡 → 渲染 → 静态站点 → GitHub Pages
                ↑                                                        ↓
         观点台账结算 ←────────── 次日自动裁定 TRIGGERED / NOT_TRIGGERED / UNEVALUABLE / MISSED_NEUTRAL
```

**同一条数据，必然得出同一个结论。** 所有方向性数字由代码计算并写入 `verdict` 字段，LLM 只负责解读，无权改分。

## 三仓架构 / Repository Topology

| 仓库 | 许可 | 内容 | 谁维护 |
|---|---|---|---|
| [`daily-decision-engine`](https://github.com/seaquake97/daily-decision-engine) | MIT | 决策协议：七步流水线、S1–S6 信号、决策卡、观点台账、4 个确定性脚本 | 引擎维护者 |
| **`daily-pulse-framework`（本仓）** | MIT | 框架资产：配置校验、技术指标、多源容灾、声明式策略、渲染/脱敏/站点构建/发布管线、设计 Token、27 套测试 | 框架维护者 |
| `daily-market-pulse` | 私有 | 产物：每日详情页、RSS、feed.json（GitHub Pages） | 用户自己 |

依赖方向**单向不可逆**：用户配置 + 行情 MCP → 框架资产 → 产物 → 内容仓。框架仓永不引用任何具体用户的路径；内容仓不含框架代码。

## 快速开始 / Quick Start

```bash
# 1. 克隆（零第三方依赖，clone 即可跑）
git clone https://github.com/seaquake97/daily-pulse-framework.git
cd daily-pulse-framework

# 2. 跑单元测试（不需要任何真实产物，约 10 秒）
python3 scripts/test_conclusion_contract.py
python3 scripts/test_dark_mode.py
# 或一键 CI 总调度（本机含集成测试）
python3 scripts/ci_verify.py

# 3. 校验配置（框架唯一的新增用户输入面）
cp framework/config/holdings.example.yaml holdings.yaml   # 填写三段持仓
python3 framework/scripts/validate_config.py --config holdings.yaml --strict

# 4. 查看线上方法论页（本项目全部规则的文档化呈现）
open site/methodology/index.html   # 或访问内容站的 /methodology/
```

完整的新用户上手指引（约 50–90 分钟）见 [docs/DEPLOY-GUIDE.md](docs/DEPLOY-GUIDE.md)。

## 仓库地图 / Repository Map

```
framework/                  框架资产（MIT，可整体复用）
├── config/                 配置契约：schema.json + strategies/*.yaml + slug_stage.json
├── engine/
│   ├── signals/            确定性信号计算（compute_signals / technical 指标）
│   ├── collect/            取数侧：健康体检、多源容灾、合并（主源优先/脏值丢弃/缺口声明）
│   └── report/             报告契约校验
├── scripts/                配置校验器 + 策略加载器/渲染器 + 路径解析唯一入口
└── skills/                 SKILL.md（继承 daily-decision-engine 协议）

scripts/                    站点构建与发布管线（纯标准库）
├── render_md.py            md → 详情页 HTML 统一渲染器（唯一呈现层生产者）
├── md_render/              渲染内核（blocks/document/inline/meta）
├── sanitizer/              发布层消毒 15 件套（emoji→SVG / 去渐变 / 色值收敛 Token / 摘 JS）
├── sanitize_body.py        消毒入口（--dir 范围收窄 + 时点护栏）
├── build_site.py           站点生成（日期/周/月归档 + feed + sitemap + methodology）
├── site_*.py / *.css       站点结构与 Apple 设计语言组件层
├── publish_to_github.py    发布编排器（收集→渲染→消毒→建站→manifest→推送）
├── ci_verify.py            统一 CI 总调度（27 项：19 套单测 + 4 套校验器 + 4 套引擎测试）
├── scan_compliance.py      P0 合规扫描（emoji/渐变/硬编码色/悬空图标引用）
└── probe_responsive.py     响应式探针（16 宽度 × 12 页面 = 192 组合零横滚）

site/                       静态页源码（methodology 方法论页，占位符注入构建）
docs/                       规格与决策：PRD / UI 规范 / ADR / 缺口清单 / 部署指南
design-tokens.css           Apple 设计语言 Token 层（全站唯一样式来源）
detail-frame.css            详情页阅读框架
_engine_stage/              引擎 canonical 副本（同步至 daily-decision-engine 仓与生产技能目录）
```

## 核心规则（节选）/ Key Rules

完整规则见线上方法论页与 [`_engine_stage/SKILL.md`](_engine_stage/SKILL.md)。以下四条是每次改动都必须遵守的：

1. **顺序铁律**：信号评分必须在硬校验**之前**（校验器强制 `verdict` 存在，fail-closed）。
2. **数据只走 MCP**：行情经 westock-mcp 采集；备用源仅只读兜底，且必须显式标注降级，绝不冒充主源。
3. **缺失即声明，禁填 0**：任何字段缺失标注「数据缺口」；降级态撤下全部可执行动作（金融场景最高危）。
4. **代码计算 Σ，LLM 禁调分**：Σ 由代码写入 `verdict`，报告引用必须原样呈现。

## 质量门禁 / Quality Gates

```bash
python3 scripts/ci_verify.py          # 27 项全绿才算过（单测 + 校验器）
python3 scripts/scan_compliance.py    # P0 扫描：违规计数必须全 0
python3 scripts/probe_responsive.py   # 192 组合横向溢出必须为 0
python3 scripts/verify_published.py   # 构建暂存与线上仓逐字节一致（漂移 0）
```

## 零依赖 / Zero Dependency

`scripts/` 与 `framework/` 实测**纯 Python 标准库**（无 requirements.txt 是有意的——框架要求「别人 clone 完就能跑」）。自带 YAML 子集解析器（`framework/scripts/yaml_min.py`）替代 PyYAML。Python ≥ 3.10（`X | None` 语法）。

## 环境变量 / Environment

| 变量 | 用途 | 默认 |
|---|---|---|
| `PULSE_WORKBUDDY_ROOT` | 任务产物根（各任务日期目录） | `~/WorkBuddy` |
| `PULSE_CONFIG` | `holdings.yaml` 路径 | 无（必填） |
| `DECISION_ENGINE_MEMORY` | 迁移期持仓记忆文件 | 无（缺省即报错，不读隐式默认） |
| `GH_TOKEN_FILE` | GitHub 发布令牌文件 | `~/.config/gh-ip/token` |
| `PULSE_FIXTURE_ROOT` / `PULSE_FIXTURE_DAY` | 集成测试产物注入（未设则 skip 不失败） | 无 |

## 文档索引 / Docs

| 文档 | 内容 |
|---|---|
| [docs/FRAMEWORK-DESIGN.md](docs/FRAMEWORK-DESIGN.md) | 框架总设计（链路、职责、演进） |
| [docs/ARCH-R5-FRAMEWORK.md](docs/ARCH-R5-FRAMEWORK.md) | 框架资产化：资产边界三分法、配置契约、版本策略 |
| [docs/ARCH-R6-MINIPROGRAM.md](docs/ARCH-R6-MINIPROGRAM.md) | 小程序消费方案（含合规阻断项分析） |
| [docs/PRD-METHODOLOGY-UPGRADE.md](docs/PRD-METHODOLOGY-UPGRADE.md) | 方法论页升级 PRD（9 模块 × Apple HIG 双端） |
| [docs/SPEC-DATA-FALLBACK.md](docs/SPEC-DATA-FALLBACK.md) | 多源容灾与降级数据契约 |
| [docs/PRODUCT-CONTRACT.md](docs/PRODUCT-CONTRACT.md) | 产品红线 26 条（含机检状态） |
| [docs/DEPLOY-GUIDE.md](docs/DEPLOY-GUIDE.md) | 新人上手：三仓结构、凭证、构建发布、故障排查 |
| [docs/CLOUD-AUTOMATION.md](docs/CLOUD-AUTOMATION.md) | GitHub Actions 云端定时编排 |
| [docs/decisions/](docs/decisions/) | ADR 架构决策记录 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更记录 |

## 参与贡献 / Contributing

见 [CONTRIBUTING.md](CONTRIBUTING.md)。提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)，所有 PR 必须通过 CI（单测层）与 P0 合规扫描。

## 许可 / License

代码部分 [MIT](LICENSE)；内容站产物（`daily-market-pulse` 仓）为个人研判档案，另行许可。
