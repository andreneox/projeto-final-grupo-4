const stationCount = 12;
const stationColumns = new Map();
const waiting = { color: "waiting", text: "Aguardando", label: "Aguardando produto" };
const processStates = [
  waiting,
  waiting,
  { color: "processing", text: "Processando", label: "Processando produto" },
  { color: "completed", text: "Finalizou", label: "Finalizou o produto e aguarda os demais postos" },
];
const andonState = { color: "andon", led: "stopped", text: "Andon ativo", label: "Andon ativo · solicitou a parada da linha" };
const pausedState = { color: "paused", led: "paused", text: "Linha parada", label: "Linha parada por Andon em outro posto" };
const rows = {
  status: document.querySelector("#row-status"),
  takt: document.querySelector("#row-takt"),
  cycle: document.querySelector("#row-cycle"),
  availability: document.querySelector("#row-availability"),
  performance: document.querySelector("#row-performance"),
  quality: document.querySelector("#row-quality"),
  oee: document.querySelector("#row-oee"),
};

function buildTable() {
  const head = document.querySelector("#station-head");
  for (let station = 1; station <= stationCount; station += 1) {
    const label = `P${String(station).padStart(2, "0")}`;
    const heading = document.createElement("th");
    heading.scope = "col";
    heading.textContent = label;
    head.appendChild(heading);
    const column = [heading];

    Object.entries(rows).forEach(([name, row]) => {
      const cell = document.createElement("td");
      cell.dataset.station = String(station);
      cell.dataset.metric = name;
      cell.textContent = "—";
      row.appendChild(cell);
      column.push(cell);
    });
    stationColumns.set(station, column);
  }
}

function setCell(metric, station, text, className = "") {
  const cell = document.querySelector(
    `[data-metric="${metric}"][data-station="${station}"]`
  );
  cell.className = className;
  cell.textContent = text;
}

function percent(value) {
  return Number.isFinite(value) ? `${value.toFixed(1).replace(".", ",")}%` : "—";
}

function seconds(value) {
  return Number.isFinite(value) ? `${value.toFixed(1).replace(".", ",")} s` : "—";
}

function minutes(value, digits = 1) {
  return Number.isFinite(value) ? `${value.toFixed(digits).replace(".", ",")} min` : "—";
}

function renderDowntime(analytics) {
  const fields = { qualidade: "quality", processo: "process", material: "material", equipamento: "equipment", total: "total" };
  Object.entries(fields).forEach(([category, id]) => {
    const cell = document.querySelector(`#stop-${id}`);
    cell.textContent = minutes(analytics.downtime_minutes[category], 2);
    cell.title = analytics.downtime_seconds && Number.isFinite(analytics.downtime_seconds[category])
      ? `Tempo registrado: ${seconds(analytics.downtime_seconds[category])}` : "";
  });
  const note = document.querySelector("#stop-overlap-note");
  const overlap = analytics.downtime_overlap_minutes ?? 0;
  note.hidden = !(overlap > 0);
  note.textContent = overlap > 0
    ? `${minutes(overlap, 2)} em comum entre categorias foram descontados do total para evitar duplicidade.` : "";
}

function renderConnection(opcua) {
  const container = document.querySelector(".connection");
  const label = document.querySelector("#connection-label");
  const updated = document.querySelector("#updated-at");
  container.classList.toggle("online", opcua.connected);
  container.classList.toggle("offline", !opcua.connected);
  container.title = opcua.connected ? "OPC UA conectado" : `OPC UA: ${opcua.status}`;
  container.setAttribute("aria-label", container.title);
  label.textContent = opcua.connected ? "OPC UA conectado" : "OPC UA desconectado";
  updated.textContent = opcua.last_seen
    ? `Atualizado ${new Date(opcua.last_seen).toLocaleTimeString("pt-BR")}`
    : opcua.status;
}

function renderStations(snapshot) {
  const lineStopped = Object.values(snapshot.opcua.stations).some((station) =>
    Object.values(station.andon).includes(true)
  );
  for (let station = 1; station <= stationCount; station += 1) {
    const key = String(station);
    const telemetry = snapshot.opcua.stations[key];
    const metrics = snapshot.analytics.stations[key];
    const andonValues = Object.values(telemetry.andon);
    const stopped = andonValues.includes(true);
    const known = snapshot.opcua.connected && andonValues.every((value) => value !== null);
    const processStatus = snapshot.opcua.connected ? processStates[telemetry.process_status] : undefined;
    const process = stopped ? andonState : lineStopped ? pausedState : processStatus;
    stationColumns.get(station).forEach((element) => {
      if (process) {
        element.dataset.processState = process.color;
      } else {
        delete element.dataset.processState;
      }
    });
    const cell = document.querySelector(
      `[data-metric="status"][data-station="${station}"]`
    );
    const led = document.createElement("span");
    led.className = `status-led ${process?.led ?? (known ? "running" : "unknown")}`;
    const state = process?.label ?? (known ? "sem solicitação de parada" : "sem telemetria");
    led.title = `Posto ${String(station).padStart(2, "0")}: ${state}`;
    led.setAttribute("role", "img");
    led.setAttribute("aria-label", led.title);
    if (process) {
      const indicator = document.createElement("span");
      indicator.className = "status-indicator";
      const text = document.createElement("span");
      text.className = "status-text";
      text.textContent = process.text;
      text.setAttribute("aria-hidden", "true");
      indicator.append(led, text);
      cell.replaceChildren(indicator);
    } else {
      cell.replaceChildren(led);
    }

    const importedTakt = snapshot.imported_cycle_base?.takt_times?.[station - 1];
    setCell("takt", station, seconds(importedTakt ?? telemetry.takt_time), "value-muted");
    setCell("cycle", station, seconds(telemetry.cycle_time), "value-muted");
    setCell("availability", station, percent(metrics.availability), "percent");
    setCell("performance", station, percent(metrics.performance), "percent");
    document.querySelector(`[data-metric="performance"][data-station="${station}"]`).title =
      snapshot.analytics.timing?.performance_ready
        ? "Produção atual do P12 ÷ Produção Estimada exibida × 100"
        : "Aguardando ciclo concluído no P12 e Produção Estimada maior que zero";
    setCell("quality", station, percent(metrics.quality), "percent");
    const counts = snapshot.analytics.production_counts?.stations[key];
    if (counts) {
      document.querySelector(`[data-metric="quality"][data-station="${station}"]`).title =
        `${counts.good} peça(s) boa(s) no P12; ${counts.defective} defeito(s) neste posto`;
    }
    setCell("oee", station, percent(metrics.oee), "percent");
  }
}

function renderSummary(analytics) {
  const timing = analytics.timing;
  if (timing) {
    document.querySelector("#production-target").textContent = `${timing.production_target} peças`;
    document.querySelector("#available-time").textContent = minutes(timing.available_time_minutes);
    document.querySelector("#elapsed-time").textContent = seconds(timing.elapsed_seconds);
    document.querySelector("#productive-time").textContent = seconds(timing.production_seconds);
    const estimatedProduction = timing.estimated_production ?? Math.floor(timing.expected_production);
    document.querySelector("#expected-production").textContent = `${estimatedProduction} peças`;
  }
  const counts = analytics.production_counts?.line;
  if (counts) {
    document.querySelector("#current-production").textContent = String(counts.good);
    document.querySelector("#defect-quantity").textContent = String(counts.defective);
  }
  document.querySelector("#line-availability").textContent = percent(analytics.line.availability);
  document.querySelector("#line-performance").textContent = percent(analytics.line.performance);
  const estimatedProduction = timing?.estimated_production ?? Math.floor(timing?.expected_production);
  document.querySelector("#line-performance").title = counts?.good > 0 && Number.isFinite(estimatedProduction) && estimatedProduction > 0
    ? `${counts.good} ÷ ${estimatedProduction} × 100 = ${percent(analytics.line.performance)}; revisão ${timing.calculation_revision ?? "anterior — reinicie o receptor após atualizar"}`
    : "Aguardando produção no P12 e Produção Estimada maior que zero";
  document.querySelector("#line-quality").textContent = percent(analytics.line.quality);
  document.querySelector("#line-oee").textContent = percent(analytics.line.oee);
  renderDowntime(analytics);
}

function render(snapshot) {
  const filename = snapshot.imported_cycle_base?.filename;
  document.querySelector("#imported-cycle-base").hidden = !filename;
  document.querySelector("#imported-cycle-base-name").textContent = filename ?? "";
  document.dispatchEvent(new CustomEvent("line-telemetry", { detail: snapshot.opcua }));
  renderConnection(snapshot.opcua);
  renderStations(snapshot);
  renderSummary(snapshot.analytics);
}

function connect() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws`);
  socket.addEventListener("message", (event) => render(JSON.parse(event.data)));
  socket.addEventListener("close", () => {
    document.dispatchEvent(new CustomEvent("line-telemetry", { detail: null }));
    document.querySelector("#connection-label").textContent = "Dashboard desconectada";
    document.querySelector(".connection").className = "connection offline";
    window.setTimeout(connect, 2000);
  });
}

buildTable();
connect();
