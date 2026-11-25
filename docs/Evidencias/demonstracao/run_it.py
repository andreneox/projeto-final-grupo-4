"""Segunda execucao: capturas da IT Digital E07 em cada passo (CDP com espera real)."""
import json, os, subprocess, time
from pathlib import Path
import httpx
from cdp_shot import Browser

E = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing")
PY = str(ROOT / "venv" / "Scripts" / "python.exe")
SHOTS = E / "shots2"; SHOTS.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8091"
SCENARIO = [[115, 7, 3, 1], [125, 7, 3, 0]]   # Andon de Processo no P07 durante a IT
procs = []


def spawn(name, args, cwd):
    out = open(E / f"{name}.run2.out.txt", "w", encoding="utf-8")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    procs.append(subprocess.Popen(args, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=env))


browser = Browser()
try:
    spawn("clp", [PY, str(E / "clp_emulado.py"), str(E / "clp_emulado.run2.jsonl"), json.dumps(SCENARIO)], E)
    time.sleep(2)
    spawn("gateway", [PY, "main.py", "--config", str(E / "gateway.toml"), "--stop-file", str(E / "gateway.stop")], ROOT / "hardware")
    spawn("receiver", [PY, "-m", "tools.reference_receiver", "--config", str(E / "mockdesktop.toml")], ROOT / "simulador")
    for _ in range(60):
        try:
            if httpx.get(BASE + "/api/snapshot", timeout=3).json()["opcua"].get("connected"): break
        except Exception: pass
        time.sleep(1)
    time.sleep(2)
    print(httpx.post(BASE + "/api/process/cycle-base?filename=base_demo.csv", content=(E / "base_demo.csv").read_bytes(), timeout=60).json())
    print(httpx.post(BASE + "/api/process/start", timeout=60).json())
    t0 = time.monotonic(); taken = set(); log = []
    while time.monotonic() - t0 < 150:
        st = httpx.get(BASE + "/api/instruction/e07", timeout=5).json()
        snap = httpx.get(BASE + "/api/snapshot", timeout=5).json()
        p07 = snap["opcua"]["stations"]["7"]["process_status"]
        log.append({"t": round(time.monotonic() - t0, 2), "p07": p07, **{k: st[k] for k in ("slide", "status", "elapsed_seconds", "cycle_id")}})
        key = (st["status"], st["slide"])
        if key not in taken and (st["status"] in ("running", "paused", "interrupted") or (st["status"] == "complete" and st["cycle_id"])):
            taken.add(key)
            browser.shot(BASE + "/instrucao/e07", SHOTS / f"it_{st['status']}_slide{st['slide']}.png", wait=1.5)
        if "dash_proc" not in taken and p07 == 2 and time.monotonic() - t0 > 60:
            taken.add("dash_proc"); browser.shot(BASE + "/", SHOTS / "dashboard_p07_processando.png", wait=3, height=1250)
        if "dash_stop" not in taken and st["status"] == "paused":
            taken.add("dash_stop"); browser.shot(BASE + "/", SHOTS / "dashboard_andon_p07.png", wait=2.5, height=1250)
        time.sleep(0.5)
    json.dump(log, open(E / "it_timeline.json", "w"), indent=0)
    httpx.post(BASE + "/api/process/clear-base", timeout=60)
finally:
    browser.close()
    (E / "gateway.stop").write_text("stop"); time.sleep(6)
    for p in procs:
        if p.poll() is None: subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    print("fim run_it", flush=True)
