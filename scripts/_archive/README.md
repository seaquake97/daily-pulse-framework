# 归档说明

`prepare_release.py`（2026-10-14 13:09 版）已被 `scripts/publish_to_github.py`（dev 实现，七步流水线）全面取代：

- 仓库名默认值已对齐 PM 决策 `daily-market-pulse`（旧版默认 market-pulse-daily）
- md 文件名映射错误已修（fund_guide.md→fund_operation_guide.md；总复盘与股票复盘共享 stock_review.md 按 slug 去重）
- 新增 --task 单选、退出码规范（0/1/2/3/4/5）、站点结构层（日期页/周月归档/feed/sitemap/methodology）

保留仅作历史参考，**不要再调用**。唯一入口为 publish_to_github.py。
