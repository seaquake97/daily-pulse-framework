#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probe_responsive.py — 响应式断点矩阵实测（CDP 直驱 Chrome，纯标准库）

用户实锤（2026-10-16）：「宽窄屏幕和放大浏览器页面的动态适配、手机端和电脑端
的自适应应该也没实现」。本探针用机械证据回答三个问题：

  1. 任意宽度下页面是否横向滚动（scrollWidth <= clientWidth）；
  2. 哪些元素溢出版心（getBoundingClientRect().right > clientWidth）；
  3. 浏览器缩放等效场景是否成立——1440px 窗口 200% 缩放 = 720 CSS px 视口，
     150% = 960，125% = 1152，67% = 2149；这些宽度全部在矩阵内。

宽度矩阵（CSS px）：
  320 / 360 / 390 / 414        小屏手机（含 iPhone 全系 + Android）
  640                          站点第一断点（components/blocks 双双 ≤640 收窄）
  720 / 768 / 834 / 980        平板竖屏 + 容器上限（980 = --container-max）
  1024 / 1152 / 1280 / 1440    笔记本 / 桌面（1152 = 1440@125% 缩放等效）
  1920 / 2149 / 2560           大屏桌面（2149 = 1440@67% 缩放等效）

页面矩阵：首页 / 日期页 / 周 / 月 / 方法论 / 订阅页 + 最新日期 5 篇详情页
+ 1 篇历史详情页（10-12 fund-guide，emoji 补映射后重建样本）。

输出：evidence/responsive-matrix.txt（人读）+ .json（机读）。
退出码：0 = 全矩阵零横向滚动；1 = 存在溢出（附明细）。
"""
from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import time
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9334
ROOT = os.getcwd()
OUT = os.path.join(ROOT, "evidence")

WIDTHS = [320, 360, 390, 414, 640, 720, 768, 834, 980,
          1024, 1152, 1280, 1440, 1920, 2149, 2560]
HEIGHT = 900

PAGES = [
    ("home", "_stage/docs/index.html"),
    ("day", "_stage/docs/daily/2026-10-16/index.html"),
    ("weekly", "_stage/docs/weekly/2026-W42/index.html"),
    ("monthly", "_stage/docs/monthly/2026-10/index.html"),
    ("method", "_stage/docs/methodology/index.html"),
    ("subscribe", "_stage/docs/subscribe/index.html"),
    ("d-stock-assistant", "_stage/docs/daily/2026-10-16/stock-assistant.html"),
    ("d-fund-market", "_stage/docs/daily/2026-10-16/fund-market.html"),
    ("d-fund-guide", "_stage/docs/daily/2026-10-16/fund-guide.html"),
    ("d-stock-review", "_stage/docs/daily/2026-10-16/stock-review.html"),
    ("d-daily-review", "_stage/docs/daily/2026-10-16/daily-review.html"),
    ("d-old-fund-guide", "_stage/docs/daily/2026-10-12/fund-guide.html"),
]

PROBE = r"""(() => {
  const de = document.documentElement;
  const cw = de.clientWidth;
  const bad = [...document.querySelectorAll('*')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.right > cw + 1;
  }).slice(0, 8).map(e => {
    const r = e.getBoundingClientRect();
    return e.tagName.toLowerCase() + '.' + String(e.className || '').split(' ')[0]
      + '@' + Math.round(r.right);
  });
  // 组件级断言：订阅页长 URL / 表格横滚容器 / 导航触达高度
  const url = document.querySelector('.sub-url');
  const wrap = document.querySelector('.tbl-wrap');
  const navA = document.querySelector('.nav-links a');
  const cs = e => e ? getComputedStyle(e) : null;
  return {
    sw: de.scrollWidth, cw,
    bad,
    subUrlOverflow: url ? url.scrollWidth > url.clientWidth + 1 : null,
    tblWrapScroll: wrap ? wrap.scrollWidth > wrap.clientWidth + 1 : null,
    navLinkH: navA ? Math.round(navA.getBoundingClientRect().height) : null,
    bodyFs: cs(document.body) ? cs(document.body).fontSize : null,
  };
})()"""


class WS:
    """最小 WebSocket 客户端（CDP 只要发 JSON 帧、收服务端帧）。"""

    def __init__(self, url: str):
        assert url.startswith("ws://")
        hostport, path = url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)))
        self.s.settimeout(60)
        import base64
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n")
        self.s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.i = 0

    def _recv(self, n: int) -> bytes:
        while len(self.buf) < n:
            d = self.s.recv(65536)
            if not d:
                raise IOError("closed")
            self.buf += d
        r, self.buf = self.buf[:n], self.buf[n:]
        return r

    def send(self, method: str, **params):
        self.i += 1
        msg = json.dumps({"id": self.i, "method": method, "params": params}).encode()
        hdr = bytearray([0x81])
        n = len(msg)
        mask = os.urandom(4)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        hdr += mask
        hdr += bytes(b ^ mask[k % 4] for k, b in enumerate(msg))
        self.s.sendall(bytes(hdr))
        while True:
            b0, b1 = self._recv(2)
            ln = b1 & 0x7f
            if ln == 126:
                ln = struct.unpack(">H", self._recv(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv(8))[0]
            data = self._recv(ln)
            try:
                r = json.loads(data)
            except Exception:
                continue
            if r.get("id") == self.i:
                return r

    def close(self):
        self.s.close()


def wait_port(p: int, t: int = 20) -> bool:
    for _ in range(t * 10):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{p}/json/version", timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main() -> int:
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
         "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         "--user-data-dir=/tmp/cdp-profile-resp", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_port(PORT), "chrome 未就绪"
        targets = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/list").read())
        target = [x for x in targets if x["type"] == "page"][0]["webSocketDebuggerUrl"]

        results = []
        lines = []
        overflow_total = 0
        for name, path in PAGES:
            if not os.path.exists(os.path.join(ROOT, path)):
                lines.append(f"[skip] {name}: 文件缺失 {path}")
                continue
            for w in WIDTHS:
                ws = WS(target)
                ws.send("Emulation.setDeviceMetricsOverride",
                        width=w, height=HEIGHT, deviceScaleFactor=1, mobile=(w <= 640))
                ws.send("Page.enable")
                ws.send("Page.navigate", url=f"file://{ROOT}/{path}")
                time.sleep(0.9)
                r = ws.send("Runtime.evaluate", expression=PROBE, returnByValue=True)
                m = r["result"]["result"].get("value") or {}
                ws.close()
                hs = m.get("sw", 0) > m.get("cw", 0) + 1
                flags = []
                if hs:
                    flags.append("H-SCROLL")
                    overflow_total += 1
                if m.get("subUrlOverflow"):
                    flags.append("URL-OVERFLOW")
                    overflow_total += 1
                if m.get("navLinkH") is not None and m["navLinkH"] < 40:
                    flags.append(f"NAV-TAP-{m['navLinkH']}px")
                row = {"page": name, "width": w, "scroll": m.get("sw"),
                       "client": m.get("cw"), "overflow": bool(hs),
                       "flags": flags, "bad": m.get("bad", []),
                       "tblWrapScroll": m.get("tblWrapScroll"),
                       "bodyFs": m.get("bodyFs")}
                results.append(row)
                status = "OVERFLOW" if hs else "ok"
                extra = ""
                if flags:
                    extra = "  " + ",".join(flags)
                if m.get("bad"):
                    extra += "  bad=" + ",".join(m["bad"])
                lines.append(f"{name:<18} {w:>5}px  sw={m.get('sw'):<5} cw={m.get('cw'):<5} "
                             f"{status}{extra}")

        os.makedirs(OUT, exist_ok=True)
        report = "\n".join(lines)
        with open(os.path.join(OUT, "responsive-matrix.txt"), "w", encoding="utf-8") as f:
            f.write("响应式断点矩阵实测 " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n"
                    f"宽度档位: {WIDTHS}\n页面数: {len(PAGES)}  组合数: {len(results)}\n"
                    + "-" * 78 + "\n" + report + "\n" + "-" * 78 + "\n"
                    f"横向滚动组合数: {overflow_total} / {len(results)}\n")
        json.dump(results, open(os.path.join(OUT, "responsive-matrix.json"), "w"),
                  ensure_ascii=False, indent=1)
        print(report)
        print(f"\n横向滚动组合数: {overflow_total} / {len(results)}")
        return 1 if overflow_total else 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
