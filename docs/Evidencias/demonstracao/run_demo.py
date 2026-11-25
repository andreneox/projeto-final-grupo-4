"""Executa a demonstracao ponta a ponta: CLP emulado -> Gateway -> Receptor/Dashboard."""
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path
import httpx

E = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing")
PY = str(ROOT / "venv" / "Scripts" / "python.exe")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SHOTS = E / "shots"; SHOTS.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8091"
SCENARIO = [[50, 5, 2, 1], [68, 5, 2, 0], [120, 9, 1, 1], [128, 9, 1, 0], [170, 3, 4, 1], [182, 3, 4, 0]]
procs = []
api_log = []
t_start = None


def spawn(name, args, cwd):
    out = open(E / f"{name}.out.txt", "w", encoding="utf-8")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen(args, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=env,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    procs.append((name, p)); return p


def call(method, path, **kw):
    t0 = time.perf_counter()
    r = httpx.request(method, BASE + path, timeout=30, **kw)
    ms = (time.perf_counter() - t0) * 1000
    try: body = r.json()
    except Exception: body = r.text[:300]
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "method": method, "path": path,
             "status": r.status_code, "ms": round(ms, 1), "response": body}
    if "json" in kw: entry["request"] = kw["json"]
    if "content" in kw: entry["request"] = f"<{len(kw['content'])} bytes: base_demo.csv>"
    api_log.append(entry); print(method, path, r.status_code, f"{ms:.0f} ms", str(body)[:160], flush=True)
    return r


def shot(name, url, w=1600, h=1200, wait_ms=6000):
    out = SHOTS / f"{name}.png"
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--user-data-dir={E / 'edge-profile'}", f"--window-size={w},{h}",
                    f"--virtual-time-budget={wait_ms}", f"--screenshot={out}", url],
                   timeout=90, capture_output=True)
    print("shot", name, out.exists(), flush=True)


def sample(fh):
    try:
        snap = httpx.get(BASE + "/api/snapshot", timeout=10).json()
        e07 = httpx.get(BASE + "/api/instruction/e07", timeout=10).json()
        fh.write(json.dumps({"t": time.monotonic() - t_start if t_start else None,
                             "at": datetime.now().isoformat(), "snapshot": snap, "e07": e07}) + "\n"); fh.flush()
    except Exception as exc:
        print("sample fail", exc, flush=True)


try:
    spawn("clp", [PY, str(E / "clp_emulado.py"), str(E / "clp_emulado.jsonl"), json.dumps(SCENARIO)], E)
    time.sleep(2)
    spawn("gateway", [PY, "main.py", "--config", str(E / "gateway.toml"), "--stop-file", str(E / "gateway.stop")], ROOT / "hardware")
    spawn("receiver", [PY, "-m", "tools.reference_receiver", "--config", str(E / "mockdesktop.toml")], ROOT / "simulador")
    for _ in range(60):
        try:
            s = httpx.get(BASE + "/api/snapshot", timeout=3).json()
            if s["opcua"].get("connected"): break
        except Exception: pass
        time.sleep(1)
    print("opcua connected:", s["opcua"].get("connected"), flush=True)
    time.sleep(3)
    shot("01_dashboard_conectada_sem_base", BASE + "/")
    call("GET", "/api/version")
    call("PUT", "/api/process/production-plan", json={"production_target": 90, "available_time_minutes": 60.0})
    call("GET", "/api/process/production-plan")
    call("GET", "/api/process/cycle-base")
    call("POST", "/api/process/cycle-base?filename=base_demo.csv", content=(E / "base_demo.csv").read_bytes())
    call("GET", "/api/process/cycle-base")
    call("POST", "/api/process/start", headers={"Origin": "http://evil.example"})   # deve ser recusado (403)
    r = call("POST", "/api/process/start")
    t_start = time.monotonic()
    plan = {20: "02_dashboard_em_producao", 32: "03_it_digital_e07_passo", 57: "04_dashboard_andon_ativo",
            58: "05_it_digital_e07_pausada", 100: "06_it_digital_e07_passo", 124: "07_dashboard_andon_qualidade",
            235: "08_dashboard_final", 238: "09_graficos_por_posto"}
    done = set()
    with open(E / "timeline.jsonl", "w", encoding="utf-8") as fh:
        while time.monotonic() - t_start < 245:
            el = time.monotonic() - t_start
            sample(fh)
            for at, name in plan.items():
                if el >= at and name not in done:
                    done.add(name)
                    url = BASE + ("/instrucao/e07" if "it_digital" in name else "/graficos" if "graficos" in name else "/")
                    shot(name, url, 1600, 1000 if "it_digital" in name else 1250)
            time.sleep(2)
    call("GET", "/api/snapshot")
    call("GET", "/api/instruction/e07")
    call("GET", "/api/process/configuration")
    call("POST", "/api/runtime/events", json={"kind": "andon", "occurred_at": "2026-11-21T10:00:00-04:00", "station": 13, "button_id": 1, "is_on": True})  # 422
    call("POST", "/api/process/clear-base")
    time.sleep(3)
    shot("10_dashboard_apos_limpar_base", BASE + "/")
    call("GET", "/api/snapshot")
finally:
    json.dump(api_log, open(E / "api_log.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    (E / "gateway.stop").write_text("stop")
    time.sleep(6)
    for name, p in reversed(procs):
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    print("fim", flush=True)
