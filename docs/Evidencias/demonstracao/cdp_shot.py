"""Captura de tela com espera em tempo real (Edge headless + Chrome DevTools Protocol)."""
import asyncio, base64, json, subprocess, time
from pathlib import Path
import httpx, websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
E = Path(__file__).resolve().parent


class Browser:
    def __init__(self, port=9333, width=1600, height=1000):
        self.port = port
        self.proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                      f"--remote-debugging-port={port}", f"--user-data-dir={E / f'cdp-profile-{port}'}",
                                      f"--window-size={width},{height}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=1); break
            except Exception: time.sleep(0.2)

    def shot(self, url, out, wait=4.0, width=1600, height=1000):
        asyncio.run(self._shot(url, out, wait, width, height))

    async def _shot(self, url, out, wait, width, height):
        target = httpx.put(f"http://127.0.0.1:{self.port}/json/new?{url}", timeout=10).json()
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
            n = 0
            async def cmd(method, **params):
                nonlocal n; n += 1; my = n
                await ws.send(json.dumps({"id": my, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == my: return msg.get("result", {})
            await cmd("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
            await asyncio.sleep(wait)
            res = await cmd("Page.captureScreenshot", format="png")
            Path(out).write_bytes(base64.b64decode(res["data"]))
        httpx.get(f"http://127.0.0.1:{self.port}/json/close/{target['id']}", timeout=5)
        print("cdp shot", Path(out).name, flush=True)

    def close(self):
        self.proc.kill()
