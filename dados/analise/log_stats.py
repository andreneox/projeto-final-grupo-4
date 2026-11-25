import re, collections
LOG = r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing\Gateway\logs\gateway.log"
rx = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+) (\w+) (\S+) (\S+): (.*)$")
levels = collections.Counter(); loggers = collections.Counter(); gw_msgs = collections.Counter()
first = last = None; starts = []; samples = {}
for line in open(LOG, encoding="utf-8", errors="replace"):
    m = rx.match(line.rstrip("\n"))
    if not m: continue
    ts, lvl, thread, logger, msg = m.groups()
    first = first or ts; last = ts
    levels[lvl] += 1; loggers[logger] += 1
    if logger == "gateway" or lvl in ("WARNING", "ERROR"):
        key = re.sub(r"\d[\d:.,T+\-]*", "#", msg)[:110]
        gw_msgs[(lvl, logger, key)] += 1
        samples.setdefault((lvl, logger, key), f"{ts} {thread}: {msg[:220]}")
    if "Gateway" in msg and "started" in msg: starts.append(ts)
print("periodo", first, "->", last)
print("niveis", dict(levels))
print("loggers", loggers.most_common(12))
print("inicios", len(starts), starts[:3], starts[-3:])
for k, n in sorted(gw_msgs.items(), key=lambda x: -x[1])[:60]:
    print(f"{n:6d} {k[0]:7s} {k[1]:30s} | {samples[k]}")
