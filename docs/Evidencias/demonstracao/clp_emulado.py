"""CLP LS XGK emulado (gemeo digital simplificado do Ladder) para gerar evidencias.

Servidor Modbus RTU sobre TCP (socket://127.0.0.1:5020) com o mesmo mapa usado
pelo Gateway em deploy/config.raspberry.toml. Uso exclusivo de demonstracao: os
dados produzidos aqui sao rotulados como "CLP emulado" no relatorio.
"""
from __future__ import annotations

import json, random, sys, threading, time
from datetime import datetime
from zoneinfo import ZoneInfo

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.framer import FramerType
from pymodbus.server import StartTcpServer

TZ = ZoneInfo("America/Manaus")
FC_CO, FC_HR, FC_IR = 1, 3, 4
D100, STATUS, COUNT, BASE = 100, 651, 15052, 16001
LOG = open(sys.argv[1] if len(sys.argv) > 1 else "clp_emulado.jsonl", "a", encoding="utf-8")
SCENARIO = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []   # [[t, station, button, on], ...]

device = ModbusDeviceContext(
    co=ModbusSequentialDataBlock(0, [0] * 16),
    di=ModbusSequentialDataBlock(0, [0] * 16),
    hr=ModbusSequentialDataBlock(0, [0] * 16400),
    ir=ModbusSequentialDataBlock(0, [0] * 200),
)
ctx = ModbusServerContext(devices=device, single=True)
get = lambda fc, a, n=1: device.getValues(fc, a, n)
put = lambda fc, a, v: device.setValues(fc, a, v)
lock = threading.Lock()


def log(kind, **data):
    LOG.write(json.dumps({"t": datetime.now(TZ).isoformat(), "kind": kind, **data}) + "\n"); LOG.flush()


def bcd(v): return ((v // 10) << 4) | (v % 10)


def event_words(station, button, on):
    now = datetime.now(TZ)
    wd = (now.weekday() + 1) % 7
    b = bytes([0, 1, 0, station, bcd(now.month), bcd(now.year % 100), bcd(now.hour), bcd(now.day),
               bcd(now.second), bcd(now.minute), bcd(now.year // 100), bcd(wd), 0, button, 0, 1 if on else 2])
    return [int.from_bytes(b[i:i + 2], "big") for i in range(0, 16, 2)]


class Line:
    def __init__(self):
        self.running = False; self.t0 = None
        self.state = [0] * 12; self.until = [0.0] * 12; self.index = [0] * 12
        self.buffer = [False] * 12; self.started = [0.0] * 12
        self.fifo = []; self.andon = {}; self.count = 0; self.prev = {}

    def base(self, st, k):
        return get(FC_HR, BASE + st * 24 + (k % 24))[0] / 10.0

    def coil_edge(self, addr):
        v = get(FC_CO, addr)[0]; p = self.prev.get(addr, 0); self.prev[addr] = v
        return v and not p

    def tick(self):
        now = time.monotonic()
        # P10001: aplica relogio (DATEWRP) e limpa a solicitacao
        if get(FC_CO, 1)[0]:
            put(FC_CO, 1, [0]); log("relogio_aplicado", words=get(FC_HR, 0, 4))
        # P10000: ACK do Gateway -> D00050=3, zera D100-D108
        if get(FC_CO, 0)[0] and get(FC_IR, D100)[0]:
            put(FC_IR, D100, [0] * 9); put(FC_CO, 0, [0]); log("ack_p10000")
        if not get(FC_IR, D100)[0] and self.fifo:
            put(FC_IR, D100, [8] + self.fifo.pop(0)); log("evento_publicado")
        if self.coil_edge(3):  # P10003 reset
            self.__init__(); self.prev[3] = 1
            put(FC_HR, STATUS, [0] * 12); put(FC_HR, COUNT, [0]); log("reset_p10003")
        if self.coil_edge(2) and not self.running:  # P10002 start
            self.running = True; self.t0 = now; self.buffer[0] = True; log("start_p10002")
        if self.running:
            self.scenario(now - self.t0)
            stopped = any(self.andon.values())
            for i in range(12):
                s = self.state[i]
                if stopped and s == 2:
                    self.until[i] += 0.1; continue
                if s == 0 and (i == 0 or self.buffer[i]):
                    self.buffer[i] = False; self.state[i] = 1; self.until[i] = now + 0.6
                elif s == 1 and now >= self.until[i]:
                    self.state[i] = 2; self.started[i] = now
                    self.until[i] = now + self.base(i, self.index[i]) * random.uniform(0.94, 1.08)
                elif s == 2 and now >= self.until[i]:
                    self.state[i] = 3; measured = now - self.started[i]
                    self.metrics(i, self.base(i, self.index[i]), measured); self.index[i] += 1
                    self.until[i] = now + 0.5
                elif s == 3 and now >= self.until[i] and (i == 11 or not self.buffer[i + 1]):
                    if i == 11:
                        self.count += 1; put(FC_HR, COUNT, [self.count]); log("peca_concluida", total=self.count)
                    else:
                        self.buffer[i + 1] = True
                    self.state[i] = 0
                    if i == 0: self.buffer[0] = True
            put(FC_HR, STATUS, self.state)
        motor = 1 if self.running and any(self.state[k] for k in (7, 8, 9)) and not any(self.andon.values()) else 0
        put(FC_IR, D100 + 12, [motor])
        words = [0, 0, 0]
        for (st, btn), on in self.andon.items():
            if on: words[(st - 1) // 4] |= 1 << (((st - 1) % 4) * 4 + btn - 1)
        put(FC_IR, D100 + 9, words)

    def metrics(self, i, takt, cycle):
        t, c = int(round(takt * 10)), int(round(cycle * 10))
        put(FC_IR, D100 + 13 + i * 4, [t & 0xFFFF, t >> 16, c & 0xFFFF, c >> 16])  # low_high

    def scenario(self, elapsed):
        while SCENARIO and elapsed >= SCENARIO[0][0]:
            _, st, btn, on = SCENARIO.pop(0)
            self.andon[(st, btn)] = bool(on); self.fifo.append(event_words(st, btn, on))
            log("andon", station=st, button=btn, on=bool(on))


line = Line()
put(FC_HR, 200, [60])  # D1200: 60 % de velocidade


def loop():
    while True:
        with lock: line.tick()
        time.sleep(0.1)


threading.Thread(target=loop, daemon=True).start()
log("clp_emulado_iniciado")
StartTcpServer(context=ctx, address=("127.0.0.1", 5020), framer=FramerType.RTU)
