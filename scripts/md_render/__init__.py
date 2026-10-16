#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""md_render — Markdown 统一渲染包（FRAMEWORK-DESIGN v2.0 §2 实现契约）

定位：框架唯一呈现层生产者。上游五个定时任务退化为 md 内容源，本包把 md
渲染为详情页 HTML，终结「五个任务五套 HTML 生成器」的风格分裂与 md-only
任务（14:30 基金指引）无页面可推送的问题。

分层（依赖只向下，code-organization 铁律）：
    render_md.py   门面 + CLI：只装配（解析参数 → 三步调用 → 落盘），零业务逻辑
      └─ document 块序列 → 正文 HTML + 整页组装（章节视觉映射，§2.4）
           ├─ blocks   md 文本 → 块序列（语法层，零表现依赖）
           └─ inline   行内 md → HTML（转义 / 行内语法 / emoji / 数学 / 徽章）
                └─ meta 标题规范（§2.1）+ meta 三级兜底（§2.3，纯函数零 IO）

四条铁律（违反即退回重做）：
  1. md 正文 100% 无损：只做结构包裹与视觉映射，不删不改任何文字
  2. 零 <script> / 零渐变 / 零裸 hex / 零内联 CSS——样式全靠 detail-frame.css
     类名（frame_pass 注入，单一 Token 源），禁第二套 CSS 漂移
  3. 幂等：纯函数式渲染，同输入两次输出字节一致（无墙钟、无随机、无 UUID）
  4. 类名纪律（C-14 门禁）：输出类名必须已被 detail-frame.css 收录（或是 A-9
     主动施加的 tbl）。连字符复合类（如 tag-gap）在 site_blocks.css 有定义但
     detail-frame.css 未收录，会撞 frame_pass 交叉类门禁直接构建失败——
     故数据缺口徽章用 `.tag gap` 双类（detail-frame.css §4 有其再皮肤规则）。
"""
from __future__ import annotations

from .document import build_page, render_body, render_md
from .inline import _math_text, convert_emoji, esc, inline, safe_url
from .meta import (RATINGS, SLUG_STAGE, STAGE_LABEL, STAGES, TASK_NAMES,
                   _clean_title, extract_meta, render_title)

__all__ = [
    # document（组装层）
    "build_page", "render_body", "render_md",
    # inline（行内层）
    "_math_text", "convert_emoji", "esc", "inline", "safe_url",
    # meta（标题与兜底）
    "RATINGS", "SLUG_STAGE", "STAGE_LABEL", "STAGES", "TASK_NAMES",
    "_clean_title", "extract_meta", "render_title",
]
