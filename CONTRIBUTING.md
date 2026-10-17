# Contributing to daily-pulse-framework

感谢参与。本仓是「研判 → 呈现 → 发布」全链路的框架资产，所有改动必须通过同一套质量门禁——这与项目「同数据同结论」的定位一致：**同一份代码，必须产出同一份质量**。

## 开发环境

- Python ≥ 3.10（无第三方依赖；若提示缺包，说明引入了不该有的依赖）
- 克隆后即可跑单元测试：`python3 scripts/test_conclusion_contract.py`
- 一键总调度：`python3 scripts/ci_verify.py`（27 项，需本机存在 `_stage/` 与任务产物时全绿；缺产物时集成测试套件按设计 skip）

## 提交规范（Conventional Commits）

```
<type>(<scope>): <subject>

type:  feat | fix | docs | style | refactor | perf | test | chore | revert
scope: engine | collect | signals | render | sanitizer | site | publish | ci | docs | config
```

示例：`feat(site): 首页新增今日一屏区块，当日结论首屏可达`、`fix(sanitizer): 背景角色不再收敛为文字色 token`。

## 分支与 PR 流程

1. 从 `main` 切出分支：`feat/<简述>` 或 `fix/<简述>`
2. 保持单个 PR 单一职责；PR 描述写清「动机 / 改动 / 验收证据」
3. PR 必须满足（CI 自动检查 + 评审确认）：
   - `python3 scripts/ci_verify.py` 全绿（本机）
   - `python3 scripts/scan_compliance.py` P0 违规计数全 0
   - `python3 scripts/probe_responsive.py` 192 组合零横滚（改了页面时）
   - `python3 scripts/verify_published.py` 漂移 0（改了发布链路时）
4. 至少一人评审通过后 squash 合并；禁止直接推 `main`

## 改动纪律（P0 绝对规则，违反即退回）

1. **零 emoji 功能图标**：只允许项目锁定的 Lucide 描边 SVG 符号（`site_theme.SYMBOLS`），emoji 仅可出现在用户生成内容里
2. **零紫粉渐变主视觉**：全站无 gradient token，也不接受组件层 gradient 字面量
3. **零硬编码颜色**：唯一例外 `#fff` / `#000`，其余一律 `var(--token)`
4. **零 JS**：生成页面为纯静态；交互只允许 `<details>` 等原生机制
5. **禁弹跳缓动**：不使用 `cubic-bezier(0.68,-0.55,0.265,1.55)` 类曲线
6. **单文件 ≤ 300 行**（Python 源文件，`test_ci_verify.py` 有机检）

## 代码组织

- 依赖只向下：`paths.py`（叶子）→ `codes.py` → `rules.py` → `validate_config.py`；`framework/*` 不得 import `scripts/*`，两侧只经 `run_pipeline.py` 的 subprocess 边界通信
- 入口文件只装配零业务；逻辑下沉 service 层
- 同一规则不允许存在两份可独立漂移的实现——要么共享模块，要么单一事实源 + 一致性测试

## 报告问题

使用 Issue 模板（Bug report / Feature request）。涉及「页面结论自相矛盾」「降级态可执行动作」「数据缺口被填 0」三类问题请直接标为 P0——它们是金融场景的最高危缺陷。
