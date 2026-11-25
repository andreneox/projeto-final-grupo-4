import json, shutil, sqlite3, datetime as dt
from pathlib import Path
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

E = Path(r"C:\Users\johng\AppData\Local\Temp\claude\5d4b98baeb9c066d\2cfb3df3-19ce-4d01-a786-e84e1fafb8c3\scratchpad\evid")
IMG = Path(r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing\Docs\Relatorio_Final\Imagens")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def crop_save(src, dst, box=None, max_w=1600):
    im = Image.open(src).convert("RGB")
    if box: im = im.crop(box)
    # remove faixa vazia inferior (fundo #eef2f5 ou branco)
    px = im.load(); w, h = im.size; bottom = h
    bg = px[w - 5, h - 5]
    for y in range(h - 1, 0, -4):
        if any(sum(abs(a - b) for a, b in zip(px[x, y], bg)) > 30 for x in range(0, w, 7)):
            bottom = min(h, y + 24); break
    im = im.crop((0, 0, w, bottom))
    im.save(IMG / dst, optimize=True)
    print(dst, im.size)


S1, S2 = E / "shots", E / "shots2"
crop_save(S1 / "01_dashboard_conectada_sem_base.png", "dash_01_conectada.png")
crop_save(S1 / "04_dashboard_andon_ativo.png", "dash_02_andon_p05.png")
crop_save(S1 / "08_dashboard_final.png", "dash_03_final.png")
crop_save(S1 / "09_graficos_por_posto.png", "dash_04_graficos.png")
crop_save(S1 / "10_dashboard_apos_limpar_base.png", "dash_05_apos_limpar.png")
crop_save(S2 / "dashboard_p07_processando.png", "dash_06_p07_processando.png")
crop_save(S2 / "dashboard_andon_p07.png", "dash_07_andon_p07.png")
crop_save(S1 / "13_dashboard_modo_simulador.png", "desk_04_dashboard_simulador.png", box=(0, 0, 1600, 520))
for n, d in [("11_desktop_inicial", "desk_01_inicial"), ("12_desktop_andons_ativos", "desk_02_andon_ativo"),
             ("14_desktop_andons_liberados", "desk_03_andon_liberado")]:
    crop_save(S1 / f"{n}.png", f"{d}.png", box=(0, 0, 1500, 820))
for n in ["it_running_slide2", "it_running_slide3", "it_running_slide4", "it_running_slide5",
          "it_complete_slide1", "it_paused_slide1", "it_interrupted_slide1"]:
    im = Image.open(S2 / f"{n}.png").convert("RGB"); im.thumbnail((1400, 1400)); im.save(IMG / f"{n}.jpg", quality=86)
    print(n, im.size)

# --- grafico IT Digital x P07 ------------------------------------------------------
log = json.load(open(E / "it_timeline.json"))
t = [r["t"] for r in log]
fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True, gridspec_kw={"height_ratios": [1, 1.3]})
a1.step(t, [r["p07"] if r["p07"] is not None else -1 for r in log], where="post", color="#2e7d32", lw=1.8)
a1.set_yticks([0, 1, 2, 3], ["0 espera", "1 prep.", "2 proc.", "3 fim"]); a1.set_ylabel("D01657 (P07)")
colors = {"running": "#2a6fb0", "complete": "#2e8b57", "paused": "#c0392b", "interrupted": "#e07b1a", "waiting": "#8a8a8a", "disconnected": "#8a8a8a"}
a2.step(t, [r["slide"] for r in log], where="post", color="#555", lw=1)
for st, c in colors.items():
    pts = [(r["t"], r["slide"]) for r in log if r["status"] == st]
    if pts: a2.scatter(*zip(*pts), s=10, color=c, label=st, zorder=3)
a2.set_yticks([1, 2, 3, 4, 5], ["capa", "passo 01", "passo 02", "passo 03", "passo 04"])
a2.set_ylabel("Slide da IT"); a2.set_xlabel("Tempo desde o Start (s) - CLP emulado, amostras a cada ~0,6 s")
a2.legend(ncol=5, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.32))
fig.tight_layout(); fig.savefig(IMG / "it_sincronizacao_p07.png", dpi=180); plt.close(fig)
# transicoes
prev = None
for r in log:
    k = (r["p07"], r["status"], r["slide"], r["cycle_id"])
    if k != prev: print("t=%.1f p07=%s %s slide=%s %s el=%.1f" % (r["t"], r["p07"], r["status"], r["slide"], r["cycle_id"], r["elapsed_seconds"]))
    prev = k

c = sqlite3.connect(E / "mock_desktop.db")
P = dt.datetime.fromisoformat
for r in c.execute("select id,station,button_id,status,delivery_status,attempts,created_at,confirmed_at,hex(payload) from outbox_event"):
    print("desktop outbox", r, "%.1f ms" % ((P(r[7]) - P(r[6])).total_seconds() * 1000))
