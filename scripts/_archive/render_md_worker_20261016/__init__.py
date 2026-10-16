# -*- coding: utf-8 -*-
"""md_render — Markdown 统一渲染包（FRAMEWORK-DESIGN v2.0 的实现契约）

定位：上游任务退化为 md 内容源后，本包是站点详情页的**唯一 HTML 生产者**。
管线位置（§2.2）：步骤 4 落盘 md → render_md.py → sanitize_body.py → frame_pass.py。

分层（依赖只向下）：
    render_md.py（CLI 入口：参数 → 读文件 → 调 document → 落盘）
        ↓
    document.py（块 → HTML 组装 + 章节视觉映射 + 页面骨架）
        ↓
    blocks.py（md 块级解析：标题/表格/列表/引用/代码/分隔线）
        ↓
    inline.py（行内渲染：粗斜体/代码/链接/图片/徽章/emoji→SVG）
    meta.py（标题规范 + meta 三级兜底，纯函数零 IO）

铁律：
  1. md 正文 100% 无损 —— 只做结构包裹与容器映射，不删不改任何文字；
     唯一例外是装饰性 emoji 的处置（映射 SVG 或按站点既定策略剥离并留痕，
     与 site_content.summary_html 同口径，P0 禁止 emoji 作功能图标）。
  2. 输出零 <script>、零渐变、零裸色值 —— 样式全部经类名走 frame_pass
     注入的 detail-frame.css（单一 Token 源），渲染器不内联 CSS。
  3. 幂等 —— 同输入两次渲染字节一致（无墙钟、无随机、无环境依赖）。
  4. 标题规范 —— <TASK_NAMES[slug]> · YYYY-MM-DD（周X）<阶段标签>（§2.1）。
"""
