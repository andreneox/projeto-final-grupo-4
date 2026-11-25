import json, re, datetime as dt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

D = r"C:\Users\johng\AppData\Local\Temp\claude\5d4b98baeb9c066d\2cfb3df3-19ce-4d01-a786-e84e1fafb8c3\scratchpad"
IMG = r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing\Docs\Relatorio_Final\Imagens"
LOG = r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing\Gateway\logs\gateway.log"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, GRAY, RED, GREEN = "#2a6fb0", "#e07b1a", "#8a8a8a", "#c0392b", "#2e8b57"

# --- 1. latencia dos 18 eventos reais -------------------------------------------
ev = json.load(open(f"{D}\\gateway_events.json"))
x = [e["id"] for e in ev]
a = [e["cap_to_plcack_ms"] for e in ev]
b = [e["cap_to_tcpconf_ms"] - e["cap_to_plcack_ms"] for e in ev]
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.bar(x, a, color=BLUE, label="Captura no SQLite → ACK P10000 no CLP (Modbus FC05)")
ax.bar(x, b, bottom=a, color=ORANGE, label="ACK P10000 → ACK TCP de 22 bytes do receptor")
for xi, ai, bi in zip(x, a, b):
    ax.text(xi, ai + bi + 0.6, f"{ai+bi:.0f}", ha="center", fontsize=8)
ax.set_xticks(x, [f"{e['id']}\n{e['button'][:4]}\n{e['status']}" for e in ev], fontsize=7)
ax.set_ylabel("Tempo desde a captura (ms)")
ax.set_xlabel("Evento (id no gateway.db, botão, estado) - posto P05, 27/09/2026")
ax.set_ylim(0, 48)
ax.legend(loc="upper left", fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(f"{IMG}\\ev_latencia_eventos_reais.png", dpi=180); plt.close(fig)

# --- 2. linha do tempo do log real ------------------------------------------------
rx = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+) (\S+) (\S+): (.*)$")
P = lambda s: dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
status, events, starts, sntp, errs = [], [], [], [], []
for line in open(LOG, encoding="utf-8", errors="replace"):
    m = rx.match(line.rstrip())
    if not m: continue
    ts, lvl, th, lg, msg = m.groups(); t = P(ts)
    if lg == "gateway" and msg.startswith("Modbus: connected"): status.append((t, 1))
    elif lg == "gateway" and msg.startswith("Modbus: unavailable"): status.append((t, 0))
    elif lg == "gateway" and "confirmed" in msg and msg.startswith("TCP: event"): events.append(t)
    elif lg == "gateway" and "started" in msg: starts.append(t)
    elif lg == "gateway" and msg.startswith("SNTP: synchronized"): sntp.append(t)
    elif lg == "pymodbus.logging" and lvl == "ERROR": errs.append(t)
end = P("2026-09-28 13:11:27")
fig, ax = plt.subplots(figsize=(9, 3.4))
segs = status + [(end, status[-1][1])]
for (t0, s), (t1, _) in zip(segs, segs[1:]):
    ax.fill_between([t0, t1], 0, 1, color=GREEN if s else RED, alpha=0.35 if s else 0.25, step="post", lw=0)
ax.vlines(events, 1.05, 1.35, color=BLUE, lw=1.2, label=f"Evento de Andon confirmado por TCP ({len(events)})")
ax.vlines(starts, -0.35, -0.05, color="black", lw=1.5, label=f"Início do Gateway ({len(starts)})")
ax.plot([], [], color=GREEN, alpha=0.5, lw=8, label="Modbus conectado ao CLP (COM10)")
ax.plot([], [], color=RED, alpha=0.4, lw=8, label="Modbus indisponível (nova tentativa a cada 2 s)")
ax.set_ylim(-0.45, 1.6); ax.set_yticks([])
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H:%M"))
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, fontsize=8, frameon=False)
ax.set_title("gateway.log - execução real no CLP LS XGK (27/09/2026 16:57 a 28/09/2026 13:11)", fontsize=10)
fig.tight_layout(); fig.savefig(f"{IMG}\\ev_linha_tempo_gateway_log.png", dpi=180); plt.close(fig)
print("status transitions", [(str(t), s) for t, s in status])
print("events", len(events), "starts", [str(s) for s in starts], "sntp", [str(s) for s in sntp], "errs", len(errs))
