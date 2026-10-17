# PRD-005: 研判方法论全面升级与 ZhuLinsen 策略深度融合方案

> **文档版本**：v3.0.0  
> **责任人**：许清楚（产品经理） / 韦优（项目总监）  
> **归档日期**：2026-10-17  
> **适用范围**：`site/methodology/index.html` 及全站方法论规则体系  
> **对齐开源标杆**：[https://github.com/ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)

---

## 一、需求背景与重构目标

用户明确指示：
> “**方法论页面做 Apple 风格适配，手机端电脑端适配，结合我之前发的 GitHub 链接 https://github.com/ZhuLinsen/daily_stock_analysis/ 做深度学习和集成，优化方法论规则，召唤团队开始干活**”

### 1.1 现状诊断
1. **排版版式单一**：
   - 目前页面使用 `.mp-shell { max-width: var(--container-prose); }`（仅 680px 宽），在 1440px / 1920px 宽屏桌面端呈现为一根细长文本条，两侧大片空白，未利用桌面宽屏优势；
   - 缺乏现代 Apple 风格的内容引导（无快速跳转锚点栏、步骤流呈现为零散方块、缺乏双列对比卡片）；
   - 移动端（375px/390px）虽无横滚，但长篇大论缺乏模块化索引胶囊，用户需要大幅滑动翻屏。
2. **方法论规则未充分反映最新研发成果**：
   - 此前方法论页面仅列出了基础的七步流水线与 S1-S6 初版公式；
   - 团队在过去几轮已完成了 **S4 动量复合升级**、**纯标准库 Wilder RSI 与动态 BIAS 1.5 倍强势补偿**、**多源行情容灾与断路器（CircuitBreaker）**、**声明式策略引擎（YAML）** 以及 **L-4 降级态动作门禁** 的工程落地；
   - 必须将开源项目 `ZhuLinsen/daily_stock_analysis` 的核心精髓与本项目的工程实现做深度融合，全面升级方法论内容，建立专业、可审计、逻辑闭环的金融工程方法论矩阵。

---

## 二、吸收与融合 ZhuLinsen 项目的五大方法论维度

| 维度 | ZhuLinsen/daily_stock_analysis 实践 | 本项目（daily-decision-engine）深化集成 |
|---|---|---|
| **1. 决策护栏机制** | `phase_decision_guardrail`（盘前禁止即时买卖）+ `daily_market_context_guardrail`（退潮期软化买入） | **双重金融级决策护栏体系**：<br>① 时相感知护栏（盘前禁止即时挂单，盘后禁止盘中成交指令）；<br>② 大盘环境与 L-4 降级态软化护栏（退潮期买入转持有，数据源降级或缺口期**绝对禁止输出具体个股挂单与买卖指令**，违规即阻断发布）。 |
| **2. 确定性技术分析** | `stock_analyzer.py` 基于 pandas 计算 MA、MACD、Wilder RSI、BIAS 强势补偿 | **纯标准库零依赖指标引擎**（`technical.py`）：<br>① 滑动均线 MA5/10/20/60；<br>② **动态 BIAS 强势趋势补偿（1.5倍）**：基准阈值 5%，单边强势主升通道自动放宽至 7.5%，顺势追踪防踏空；<br>③ Wilder's SMMA RSI（6/12/24日）平滑算法，杜绝均线跳变；<br>④ 确定性 MACD（DIF/DEA/BAR）结构判定。 |
| **3. 动量复合评分** | 基于自然语言提示词综合量化 | **S4 复合动量评分算法**：<br>`S4 = clamp(0.6 * 分化项 + 0.4 * 动量项)`，分化项衡量成长/蓝筹价差，动量项衡量 Wilder RSI 与 BIAS 均值。保持 opt-in 向后兼容与有效权重封顶机制。 |
| **4. 多源数据容灾** | `DataFetcherManager` + `CircuitBreaker` 连续 3 次失败熔断 300 秒，支持 12 类数据源 | **多源行情容灾与断路器链路**（`fallback_fetcher.py` + `merge_fallback.py`）：<br>腾讯主源 + 新浪备源自动故障转移；连续 3 次失败熔断 300 秒；支持单请求批量抓取 9 只持仓；**主源优先、脏值丢弃、缺口声明绝不填 0、绝不冒充主源**。 |
| **5. 声明式策略库** | `strategies/*.yaml` 包含 15 套自然语言战法（缠论、情绪周期、龙头战法、箱体震荡等） | **无代码声明式策略矩阵**（`framework/config/strategies/`）：<br>基于受限 YAML 语法，将十五五六张网战略、智能网格做T、高股息防御以及情绪周期与箱体震荡固化为声明式规范，供引擎与页面单一事实源消费。 |

---

## 三、方法论页面全新 9 大模块架构设计

页面分为 9 个高度结构化的业务卡片模块，每个模块均支持锚点快速直达：

```
[ 顶部 Hero：每交易日的判断轨迹，同一份数据必然得出同一结论 ]
[ 快捷胶囊锚点栏（TOC）：流水线 | 信号量化 | 五档评级 | 技术指标 | 双重护栏 | 策略体系 | 多源容灾 | 基金穿透 | 反滥用 ]
  │
  ├── 1. 决策引擎七步确定性流水线 (Seven-Step Deterministic Pipeline)
  ├── 2. S1-S6 确定性信号与 S4 复合动量算法 (Signal Scoring & S4 Momentum)
  ├── 3. Σ 评级五档体系与行动指南 (Sigma Rating Tiers & Standard Actions)
  ├── 4. 纯代码技术分析指标体系与动态 BIAS 补偿 (Technical Indicators & Dynamic BIAS 1.5x)
  ├── 5. 双重金融级决策护栏体系 (Dual Financial Guardrails: Phase & Context)
  ├── 6. 声明式战法策略库与无代码扩展 (Declarative YAML Strategy Matrix)
  ├── 7. 多源行情容灾与断路器机制 (Multi-Source Failover & Circuit Breaker)
  ├── 8. 基金持仓穿透与资产配置方法论 (Fund Look-Through & Asset Tiering)
  └── 9. 反滥用设计、合规披露与隐私边界 (Anti-Abuse, Compliance & Privacy)
```

---

## 四、Apple HIG 双端体验与排版需求

### 4.1 桌面端适配（Desktop `> 900px`）
1. **舒适阅读容器**：将主容器宽度从 680px 扩宽至 **`920px`**（`max-width: 920px`），两翼留白舒展，契合 Apple Developer 官方文档气场；
2. **快速胶囊导航（TOC Navigator）**：在页头下方提供一排**微质感胶囊按钮（Segmented Pill Bar）**，支持一键平滑滚动直达 9 大章节，随页面滚动吸顶（`position: sticky; top: var(--nav-h);`）；
3. **栅格化卡片排版**：
   - 七步流水线：采用 **7 步连贯网格卡片（Responsive Grid）**，数字采用等宽强调；
   - 护栏与容灾：采用 **双列并排对比卡片**（左主源/右备用；左时相/右大盘环境）；
   - 表格：保持规范边框，数据列等宽右对齐，斑马纹与悬浮响应。

### 4.2 手机端适配（Mobile `<= 640px`，尤其是 375px/390px 视口）
1. **横向无阻滑动胶囊导航**：移动端胶囊导航栏采用单行水平滚动（`-webkit-overflow-scrolling: touch;`），不折行、不拥挤，单手大拇指轻滑即可切换章节；
2. **零横向滚动与自适应布局**：七步流水线折为自适应双列或单列卡片，双列对比卡片在手机端转为纵向单列卡片；
3. **表格平滑滚动容器**：所有表格均包裹于 `.tbl-wrap`，表头紧凑，字体调至移动端最佳的可读大小（13px~14px）；
4. **安全边距**：底部注入 `padding-bottom: max(var(--space-16), calc(env(safe-area-inset-bottom, 24px) + var(--space-8)))`，防止 iOS Safari 底栏遮挡。

---

## 五、验收标准（Acceptance Criteria）

1. **AC-1 内容完整性**：
   - 完整涵盖 9 大核心模块，全面吸收并呈现 `ZhuLinsen` 护栏、动态 BIAS、Wilder RSI、断路器、YAML 策略等核心规则；
   - 策略区块无缝支持 `inject_strategies.py` 自动化注入。
2. **AC-2 Apple HIG 风格与双端响应式**：
   - 桌面端（980px+）与手机端（375px/390px）自适应，各断点零横向溢出；
   - 吸顶式快速胶囊导航在双端正常工作；
   - 零 emoji 功能图标，零紫粉渐变，零硬编码颜色字面量，全走 Design Token。
3. **AC-3 工程门禁与测试**：
   - 运行 `python3 scripts/ci_verify.py`，全量 27 套测试套件 100% 全部通过；
   - `scripts/scan_compliance.py` 扫描违规项全为 0；
   - `scripts/probe_responsive.py` 192 组合横向溢出为 0。
