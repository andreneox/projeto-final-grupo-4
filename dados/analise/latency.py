import sqlite3, datetime as dt, statistics as st, json, collections
ROOT = r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing"
D = r"C:\Users\johng\AppData\Local\Temp\claude\5d4b98baeb9c066d\2cfb3df3-19ce-4d01-a786-e84e1fafb8c3\scratchpad"
P = lambda s: dt.datetime.fromisoformat(s)
BTN = {1: "Qualidade", 2: "Equipamento", 3: "Processo", 4: "Material"}
g = sqlite3.connect(f"file:{ROOT}\\Gateway\\data\\gateway.db?mode=ro", uri=True)
rows = g.execute("select id,event_uid,station,button_id,status,occurred_at,captured_at,plc_acknowledged_at,confirmed_at,attempts,hex(payload) from gateway_event order by id").fetchall()
ev = []
for r in rows:
    cap, ack, conf = P(r[6]), P(r[7]), P(r[8])
    ev.append(dict(id=r[0], uid=r[1], station=r[2], button=BTN[r[3]], status="ON" if r[4] == 1 else "OFF",
                   occurred=r[5], cap_to_plcack_ms=(ack - cap).total_seconds() * 1000,
                   cap_to_tcpconf_ms=(conf - cap).total_seconds() * 1000, attempts=r[9], hex=r[10]))
for e in ev: print(e)
for k in ["cap_to_plcack_ms", "cap_to_tcpconf_ms"]:
    v = [e[k] for e in ev]
    print(k, "min %.1f med %.1f media %.1f max %.1f" % (min(v), st.median(v), st.mean(v), max(v)))
print("estacoes", collections.Counter(e["station"] for e in ev), "botoes", collections.Counter(e["button"] for e in ev))

r = sqlite3.connect(f"file:{ROOT}\\simulador\\data\\reference_receiver.db?mode=ro", uri=True)
print("recepcoes por resultado", r.execute("select result,count(*) from reception group by result").fetchall())
print("por tipo", r.execute("select message_type,count(*) from reception group by message_type").fetchall())
print("faixa", r.execute("select min(received_at),max(received_at) from reception").fetchone())
print("por dia", r.execute("select substr(received_at,1,10),message_type,count(*) from reception group by 1,2").fetchall())
lat = []
for rec, occ, mt in r.execute("select received_at,occurred_at,message_type from reception where occurred_at is not null"):
    lat.append(((P(rec) - P(occ)).total_seconds(), mt))
print("atraso recebido-ocorrido (s) tipo1:", [round(x, 3) for x, m in lat if m == 1][:40])
print("ocorrencias", r.execute("select count(*), sum(closed_at is null) from stop_occurrence").fetchone())
print("ocorr por botao", r.execute("select button_id,count(*) from stop_occurrence group by 1").fetchall())
print("defect", r.execute("select count(*) from defect_item").fetchone(), "plan", r.execute("select * from production_plan").fetchall())
print("proc cfg", r.execute("select station,cycle_time_seconds,has_prototype from process_configuration").fetchall())
m = sqlite3.connect(f"file:{ROOT}\\simulador\\data\\mock_line.db?mode=ro", uri=True)
for x in m.execute("select id,station,button_id,status,occurred_at,delivery_status,created_at,confirmed_at,hex(payload) from outbox_event"):
    print("mock outbox", x, "lat ms %.1f" % ((P(x[7]) - P(x[6])).total_seconds() * 1000))
json.dump(ev, open(f"{D}\\gateway_events.json", "w"), indent=1)
