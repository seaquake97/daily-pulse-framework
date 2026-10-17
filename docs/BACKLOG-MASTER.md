# BACKLOG-MASTER — 未完成事项总账（产品 × 框架双维审计）

> 审计人：韦优（项目总监）｜日期：2026-10-17
> 方法：读取全部交互上下文（PROGRESS.md、五份 GAP 清单、50 项任务列表、项目记忆），
> 并对每条「未完成」主张做**当前产物实测**——不照抄过期清单。实测命令与输出本文附录可复跑。
> 定位：这是「还有什么没做完」的**唯一权威清单**。各 GAP-*.md 是分线明细，本文是汇总与排期。

---

## 0. 一句话结论

上轮（10-16）把「手机端体验」这条线做到了 100% 闭环并推送；本轮（10-17）把「GitHub 管理」从零补齐到常见模式（框架仓上线 + 引擎仓同步 + 门面四件套 + tag/release）。

**当前真实状态**：框架与治理债基本清零，剩下的是**产品债**——站点对「每天回访的用户」仍有三个真缺口：首页不回答「今天该做什么」、RSS 只给日期不给结论、周月报是同内容两个壳。另有 2 项基础设施（PAT scope、内容仓可见性）需用户决策。

## 1. 已完成基线（本轮 2026-10-17，均附证据）
| # | 事项 | 证据 |
|---|---|---|
| D-1 | 方法论页 Apple 风格双端重构（920px 容器/吸顶胶囊/七步网格/双列对比/9 模块：新增双重护栏+多源容灾+S4 公式） | `site/methodology/index.html` 重写；probe 192 组合零横滚；commit 320ee7e 上线 |
| D-2 | 框架仓 `seaquake97/daily-pulse-framework` 创建并全量推送（199 文件，HEAD 4b82f15 本地远端一致） | GitHub API 树比对 |
| D-3 | 引擎仓 `daily-decision-engine` 同步 canonical（S4 动量+路径参数化一直在工作区未提交），tag v1.3/v1.4.0 + Release | commit c11d8ef + release 页 |
| D-4 | GitHub 门面四件套：README（三仓架构/快速开始/仓库地图/环境变量/文档索引）、CONTRIBUTING、Issue×2+PR 模板、CHANGELOG、MIT LICENSE | 已在仓内 |
| D-5 | `.gitignore` 两处静默失效修复（行内注释致 pattern 永不匹配；framework 下 `*.json` 误吞两份契约文件） | `git check-ignore` 实测 + 白名单 |
| D-6 | 框架仓此前漏追踪 22 个源码文件补齐（ci_verify/verify_published/path_scrub/容灾五件套/策略三件套/两份 schema） | 199 vs 226→ 清点 |
| D-7 | `paths.py` 可移植性修复：WORKBUDDY_ROOT 默认值 `~/WorkBuddy`（原按 `__file__` 上溯四级，clone 到任意路径即错根） | 换目录实测 |
| D-8 | 集成测试守卫：test_render_md 产物缺失整体 skip（A-07） | 全新克隆 25 套件全绿实测 |
| D-9 | CI 工作流 `ci.yml`（单测层 + 「Ran 0 tests 假绿灯」判定）——**待令牌升级后入仓** | 见 §4 U-1 |

### 1.1 本轮追加闭环（2026-10-17 下午，逐项实测）

| # | 事项 | 证据 |
|---|---|---|
| D-10 | P-1 首页「今日一屏」上线 | `site_today.py`（100 行）；首页含最近交易日 5 条目评级+结论；390px 首屏可达 |
| D-11 | P-2 RSS 条目级化上线 | `site_feed.py`（109 行）；feed.xml 24 items == entries 总和；guid/pubDate 保证幂等 |
| D-12 | P-3 PWA 三件套上线 | `gen_app_icon.py`（纯标准库手写 PNG，字节确定）；manifest + apple-touch-icon + icon-192/512 + theme-color 双 meta |
| D-13 | 发布管线二进制 bug 修复 | manifest 读取改 read_bytes——PWA 图标会让 read_text(utf-8) 在 PNG 魔数处炸掉整条管线（前端实测发现） |
| D-14 | P-6 历史产物绝对路径清零 | 10-15 stock_review.md 源句按 PM-17 裁决改为「依据引擎自动结算结果」并重发布；三载体扫描 `/Users/` = 0 |
| D-15 | P-4/F-3 周月报真聚合上线 | `site_aggregate.py`（150 行）；周月 KPI（迁移/Σ 方向/防守/矛盾/条目）人工核对 10/10 一致；commit 4a028ee 上线 |
| D-16 | F-1 引擎四脚本迁入 framework/engine/signals/ | 字节级回归一致；A-10 前缀收敛至 codes.py 单一实现（3527 例语料零差异）；README 声明 framework → _engine_stage → GitHub 单向同步 |
| D-17 | v1.4.0 回合框架侧 | compute_signals + signal_momentum + test_compute_signals 自引擎仓同步，同 fixture 输出逐字节一致；ci_verify 28 项 |

### 1.2 两项总监裁决（记录在案）

1. **周月相似度代理指标废止（P-4 验收口径修正）**：原验收「两页相似度 < 0.9」被实测证伪——两页共享 58,982 字节内联 CSS，序列相似度 0.9934 由共享 CSS 支配（理论下限 0.86），可见文本口径 0.9528；周期重叠 5/6 天使诚实相异信息仅约 150–250 字符，压到 0.9 需每页新增约 2,547 字符低相似内容 = 编造。**裁决：采纳实质判据（两页含可审计的独有聚合指标且人工核对一致），废止相似度代理。** 判据变更理由：相似度度量的是「看起来不同」，不是「信息量不同」。
2. **v1.4.0 回合（架构师 advisory-1）**：框架侧 canonical 承载 v1.4.0（S4 动量复合），与 GitHub 引擎仓 v1.4.0 字节级一致；后续同步方向严格 framework → _engine_stage → GitHub，禁止以旧基线覆盖已发布版本。

## 2. 未完成事项总账（按域汇总，实测状态）

### 2.1 产品债（内容站对用户的价值缺口）

| 编号 | 事项 | 实测证据（2026-10-17） | 影响 | 优先级 |
|---|---|---|---|---|
| P-1 ✅D-10 | **首页「今日一屏」**：首屏无当日评级/标准动作（实测首页「今日」「该做什么」命中 0） | `_stage/docs/index.html` 全文检索 | 每天回访用户要翻到第 3 屏后才看到第一条任务卡；首页是「档案馆」不是「仪表盘」 | P0 |
| P-2 ✅D-11 | **RSS 条目级化**：feed.xml 仅 6 个 `<item>`（日期级），订阅者拿不到「今天该做什么」 | `feed.xml` 计数 | 订阅解决了「知道有更新」，没解决「看了怎么做」 | P0 |
| P-3 ✅D-12 | **PWA 三件套缺失**：manifest / apple-touch-icon / theme-color 均为 False | 产物检索 | iOS 加到主屏图标是空白截图；回访只能靠收藏夹 | P1 |
| P-4 ✅D-15（代理指标裁决见 §1.2） | **周报/月报同内容**：两页文本相似度 0.9937（仅标题词不同），无周月粒度聚合指标 | difflib 实测 | 「周报」「月报」是两个标签壳，导航入口给人假象 | P1 |
| P-5 | **持仓/基金标的不可点**：fund-guide 里「卖出 100 股平高电气」无站内落地页 | 15 链接全为导航 | 行动链最后一环断开；抄单用户无法回溯该标的历史建议 | P2（工程量大，需新建标的档案数据链） |
| P-6 ✅D-14 | **历史产物绝对路径残留**：`_stage/docs/daily/2026-10-15/stock-review.md` 仍含 `/Users/lianghaizhen` 完整路径（发布物，Pages 可直接访问） | 三载体扫描唯一命中 | 用户名+目录结构公开泄漏；与「产物不可篡改」纪律冲突，但隐私优先 | P1 |

### 2.2 框架债（引擎资产化剩余项）

| 编号 | 事项 | 实测证据 | 影响 | 优先级 |
|---|---|---|---|---|
| F-1 ✅D-16/17 | **引擎四脚本未迁入 framework/engine/signals/**（A-09/L-3）：目前 framework 内只有 technical.py；compute_signals 等 4 脚本仍在 `_engine_stage/` 与 `~/.workbuddy/skills/` 两处 | 目录实测 | 引擎存在「GitHub 仓 / _engine_stage / 生产技能目录」三份副本，靠人肉同步——已发生 parse_holdings 漂移实证 | P1 |
| F-2 | **R5 配置契约未落地**：`config/holdings.example.yaml` 不存在（R5 §6 一键复用第 2 步即断） | 目录实测 | 新用户无法按框架复用；`validate_config.py` 有器无示例 | P2 |
| F-3 ✅D-15 | **周/月报与日粒度同源渲染**（P-4 的工程侧根因）：site_pages.py 对周月复用全量日数据 | 源码 | 同 P-4 | P1 |
| F-4 | **单元/集成测试未分层**（A-06）：fixture 依赖套件与纯单测混在 scripts/，靠逐套 skip 守卫；CI 只能跑单测层 | 25 套件矩阵实测 | 「换机器全绿」已达成（D-8），但结构上仍是一层 | P2 |
| F-5 | **降级态三出口断言只剩两出口**：entries.json/feed.json 已置 None（实测 0 泄漏），页面徽章层由 site_render 的 None 范式保证，但 PC-5 断言未覆盖「页面不渲染 rating-* 徽章」 | GAP-PM PC-5 记录 | 字段对、页面仍可能错（该清单原论断）——当前无实测违规，属守护缺口 | P2 |

### 2.3 治理债（仓库与流程）

| 编号 | 事项 | 状态 | 优先级 |
|---|---|---|---|
| G-1 | **CI 工作流入仓**：PAT 缺 `workflow` scope，`ci.yml`/`daily_pulse.yml` 暂存本地未推送 | 待用户升级令牌（§4 U-1） | P0（30 秒操作） |
| G-2 | **内容仓可见性**：`daily-market-pulse` 为 public，含个人持仓研判（R5 §7.4 标注高风险） | 待用户决策（§4 U-2） | P1 |
| G-3 | **分支保护/必过 CI**：GitHub 仓级设置（Settings → Branches），需网页操作 | 待用户（§4 U-3） | P2 |
| G-4 | **`_engine_stage` 三份副本收敛**：F-1 落地后，_engine_stage 应退化为「发布到引擎仓的中转」，生产技能目录改由框架仓 hook 同步 | 依赖 F-1 | P2 |

## 3. 执行批次（依赖排序）

```
批次 1（进行中，治理）：G-1 待令牌 → 之后 workflows 入仓、开分支保护
批次 2（产品 P0，并行）：P-1 首页今日一屏 ｜ P-2 RSS 条目级 ｜ P-6 历史路径残留
批次 3（产品 P1）：P-3 PWA 三件套 ｜ P-4/F-3 周月真聚合
批次 4（框架 P1）：F-1 引擎迁入 + 三副本收敛
批次 5（产品 P2/框架 P2）：P-5 标的档案 ｜ F-2 配置示例 ｜ F-4 测试分层 ｜ F-5 页面徽章断言
```

## 4. 用户待决事项（不阻塞上述批次，但需本人操作）

| # | 事项 | 操作 | 影响 |
|---|---|---|---|
| U-1 | **PAT 加 `workflow` scope** | GitHub → Settings → Developer settings → Fine-grained tokens → 编辑现有令牌，勾选 Workflows 的 read/write；或推送时改用网页上传两个 workflow 文件 | G-1：CI 与云端定时编排入仓 |
| U-2 | **内容仓是否转私有** | `daily-market-pulse` Settings → Danger Zone → Change visibility → Private（Pages 私有需 Pro 或保持公开但确认收录边界） | 持仓研判内容当前公开可索引 |
| U-3 | **分支保护** | 框架仓 Settings → Branches → Add rule：main 必过 CI + 必评审 | 落地「GitHub 常见模式」最后一环 |

## 5. 明确不做（防止范围蔓延，均有据可查）

- 站内搜索框：5 天 21 篇全量 1–2 点击可达，搜索是不存在的需求（GAP-PM §4.1）
- 评论/点赞/登录：个人非持牌内容站，互动引入审核与合规成本（GAP-PM §4.2）
- 跨日期 Σ 折线图：口径未统一前图表比表格更危险（GAP-PM §4.3）
- 季报/半年报：5 天数据无聚合意义（GAP-PM §4.4）
- 小程序 Phase 1 之外的能力：合规阻断项未解（金融类目需持牌，ARCH-R6 §5.1）

## 6. 审计方法与复跑

```bash
# 本文所有「实测」数字的复跑方式
python3 - <<'EOF'
import json, re, difflib
from pathlib import Path
S = Path('_stage/docs')
print('RSS items:', (S/'feed.xml').read_text().count('<item>'))
print('PWA:', (S/'manifest.webmanifest').exists(), (S/'apple-touch-icon.png').exists(),
      'theme-color' in (S/'index.html').read_text())
w = re.sub(r'<[^>]+>','',(S/'weekly/2026-W42/index.html').read_text())
m = re.sub(r'<[^>]+>','',(S/'monthly/2026-10/index.html').read_text())
print('周月相似度: %.4f' % difflib.SequenceMatcher(None,w,m).ratio())
fj = json.loads((S/'api/feed.json').read_text())
leak = [(d['date'],e['slug']) for d in fj['days'] for e in d['entries']
        if e.get('degraded') and (e.get('rating') or e.get('sigma') is not None)]
print('降级态方向值泄漏:', len(leak))
hits = [str(p) for p in S.rglob('*') if p.is_file() and p.suffix in ('.html','.md','.json')
        and '/Users/lianghaizhen' in p.read_text(errors='replace')]
print('绝对路径残留:', hits)
EOF
python3 scripts/ci_verify.py        # 27 项全绿
python3 scripts/probe_responsive.py # 192 组合零横滚
python3 scripts/verify_published.py # 漂移 0
```
