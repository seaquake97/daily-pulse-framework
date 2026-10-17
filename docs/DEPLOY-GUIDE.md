# GitHub 上传 / 部署指引（daily-market-pulse）

> 面向「新人接手 / 重新部署」场景。照着做就能把当日产出发布到 GitHub Pages 公开站点
> `https://seaquake97.github.io/daily-market-pulse/`。
> 本文命令均经源码核对（`scripts/publish_to_github.py`、`scripts/push_repo.py`、
> `framework/scripts/paths.py`、`scripts/scan_compliance.py`、`scripts/verify_published.py`），
> 可直接复制执行。
> 最后核对：2026-10-16（基于 PROGRESS.md 实测状态）。

---

## 0. 一句话心智模型

站点不是「把 github-ip-plan 推到 GitHub」。真实链路是：

```
5 个每日任务产出（WorkBuddy 任务目录）
        ↓  collect（按日期读取 .md/.html）
publish_to_github.py --date <日期> [--push]     # 编排：构建 _stage + 写 manifest
        ↓  _stage/docs 构建产物（构建暂存，可重建）
push_repo.py  →  git push  →  _git_pulse（线上源仓）  →  GitHub Pages
```

- `_git_pulse` 才是**唯一线上产物**，GitHub Pages 直接读它的 `docs/`。
- `github-ip-plan` 只是框架 + 发布脚本，本身**不进 GitHub Pages**。
- `_git_engine` 是决策引擎副本，**不参与部署**。

---

## 1. 仓库结构总览（三者关系与 git 边界）

工作区根：`/Users/lianghaizhen/WorkBuddy/2026-10-14-10-29-45/github-ip-plan`
（下文用 `$ROOT` 指代）。

| 目录 | 角色 | 是否 git 仓 | 边界 / 注意事项 |
|------|------|-------------|----------------|
| `$ROOT`（github-ip-plan） | 框架 + 发布脚本 + 站点规范文档 | 是（独立 .git，本地仓） | 只提交框架与脚本，**绝不**把它当成 Pages 源推送 |
| `$ROOT/_git_pulse/` | **线上 GitHub Pages 源**（daily-market-pulse 仓本体） | 是（独立 .git） | 远端 `origin` = `https://github.com/seaquake97/daily-market-pulse.git`，分支 `main`；只放 `docs/` 静态产物 |
| `$ROOT/_git_engine/` | 决策引擎（daily-decision-engine 技能副本） | 是（独立 .git） | 与站点发布无关，勿向 _git_pulse 误推 |
| `$ROOT/_stage/` | 构建暂存（publish 产物落点） | 否（被 .gitignore 排除） | 可由 `publish_to_github.py` 随时重建，丢了不慌 |
| `$ROOT/_engine_stage/` | 引擎暂存 | 否 | 与站点发布无关 |

`$ROOT/.gitignore` 已排除：`_git_pulse/`、`_git_engine/`、`_stage/`、`_stage_v2check/`、
`evidence/*.png`、`__pycache__/`。所以**在 `$ROOT` 里 `git add .` 不会碰嵌套仓**，
但仍要小心：进入 `_git_pulse` / `_git_engine` 目录后再操作 git，作用域只在那个仓。

### git 边界红线（勿混淆、勿误推）
- 不要对 `$ROOT` 执行 `git push` 把框架仓推成 Pages 站点——站点源是 `_git_pulse`。
- 不要在 `_git_pulse` 里手动 `git add` 框架脚本/文档——它只接受 `push_repo.py`
  从 `_stage/docs` 同步过来的静态产物。
- 不要在 `_git_engine` 里提交站点内容。

---

## 2. 首次克隆与目录准备

### 2.1 取得框架工作区
框架工作区 `$ROOT`（github-ip-plan）来自 WorkBuddy 项目。若从零重建，先把项目目录
放到 `$ROOT`，确保 `scripts/`、`framework/`、`docs/` 齐全。它本身是一个 git 仓
（`$ROOT/.git` 已存在）。

### 2.2 克隆线上源仓到 `_git_pulse`
`_git_pulse` 必须是 seaquake97/daily-market-pulse 的克隆（与线上同源，保留历史）：

```bash
cd "$ROOT"
git clone https://github.com/seaquake97/daily-market-pulse.git _git_pulse
```

验证：

```bash
git -C _git_pulse branch -a          # 应见 * main 与 remotes/origin/main
git -C _git_pulse remote -v          # origin 指向 daily-market-pulse.git
```

> `push_repo.py` 的 `ensure_repo()` 也能在 `_git_pulse` 缺失时自动 `git init -b main`
> 并设远端，但那会得到无历史的全新仓。重新部署请优先用上面的 `git clone` 保留历史。

### 2.3 决策引擎（可选，仅当需要在本机跑引擎）
```bash
cd "$ROOT"
git clone <daily-decision-engine 仓地址> _git_engine
```
它不参与部署，仅用于本地运行研判。数据来源 westock-mcp 是**平台级 MCP 连接器**
（在 agent / 连接器设置里配置），**不是本仓库内的文件或环境变量**，无需在此处配置密钥。

### 2.4 目录约定小结
```
github-ip-plan/                 ← 框架 + 发布脚本（本地 git 仓）
├── scripts/                    ← publish_to_github.py / push_repo.py / scan_compliance.py / verify_published.py ...
├── framework/                  ← paths.py / config / 引擎校验
├── docs/                       ← 本指引 + GAP-*.md + 设计规范
├── _stage/                     ← 构建暂存（gitignore，可重建）
├── _git_pulse/                 ← 线上源仓（独立 git，唯一线上产物）
└── _git_engine/                ← 决策引擎（独立 git，不参与部署）
```

---

## 3. 环境变量与凭证

### 3.1 托管 Python 解释器（必设）
`publish_to_github.py` 内部会用 `PULSE_MANAGED_PY` 调起子进程
（消毒 / 渲染 / 站点生成），默认指向 `~/.workbuddy/binaries/python/envs/default/bin/python3`。
本机实际可用的解释器是：

```
/Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3
```

建议把上述路径同时用于「运行脚本」与「子进程」两处，保证版本一致：

```bash
export PY=/Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3
export PULSE_MANAGED_PY="$PY"     # 让 publish 内部子进程也用同一解释器
```

### 3.2 GitHub fine-grained PAT（必设）
令牌文件位置由 `paths.GH_IP_TOKEN_PATH` 决定，**默认 `~/.config/gh-ip/token`**，
可用环境变量 `GH_IP_TOKEN_PATH` 覆盖（见 `framework/scripts/paths.py`）。

创建 / 续期令牌（权限 600，目录 700；令牌内容无换行）：

```bash
mkdir -p ~/.config/gh-ip && chmod 700 ~/.config/gh-ip
echo -n '<你的 fine-grained PAT>' > ~/.config/gh-ip/token
chmod 600 ~/.config/gh-ip/token
```

PAT 所需权限（在 GitHub → Settings → Developer settings 创建 fine-grained token）：
- `Contents: Read and write`
- `Administration: Read and write`（首次建仓用）
- `Pages: Read and write`（开启 Pages，可选）

安全铁律（来自 `push_repo.py` 与 `PUBLISH-CONVENTION.md`）：
令牌**只**经 `git -c http.https://github.com/.extraheader=...` 单次注入，
**永不**进入命令行参数、remote URL、`.git/config`、提交历史或日志。
令牌 90 天有效，到期前续期，否则推送失败（产出不丢，重推即可）。

覆盖默认路径的方式（如令牌放在别处）：
```bash
export GH_IP_TOKEN_PATH=/path/to/your/token
```

### 3.3 路径覆盖点（一般不用动）
来自 `framework/scripts/paths.py`，均可用环境变量覆盖：

| 变量 | 含义 | 默认推导 |
|------|------|----------|
| `PULSE_ROOT` | 项目根 github-ip-plan | `paths.py` 的 `__file__` 上级（`parents[1]`） |
| `PULSE_WORKBUDDY_ROOT` | 工作区根（任务产出所在） | `parents[3]`（即 `2026-10-14-10-29-45`） |
| `PULSE_MANAGED_PY` | 托管 Python | `~/.workbuddy/.../envs/default/bin/python3` |
| `GH_IP_TOKEN_PATH` | PAT 文件路径 | `~/.config/gh-ip/token` |

> 默认路径均由 `paths.py` 相对定位，**不写死用户名**，换机通常无需改。
> 仅在迁移目录或被 CI 调用时才显式 export。

---

## 4. 本地构建流程（仅 _stage，不推送）

```bash
cd "$ROOT"
$PY scripts/publish_to_github.py --date 2026-10-16
```

- `--date` 必填，格式 `YYYY-MM-DD`。
- 默认 **dry-run**：只构建 `_stage`、写 `manifest.json`，**不推送**（不传 `--push`）。
- 等价于「先演练」，推送前置条件（令牌就位）会在末尾预检并打印。

### 4.1 核验 _stage 产物
构建成功后检查：

```bash
# 当日详情页 + 索引
ls -1 _stage/docs/daily/2026-10-16/
#   期望含：meta.json  entries.json  <slug>.html  <slug>.md
ls -1 _stage/docs/index.html _stage/docs/feed.xml _stage/docs/sitemap.xml

# 合规扫描（P0 门禁）：emoji(P0) 必须为 0、紫粉/渐变必须为 0
$PY scripts/scan_compliance.py
```

`scan_compliance.py` 输出重点关注：
- `emoji 数（P0 口径）: 0`（团队 P0-1 硬规则；否则见第 7 节「emoji 回归」）
- `紫粉渐变/靛蓝: 0`（团队 P0-2 硬规则）
- 上游详情页 `gradient 数: 0`、`<script 数: 0`

> 已知噪声（PM-15 进行中）：扫描里「弹跳缓动: 11」是 CSS 注释内的**假阳性**，
> 真实违规为 0，当前**不阻断**发布，待 PM-15 收口后归零。不要因为它而误判失败。

### 4.2 可选参数
| 参数 | 作用 |
|------|------|
| `--task <slug>` | 只发布单个任务（如 `stock-assistant`）；其余缺失不报 2 |
| `--source-root <dir>` | 覆盖任务产出根目录（默认 `PULSE_WORKBUDDY_ROOT`） |
| `--no-sanitize` | 跳过发布层消毒（回退通道）；若目标日期存在早于消毒代码的陈旧产物，会被 B-8 时点护栏**阻断** |
| `--unified-render` | 统一渲染：一律由 `render_md.py` 从 md 生成详情页（历史日期重渲染用） |

---

## 5. 发布到线上（--push）

```bash
cd "$ROOT"
$PY scripts/publish_to_github.py --date 2026-10-16 --push
```

流程（由 `push_repo.py` 执行）：
1. `read_token()` 读 `GH_IP_TOKEN_PATH` 的 PAT（缺失/过短直接报错）。
2. `verify_token()` 校验令牌身份 == `--owner`（默认 `seaquake97`），防推错账号。
3. `sync_stage()` 把 `_stage/docs` 同步进 `_git_pulse/docs`（逐字节对比，删旧增新）。
4. `git commit`（内容无变化则**幂等跳过**，不产生空提交）。
5. `git push -u origin main`。

### 5.1 GitHub Pages 配置（在仓库 Settings → Pages）
- Source（源）：**Deploy from a branch**
- Branch：**`main`**
- Folder：**`/docs`**（站点 `index.html` 位于 `_git_pulse/docs/index.html`）

线上地址：`https://seaquake97.github.io/daily-market-pulse/`
（若你的仓库改用 `gh-pages` 分支承载，发布时加 `--branch gh-pages`。当前仓默认 `main`。）

### 5.2 发布后验证（漂移校验）
```bash
# 逐文件比对 _stage 与 _git_pulse，并做内容级断言（降级条目不得带方向值）
$PY scripts/verify_published.py            # 人类可读
$PY scripts/verify_published.py --json     # 机器可读
```
- 退出码 `0`：stage 与线上一致、内容契约通过。
- 退出码 `1`：发现漂移（文件数 / 内容不一致 / 内容违规），需重推。
- 退出码 `2`：目录缺失等 IO 错误。
- 同时人工访问 `https://seaquake97.github.io/daily-market-pulse/` 确认当日时间线、
  评级、摘要正常呈现。

> 事故教训（CAP-03 / 2026-10-16）：推送成功 ≠ 发布成功。必须跑 `verify_published.py`
> 确认漂移 = 0，否则线上可能仍在输出「数据源降级」与「进攻 +0.510」的危险组合。

---

## 6. CI / 门禁校验清单（发布前必跑）

发布当日产物前，按下面顺序跑完。**任一项不通过则不得 `--push`**。

### 6.1 14 套单元测试（全绿才放行）
13 个在 `scripts/`，1 个在 `framework/scripts/`：

```bash
cd "$ROOT"
PY=/Users/lianghaizhen/.workbuddy/binaries/python/versions/3.13.12/bin/python3
for t in \
  scripts/test_conclusion_contract.py \
  scripts/test_content_contract.py \
  scripts/test_dark_mode.py \
  scripts/test_emoji_body.py \
  scripts/test_frame_fixed_point.py \
  scripts/test_path_scrub.py \
  scripts/test_real_outputs.py \
  scripts/test_render_md.py \
  scripts/test_sanitize_gate_pipeline.py \
  scripts/test_sanitize_gate_visual.py \
  scripts/test_sanitize_pipeline.py \
  scripts/test_sanitize_scope.py \
  scripts/test_site_links.py \
  framework/scripts/test_validate_config.py ; do
  echo "### $t"
  "$PY" "$t" || { echo "FAIL: $t"; exit 1; }
done
echo "ALL 14 PASS"
```

### 6.2 合规扫描（P0 门禁）
```bash
$PY scripts/scan_compliance.py
# 必为 0：emoji 数（P0 口径）、紫粉渐变/靛蓝、上游详情页 gradient 数、<script 数
```

### 6.3 发布后漂移校验（推送后再跑）
```bash
$PY scripts/publish_to_github.py --date 2026-10-16 --push
$PY scripts/verify_published.py        # 必须 drift=0 且 内容违规=0
```

### 门禁速查表
| 门禁 | 命令 | 通过标准 |
|------|------|----------|
| 单元测试 | 6.1 循环 | 14 套全绿 |
| 合规（P0） | `scan_compliance.py` | emoji(P0)=0、紫粉/渐变=0、script=0 |
| 漂移 | `verify_published.py` | drift=0、内容违规=0 |

---

## 7. 常见故障排查

### 7.1 publish 退出码 2（缺失任务）
现象：`❌ 部分/全部任务产物缺失（实收 X/5）——发布中止（退出码 2）`，stdout 列出缺失任务名与预期目录。
根因（A-03）：当日某任务目录不存在或无 `.md/.html` 产物，`collect()` 在写 `_stage` 前中止——
缺的产物**不会**进 `_stage`，避免「发布 4 条、看起来像成功」的静默事故。
处理：
1. 按 stdout 给出的「预期目录」补跑缺失的上游任务（如 `股票助手/2026-10-16/stock_assistant.md`）。
2. 同一命令重跑（幂等，不重复提交）。
3. 若只需发布已就绪的单个任务：`--task <slug>` 只跑那一个（不报 2）。

### 7.2 _stage 与 _git_pulse 漂移（verify_published 退出码 1）
现象：`[fail] 漂移 N 个文件`。
处理：重推即可（幂等）。
```bash
$PY scripts/publish_to_github.py --date 2026-10-16 --push
$PY scripts/verify_published.py
```
> 已知历史坑：A-03 重建某日 `_stage` 后未同步 `_git_pulse`，会产生大量漂移文件；
> 重推一轮归零。

### 7.3 推送失败（退出码 6 / 令牌过期）
现象：`❌ 推送失败: ...` 或 `令牌文件不存在` / `令牌校验失败 HTTP 4xx`。
处理：
- 令牌过期/误删：重建并写入（见 3.2），再同一命令重推。
- 令牌身份与 `--owner` 不符：`verify_token()` 会拒绝，检查 PAT 所属账号。
- 产出不丢，主任务不受影响；修复后 `--push` 重推（幂等）。

### 7.4 429 额度（子代理 / 数据源）
数据源 westock-mcp 走平台 MCP 连接器，调用受 GitHub / 连接器配额限制，可能返回 429。
这发生在**取数层（每日任务产出阶段）**，不在 `publish_to_github.py` 内。
处理：等待配额恢复后重跑对应每日任务，再走发布流程；发布脚本本身与 429 无关。

### 7.5 emoji 回归（PM-07）
现象：`scan_compliance.py` 报 `emoji 数（P0 口径）> 0`。
处理：重跑发布层消毒（正常路径默认执行）；若为 `ip-mark` 内残留，检查
`scripts/sanitizer/emoji_map.py` 的 SVG 策略是否生效。**emoji>0 不得发布**。

### 7.6 降级态详情页含可执行动作（L-4，进行中门禁）
现象：`verify_published.py` 或内容审查发现 degraded 页含「挂单 / 卖出 N 股 / 买入 N 股 /
逢低加仓 / 分批高抛 + 数量」等动作指令词。
规则（C-9 / L-4）：数据源降级时**只陈述状态，撤下标准动作与关键事实**，
降级页不得带可执行动作。若命中，应拒绝发布并在内容层清理动作段后重渲。

---

## 8. 异常终止快速拉起

session 中断后，按以下顺序重新拉起，无需从零：

1. 先读 `PROGRESS.md`（末尾「四、异常终止快速拉起手册」）+ `docs/GAP-*.md`
   五份缺口清单：`GAP-A-采集三步缺口清单.md`、`GAP-ARCH-工程侧待办清单.md`、
   `GAP-UI-设计侧待办清单.md`、`GAP-LEAD-总监自查待办清单.md`、`GAP-PM-产品侧待办清单.md`。
2. 已闭环任务（PROGRESS 第一节）**勿重做**，仅用其「验收命令」复核。
3. 进行中任务（PROGRESS 第二节）重新 spawn 对应专家，prompt 附该条目的
   「落点文件 + 验收命令」。例如「重推站点（运维）」需先等 L-4 完成，再执行：
   ```bash
   $PY scripts/publish_to_github.py --date 2026-10-16 --push
   $PY scripts/verify_published.py     # 确认 degraded rating=None 生效、emoji=0
   ```
4. 未决根因 / 已知坑见 `scripts/pitfalls.jsonl`（如有）与项目 MEMORY。
5. Python **必须用托管 runtime**（见 3.1），勿用系统 python。

---

## 附：关键路径与退出码速查

**关键路径（来自 `framework/scripts/paths.py`）**
- `PROJECT_ROOT` = `$ROOT`（github-ip-plan）
- `STAGE` = `$ROOT/_stage`
- `GIT_PULSE` = `$ROOT/_git_pulse`
- `GIT_ENGINE` = `$ROOT/_git_engine`
- `GH_IP_TOKEN_PATH` = `~/.config/gh-ip/token`（可 `GH_IP_TOKEN_PATH` 覆盖）
- `MANAGED_PY` = `PULSE_MANAGED_PY`（默认 `~/.workbuddy/.../envs/default/bin/python3`）

**publish_to_github.py 退出码**
| 码 | 含义 | 动作 |
|----|------|------|
| 0 | 成功（dry-run 完成 / 推送完成 / 幂等跳过） | 继续 |
| 1 | 已废弃（原脱敏门禁） | — |
| 2 | 任务产物缺失 / 无产出 / 参数错误 | 补产物后重跑 |
| 3 | 站点生成失败 / 消毒失败 / 时点护栏阻断（B-8） | 查 stderr |
| 4 | manifest 写入失败 | 查磁盘/权限 |
| 5 | 结构或幂等校验失败 | 查校验输出 |
| 6 | 推送失败 | 修令牌后重推 |

**verify_published.py 退出码**：0 一致｜1 漂移/内容违规｜2 IO 错误。
