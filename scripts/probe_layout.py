"""用 CDP 直接驱动本机 Chrome 做布局探测（不引新依赖，纯标准库 + websocket 手写）。"""
import json, subprocess, time, urllib.request, os, base64, socket, hashlib, struct

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT=9333
ROOT=os.getcwd()
OUT=os.path.join(ROOT,"evidence/apple-redesign")

proc=subprocess.Popen([CHROME,"--headless=new",f"--remote-debugging-port={PORT}",
    "--disable-gpu","--hide-scrollbars","--no-first-run","--user-data-dir=/tmp/cdp-profile",
    "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_port(p, t=20):
    for _ in range(t*10):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{p}/json/version", timeout=1); return True
        except Exception: time.sleep(0.1)
    return False

class WS:
    def __init__(self, url):
        import base64 as b
        assert url.startswith("ws://")
        rest=url[5:]
        hostport, path = rest.split("/",1)
        host, port = hostport.split(":")
        self.s=socket.create_connection((host,int(port)))
        self.s.settimeout(30)
        key=b.b64encode(os.urandom(16)).decode()
        req=(f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
             f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.s.sendall(req.encode())
        buf=b""
        while b"\r\n\r\n" not in buf: buf+=self.s.recv(4096)
        self.buf=buf.split(b"\r\n\r\n",1)[1]
        self.i=0
    def _recv(self, n):
        while len(self.buf)<n:
            d=self.s.recv(65536)
            if not d: raise IOError("closed")
            self.buf+=d
        r, self.buf = self.buf[:n], self.buf[n:]
        return r
    def send(self, method, **params):
        self.i+=1
        msg=json.dumps({"id":self.i,"method":method,"params":params}).encode()
        hdr=bytearray([0x81])
        n=len(msg)
        mask=os.urandom(4)
        if n<126: hdr.append(0x80|n)
        elif n<65536: hdr.append(0x80|126); hdr+=struct.pack(">H",n)
        else: hdr.append(0x80|127); hdr+=struct.pack(">Q",n)
        hdr+=mask
        hdr+=bytes(b^mask[k%4] for k,b in enumerate(msg))
        self.s.sendall(bytes(hdr))
        while True:
            b0,b1=self._recv(2)
            ln=b1&0x7f
            if ln==126: ln=struct.unpack(">H",self._recv(2))[0]
            elif ln==127: ln=struct.unpack(">Q",self._recv(8))[0]
            data=self._recv(ln)
            try: r=json.loads(data)
            except Exception: continue
            if r.get("id")==self.i: return r
    def close(self): self.s.close()

assert wait_port(PORT), "chrome 未就绪"
_t=json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
TARGET=[x for x in _t if x["type"]=="page"][0]["webSocketDebuggerUrl"]
pages=[("index","_stage/docs/index.html"),("day","_stage/docs/daily/2026-10-14/index.html"),
       ("weekly","_stage/docs/weekly/2026-W42/index.html"),("monthly","_stage/docs/monthly/2026-10/index.html"),
       ("method","_stage/docs/methodology/index.html")]
PROBE="""(() => {
  const de=document.documentElement;
  const bad=[...document.querySelectorAll('*')].filter(e=>{
    const r=e.getBoundingClientRect(); return r.right > de.clientWidth+1 && r.width>0;})
    .slice(0,5).map(e=>e.tagName+'.'+String(e.className||'').split(' ')[0]);
  const tl=document.querySelector('.tl-item');
  const cs=e=>e?getComputedStyle(e):null;
  return {sw:de.scrollWidth, cw:de.clientWidth, bad,
    navH:cs(document.querySelector('.nav'))?.height,
    tlCols: tl?cs(tl).gridTemplateColumns:null,
    shellMax:cs(document.querySelector('.shell'))?.maxWidth,
    bg:cs(document.body).backgroundColor, fg:cs(document.body).color,
    navBlur:cs(document.querySelector('.nav'))?.backdropFilter,
    cardShadow:cs(document.querySelector('.tl-item'))?.boxShadow,
    radius:cs(document.querySelector('.rating'))?.borderRadius};
})()"""
results=[]
for scheme in ("light","dark"):
    for name,path in pages:
        for label,w,h in (("desktop",1440,900),("mobile",390,844)):
            ws=WS(TARGET)
            ws.send("Emulation.setEmulatedMedia", features=[{"name":"prefers-color-scheme","value":scheme}])
            ws.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=(label=="mobile"))
            ws.send("Page.enable")
            ws.send("Page.navigate", url=f"file://{ROOT}/{path}")
            time.sleep(1.4)
            r=ws.send("Runtime.evaluate", expression=PROBE, returnByValue=True)
            m=r["result"]["result"].get("value") or {}
            hs = m.get("sw",0) > m.get("cw",0)
            results.append((scheme,label,name,hs,m))
            print(f"{scheme:<5} {label:<7} {name:<8} 横向滚动={'YES '+str(m.get('sw'))+'>'+str(m.get('cw')) if hs else 'no':<6} "
                  f"nav={m.get('navH')} tlCols={m.get('tlCols')} shell={m.get('shellMax')} "
                  f"bg={m.get('bg')} fg={m.get('fg')} blur={m.get('navBlur')} shadow={m.get('cardShadow')} r={m.get('radius')}"
                  + ("  OVERFLOW:"+",".join(m.get('bad',[])) if m.get('bad') else ""))
            if scheme=="light" and label=="desktop" and name=="index":
                s=ws.send("Page.captureScreenshot", format="png")
                open(os.path.join(OUT,"site-light-desktop-1440.png"),"wb").write(base64.b64decode(s["result"]["data"]))
            if scheme=="dark" and label=="mobile" and name=="index":
                s=ws.send("Page.captureScreenshot", format="png")
                open(os.path.join(OUT,"site-dark-mobile-390.png"),"wb").write(base64.b64decode(s["result"]["data"]))
            if scheme=="light" and label=="mobile" and name=="day":
                s=ws.send("Page.captureScreenshot", format="png", captureBeyondViewport=True)
                open(os.path.join(OUT,"site-light-mobile-day-390.png"),"wb").write(base64.b64decode(s["result"]["data"]))
            if scheme=="light" and label=="desktop" and name=="method":
                s=ws.send("Page.captureScreenshot", format="png")
                open(os.path.join(OUT,"site-light-methodology-1440.png"),"wb").write(base64.b64decode(s["result"]["data"]))
            ws.close()
proc.terminate()
hs=sum(1 for r in results if r[3])
print(f"\n横向滚动页面数: {hs} / {len(results)}")
