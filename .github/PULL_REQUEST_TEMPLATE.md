## PR 自查清单 / PR Checklist

> 合并前逐项确认，未通过项在评论里说明原因。

**门禁（附命令输出）**

- [ ] `python3 scripts/ci_verify.py` 全绿（27 项）
- [ ] `python3 scripts/scan_compliance.py` P0 违规计数全 0（emoji / 渐变 / 硬编码色 / 弹跳缓动）
- [ ] 改了页面或样式：`python3 scripts/probe_responsive.py` 192 组合零横滚
- [ ] 改了发布链路：`python3 scripts/verify_published.py` 漂移 0

**P0 绝对规则**

- [ ] 零 emoji 功能图标（只允许 `site_theme.SYMBOLS` 锁定的一套 Lucide SVG）
- [ ] 零紫粉渐变；零硬编码颜色（唯一例外 `#fff` / `#000`）
- [ ] 零 JS；禁弹跳缓动；Python 单文件 ≤ 300 行

**契约一致性**

- [ ] 数据缺失标注「数据缺口」，无填 0、无代理冒充
- [ ] 降级态无任何可执行动作（三出口：entries.json / feed.json / 页面徽章）
- [ ] 站点文案与引擎决策卡同源（改了标准动作必须同步两侧）

**说明**

- 动机：
- 改动点：
- 验收证据：
