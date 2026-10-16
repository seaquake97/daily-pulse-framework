# 定时任务发布约定（每日 GitHub 内容站）

> 本文件是 6 个每日研判定时任务与 GitHub 内容站之间的**唯一契约**。
> 修改推送行为前必读。

## 架构

```
定时任务（5 个产出任务）
    ↓落盘到各自目录
/Users/lianghaizhen/WorkBuddy/<任务名>/<YYYY-MM-DD>/*.md|html
    ↓ 15:30 唯一推送者触发
publish_to_github.py --date <今日> --push
    ↓
push_repo.py（git + fine-grained PAT）
    ↓
github.com/seaquake97/daily-market-pulse → GitHub Pages
```

## 单一发布者原则

**只有 15:30 每日总复盘（automation-1785332237194）执行推送**，其余 5 个任务只做 dry-run 自检。

原因：6 个任务同日写同一分支会产生 push竞争，且 9:28/11:00/14:30 的产出尚未收齐，
提前推送会导致时间线残缺。15:30 是当日最后时点，此时 5 份产出已全部落盘。

| 任务 | 时点 | 角色 |
|---|---|---|
| 股票助手 automation-1784899435961 | 9:28 | dry-run 自检 |
| 基金盘面 automation-1785247840681 | 11:00 | dry-run 自检 |
| 基金指引 automation-1785247840781 | 14:30 | dry-run 自检 |
| 股票复盘 automation-1785245996901 | 15:05 | dry-run 自检 |
| **每日总复盘 automation-1785332237194** | **15:30** | **唯一推送者** |
| v2 决策引擎 cloud:12209141 | 15:31 | dry-run 自检（顺延次日）|

## 认证

- 令牌：`~/.config/gh-ip/token`（fine-grained PAT，权限 600，目录 700）
- 必要权限：`Contents: Read and write`、`Administration: Read and write`（建仓）、`Pages: Read and write`（开 Pages，可选）
- **安全铁律**：令牌只经 `git -c http.https://github.com/.extraheader=...` 单次注入，
  永不进入命令行参数、remote URL、`.git/config`、提交历史、日志。
- 令牌 90 天有效。到期前需续期，否则推送失败（产出不丢，修复后重推即可）。

## 幂等性（关键）

同一天重复执行必须**不产生新提交**，否则 GitHub 提交历史会被空提交淹没。

已剔除的易变字段：

| 位置 | 字段 | 处理 |
|---|---|---|
| `daily/<date>/meta.json` | `generated_at` | 落盘前 `pop`（首次发布时点记在 `manifest.pushed_at`）|
| `methodology/index.html` | `__GENERATED_AT__` | 改注入「当期数据日期」而非运行时刻 |
| `index.html` | 「最近更新」 | 用当期日期，不用运行时刻 |

验证方法：
```bash
for i in 1 2 3; do
  find _stage/docs -type f | sort | xargs shasum -a 256 | shasum -a 256 | cut -c1-16
done
# 三次输出必须完全相同
```

## 退出码

| 码 | 含义 | 任务动作 |
|---|---|---|
| 0 | 成功（dry-run 完成 / 推送完成 / 幂等跳过） | 继续 |
| 1 | 已废弃（原脱敏门禁） | — |
| 2 | 当日无产出 | 静默结束（非失败）|
| 3 | 站点生成失败 | 记录异常，不阻塞主任务 |
| 4 | manifest 写入失败 | 记录异常，不阻塞主任务 |
| 6 | 推送失败 | 记录原因，**不阻塞主任务**，修复后重推 |

## 故障韧性

推送失败**绝不影响主任务产出**。修复路径：

```bash
# 令牌过期/误删 → 重新创建后写入
echo -n '<新token>' > ~/.config/gh-ip/token && chmod 600 ~/.config/gh-ip/token
# 同一命令重推（幂等，不会有重复提交）
$PY .../publish_to_github.py --date <今日> --push
```

## 站点结构约定

- 每日时间线数据源：`daily/<date>/entries.json`（由 `extract_entry()` 生成）
- 排序键：`time` = **调度时点**（09:28→11:00→14:30→15:05→15:30）；`run_time` = 实际生成时刻，仅作副标展示
- 链接文案必须是**产出文件的真实 H1 标题**，禁止「阅读网页版 / HTML」这类无信息标签
- Markdown 仍提交入库，但**不在页面做导航展示**（读者点进去只看到源码）
- 数据时点按任务性质判定（`SLUG_STAGE`），不能一律套用全局 `verdict.data_stage`

## 脱敏状态：已移除

2026-10-14 起，发布链路**不做任何脱敏**，内容原样呈现。

原脱敏层（`desensitize.py` / `redline_hardening.py`）已归档至
`scripts/_archive/desensitize_20261014/`。移除原因不只是隐私偏好——
它会**破坏可见文本**（实测把「11:00午盘版」写成「[已脱敏]:00午盘版」，
把「2026-10-14日」写成「2026-10-[已脱敏]票」），导致站点信息不可读。