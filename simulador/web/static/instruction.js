(() => {
  "use strict";
  const titles = ["Capa", "01 Conferir unidade e kit", "02 Posicionar no gabarito", "03 Fixar as conexões", "04 Inspecionar e registrar"];
  const images = [1, 2, 3, 4, 5].map(index => document.querySelector(`#instruction-slide-${index}`));
  let socket = null, reconnect = null, disposed = false, lastReceived = null;

  function show(state) {
    const fromPlc = state?.source === "plc";
    const running = state?.status === "running";
    const requested = state?.slide;
    const slide = running && Number.isInteger(requested) && requested >= 2 && requested <= 5 ? requested : 1;
    images.forEach((image, index) => { image.hidden = index + 1 !== slide; });
    const elapsed = Number.isFinite(state?.elapsed_seconds) ? Math.max(0, state.elapsed_seconds) : 0;
    document.querySelector("#instruction-step").textContent = `Slide ${String(slide).padStart(2, "0")} · ${titles[slide - 1]}`;
    document.querySelector("#instruction-elapsed").textContent = `${Math.min(elapsed, 36).toFixed(1).replace(".", ",")} / 36,0 s`;
    document.querySelector("#instruction-progress").value = slide === 1 && state?.status !== "complete" ? 0 : Math.min(elapsed, 36);
    const status = document.querySelector("#instruction-status");
    const message = document.querySelector("#instruction-message");
    status.dataset.state = state?.status ?? "disconnected";
    if (state?.status === "paused") {
      status.textContent = "Linha parada";
      message.textContent = state.stop_station
        ? `Parada em P${String(state.stop_station).padStart(2, "0")} · ${state.stop_category}. Instrução na capa.`
        : "Solicitação de parada da linha. Instrução na capa.";
    } else if (state?.status === "interrupted") {
      status.textContent = "Aguardando próximo ciclo";
      message.textContent = "A instrução reiniciará no próximo início de ciclo do E07.";
    } else if (running && slide !== 1) {
      status.textContent = "E07 em ciclo";
      message.textContent = fromPlc ? "Sincronizado ao ciclo do P07 no CLP." : "Sincronizado ao ciclo do simulador.";
    } else if (state?.status === "complete") {
      status.textContent = fromPlc && state.short_cycle ? "Ciclo concluído" : "Sequência concluída";
      message.textContent = "Aguardando o próximo início de ciclo do E07.";
    } else if (state?.status === "waiting") {
      status.textContent = "Aguardando ciclo";
      message.textContent = fromPlc
        ? "Aguardando o início do próximo ciclo no P07."
        : "Importe uma base no simulador para iniciar os ciclos do E07.";
    } else {
      status.textContent = "Sem sincronização";
      message.textContent = "Aguardando o sinal de ciclo do P07. A instrução permanece na capa.";
    }
    const warning = document.querySelector("#instruction-warning");
    warning.hidden = !state?.short_cycle;
    if (state?.short_cycle) {
      const duration = Number(state.cycle_time_seconds).toFixed(1).replace(".", ",");
      warning.textContent = fromPlc
        ? `O P07 concluiu o ciclo em cerca de ${duration} s. A sequência completa da instrução leva 36 s.`
        : `A sequência tem 36 s e o ciclo atual do E07 tem ${duration} s. Um novo ciclo reinicia os slides; use ciclo de pelo menos 36 s para exibir todas as etapas completas.`;
    } else {
      warning.textContent = "";
    }
  }

  function connect() {
    if (disposed) return;
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const current = new WebSocket(`${scheme}://${window.location.host}/ws/instruction/e07`);
    socket = current;
    current.addEventListener("message", event => {
      if (disposed || socket !== current) return;
      let state;
      try { state = JSON.parse(event.data); } catch { show(null); return; }
      if (state?.station !== 7) { show(null); return; }
      lastReceived = performance.now();
      show(state);
    });
    current.addEventListener("error", () => current.close());
    current.addEventListener("close", () => {
      if (socket !== current) return;
      show(null);
      if (!disposed && reconnect === null) reconnect = window.setTimeout(() => { reconnect = null; connect(); }, 1000);
    });
  }

  const watchdog = window.setInterval(() => {
    if (!disposed && lastReceived !== null && performance.now() - lastReceived > 1500) show(null);
  }, 200);
  document.querySelector("#instruction-fullscreen").addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch { document.querySelector("#instruction-message").textContent = "Use F11 para abrir o navegador em tela cheia."; }
  });
  document.addEventListener("fullscreenchange", () => {
    document.querySelector("#instruction-fullscreen").textContent = document.fullscreenElement ? "Sair da tela cheia" : "Tela cheia";
  });
  window.addEventListener("pagehide", () => {
    disposed = true;
    if (reconnect !== null) window.clearTimeout(reconnect);
    socket?.close();
  });
  window.addEventListener("pageshow", () => {
    if (disposed) { disposed = false; reconnect = null; lastReceived = null; show(null); connect(); }
  });
  show(null);
  connect();
})();
