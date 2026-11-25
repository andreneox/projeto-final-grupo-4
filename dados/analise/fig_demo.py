import json, datetime as dt, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np

E = r"C:\Users\johng\AppData\Local\Temp\claude\5d4b98baeb9c066d\2cfb3df3-19ce-4d01-a786-e84e1fafb8c3\scratchpad\evid"
IMG = r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing\Docs\Relatorio_Final\Imagens"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
L = [json.loads(l) for l in open(f"{E}\\run1\\timeline.jsonl", encoding="utf-8")]
L = [r for r in L if r["t"] is not None]
t = np.array([r["t"] for r in L])

# --- 1. estados dos 12 postos -------------------------------------------------------
M = np.full((12, len(L)), np.nan)
andon = np.zeros((12, len(L)))
for j, r in enumerate(L):
    for s in range(12):
        st = r["snapshot"]["opcua"]["stations"][str(s + 1)]
        v = st["process_status"]; M[s, j] = -1 if v is None else v
        andon[s, j] = any(st["andon"].values())
cmap = ListedColormap(["#d9d9d9", "#f2d16b", "#f7e9a8", "#5cb85c", "#2e7d32"])  # -1,0,1,2,3
fig, ax = plt.subplots(figsize=(9.5, 4.2))
ax.pcolormesh(np.append(t, t[-1] + 2), np.arange(13) + 0.5, M, cmap=cmap, vmin=-1.5, vmax=3.5, shading="flat")
for s in range(12):
    on = andon[s] > 0
    if on.any():
        for j in np.where(on)[0]:
            ax.add_patch(plt.Rectangle((t[j], s + 0.5), 2.6, 1, color="#c0392b", lw=0))
ax.set_yticks(range(1, 13), [f"P{i:02d}" for i in range(1, 13)]); ax.invert_yaxis()
ax.set_xlabel("Tempo desde o Start confirmado (s)")
ax.legend(handles=[Patch(color="#f2d16b", label="0 - espera"), Patch(color="#f7e9a8", label="1 - preparação"),
                   Patch(color="#5cb85c", label="2 - processando"), Patch(color="#2e7d32", label="3 - concluído"),
                   Patch(color="#c0392b", label="Andon ativo")], ncol=5, fontsize=8, frameon=False,
          loc="upper center", bbox_to_anchor=(0.5, -0.17))
ax.set_title("Estados D01651-D01662 recebidos pela Dashboard via OPC UA (CLP emulado, amostras a cada ~2,6 s)", fontsize=9.5)
fig.tight_layout(); fig.savefig(f"{IMG}\\demo_estados_postos.png", dpi=180); plt.close(fig)

# --- 2. producao e OEE ----------------------------------------------------------------
an = [r["snapshot"]["analytics"] for r in L]
prod = [a["production_counts"]["line"]["good"] for a in an]
est = [a["timing"]["estimated_production"] for a in an]
expd = [a["timing"]["expected_production"] for a in an]
avail = [a["line"]["availability"] for a in an]
oee = [a["line"]["oee"] if a["line"]["oee"] is not None else np.nan for a in an]
stop = [a["downtime_seconds"]["total"] for a in an]
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
ax1.step(t, prod, where="post", color="#2a6fb0", lw=2, label="Produção atual (D16052, peças boas no P12)")
ax1.plot(t, expd, color="#8a8a8a", lw=1, ls="--", label="Produção esperada = meta x tempo decorrido / tempo disponível")
ax1.step(t, est, where="post", color="#e07b1a", lw=1.5, label="Produção estimada (parte inteira)")
ax1.set_ylabel("Peças"); ax1.legend(fontsize=8, frameon=False, loc="upper left")
ax2.plot(t, avail, color="#2e8b57", lw=2, label="Disponibilidade (%)")
ax2.plot(t, oee, color="#6a3d9a", lw=2, label="OEE da linha (%)")
ax2b = ax2.twinx(); ax2b.fill_between(t, stop, color="#c0392b", alpha=0.15, step="post"); ax2b.set_ylabel("Tempo parado acumulado (s)", color="#c0392b")
ax2b.spines["top"].set_visible(False)
ax2.set_ylabel("%"); ax2.set_ylim(0, 105); ax2.set_xlabel("Tempo desde o Start confirmado (s)")
ax2.legend(fontsize=8, frameon=False, loc="lower left")
fig.tight_layout(); fig.savefig(f"{IMG}\\demo_producao_oee.png", dpi=180); plt.close(fig)

last = an[-1]
print("final", t[-1], json.dumps(last["timing"])[:500], last["line"], last["downtime_seconds"], last["production_counts"]["line"])
for r in L:
    if r["snapshot"]["analytics"]["production_counts"]["line"]["good"] != (L[L.index(r) - 1]["snapshot"]["analytics"]["production_counts"]["line"]["good"] if L.index(r) else 0):
        print("peca em t=", r["t"])
