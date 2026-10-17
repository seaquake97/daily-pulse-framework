# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与 [Conventional Commits](https://www.conventionalcommits.org/)。
版本号规则见 `docs/ARCH-R5-FRAMEWORK.md` §3.3：MAJOR = 配置契约不兼容；MINOR = 新增可选能力；PATCH = 修 bug。

## [1.0.0] - 2026-10-17

首个公开版本：`daily-decision-engine` 决策引擎 + 呈现发布框架的完整源码资产化。

### Added

- **框架资产首次成仓**：配置校验层（`framework/scripts/`：`paths.py` / `codes.py` / `rules.py` / `yaml_min.py` / `validate_config.py`，29 例单测）、声明式策略库（`framework/config/strategies/` 3 套 YAML + 加载/渲染/注入器，30 例单测）
- **确定性技术指标**：`framework/engine/signals/technical.py` 纯标准库 MA / 动态 BIAS 1.5× 强势补偿 / Wilder SMMA RSI(6/12/24) / MACD（13 例单测）
- **多源容灾链路**：`framework/engine/collect/` 主源健康体检 + 腾讯/新浪双源故障转移 + CircuitBreaker（3 次失败熔断 300 秒）+ 批量持仓抓取 + 合并纪律（主源优先/脏值丢弃/缺口声明不填 0）（121 例单测）
- **S4 复合动量**：`S4 = clamp(0.6×分化项 + 0.4×动量项)`，动量项由 RSI/BIAS 均值度量，opt-in 向后兼容
- **统一渲染与发布管线**：`render_md.py` + `md_render/`（md→详情页唯一生产者）、`sanitizer/` 15 件套发布层消毒、`build_site.py` 站点生成、`publish_to_github.py` 编排器（缺失任务退出码 2 不再静默）
- **质量门禁**：`ci_verify.py` 统一调度 27 项、`scan_compliance.py` P0 扫描、`probe_responsive.py` 192 组合响应式探针、`verify_published.py` 线上漂移校验
- **方法论页 v3**：Apple HIG 双端适配（920px 桌面容器 / 吸顶胶囊导航 / 七步网格 / 双列对比卡片）、9 大模块（新增双重金融护栏、多源容灾断路器、S4 复合动量公式）
- **站点设计系统**：`design-tokens.css` 四层 Token（含 `--container-methodology`）、深色模式契约守护测试
- **GitHub 维护体系**：README / CONTRIBUTING / Issue 与 PR 模板 / CI 工作流（单测层 + 假绿灯判定）/ CHANGELOG

### Fixed

- `framework/scripts/paths.py`：`WORKBUDDY_ROOT` 默认值从 `__file__` 上溯四级改为 `~/WorkBuddy`——框架仓可 clone 到任意路径（此前换目录即解析错根，集成测试全红）
- `scripts/test_render_md.py`：真实产物缺失时整体 skip 而非 14 个 error（A-07 集成层守卫）
- `.gitignore`（根与 framework/）：行内 `#` 注释导致 pattern 永不匹配的静默失效——`_stage/`、`_git_engine/`、`framework/**/*.json`（含 `slug_stage.json` 与 `market_data.schema.json` 两份契约文件）此前被误提交/误忽略，已修复并补白名单

### Security

- 发布产物中本机绝对路径脱敏（`path_scrub.py` + `sanitizer/path_pass.py`），`.md` 与 HTML 双载体覆盖

[1.0.0]: https://github.com/seaquake97/daily-pulse-framework/releases/tag/v1.0.0
