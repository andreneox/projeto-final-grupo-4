(() => {
  "use strict";
  const ns = "http://www.w3.org/2000/svg";
  const plot = { left: 64, right: 1176, top: 38, bottom: 322 };
  const columns = [];
  const ticks = [];
  const gridLines = [];
  let chartWidth = 1200;
  let chartHeight = 380;
  const modeButtons = { cycle: document.querySelector("#show-cycle"), takt: document.querySelector("#show-takt") };
  let mode = "cycle";
  let latest = null;
  let dashboardConnected = false;
  let socket = null;
  let reconnectTimer = null;
  let disposed = false;

  function svgNode(name, attributes, text = "") {
    const node = document.createElementNS(ns, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    node.textContent = text;
    return node;
  }

  function format(value) {
    return value.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 3 });
  }

  function buildChart() {
    const grid = document.querySelector("#chart-grid");
    for (let tick = 0; tick <= 4; tick += 1) {
      const y = plot.bottom - (plot.bottom - plot.top) * tick / 4;
      const line = svgNode("line", { x1: plot.left, x2: plot.right, y1: y, y2: y, class: tick === 0 ? "chart-baseline" : "chart-grid-line" });
      const label = svgNode("text", { x: plot.left - 16, y: y + 5, "text-anchor": "end", class: "chart-tick" });
      grid.appendChild(line);
      grid.appendChild(label);
      ticks.push(label);
      gridLines.push(line);
    }
    grid.appendChild(svgNode("text", { x: plot.left - 16, y: 17, "text-anchor": "end", class: "chart-axis-label" }, "s"));
    const group = document.querySelector("#chart-columns");
    const table = document.querySelector("#chart-value-rows");
    for (let station = 1; station <= 12; station += 1) {
      const stationName = `P${String(station).padStart(2, "0")}`;
      const slot = (plot.right - plot.left) / 12;
      const center = plot.left + slot * (station - 0.5);
      const column = svgNode("g", { "data-station": station, tabindex: "0", role: "img" });
      const title = svgNode("title", {});
      const bar = svgNode("rect", { x: center - slot * 0.25, y: plot.bottom, width: slot * 0.50, height: 0, rx: 5, fill: "url(#chart-column-fill)", class: "chart-bar" });
      const value = svgNode("text", { x: center, y: plot.bottom - 12, "text-anchor": "middle", class: "chart-column-value" });
      column.appendChild(title);
      column.appendChild(bar);
      column.appendChild(value);
      const stationLabel = svgNode("text", { x: center, y: 352, "text-anchor": "middle", class: "chart-station-label" }, stationName);
      column.appendChild(stationLabel);
      group.appendChild(column);
      const row = document.createElement("tr");
      const nameCell = document.createElement("th");
      nameCell.setAttribute("scope", "row");
      nameCell.textContent = stationName;
      const timeCell = document.createElement("td");
      row.appendChild(nameCell);
      row.appendChild(timeCell);
      table.appendChild(row);
      columns.push({ station, stationName, column, title, bar, value, timeCell, stationLabel });
    }
  }

  function resizeChart() {
    if (disposed) return;
    const chart = document.querySelector("#station-time-chart");
    const width = chart.clientWidth || 1200;
    const height = chart.clientHeight || 380;
    if (width === chartWidth && height === chartHeight) return;
    chartWidth = width;
    chartHeight = height;
    chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
    plot.right = width - 24;
    plot.bottom = Math.max(plot.top + 40, height - 58);
    ticks.forEach((tick, index) => {
      const y = plot.bottom - (plot.bottom - plot.top) * index / 4;
      tick.setAttribute("y", String(y + 5));
      gridLines[index].setAttribute("y1", String(y));
      gridLines[index].setAttribute("y2", String(y));
      gridLines[index].setAttribute("x2", String(plot.right));
    });
    const slot = (plot.right - plot.left) / 12;
    columns.forEach((column, index) => {
      const center = plot.left + slot * (index + 0.5);
      column.bar.setAttribute("x", String(center - slot * 0.25));
      column.bar.setAttribute("width", String(slot * 0.5));
      column.value.setAttribute("x", String(center));
      column.stationLabel.setAttribute("x", String(center));
      column.stationLabel.setAttribute("y", String(plot.bottom + 30));
    });
    renderChart();
  }

  function renderConnection() {
    const online = dashboardConnected && latest?.connected === true;
    const connection = document.querySelector(".connection");
    connection.classList.toggle("online", online);
    connection.classList.toggle("offline", !online);
    document.querySelector("#connection-label").textContent = online ? "OPC UA conectado" : dashboardConnected ? "OPC UA desconectado" : latest ? "Dashboard desconectado" : "Aguardando conexão";
    const lastSeen = latest?.last_seen ? new Date(latest.last_seen) : null;
    const validDate = lastSeen && Number.isFinite(lastSeen.getTime());
    document.querySelector("#updated-at").textContent = validDate ? `Atualizado ${lastSeen.toLocaleTimeString("pt-BR")}` : "Aguardando telemetria";
    const note = document.querySelector("#chart-connection-note");
    const noteText = online ? "Atualização em tempo real" : latest ? "Sem conexão: os valores exibidos podem estar desatualizados." : "Aguardando dados dos postos.";
    if (note.textContent !== noteText) note.textContent = noteText;
    note.classList.toggle("is-live", online);
    connection.setAttribute("aria-label", document.querySelector("#connection-label").textContent);
    document.querySelector("#station-time-chart").classList.toggle("stale", !online && latest !== null);
  }

  function renderChart() {
    const label = mode === "cycle" ? "Ciclo" : "Takt time";
    const field = mode === "cycle" ? "cycle_time" : "takt_time";
    const values = columns.map(({ station }) => {
      const value = latest?.stations?.[String(station)]?.[field];
      return Number.isFinite(value) && value >= 0 ? value : null;
    });
    const maximum = Math.max(0, ...values.filter(value => value !== null));
    const target = maximum > 0 ? maximum * 1.12 : 1;
    const magnitude = 10 ** Math.floor(Math.log10(target));
    const ceiling = Math.ceil(target / magnitude * 2) / 2 * magnitude;
    ticks.forEach((tick, index) => {
      tick.textContent = (ceiling * index / 4).toLocaleString("pt-BR", { maximumFractionDigits: 6 });
    });
    const descriptions = [];
    columns.forEach((column, index) => {
      const value = values[index];
      const height = value === null ? 0 : value / ceiling * (plot.bottom - plot.top);
      const y = plot.bottom - height;
      const text = value === null ? "—" : format(value);
      column.bar.setAttribute("y", String(y));
      column.bar.setAttribute("height", String(height));
      column.value.setAttribute("y", String(y - 12));
      column.value.textContent = text;
      column.timeCell.textContent = text;
      const description = `${column.stationName}: ${value === null ? "sem dados" : `${text} segundos`}`;
      column.title.textContent = `${label} · ${description}`;
      column.column.setAttribute("aria-label", `${label} · ${description}`);
      descriptions.push(description);
    });
    Object.entries(modeButtons).forEach(([name, button]) => {
      button.classList.toggle("active", name === mode);
      button.setAttribute("aria-pressed", String(name === mode));
    });
    document.querySelector("#chart-heading").textContent = `${label} por posto`;
    document.querySelector("#chart-svg-title").textContent = `${label} por posto, em segundos`;
    document.querySelector("#chart-svg-description").textContent = descriptions.join("; ");
    document.querySelector("#chart-table-caption").textContent = `${label} por posto (s)`;
    document.querySelector("#chart-help").textContent = mode === "cycle"
      ? "Ciclo: último tempo de ciclo informado por posto."
      : "Takt time: ritmo de referência informado por posto.";
  }

  function connect() {
    if (disposed) return;
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const currentSocket = new WebSocket(`${scheme}://${window.location.host}/ws`);
    socket = currentSocket;
    currentSocket.addEventListener("message", event => {
      if (socket !== currentSocket || disposed) return;
      let snapshot;
      try { snapshot = JSON.parse(event.data); } catch { return; }
      if (!snapshot?.opcua || typeof snapshot.opcua !== "object") return;
      latest = snapshot.opcua;
      dashboardConnected = true;
      renderChart();
      renderConnection();
    });
    currentSocket.addEventListener("error", () => currentSocket.close());
    currentSocket.addEventListener("close", () => {
      if (socket !== currentSocket) return;
      dashboardConnected = false;
      renderConnection();
      if (!disposed && reconnectTimer === null) {
        reconnectTimer = window.setTimeout(() => { reconnectTimer = null; connect(); }, 2000);
      }
    });
  }

  Object.entries(modeButtons).forEach(([name, button]) => {
    button.addEventListener("click", () => { mode = name; renderChart(); });
  });
  window.addEventListener("pagehide", () => {
    disposed = true;
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
    socket?.close();
  });
  // Back/forward cache can restore the document after pagehide closed its socket.
  window.addEventListener("pageshow", () => {
    if (disposed) { disposed = false; reconnectTimer = null; resizeChart(); connect(); }
  });
  buildChart();
  renderChart();
  resizeChart();
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resizeChart).observe(document.querySelector("#station-time-chart"));
  } else {
    window.addEventListener("resize", resizeChart);
  }
  connect();
})();
