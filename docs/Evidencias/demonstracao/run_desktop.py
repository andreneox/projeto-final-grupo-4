"""Evidencia do Desktop (MockDesktop PyQt6): abre a janela real, aciona Andons e captura a tela."""
import json, os, subprocess, sys, time
from pathlib import Path

E = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing")
MOCK = ROOT / "simulador"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SHOTS = E / "shots"; SHOTS.mkdir(exist_ok=True)

cfg = (E / "mockdesktop.toml").read_text(encoding="utf-8")
cfg = (cfg.replace("opc.tcp://127.0.0.1:4850/mock-linha/", "opc.tcp://127.0.0.1:4851/mock-linha/")
          .replace("port = 8091", "port = 8092").replace("port = 15010", "port = 15011")
          .replace("receiver_demo.db", "receiver_desktop.db").replace("mock_demo.db", "mock_desktop.db"))
(E / "desktop.toml").write_text(cfg, encoding="utf-8")

env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
recv = subprocess.Popen([sys.executable, "-m", "tools.reference_receiver", "--config", str(E / "desktop.toml")],
                        cwd=MOCK, stdout=open(E / "receiver_desktop.out.txt", "w", encoding="utf-8"),
                        stderr=subprocess.STDOUT, env=env)

os.chdir(MOCK); sys.path.insert(0, str(MOCK))
sys.argv = ["main.py", "--config", str(E / "desktop.toml")]
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
import app.bootstrap as bootstrap
from domain.models import AndonCategory

steps = []
orig_show = bootstrap.MainWindow.show


def patched_show(self):
    self.move(-3000, 40); orig_show(self); self.resize(1500, 820); self.move(-3000, 40)
    window = self
    service = None
    for obj in QApplication.instance().allWidgets():
        pass

    def click(station, category):
        window.grid.toggle_requested.emit(station, category)

    def grab(name):
        window.grab().save(str(SHOTS / f"{name}.png")); print("grab", name, flush=True)

    def web(name, url):
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={E / 'edge-profile2'}",
                        "--window-size=1600,1250", "--virtual-time-budget=6000", f"--screenshot={SHOTS / (name + '.png')}", url],
                       timeout=90, capture_output=True); print("web", name, flush=True)

    seq = [
        (6000, lambda: grab("11_desktop_inicial")),
        (6500, lambda: click(3, AndonCategory.MATERIAL)),
        (9500, lambda: grab("12_desktop_andons_ativos")),
        (10000, lambda: web("13_dashboard_modo_simulador", "http://127.0.0.1:8092/")),
        (25000, lambda: click(3, AndonCategory.MATERIAL)),
        (28000, lambda: grab("14_desktop_andons_liberados")),
        (29000, lambda: QApplication.instance().quit()),
    ]
    for ms, fn in seq:
        QTimer.singleShot(ms, fn)


bootstrap.MainWindow.show = patched_show
try:
    code = bootstrap.run()
finally:
    time.sleep(1)
    subprocess.run(["taskkill", "/PID", str(recv.pid), "/T", "/F"], capture_output=True)
print("fim desktop", flush=True)
