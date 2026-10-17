"""scan_compliance.py — Apple redesign 合规扫描（框架页 + 上游详情页）

覆盖两类产物：
  GEN    站点框架页（index / methodology / daily|weekly|monthly 的 index.html）
  DETAIL 上游详情页（_stage/docs/daily/*/*.html，排除各目录 index.html
         避免与框架页重复计数）

「上游详情页」章节度量（供消毒前后对比）：
  script 数 / gradient 数 / emoji 数（P0 口径 + sanitizer 口径）/
  裸 hex 数 / <use> 悬空引用数（引用无对应 symbol 定义的个数）

运行：
  python3 scan_compliance.py            # 扫描并写 evidence/apple-redesign/compliance-scan.txt
  python3 scan_compliance.py --baseline # 另写详情页消毒前基线 JSON（只增不改，已存在则跳过）
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "framework", "scripts"))   # A-04: 集中路径
import paths

os.chdir(str(paths.PROJECT_ROOT))

EVIDENCE = 'evidence/apple-redesign/compliance-scan.txt'
BASELINE = 'evidence/apple-redesign/detail-pages-baseline.json'

# P0 绝对规则 emoji 口径（团队级 P0 规则认知 §1：禁止 emoji 作为功能图标）
P0_EMOJI_RE = re.compile('[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]')
# sanitizer emoji_inline.EMOJI_PATTERN 同口径（分段枚举；与 P0 口径的差值即覆盖缺口）
# 2026-10-15：随 emoji_inline 补 \u26c0-\u26ff 与 \u2700-\u27bf（QA 返工 P0，
# ✅/❌ 状态标记曾从旧口径漏过消毒）。此改动后 gap_chars 恒为 0——差值检测
# 保留是为了未来再出现「P0 扩段而 sanitizer 没跟」时立刻报警。
SAN_EMOJI_RE = re.compile(
    '[\U0001F300-\U0001F9FF\U0001FAFF\u2600-\u26bf\u26c0-\u26ff'
    '\u2700-\u27bf\u2b00-\u2bff\ufe0f\u200d\u2b50]')

GEN = (['_stage/docs/index.html', '_stage/docs/methodology/index.html']
       + sorted(glob.glob('_stage/docs/daily/*/index.html'))
       + sorted(glob.glob('_stage/docs/weekly/*/index.html'))
       + sorted(glob.glob('_stage/docs/monthly/*/index.html')))
# 上游详情页：daily 目录下除 index.html 外的全部 HTML
DETAIL = [f for f in sorted(glob.glob('_stage/docs/daily/*/*.html'))
          if not f.endswith('/index.html')]

blob = "\n".join(open(f, encoding='utf-8').read() for f in GEN)

_lines = []


def say(s=''):
    print(s)
    _lines.append(s)


def strip_comments(text: str) -> str:
    """剥离 HTML/CSS 注释，避免规范说明文字被扫描器误判为代码违规（PM-15 / OPEN-006）。"""
    t = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    return re.sub(r'/\*.*?\*/', '', t, flags=re.S)


blob_clean = strip_comments(blob)


def n(pat, flags=0):
    return len(re.findall(pat, blob, flags))


def n_clean(pat, flags=0):
    return len(re.findall(pat, blob_clean, flags))


def measure(path):
    """单页合规度量（详情页基线 + 悬空 use 检测共用）。"""
    t = open(path, encoding='utf-8').read()
    uses = re.findall(r'<use href="#(i-[\w-]+)"', t)
    syms = set(re.findall(r'<symbol id="(i-[\w-]+)"', t))
    dangling = sorted(set(uses) - syms)
    # sanitizer 覆盖缺口：P0 口径命中但 sanitizer 口径漏检的字符（逐字符判定）
    gap_chars = [c for c in t if P0_EMOJI_RE.match(c)
                 and not SAN_EMOJI_RE.match(c)]
    return {
        'script': len(re.findall(r'<script', t)),
        'gradient': len(re.findall(r'(?:linear|radial|conic)-gradient', t)),
        'emoji_p0': len(P0_EMOJI_RE.findall(t)),
        'emoji_sanitizer': len(SAN_EMOJI_RE.findall(t)),
        'emoji_gap': len(gap_chars),
        'emoji_gap_ids': sorted({f'U+{ord(c):04X}' for c in gap_chars}),
        'bare_hex': len(re.findall(r'#[0-9a-fA-F]{3,8}', t)),
        'use_refs': len(uses),
        'symbols': len(syms),
        'dangling_use': len(dangling),
        'dangling_ids': dangling,
    }


def detail_rows():
    return {f: measure(f) for f in DETAIL}


say(f"# 合规扫描 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
say(f"生成页面数: {len(GEN)}")
say(f"上游详情页数: {len(DETAIL)}（daily/*/ 下非 index.html）")
say("── 2. GRADIENT ──")
say(f"   linear/radial/conic-gradient: {n(r'(?:linear|radial|conic)-gradient')}")
say(f"   background-image 残留:        {n(r'background-image')}")
say("── 3. ZERO-JS ──")
say(f"   <script:        {n(r'<script')}")
say(f"   on*= 事件属性:   {n(r' on[a-z]+=')}")
say(f"   外部 http(s):{n(r'(?:src|href)=\"https?://')}")
say(f"   javascript:      {n(r'javascript:')}")
say("── 4. LINE COUNT ──")
wc = subprocess.run(
    ['wc', '-l', 'scripts/build_site.py', 'scripts/site_theme.py',
     'scripts/site_content.py', 'scripts/site_render.py',
     'scripts/site_pages.py', 'scripts/site_components.css'],
    capture_output=True, text=True)
for line in wc.stdout.strip().splitlines():
    say('      ' + line.strip())
say("── 5. 禁用项 ──")
say(f"   弹跳缓动:                {n_clean(r'0\.68,\s*-0\.55,\s*0\.265,\s*1\.55')}")
say(f"   紫粉渐变/靛蓝:            {n(r'#7C3AED|#A855F7|#EC4899|from-purple|from-pink|#6366f1', re.I)}")
say(f"   组件层裸 hex:            {len(re.findall(r'#[0-9a-fA-F]{3,8}', open('scripts/site_components.css', encoding='utf-8').read()))}")
say(f"   组件层彩色 border-left:    {len(re.findall(r'border-left:\s*[2-9]px solid', open('scripts/site_components.css', encoding='utf-8').read()))}")
say(f"   font-weight 800+:         {n(r'font-weight[^;}]*[\s:](?:800|900)')}")
say("── 6. 深色模式 / 动效降级 / 断点 ──")
say(f"   prefers-color-scheme 块:  {n(r'prefers-color-scheme:\s*dark')}")
say(f"   prefers-reduced-motion:   {n(r'prefers-reduced-motion')}")
say(f"   @media 总数:              {n(r'@media')}")
say(f"   @supports corner-shape:   {n(r'@supports \(corner-shape')}")
say(f"   saturate(180%) blur(20px):{n(r'saturate\(180%\) blur\(20px\)')}")
say(f"   color-scheme meta:        {n(r'content=\"light dark\"')}")
say("── 7. 栅格 / 行宽 / 交互蓝 ──")
say(f"   --container-max:980px:    {n(r'--container-max:\s*980px')}")
say(f"   --container-prose:680px:  {n(r'--container-prose:\s*680px')}")
say(f"   --tl-gutter:92px:         {n(r'--tl-gutter:\s*92px')}")
say(f"   浅色交互蓝 #0071e3:       {n(r'--ap-blue:\s*#0071e3')}")
say(f"   深色交互蓝 #2997ff:       {n(r'#2997ff')}")
say(f"   CJK tracking (非拉丁):    {n(r'--tracking-title4:\s*-0\.012em')}")
say(f"   手写 -0.028em(应为0):     {n(r'-0\.028em')}")
say("── 8. 功能契约 ──")
say(f"   .tl-item[data-time][data-slug]:        {n(r'class=\"tl-item\" data-time=')}")
say(f"   .dp-card[data-date/-rating/-sigma]:     {n(r'class=\"issue dp-card\" data-date=')}")
say(f"   tag gap 双类（Σ 数据缺口）:{n(r'tag gap')}")
say(f"   tag-warn（统计口径不同）:      {n(r'tag-warn')}")
say(f"   chip-pending（网页版待补齐）:  {n(r'chip-pending')}")
say(f"   Σ 0.000 兜底(应为 0):        {n(r'>\+?0\.000<')}")
say(f"   评级箭头冗余编码:            {n(r'class=\"arrow\"')}")
say(f"   SVG symbol sprite:          {n(r'<symbol id=\"i-')}")
say(f"   内联 <use> 引用:            {n(r'<use href=\"#i-')}")
say("── 9. 无信息量链接标签（应为 0）──")
for bad in ('阅读网页版', 'HTML 版', '阅读 Markdown', '阅读全文 / Read Full'):
    say(f"   {bad!r}: {blob.count(bad)}")
say("── 10. 产物完整性 ──")
for f in ['_stage/docs/feed.xml', '_stage/docs/sitemap.xml', '_stage/docs/index.html',
          '_stage/docs/methodology/index.html', '_stage/docs/weekly/2026-W42/index.html',
          '_stage/docs/monthly/2026-10/index.html']:
    say(f"   {f}: {os.path.getsize(f)} bytes")

# ---------------------------------------------------------------- 11. 上游详情页
say("── 11. 上游详情页（daily 详情页，消毒前后对比基准）──")
rows = detail_rows()
tot = {k: sum(r[k] for r in rows.values())
       for k in ('script', 'gradient', 'emoji_p0', 'emoji_sanitizer',
                 'emoji_gap', 'bare_hex', 'use_refs', 'symbols',
                 'dangling_use')}
gap_ids = sorted({g for r in rows.values() for g in r['emoji_gap_ids']})
say(f"   详情页数:                  {len(rows)}")
say(f"   <script 数:                {tot['script']}")
say(f"   gradient 数:               {tot['gradient']}")
say(f"   emoji 数（P0 口径）:        {tot['emoji_p0']}")
say(f"   emoji 数（sanitizer 口径）: {tot['emoji_sanitizer']}")
say(f"   sanitizer 漏检字符数:       {tot['emoji_gap']}"
    f"（P0 口径命中但 sanitizer EMOJI_PATTERN 未覆盖）码点: {gap_ids if gap_ids else '无'}")
say(f"   裸 hex 数:                 {tot['bare_hex']}")
# hex 分区解剖：frame_pass 给详情页内联了四层站点 CSS（Token 定义层天然含 hex
# 字面量——那是颜色的唯一合法归宿；组件/框架层声明零字面量）。不分区会让
# 「注入 Token 层」被误读成「引入硬编码颜色」，故单列一行说明增量构成。
_style_hex = sum(len(re.findall(r'#[0-9a-fA-F]{3,8}',
                                re.sub(r'/\*.*?\*/', ' ', m, flags=re.S)))
                 for f in DETAIL for m in re.findall(r'<style\b[^>]*>(.*?)</style\s*>',
                                                     open(f, encoding='utf-8').read(), re.S))
say(f"     其中 <style> 层内:       {_style_hex}"
    f"（Token 定义层 + 注释；declaration 级非 #fff/#000 字面量须为 0，"
    f"由组件/框架层分别度量）")
say(f"   <use> 引用数:              {tot['use_refs']}")
say(f"   <symbol> 定义数:           {tot['symbols']}")
say(f"   <use> 悬空引用数:          {tot['dangling_use']}（引用无对应 symbol 定义）")
say("   逐页明细:  file | script | gradient | emoji(P0/san/gap) | hex | use/symbol | dangling")
for f, r in rows.items():
    say(f"     {f}: {r['script']} | {r['gradient']} | "
        f"{r['emoji_p0']}/{r['emoji_sanitizer']}/{r['emoji_gap']} | {r['bare_hex']} | "
        f"{r['use_refs']}/{r['symbols']} | {r['dangling_use']}")
dangling_all = sorted({d for r in rows.values() for d in r['dangling_ids']})
say(f"   悬空 <use> 引用明细: {dangling_all if dangling_all else '无'}")

# 基线对比（消毒前快照，只增不改）
if os.path.exists(BASELINE):
    base = json.load(open(BASELINE, encoding='utf-8'))
    say(f"   基线对比（{base['captured_at']}，{base['note']}）:")
    bt = base['totals']
    for k, label in (('script', 'script'), ('gradient', 'gradient'),
                     ('emoji_p0', 'emoji(P0)'), ('emoji_gap', 'sanitizer 漏检'),
                     ('bare_hex', '裸 hex'), ('dangling_use', '悬空 use')):
        delta = tot[k] - bt[k]
        sign = '+' if delta > 0 else ''
        say(f"     {label}: 基线 {bt[k]} → 当前 {tot[k]}（{sign}{delta}）")
else:
    say(f"   基线对比: 基线文件缺失（{BASELINE}），用 --baseline 生成消毒前快照")

# ---------------------------------------------------------------- 落盘
os.makedirs(os.path.dirname(EVIDENCE), exist_ok=True)
with open(EVIDENCE, 'w', encoding='utf-8') as fh:
    fh.write("\n".join(_lines) + "\n")
print(f"\n[scan_compliance] 报告已写入 {EVIDENCE}")

if '--baseline' in sys.argv:
    if os.path.exists(BASELINE):
        print(f"[scan_compliance] 基线已存在，跳过（只增不改）: {BASELINE}")
    else:
        snap = {
            'captured_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': '上游详情页消毒前基线（backend sanitizer 修复前快照，供对比消毒前后）',
            'files': DETAIL,
            'per_page': rows,
            'totals': tot,
        }
        with open(BASELINE, 'w', encoding='utf-8') as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=2)
        print(f"[scan_compliance] 基线已写入 {BASELINE}")
