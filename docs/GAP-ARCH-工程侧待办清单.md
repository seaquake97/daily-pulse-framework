# GAP-ARCH — 工程侧待办清单

审计对象：`github-ip-plan/`（站点）+ `~/.workbuddy/skills/daily-decision-engine/`（引擎技能）
审计人：高见远（首席架构师）｜审计日期：2026-10-16
方法：全量 grep + 换机器模拟实测 + 幂等性双跑比对 + 逐文件失败归因。所有结论附文件:行号或实测输出。

本轮只产出清单与骨架代码，不做全量迁移。

---

## 0. 摘要：实测数据（先说结论）

| 项 | 上一轮说法 | 实测 | 差异 |
|---|---|---|---|
| 站点 py 文件数 | 72 | **59**（`scripts/` 递归），排除 `_archive/` 为 **48** | 上轮数字偏高 |
| 硬编码 `/Users/lianghaizhen` | 17 处 | **17 处**（生产脚本与 framework 内） | 一致 |
| 换机器后失败测试套件 | 3 套 | **2 套真失败 + 1 套部分 skip** | 见 §3 |
| 引擎脚本互相 import | 未查 | **零互相 import** | 迁移难度低于预期 |
| 引擎代码三方一致性 | 未查 | **1 个文件漂移**（parse_holdings.py） | 见 §4.4 |

**新发现的 3 个 P0 缺陷**（上轮未报，均为实测复现）：

1. `sanitizer` 把背景色收敛成**文字色 Token**（`background: var(--warn)`），已污染 2 个已发布 HTML —— §6.1
2. `publish_to_github.py` 对缺失任务**静默跳过且退出码仍为 0**，15:05 `stock-review` 在 2026-10-16 整条消失 —— §6.2
3. 站点目录**完全不在版本控制下**（无 `.git`），而引擎与站点各有一个 GitHub 仓 —— §5.4

---

## 1. 硬编码与可迁移性审计（17 处，逐处核实）

全部 17 处均为「绝对路径写死」，无一处可通过环境变量覆盖。分三类。

### 1.1 阻塞他人复用的（生产脚本，7 处）

| # | 文件:行号 | 硬编码内容 | 迁移方案 | 阻塞复用 |
|---|---|---|---|---|
| 1 | `scripts/publish_to_github.py:76` | `SOURCE_ROOT = Path("/Users/lianghaizhen/WorkBuddy")` | 改 `Path(os.environ.get("PULSE_WORKBUDDY_ROOT", ...))`，默认值取 `Path.home()/"WorkBuddy"` | **是** — 发布管线总入口，换机器即崩 |
| 2 | `scripts/publish_to_github.py:78` | `MANAGED_PY = "/Users/lianghaizhen/.workbuddy/binaries/python/envs/default/bin/python3"` | 改 `os.environ.get("PULSE_PYTHON", sys.executable)`（`run_pipeline.py:54` 已用此写法，保持一致） | **是** — 换机器无此二进制 |
| 3 | `scripts/push_repo.py:33` | `WORK_ROOT = Path("/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45")` | 改环境变量 `PULSE_WORK_ROOT`，默认值取本文件上两级 | **是** — 且写死了单个任务目录名，任何复用都错 |
| 4 | `scripts/scan_compliance.py:24` | `os.chdir('/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan')` | 改 `Path(__file__).resolve().parent.parent`（脚本自身已在仓内，无需 chdir） | **是** |
| 5 | `scripts/build_body_css.py:40` | `DEFAULT_SOURCE = Path("/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan")` | 同上，改 `__file__` 相对定位 | **是** |
| 6 | `framework/engine/run_pipeline.py:53` | `PULSE_WORKBUDDY_ROOT` 默认值 `/Users/lianghaizhen/WorkBuddy` | 默认值改 `Path.home()/"WorkBuddy"`，保留环境变量优先 | **是** — 但已有 env 覆盖能力，改默认值即解 |
| 7 | `framework/engine/collect/COLLECTION.md:73` | `PY=/Users/lianghaizhen/.workbuddy/binaries/python/envs/default/bin/python3` | 文档示例改 `PY=python3` | 否（文档） |

### 1.2 阻塞他人复用的（测试，6 处）

| # | 文件:行号 | 硬编码内容 | 迁移方案 | 阻塞复用 |
|---|---|---|---|---|
| 8 | `scripts/test_real_outputs.py:21` | `BASE = Path("/Users/lianghaizhen/WorkBuddy")` | `os.environ.get("PULSE_FIXTURE_ROOT")` | **是** |
| 9 | `scripts/test_real_outputs.py:22` | `DAY = "2026-10-14"` | `PULSE_FIXTURE_DAY` 环境变量，默认取最新可用目录 | **是** — 与 #8 独立的第二个故障轴 |
| 10 | `scripts/test_render_md.py:22` | `SRC = Path("/Users/lianghaizhen/WorkBuddy")` | 同 #8 | **是** |
| 11 | `scripts/test_render_md.py:17` | `PY = "/Users/lianghaizhen/.workbuddy/binaries/python/envs/default/bin/python3"` | `sys.executable` | **是** |
| 12 | `scripts/test_sanitize_pipeline.py:36` | `UPSTREAM = Path("/Users/lianghaizhen/WorkBuddy")` | 同 #8 | 是（但实测 skip 6 例后通过，见 §3.2） |
| 13 | `scripts/test_content_contract.py:21` | `BASE = Path("/Users/lianghaizhen/WorkBuddy")` | 同 #8 | 否（实测 BASE 未被实际断言使用，见 §3.2） |

### 1.3 不阻塞（fixture 声明 / 文档，4 处）

| # | 文件:行号 | 硬编码内容 | 处理方式 |
|---|---|---|---|
| 14 | `scripts/test_frame_fixed_point.py:35` | `REAL_SRC = .../股票助手/2026-10-16/stock_assistant.html` | 保留但加 `SkipTest` 守卫（实测已 skip 1 例，行为正确） |
| 15 | `scripts/test_sanitize_gate_visual.py:34` | `.../股票复盘/2026-10-15/stock_review.html` | 同上（实测 skip 2 例，行为正确） |
| 16 | `framework/README.md:167` | 表格中 `PULSE_WORKBUDDY_ROOT` 示例值 | 文档示例，可保留 |
| 17 | `framework/engine/run_pipeline.py:30` | docstring 中的默认值说明 | 随 #6 一并改 |

**不在 17 之列但同源的一处（本次新发现）**：

`~/.workbuddy/skills/daily-decision-engine/scripts/parse_holdings.py:23` 硬编码了带 UUID 的用户级 MEMORY 路径。
**GitHub 开源版 `_git_engine/scripts/parse_holdings.py:24` 已改为 `"./holdings-memory.md"`** —— 即上游已修，本机安装版是回归。见 §4.4。

### 1.4 路径参数化统一方案

新增一个模块 `framework/scripts/paths.py`，作为**唯一**路径解析入口（当前 `run_pipeline.py` 已有正确的 env 解析逻辑，但未抽出复用）：

```python
# framework/scripts/paths.py — 骨架，无硬编码
"""路径解析唯一入口。所有 PULSE_* 环境变量在此定义一次。"""
import os
import sys
from pathlib import Path


def _root(env: str, fallback: Path) -> Path:
    return Path(os.environ.get(env, str(fallback))).expanduser()


def workbuddy_root() -> Path:
    """工作区根（含各任务日期目录）。"""
    return _root("PULSE_WORKBUDDY_ROOT", Path.home() / "WorkBuddy")


def site_root() -> Path:
    """站点根（含 scripts/publish_to_github.py）。"""
    return _root("PULSE_SITE_ROOT", Path(__file__).resolve().parents[2])


def framework_root() -> Path:
    return _root("PULSE_FRAMEWORK_ROOT", Path(__file__).resolve().parents[1])


def engine_scripts() -> Path:
    """引擎脚本目录。默认本机技能安装位置，可用 PULSE_ENGINE_SCRIPTS 覆盖。"""
    return _root(
        "PULSE_ENGINE_SCRIPTS",
        Path.home() / ".workbuddy/skills/daily-decision-engine/scripts")


def python_exe() -> str:
    """解释器。默认当前解释器，避免写死绝对路径。"""
    return os.environ.get("PULSE_PYTHON", sys.executable)


def fixture_root() -> Path | None:
    """集成测试的产物根。未设返回 None —— 调用方据此 skip 而非失败。"""
    return os.environ.get("PULSE_FIXTURE_ROOT") and Path(
        os.environ["PULSE_FIXTURE_ROOT"]).expanduser() or None
```

纪律：`paths.py` 里**只能出现 `Path.home()` 与 `__file__`**，禁止任何具体用户名。CI 用环境变量注入真实根目录。

---

## 2. 引擎迁移方案（R5 最大工程债）

### 2.1 关键实测发现：迁移难度低于预期

```
$ 对 4 个引擎脚本 grep 互相 import → 零命中
compute_signals.py   无内部 import
parse_holdings.py    无内部 import
settle_viewpoints.py 无内部 import
validate_market_data.py 无内部 import
```

4 个脚本**完全独立**，只依赖标准库。这意味着迁移是**纯文件搬迁 + 路径参数化**，无依赖图重排风险。这是本方案能分 3 阶段低风险落地的依据。

### 2.2 `framework/engine/` 目标结构

```
framework/
├── engine/
│   ├── run_pipeline.py              # 编排入口（保留，路径改走 paths.py）
│   ├── collect/                     # 取数侧
│   │   ├── check_market_data.py     # 已有
│   │   ├── normalize_market_data.py # 已有
│   │   ├── market_data.schema.json  # 已有
│   │   ├── COLLECTION.md            # 已有（改 PY 示例）
│   │   └── test_market_data_contract.py
│   ├── report/                      # 报告侧
│   │   ├── check_report.py          # 已有
│   │   ├── report_contract.yaml     # 已有
│   │   └── test_report_contract.py
│   ├── signals/                     # 【新增】从引擎技能迁入的确定性计算
│   │   ├── compute_signals.py       # 迁入
│   │   ├── parse_holdings.py        # 迁入（改默认路径）
│   │   ├── settle_viewpoints.py     # 迁入
│   │   ├── validate_market_data.py  # 迁入
│   │   └── test_signals.py          # 【新增】迁入后的回归
│   └── holdings/                    # 【新增】持仓事实源
│       └── MEMORY.md.example        # 开源版示例文件（替代硬编码路径）
├── scripts/
│   ├── paths.py                     # 【新增】§1.4 骨架
│   ├── codes.py / rules.py / validate_config.py / yaml_min.py  # 已有
└── skills/daily-pulse-framework/SKILL.md
```

### 2.3 逐文件迁移动作

| 脚本 | 改什么 | 签名变不变 | 回归怎么保 |
|---|---|---|---|
| `compute_signals.py` | **不改逻辑**，仅位置变 | 不变（`path` 位置参数 + `--kline` + `-o`） | 迁入前后对同一 fixture 跑 `diff` 输出字节 |
| `validate_market_data.py` | 不改 | 不变（`path` + `--expect-date`） | 同上 |
| `settle_viewpoints.py` | 不改 | 不变（`--archive` / `--today` / `--market-data` 全为必填或可选，**本就无硬编码**） | 同上 |
| `parse_holdings.py` | **删 `_default_memory_path()` 的绝对路径回退**，改为 `os.environ.get("DECISION_ENGINE_MEMORY", "./holdings-memory.md")` —— 与 GitHub 开源版对齐 | 不变（`--memory` 默认值变，参数名不变） | 新增「未设 env 时不崩且给出可读错误」用例 |

统一验证命令（字节级）：

```bash
# 迁入前后逐文件比对，退出码非 0 即回归
for f in compute_signals validate_market_data settle_viewpoints; do
  python3 framework/engine/signals/$f.py --help > /tmp/new_$f.txt 2>&1
  diff /tmp/old_$f.txt /tmp/new_$f.txt || echo "REGRESSION: $f"
done
```

### 2.4 `fetch_data.py` / `generate_report.py` 的取舍

**实测事实**：两个脚本散落在 3 个任务目录（不是技能内），已归档至 `_legacy_http/`：

| 文件 | 归档位置 | 外部依赖 | 证据 |
|---|---|---|---|
| 11:00 `fetch_data.py` | `_legacy_http/基金每日盘面分析（11:00）_fetch_data.py` | `requests` + `bs4` | `fetch_data.py:21` sina `Market_Center.getHQNodeData`；`:82` eastmoney `push2.eastmoney.com`；`:215` `fund.eastmoney.com/pingzhongdata` |
| 11:00 `generate_report.py` | `_legacy_http/fund_market_generate_report.py`（48KB） | 无（但内联 Tailwind CDN + Google Fonts） | `:214` `cdn.tailwindcss.com`；`:216` `fonts.googleapis.com` |
| 14:30 `generate_report.py` | `_legacy_http/基金每日操作指引（14:30）_generate_report.py`（36KB） | `urllib.request`（标准库） | `:117` sina API；`:185` eastmoney `push2` |
| 股票助手 `generate_report.py` | `_legacy_http/stock_assistant_generate_report_hardcoded.py` | 无 | 文件名即含 `hardcoded` |

**我的建议：删除重写，不迁移。理由三条，每条都有证据：**

1. **违反 MCP 铁律，不可修**。这四个脚本直连 `hq.sinajs.cn` / `push2.eastmoney.com` / `data.10jqka.com.cn`。数据源必须经 MCP 工具层（`westock` / `domain_search`），脚本直连意味着绕过数据源审计与降级链路——而 `publish_to_github.py:228` 已定义 `_DEGRADED_RE` 专门处理「未连接/无法调用/降级使用」，直连脚本根本无法产出这个标记。
2. **不可测**。`requests` + `bs4` 是 `_legacy_http` 唯一的第三方依赖（实测该目录 import 集合：`bs4 concurrent requests ssl urllib`），站点与 framework 已实测为**纯标准库**。迁入即打破零依赖属性，且这四个脚本无任何测试覆盖。
3. **已被取代**。`framework/engine/collect/` 的既定取舍（`run_pipeline.py:16-27` docstring 原文）是：*"MCP 调用与研判撰写需要 LLM 判断力，硬要脚本化只会得到一个巨大的 if-else"*。采集的正确形态是 agent 调 MCP → 写 JSON → `check_market_data.py` 校验。`fetch_data.py` 正是那个"巨大的 if-else"。

**动作**：
- `_legacy_http/` 目录加 `README.md`（**已存在**，需补一句「禁止回流」）
- 三个任务目录内的原文件：保留 1 周观察期，确认无调用后删除
- **不做**：把它们"改造成 MCP 版本"。采集侧的 MCP 化已由 `COLLECTION.md` 覆盖，无需第二套实现。

### 2.5 依赖方向图（禁止环）

```
                    paths.py                (叶子：只依赖 os/sys/pathlib)
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     codes.py ──► rules.py ──► validate_config.py
        │                            │
        │                            ▼
        │                      yaml_min.py
        ▼
  signals/*.py  (4 个迁入脚本，彼此零依赖)
        │
        ▼
  collect/check_market_data.py
  collect/normalize_market_data.py
        │
        ▼
  run_pipeline.py  ──►  [subprocess] ──► <site>/scripts/publish_to_github.py
        │
        ▼
  report/check_report.py
```

**三条硬约束**：
1. `paths.py` 是叶子，不得 import 任何项目内模块（否则 `codes.py`/`rules.py`/`signals`/`collect` 全反向依赖它成环）。
2. `framework/*` 任何模块**不得** import `<site>/scripts/*`。二者只通过 `run_pipeline.py` 的 subprocess 边界通信——这是防环的关键，也是 `run_pipeline.py:73-79` 已经在做的（用绝对路径拼 `CHECK_MD`/`NORMALIZE`）。
3. `signals/*.py` 之间**禁止**互相 import（现状已满足，迁移时保持）。

### 2.6 分阶段落地顺序

| 阶段 | 动作 | 验收命令 | 阶段出口 |
|---|---|---|---|
| **S1** | 建 `framework/scripts/paths.py`；把 `publish_to_github.py:76-78`、`push_repo.py:33`、`scan_compliance.py:24`、`build_body_css.py:40`、`run_pipeline.py:53` 五处改为走 paths/env | `grep -rn "/Users/lianghaizhen" scripts/*.py framework/ --include="*.py" \| grep -v _archive` → 仅剩测试文件命中 | 硬编码 17 → 11 |
| **S2** | 建 `framework/engine/signals/`，迁入 4 个引擎脚本（`parse_holdings.py` 改默认路径）；技能侧改为软链或文档指向 | `python3 framework/engine/test_signals.py` 全绿 + §2.3 的 `diff` 命令无输出 | 引擎不再依赖 `~/.workbuddy` 隐式路径 |
| **S3** | 测试分单元/集成两层（§3），删除 `_legacy_http` 原文件，`_archive/` 归档清理 | `python3 -m pytest tests/ -q` 全绿且**不设任何 PULSE_ 环境变量** | 换机器可跑 |

阶段顺序不可颠倒：S1 不改测试→S2 迁引擎→S3 动测试。S2 会新增 fixture 需求，若先动测试会返工。

---

## 3. 测试可迁移性改造方案

### 3.1 实测：换机器后到底哪套坏

模拟方法：整站拷到 `/tmp/migr_sim2`，把 `scripts/test_*.py` 里的 `/Users/lianghaizhen/WorkBuddy` 全替换为不存在的目录（等价于换机器且无产物）：

```
test_conclusion_contract      Ran 9    OK
test_content_contract        Ran 12    OK
test_dark_mode               Ran 3     OK
test_frame_fixed_point       Ran 10    OK (skipped=1)
test_real_outputs            Ran 17    FAILED (failures=1, errors=1, skipped=9)
test_render_md               Ran 22    FAILED (errors=14)
test_sanitize_gate_pipeline  Ran 13    OK
test_sanitize_gate_visual    Ran 9     OK (skipped=2)
test_sanitize_pipeline       Ran 24    OK (skipped=6)
test_sanitize_scope          Ran 8     OK
test_site_links              Ran 6     OK
```

**11 套中 2 套真失败**，共 15 个用例。逐个归因：

| 套件 | 失败用例 | 根因（实测 FileNotFoundError） |
|---|---|---|
| `test_real_outputs` | `test_three_snapshots_have_distinct_verdicts` | `assertIsNotNone(sa and fg and dr)` 拿 `None`，未 skip |
| `test_real_outputs` | `test_publish_layer_sigma_is_task_own` | 依赖 `_stage/docs/daily/2026-10-14/entries.json` |
| `test_render_md` | 14 个 error | `FileNotFoundError: .../基金每日操作指引（14:30）/2026-10-16/fund_operation_guide.md` 等 3 个 fixture |

**两个设计缺陷**：
- `test_real_outputs.py:26-30` 的 `real_md()` **有** `SkipTest` 守卫，但 `:33-35` 的 `real_json()` **没有**——返回 `None` 而不 skip，导致 `:232` 的断言炸掉。这是守卫漏加，不是用例设计问题。
- `test_render_md.py:24-26` 把 fixture 路径写成模块级常量，`setUp` 里直接用，**完全没有守卫**——fixture 缺失即 14 个 error。

### 3.2 三个「看起来该坏实际没坏」的说明（避免误判）

- `test_content_contract.py:21` 的 `BASE` 硬编码存在，但实测 12 例全过——该常量**实际未被断言使用**（真实 fixture 走 `:22` 的 `DAY` 构造，但断言已被 `:107-128` 的构造样本取代）。仍需参数化，否则是定时炸弹。
- `test_sanitize_pipeline.py:36` 的 `UPSTREAM` 缺失时实测 skip 6 例后通过——守卫正确，仅需参数化路径。
- `test_frame_fixed_point.py` / `test_sanitize_gate_visual.py` 的 fixture 缺失时 skip 1/2 例后通过——守卫正确。

### 3.3 拆分方案：目录与命名约定

```
tests/
├── unit/                      # 零外部依赖，CI 必跑
│   ├── test_content_contract.py
│   ├── test_conclusion_contract.py
│   ├── test_dark_mode.py
│   ├── test_site_links.py
│   ├── test_sanitize_scope.py
│   ├── test_sanitize_gate_pipeline.py
│   ├── test_sanitize_gate_visual.py
│   └── conftest.py            # 统一 fixture 根解析
├── integration/               # 依赖真实产物，未设 env 时整体 skip
│   ├── conftest.py
│   ├── test_real_outputs.py
│   ├── test_render_md.py
│   └── test_frame_fixed_point.py
└── fixtures/                  # 从真实产物脱敏后的最小样本（新增）
    ├── 2026-10-14/
    │   ├── stock_assistant.md
    │   ├── market_data.json
    │   └── ...
    └── MANIFEST.json          # 记录每个 fixture 的来源路径与校验和
```

命名约定：
- `tests/unit/` 前缀 `test_`，不带日期
- `tests/integration/` 文件名**必须**能被 `pytest -m integration` 收集，且**不允许**出现真实日期字面量
- 禁止再出现 `test_real_outputs.py` 这类"名字暗示依赖真实环境但没在名字里说明 skip 条件"的文件——集成性靠**目录**表达，不靠文件名

### 3.4 skip 条件写法（统一模板）

`tests/integration/conftest.py` 骨架：

```python
# tests/integration/conftest.py — 骨架，无硬编码
"""集成测试统一入口：产物根与基准日均由环境变量提供。

未设 PULSE_FIXTURE_ROOT 时整个目录 skip，绝不伪造样本、绝不静默通过。
"""
import os
from pathlib import Path

import pytest

# 未设环境变量即整体跳过——这是集成测试的默认行为，不是失败
pytestmark = pytest.mark.integration


def _fixture_root() -> Path | None:
    v = os.environ.get("PULSE_FIXTURE_ROOT")
    return Path(v).expanduser() if v else None


ROOT = _fixture_root()


@pytest.fixture(scope="session")
def fixture_root() -> Path:
    if ROOT is None or not ROOT.is_dir():
        pytest.skip("未设 PULSE_FIXTURE_ROOT，跳过集成测试")
    return ROOT


@pytest.fixture(scope="session")
def day() -> str:
    """基准交易日。优先环境变量，其次取产物根下最新日期目录。"""
    d = os.environ.get("PULSE_FIXTURE_DAY")
    if d:
        return d
    cands = sorted(p.name for p in ROOT.iterdir()
                   if p.is_dir() and _is_date(p.name))
    if not cands:
        pytest.skip("产物根下无可用日期目录")
    return cands[-1]


@pytest.fixture
def real_md(fixture_root: Path, day: str):
    """取当日真实产出；缺失则 skip 而非失败。"""
    def _get(task_dir: str, fname: str) -> Path:
        p = fixture_root / task_dir / day / fname
        if not p.exists():
            pytest.skip(f"真实产出缺失：{p}")
        return p
    return _get


@pytest.fixture
def real_json(fixture_root: Path, day: str):
    """JSON 取用；缺失返回 None —— 调用方须显式断言，不得隐式通过。"""
    def _get(task_dir: str, fname: str = "market_data.json"):
        p = fixture_root / task_dir / day / fname
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return _get
```

关键点：`real_json` **保留返回 `None` 的语义**（这是 `test_real_outputs.py:192-197`「11:00 盘面无 market_data.json」用例依赖的），但把"缺失即炸"的断言责任显式交给用例作者。`:232` 那个用例应改成 `pytest.skip` 而非 `assertIsNotNone`。

### 3.5 换机器后 CI 怎么跑

```bash
# 单元层：不需要任何产物，克隆即可跑
python3 -m pytest tests/unit/ -q

# 集成层：显式注入真实产物根与基准日
export PULSE_FIXTURE_ROOT=/Users/lianghaizhen/WorkBuddy   # CI 上换成 secret/挂载路径
export PULSE_FIXTURE_DAY=2026-10-16
python3 -m pytest tests/integration/ -q

# 未注入时必须整体 skip 而非 fail（这是「不依赖产物」的验收标准）
env -u PULSE_FIXTURE_ROOT -u PULSE_FIXTURE_DAY python3 -m pytest tests/integration/ -q
# 期望输出：N skipped，0 failed
```

**CI 门禁规则**：
1. `tests/unit/` 任何 failed → 阻断合并
2. `tests/integration/` skipped 比例 > 30% → 告警（说明产物注入失效）
3. `tests/integration/` 出现 failed → 阻断（说明产物契约真的破了）

---

## 4. 其余工程缺口

### 4.1 15:05 与 15:30 零脚本 —— 要补，但补的不是"生成器"

**实测**：6 个任务目录中，只有 3 个有 py 脚本。

```
0  股票复盘                     ← 15:05，无脚本
0  每日总复盘（15:30）            ← 15:30，无脚本
1  基金每日操作指引（14:30）
2  基金每日盘面分析（11:00）
6  股票助手
```

15:05 目录**只有 JSON 产物，没有报告**：

```
$ ls 股票复盘/2026-10-16/
holdings.json  market_data.json  settlement.json  sh000001_kline.json  viewpoint.json
                                  ↑ 无 stock_review.md
```

**结论：不补报告生成脚本。** 理由与 §2.4 同源——撰写需要研判力，脚本化只能得到巨大 if-else。

**但要补一个 `settle` 收口步骤**，因为 15:05 与 15:30 都产出了 `settlement.json` / `viewpoint.json`，而 `settle_viewpoints.py` 是现成的确定性脚本，目前靠人肉调用。补的是**编排接线**，不是新逻辑：

```bash
# 建议新增到 run_pipeline.py 的 stage 列表（与现有 collect/score/report/publish 并列）
settle    观点结算：跑 settle_viewpoints.py
          （--archive $PULSE_WORKBUDDY_ROOT/股票复盘 --today $DATE）
```

工作量：约 0.5 人日（复用现有 `run_step` 模式，无需新测试框架）。

### 4.2 幂等性：实测只差一个字段

**实测方法**：同一天连跑两次 `publish_to_github.py --date 2026-10-16`，全量内容哈希比对。

```
A: 66 文件，全量哈希 2b9da3b283117df6cebd3e9d7c718a32500f550afacfac7601d2f3c543356bb9
B: 66 文件，全量哈希 2b9da3b283117df6cebd3e9d7c718a32500f550afacfac7601d2f3c543356bb9
diff -rq A B → 无差异
```

**结论：除一个字段外，发布管线字节幂等。**唯一漂移源：

| 文件:行号 | 字段 | 现状 | 修法 |
|---|---|---|---|
| `publish_to_github.py:792` | `manifest.created_at` | `datetime.now().isoformat(timespec="seconds")` | 改 `args.date + "T" + 产出文件 mtime` 或加 `--frozen-timestamp` 开关供 CI 用 |

（实测证据：run1/run3 间隔约 13 秒，`created_at` 从 `2026-10-16T20:51:29` 变为 `2026-10-16T20:51:42`。）

**尚未验证的幂等环节**：上游 5 个任务的 LLM 撰写过程。报告 md 每次重跑是否字节一致，取决于 agent 而非脚本，不在本管线保证范围内。若要闭环，需在 `publish_to_github.py` 的 manifest 里增加 `source_md_sha256` 字段做输入侧锁定（当前 manifest 只有输出侧哈希）。

### 4.3 可观测性：目前定位问题靠 print

**实测**：

```
logging 调用数（全站 scripts + framework，排除 _archive）: 0
print( 调用数: 135
日志文件写入（logging.FileHandler / *.log / --log）: 0
```

现有可观测手段只有三样，且都有局限：

| 手段 | 位置 | 局限 |
|---|---|---|
| 退出码契约 | `publish_to_github.py:50-57`（0/2/3/4/5/6） | 只能表达"失败"，无法定位"哪一步失败" |
| `manifest.json` | `_stage/manifest.json` | 事后可查，但 `sanitize_warn` 只记布尔位，不记原因 |
| stdout `[step] msg` | `run_pipeline.py:69-70` `_log()` | 不落文件，定时任务里随 stdout 丢失 |

**最小改造（P1，约 1 人日）**：
1. `framework/scripts/logging_util.py`：统一 JSON 行日志输出到 stderr（不污染 stdout 的数据管道），字段 `ts/stage/slug/date/msg/level/code`
2. `run_pipeline.py:69` 的 `_log()` 改为调它（保留 print 兼容）
3. `publish_to_github.py` 的 `manifest.json` 增加 `sanitize_warn_reasons: []`，把 `sanitize_body.py` 报告的 warn 明细落盘——**当前只记 `sanitize_warn: true`，丢失了"哪些 token 未注入"这一关键信息**

### 4.4 版本管理：框架与站点仓的关系（本次最重要的架构结论）

**实测三方状态**：

| 位置 | 是否 Git 仓 | remote | 状态 |
|---|---|---|---|
| `github-ip-plan/`（站点，59 个 py + 全部设计文档） | **否**（`fatal: not a git repository`） | — | **完全不在版本控制下** |
| `github-ip-plan/_git_engine/` | 是 | `github.com/seaquake97/daily-decision-engine.git` | 1 个 commit（`2c4f6e9` v1.3） |
| `github-ip-plan/_git_pulse/` | 是 | `github.com/seaquake97/daily-market-pulse.git` | 空壳（LICENSE/NOTICE/README/docs） |

**三方代码漂移实测**：

```
compute_signals.py    一致
settle_viewpoints.py  一致
validate_market_data.py 一致
parse_holdings.py     不一致 → 3 行差异
SKILL.md              不一致 → 3 行差异
```

唯一实质差异（**上游已修、本机回归**）：

```diff
  # _git_engine/scripts/parse_holdings.py:21（GitHub 开源版，正确）
+ # 开源版默认值：请通过环境变量或 --memory 指定你的持仓记忆文件
  "/Users/lianghaizhen/.../MEMORY.md"   →   "./holdings-memory.md"
```

即：引擎在 GitHub 上是**开源干净版**，本机技能安装的是**生产定制版**（带硬编码 MEMORY 路径）。二者靠人工记忆保持同步——`parse_holdings.py` 已经漂移，说明这个机制失效。

**另一处重复实现风险**：`framework/scripts/codes.py:12-66` 与引擎 `parse_holdings.py:53-58` 是**两份市场前缀推断实现**。`codes.py` 自己的 docstring 写着：

> *"规则与 `daily-decision-engine/scripts/parse_holdings.py` 的 `full_code()` 逐条对齐，任何一方修改都必须同步另一方，否则会出现「配置校验说 ok、实际取数打空」的静默故障。"*

这就是用注释代替依赖治理。S2 迁入引擎后应让 `codes.py` 直接 import 引擎的实现（依赖方向已在 §2.5 图中定好：`codes.py` 是 `signals/*` 的下游，反向依赖会成环——因此**正确做法是把前缀推断收敛到 `codes.py` 单一实现，引擎侧改为 import 它**，而不是反过来）。

**我的建议**：

| 动作 | 结论 | 理由 |
|---|---|---|
| 站点 `github-ip-plan/` 纳入 Git | **必须，且最高优先** | 59 个 py + 设计文档 + 3 份 ADR 全部无历史记录。一次误删即不可恢复。这是比所有硬编码更严重的基础设施缺失 |
| 引擎与站点拆仓？ | **暂不拆** | 二者发布节奏耦合（`run_pipeline.py` 直接 subprocess 调站点脚本），拆仓后需版本矩阵管理，MVP 阶段收益为负 |
| 引擎代码以哪份为准 | **以 GitHub 开源版为基线，生产定制走环境变量** | 开源版无硬编码且已修 MEMORY 路径问题；定制需求（持仓路径）用 `DECISION_ENGINE_MEMORY` 表达，不需要改代码 |
| `_git_engine` / `_git_pulse` 目录 | 归档到 `_archive/`，不进版本库 | 是仓内嵌的仓克隆，会造成递归与混淆 |

**技术栈与版本锁定**（`scripts/` 与 `framework/` 实测**零第三方依赖**，纯标准库）：

```
Python 3.13.12（`dev-architecture.md:167` 记录的解释器版本）
依赖：无（实测 import 集合仅标准库 argparse/json/pathlib/subprocess/unittest/urllib 等）
唯一自研 YAML 子集解析器：framework/scripts/yaml_min.py（205 行）
包管理：无 requirements.txt / pyproject.toml / lock 文件（实测确认）
```

结论：**"锁定版本"对本项目等价于"锁定 Python 解释器版本"**。因为无第三方依赖，不需要 lock 文件；但必须在 `README` 写明最低版本（`yaml_min.py` 与 `dataclasses` 的用法决定下限为 3.8，`X | None` 语法决定下限为 **3.10**）。

---

## 5. 待办清单

| 编号 | 待办 | 阻塞等级 | 预估工作量 | 依赖 | 验收命令 |
|---|---|---|---|---|---|
| A-01 | **站点纳入 Git 仓**（`git init` + `.gitignore` + 首次提交，排除 `_git_*`/`_archive`/`__pycache__`） | **P0** | 0.5 人日 | 无 | `git -C github-ip-plan log --oneline \| wc -l` ≥ 1 且 `git -C github-ip-plan status --short` 为空 |
| A-02 | **修 sanitizer 背景色→文字色 Token 缺陷**：`token_map.py` 的 `ROLE_OVERRIDE` 对 bg 角色返回文字 token（实测 `#f59e0b` bg 角色返回 `--warn`，应为 `--rating-balanced-wash`） | **P0** | 0.5 人日 | 无 | `python3 -c "import sys;sys.path.insert(0,'scripts');from sanitizer import token_map as T;assert not T.token_for_hex('#f59e0b',role='bg').startswith('--warn')"` + `grep -c "background[^;]*var(--warn)" _stage/docs/daily/*/*.html` == 0 |
| A-03 | **修 publish 静默跳过缺失任务**：`publish_to_github.py:192-193` 与 `:199` 的 `continue`，缺任务时仅记 warn 且退出码仍为 0（实测 2026-10-16 15:05 `stock-review` 整条消失而退出码 0） | **P0** | 0.5 人日 | 无 | `python3 scripts/publish_to_github.py --date <无产物日>` 退出码 ≥ 2，且 stdout 含缺失任务名 |
| A-04 | 建 `framework/scripts/paths.py`，S1 批次参数化 5 处生产硬编码 | **P0** | 1 人日 | 无 | `grep -rn "/Users/lianghaizhen" scripts/*.py framework/ --include="*.py" \| grep -v _archive \| wc -l` 从 17 降到 11 |
| A-05 | `parse_holdings.py` 删 MEMORY 绝对路径回退，与 `_git_engine/scripts/parse_holdings.py:24` 对齐 | **P0** | 0.5 人日 | 无 | `grep -c "/Users/lianghaizhen" framework/engine/signals/parse_holdings.py` == 0（迁入后） |
| A-06 | 建 `tests/unit` + `tests/integration` 拆分，集成层加 skip 守卫 | **P1** | 1.5 人日 | A-04 | `env -u PULSE_FIXTURE_ROOT -u PULSE_FIXTURE_DAY python3 -m pytest tests/integration/ -q` → 全 skip 0 failed |
| A-07 | 修 `test_real_outputs.py:232` 的 `assertIsNotNone` → skip；`:33-35` `real_json` 补守卫 | **P1** | 0.5 人日 | A-06 | `grep -c "assertIsNotNone" tests/integration/test_real_outputs.py` == 0 |
| A-08 | 参数化 6 处测试硬编码路径（#8-#13） | **P1** | 0.5 人日 | A-06 | 同 A-06 |
| A-09 | 4 个引擎脚本迁入 `framework/engine/signals/`，`run_pipeline.py` 改指向 | **P1** | 2 人日 | A-04, A-05 | `python3 framework/engine/test_signals.py` 全绿；§2.3 diff 命令无输出 |
| A-10 | `codes.py` 与引擎 `parse_holdings.py` 前缀推断去重（前缀表收敛到 `codes.py` 单一实现） | **P1** | 0.5 人日 | A-09 | `grep -c "SH_PREFIX" framework/scripts/codes.py framework/engine/signals/parse_holdings.py` 两处均 1 定义 |
| A-11 | 统一 JSON 行日志（`logging_util.py`），manifest 增加 `sanitize_warn_reasons` | **P1** | 1 人日 | 无 | `python3 scripts/publish_to_github.py --date 2026-10-16 2>/tmp/log.jsonl` 后 `python3 -c "import json;[json.loads(l) for l in open('/tmp/log.jsonl')]"` 不抛异常 |
| A-12 | `manifest.json` 增加 `source_md_sha256`（输入侧幂等锁定） | **P2** | 0.5 人日 | 无 | 重跑同一天 `manifest.source_md_sha256` 不变 |
| A-13 | `manifest.created_at` 改可冻结（CI 用） | **P2** | 0.5 人日 | A-12 | `python3 scripts/publish_to_github.py --date X --frozen-timestamp T` 连跑两次 `_stage` 全量哈希一致 |
| A-14 | `run_pipeline.py` 增加 `settle` stage，接线 `settle_viewpoints.py`（15:05/15:30 收口） | **P2** | 0.5 人日 | A-09 | `python3 framework/engine/run_pipeline.py --date 2026-10-16 --stage settle` 退出码 0 |
| A-15 | 删除 `_legacy_http` 在 3 个任务目录的原文件（观察期满后），补「禁止回流」说明 | **P2** | 0.5 人日 | 无 | `find /Users/lianghaizhen/WorkBuddy -maxdepth 2 -name "fetch_data.py" -o -maxdepth 2 -name "generate_report.py" \| wc -l` == 0 |
| A-16 | `_git_engine` / `_git_pulse` 归档到 `_archive/`，写入 `.gitignore` | **P2** | 0.5 人日 | A-01 | `git -C github-ip-plan ls-files \| grep -c "_git_"` == 0 |
| A-17 | `README` 写明 Python ≥ 3.10（受 `X \| None` 语法约束）、零第三方依赖、4 类 PULSE_* 环境变量 | **P2** | 0.5 人日 | A-04, A-09 | `grep -c "PULSE_" github-ip-plan/README.md` ≥ 4 |
| A-18 | `scripts/_archive/`（11 个 py）与 `test_sanitize_gate_visual.py` 的 fixture 日期治理 | **P2** | 1 人日 | A-06 | 全站 `grep -rn "2026-10-1[0-9]" --include="*.py" \| grep -v fixtures/` 命中仅注释 |
| A-19 | **`SLUG_STAGE` 三处定义收敛为单一数据源**：`publish_to_github.py:129`（`pre_open`）与 `md_render/meta.py:40`（`intraday`）已实测漂移，`render_md.py:43` 再导出一次。下沉为 JSON/YAML 供两侧读取 | **P1** | 1 人日 | A-09 | `grep -rn '"stock-assistant": "intraday"' scripts/ \| wc -l` == 0；`python3 -c "import json;d=json.load(open('framework/config/slug_stage.json'));assert d['stock-assistant']=='pre_open'"` |
| A-20 | **补 `settlement.schema.json` + 校验器**：`settlement.json` 结构实测稳定（`status`/`counts`/`hits`/`evaluable`/`hit_rate`/`by_type`/`viewpoints[]`），但 `framework/engine/collect/` 与 `report/` 下**零引用**，无任何契约。无契约 JSON 直接接发布层 = 上游格式变更直接变线上故障 | **P1** | 0.5 人日 | A-09 | `python3 framework/engine/collect/check_settlement.py <path>` 退出码 0；缺 `status` 或 `viewpoints` 非 list 即非 0 |
| A-21 | **`_stage` 与 `_git_pulse` 同步校验入 CI**（PM 补充的 CAP-03 验收项）：实测当前 15 个文件不同步，`_git_pulse` 是上一版产物——3 个 degraded 条目的 `rating`/`sigma`/`dataGap` 仍是修复前的值。线上真实产物是 `_git_pulse`，只测 `_stage` 等于没测线上 | **P1** | 0.5 人日 | A-04 | `diff -rq _stage/docs _git_pulse/docs` 输出为空 |
| A-22 | **修站点正文的本机绝对路径泄漏**：实测 `_stage/docs/daily/2026-10-15/stock-review.html:1939` 与同名 `.md` 渲染出 `依据 /Users/lianghaizhen/WorkBuddy/股票复盘/2026-10-15/settlement.json 自动结算结果`。GitHub Pages 是公开站点，暴露用户名与目录结构。改为中性表述（如「依据引擎自动结算结果」），路径信息留 HTML 注释或删除。**这是 15:05 停产 md 的前置条件**（ADR-005 决策二之二） | **P0** | 0.5 人日 | 无 | `grep -rl "/Users/lianghaizhen" _stage/docs/ \| wc -l` == 0 |

**补充：A-19 的实测证据（2026-10-16 第二轮审计发现）**

`SLUG_STAGE` 与 A-10 的 `codes.py` / `parse_holdings.py` 是**完全同型**的问题——
用注释维系两份可独立漂移的实现，且已经漂移：

| 位置 | `stock-assistant` 取值 | 后果 |
|---|---|---|
| `publish_to_github.py:130` | `pre_open` | 正确（`:127-128` 注释引用裁决 OPEN-004） |
| `md_render/meta.py:40` | `intraday` | 与发布层相反 |

**当前恰好未显形的原因**：`meta.py` 的 `extract_meta()` 走 L2 启发式，
上游 `stock_assistant.md` 第 3 行自带 `data_stage: pre_open`，
实测返回 `{'rating':'进攻','stage':'pre_open','source':'heuristic'}`，
绕过了 `SLUG_STAGE`。一旦 md 缺该声明，L2 落空即回落到错误的 `intraday`。

`meta.py:22` 自陈「复制而非 import：反向 import 会把整条发布管线拖进渲染进程」——
顾虑成立，但代价是两处独立漂移。裁决见 `docs/decisions/ADR-004.md` 决策三。
归口建议：并入 A-09 一并处理，避免与 PM 侧同时改 `md_render/meta.py`。

**统计：22 条，其中 P0 = 6 条、P1 = 9 条、P2 = 7 条。**

P0 五条的执行顺序建议：A-01（入 Git）必须最先做，它是所有改动的回滚能力保障；
A-02 / A-03 是已在线上产物里显形的正确性缺陷，与 A-01 无依赖可并行；
A-04 → A-05 → A-09 是同一条迁移链，务必按序。

---

## 6. 附：三个新发现 P0 的完整证据

### 6.1 背景色被收敛成文字 Token（`sanitizer`）

**现象**：`publish_to_github.py` 运行时输出
```
[sanitize] [style] <style>: background → var(--warn)
[sanitize] [style] <style>: color → var(--warn)
[sanitize] [style] <style>: border → 2px solid var(--warn)
```

**根因实测**：

```python
>>> from sanitizer import token_map as TM
>>> TM.token_for_hex('#f59e0b', role='bg')    # 背景角色
'--warn'                                        # ← 文字 Token
>>> TM.token_for_hex('#3b82f6', role='bg')
'--accent'                                      # ← 文字 Token
```

`token_map.py:168` 的 `FAMILY_ROLE_TOKEN` 已正确定义了
`"warn": {"bg": "--rating-balanced-wash"}`，但 `token_for_hex()`（`:223`）只在
`ROLE_OVERRIDE`（`:234`，**仅 4 条**）命中时才走 role 覆写；`#f59e0b` 不在这 4 条里，
于是落到平表 `HEX_TO_TOKEN`（`:238`）直接返回 `--warn`。

**这正是 `style_pass.py:65-68` docstring 自己警告的错误类型**：

> *"不区分 role 会把 color:#FFFFFF 映射成 var(--surface)（浅色模式下白底白字，文字直接消失）—— 这类沉默错误正是本任务最需要防的。"*

role 机制建好了，但平表兜底路径绕过了它。`token_map.py:241` 只防了"文字角色拿到 wash"，**没防"背景角色拿到文字 token"**——这是守卫的另一半缺口。

**已污染产物**：
```
_stage/docs/daily/2026-10-16/daily-review.html:background: var(--warn)
_stage/docs/daily/2026-10-16/fund-market.html:background-color: var(--warn)"></span>
命中文件数: 2
```

视觉后果：`--warn` 是警告色文字 Token，被当作背景后，该区块底色与警告文字同色——浅色模式下文字融入背景，**与 style_pass 自己写的失败模式完全一致**。

**修法**（A-02）：在 `token_for_hex()` 的 `role == "bg"` 分支加对称守卫——
```python
if role == "bg" and tok in _TEXT_TOKENS:
    return None   # 让调用方记 unmapped-color 显式报告，不静默换错
```
`FAMILY_ROLE_TOKEN` 里所有 `"bg"` 值均以 `-wash`/`-alt` 结尾，可用此判据，
`__init__` 时断言一次表自洽。

### 6.2 缺失任务静默跳过（`publish_to_github.py`）

**现象**：2026-10-16 的 15:05 股票复盘目录**没有 `stock_review.md`**，发布结果只有 4 个 slug：

```
stock-assistant  md=True  html=True
fund-market      md=True  html=True
fund-guide       md=True  html=True
daily-review     md=False html=True
                                  ← stock-review 整条不存在
```

而 `publish_to_github.py` 退出码 **0**（`echo $?` 实测）。

**根因**（`publish_to_github.py:185-201`）：

```python
for slug, (dir_name, candidates) in TASK_SOURCES.items():
    d = src_root / dir_name / date
    if not d.is_dir():
        continue                      # ← 目录在但不产 md 时：entry 为空
    entry = {}
    for fname in candidates:
        p = d / fname
        if p.exists():
            entry[p.suffix.lstrip(".")] = p
    if entry:                         # ← 有 json 也算 entry，非空即收录
        outputs[slug] = entry
return outputs                         # ← 缺失 slug 无任何标记
```

15:05 目录**存在**且 `TASK_SOURCES` 声明的 `stock_review.md` 不存在，但目录下有
`market_data.json`/`settlement.json` 等——`entry` 只收录 `candidates` 里存在的文件，
若 candidates 全缺则 `entry` 为空、`if entry:` 不成立、`continue` 静默跳过。

**为什么这是 P0**：docstring 第 5 行声称退出码 `2` = "无产出 / 参数错误"，
但**部分**任务缺失从不走 `2`。定时任务侧只判退出码，会把"15:05 没写报告"当成成功，
读者在站点上看不到当日复盘却**无任何告警**。这比直接失败危险得多——它是一个
静默的内容缺口。

**修法**（A-03）：`collect()` 返回 `(outputs, missing)`；`main` 在 `missing` 非空且
未显式 `--allow-missing` 时返回退出码 2，并在 manifest 记 `missing_tasks: [...]`。

### 6.3 站点不在版本控制下

```
$ git status --short
fatal: not a git repository (or any of the parent directories): .git
```

59 个 py 脚本 + `design-tokens.json` + `market_data.schema.json` +
`report_contract.yaml` + `APPLE-DESIGN-SPEC.md`（41KB）等全部无历史记录。
`_stage/manifest.json:335-337` 里甚至记录着脚本的绝对路径，说明发布链路已经依赖
这份不在版本控制下的代码。

这是所有其他待办的前置风险：A-02~A-18 的任何改动都没有回滚能力。

---

## 7. 技术栈锁定声明

```
Python        3.13.12（实测运行版本）；最低 3.10（受 X | None 语法约束）
第三方依赖    无。scripts/ + framework/ 实测纯标准库
              （唯一自研替代：framework/scripts/yaml_min.py，205 行 YAML 子集解析）
测试框架      unittest（现状）→ 迁移期保持，CI 层可用 pytest 兼容运行
包管理        无 lock 文件需求（零第三方依赖）；A-17 落地 README 版本声明
平台约束      依赖 /Users 之外的绝对路径仅 MANAGED_PY 一处（A-04 后消除）
              → 迁移后全站可在任意 POSIX 路径运行
路径解析      统一入口 framework/scripts/paths.py（骨架见 §1.4）
              环境变量 4 个：PULSE_WORKBUDDY_ROOT / PULSE_SITE_ROOT /
                           PULSE_FRAMEWORK_ROOT / PULSE_ENGINE_SCRIPTS
              测试追加 2 个：PULSE_FIXTURE_ROOT / PULSE_FIXTURE_DAY
```
