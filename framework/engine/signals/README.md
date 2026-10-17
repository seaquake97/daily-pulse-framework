# framework/engine/signals/ — 引擎确定性脚本（框架侧 canonical）

daily-decision-engine 决策协议中**可确定性执行**的四个脚本：信号评分、市场数据硬校验、
持仓解析、观点台账结算。评级由代码计算，LLM 禁止参与打分、禁止上调/下调。

## 单一事实源声明（本目录存在的理由）

引擎脚本历史上有三份副本靠人肉同步，已经造成漂移（`parse_holdings.py` 的 MEMORY 路径
分歧，见 `docs/GAP-ARCH-工程侧待办清单.md` §4.4）。自 A-09（2026-10-17）起归属如下：

```
framework/engine/signals/      <- 本目录：框架侧 canonical，修改只允许发生在这里
          |
          |  同步方向（单向，禁止逆行）
          v
_engine_stage/scripts/         <- 引擎仓发布中转（staging）：要发 GitHub 时先同步到这里
          |
          v
GitHub seaquake97/daily-decision-engine   <- 开源发布仓
```

三条规则：

1. **修改顺序只能是 framework → _engine_stage → GitHub。** 禁止从 `_engine_stage` 或
   生产技能目录（`$HOME/.workbuddy/skills/daily-decision-engine/scripts`）反向改回
   本目录——那是漂移的入口，本目录落后一分，线上就多一分不可解释。
2. `_engine_stage/` 在生产技能与 GitHub 之间保留为发布中转，本目录不直接覆盖生产技能；
   生产技能的更新走发布管线。
3. 四个脚本之间**零互相 import、纯标准库**，这是它们可以被任意一方安全复用的前提，
   迁入后仍然成立（`test_signals.py` 覆盖）。

## 版本状态（2026-10-17 skew 已裁决：v1.4.0 回合）

`compute_signals.py` 已回合至 **v1.4.0**：S4「分化 + 动量确认」复合信号
（`signal_momentum.py` + `--rsi/--bias/--strong-trend` 入参）由 GitHub 引擎仓
同步进本目录，回合时与引擎仓 v1.4.0 做了字节级回归（同一 fixture 下 stdout 与
`verdict.json` 逐字节一致）。向后兼容铁律不变：不传入参时 S4 与 v1.2 逐字节一致
（黄金副本由 `test_compute_signals.py` 守护）。自此本目录 = v1.4.0，且为唯一 canonical；
下一次同步方向仍是 framework → _engine_stage → GitHub。

## 文件清单

| 文件 | 职责 | 本次迁入变更 |
|---|---|---|
| `compute_signals.py` | 步骤 5：S1-S6 信号评分 → Σ → 四档评级（v1.4.0 含 S4 动量复合） | 纯搬迁 + v1.4.0 回合 |
| `validate_market_data.py` | 步骤 3：market_data.json 硬校验（失败 → rating=暂停） | 纯搬迁 |
| `settle_viewpoints.py` | 步骤 7：观点台账四态结算 + 命中率 | 纯搬迁 |
| `parse_holdings.py` | 步骤 4：MEMORY.md 持仓解析 | 纯搬迁 + 前缀推断收敛（A-10），见下 |
| `technical.py` | 个股技术指标库（MA/BIAS/Wilder RSI/MACD） | 既有文件，未改动 |
| `test_technical.py` | `technical.py` 单测（13 例） | 既有文件 |
| `test_signals.py` | 四脚本回归套件（24 例，全离线） | 新增 |

`parse_holdings.py` 的两处纪律：

- **A-05（来源纪律）**：持仓记忆文件只认 `--memory` 参数与 `DECISION_ENGINE_MEMORY`
  环境变量，二者皆缺报错退出（exit 2），不存在任何隐式默认文件。
- **A-10（前缀收敛）**：`full_code()` 不再自己维护 `sh/sz/bj` 前缀规则表，改为委托
  `framework/scripts/codes.py` 的 `normalize_code()`——规则表只存一处。适配器保留
  原契约（表格行解析失败返回 `None`）与历史行为（大写显式前缀按数字段重推断），
  3527 例语料属性测试确认迁入前后逐一致；一致性由 `test_signals.py` 长期看守。

## 依赖方向（禁止成环）

```
framework/scripts/paths.py    叶子，只依赖 os/sys/pathlib
framework/scripts/codes.py   叶子；parse_holdings.py 的唯一项目内依赖方向：
                              signals/parse_holdings.py -> scripts/codes.py
signals/*.py 四脚本           彼此零 import
```

`codes.py` 不得反向 import `signals/`。路径解析一律走 `framework/scripts/paths.py` 的
环境变量约定；本目录四个脚本的输入全部由 CLI 参数显式传入，无隐式默认路径。

## 验证

```bash
python3 framework/engine/signals/test_signals.py     # 24 例
python3 framework/engine/signals/test_technical.py   # 13 例
python3 scripts/ci_verify.py                          # 两套均纳入统一门禁
```

A-09 字节级回归证据（2026-10-17）：迁入前后对同一 fixture 分别跑 `_engine_stage/scripts/`
与 `framework/engine/signals/` 两版，`compute_signals`（stdout、`-o` verdict.json、
合入后的 market_data.json）、`validate_market_data`（stdout）、`settle_viewpoints`
（stdout、settlement.json）、`parse_holdings`（stdout、holdings.json）共 8 份产物
`diff` 全部为空、md5 一致，退出码全部为 0。
