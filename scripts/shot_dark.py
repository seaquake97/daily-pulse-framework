#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""shot_dark.py — 深色模式逐页截图（目检用，CDP 直驱 Chrome）

用法：python3 scripts/shot_dark.py [宽度=1440]
输出：evidence/dark-<page>-<width>.png
深色偏好通过 Emulation.setEmulatedMedia(prefers-color-scheme=dark) 注入。
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9338
ROOT = os.getcwd()
OUT = os.path.join(ROOT, "evidence")
WIDTH = int(sys.argv[1]) if len(sys.argv) > 1 else 1440

PAGES = [
    ("home", "_stage/docs/index.html"),
    ("day", "_stage/docs/daily/2026-10-16/index.html"),
    ("detail", "_stage/docs/daily/2026-10-16/fund-guide.html"),
    ("subscribe", "_stage/docs/subscribe/index.html"),
    ("method", "_stage/docs/methodology/index.html"),
]


class WS:
    def __init__(self, url: str):
        hostport, path = url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)))
        self.s.settimeout(60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                        "Sec-WebSocket-Version: 13\r\n\r\n").encode())
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


def main() -> int:
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT}", "--disable-gpu",
         "--hide-scrollbars", "--no-first-run", "--user-data-dir=/tmp/cdp-profile-dark",
         "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        tgt = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
        url = [x for x in tgt if x["type"] == "page"][0]["webSocketDebuggerUrl"]
        os.makedirs(OUT, exist_ok=True)
        for name, path in PAGES:
            if not os.path.exists(os.path.join(ROOT, path)):
                print(f"[skip] {name}")
                continue
            ws = WS(url)
            ws.send("Emulation.setEmulatedMedia",
                    features=[{"name": "prefers-color-scheme", "value": "dark"}])
            ws.send("Emulation.setDeviceMetricsOverride",
                    width=WIDTH, height=1000, deviceScaleFactor=1, mobile=False)
            ws.send("Page.enable")
            ws.send("Page.navigate", url=f"file://{ROOT}/{path}")
            time.sleep(1.2)
            shot = ws.send("Page.captureScreenshot", format="png")
            dst = os.path.join(OUT, f"dark-{name}-{WIDTH}.png")
            with open(dst, "wb") as f:
                f.write(base64.b64decode(shot["result"]["data"]))
            print(f"[shot] {dst}")
            ws.close()
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
