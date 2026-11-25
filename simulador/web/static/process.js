(() => {
  // const configure = document.querySelector("#configure-process");
  const editPlan = document.querySelector("#edit-production-plan");
  const start = document.querySelector("#start-process");
  const importBase = document.querySelector("#import-cycle-base");
  const clearBase = document.querySelector("#clear-cycle-base");
  const cycleBaseFile = document.querySelector("#cycle-base-file");
  /*
  const dialog = document.querySelector("#process-dialog");
  const form = document.querySelector("#process-form");
  const fields = document.querySelector("#process-fields");
  const confirm = document.querySelector("#confirm-configuration");
  const cancel = document.querySelector("#cancel-configuration");
  const formFeedback = document.querySelector("#configuration-feedback");
  const rows = document.querySelector("#configuration-rows");
  const decimalDraft = /^\d*(?:[.,]\d*)?$/;
  */
  const dialog = document.querySelector("#plan-dialog");
  const form = document.querySelector("#plan-form");
  const fields = document.querySelector("#plan-fields");
  const confirm = document.querySelector("#save-plan");
  const cancel = document.querySelector("#cancel-plan");
  const target = document.querySelector("#plan-target");
  const minutes = document.querySelector("#plan-minutes");
  const feedback = document.querySelector("#process-feedback");
  const formFeedback = document.querySelector("#plan-feedback");
  const planUrl = "/api/process/production-plan";
  let loading = null;
  let saving = false;
  let starting = false;
  let importing = false;
  let clearing = false;
  let plcMode = null;
  let baseReady = false;
  let checkingBase = true;
  let stationsReady = false;

  function notify(message, error = false) {
    feedback.textContent = message;
    feedback.classList.toggle("error", error);
    feedback.hidden = false;
  }

  function showFormError(message) {
    formFeedback.textContent = message;
    formFeedback.hidden = false;
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {cache: "no-store", ...options});
    let data;
    try { data = await response.json(); }
    catch { throw new Error("O servidor retornou uma resposta inválida."); }
    if (!response.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail :
        "Confira os valores informados e tente novamente.");
    }
    return data;
  }

  function updateProcessControls() {
    const busy = importing || starting || clearing;
    editPlan.disabled = busy;
    importBase.hidden = !plcMode;
    importBase.disabled = busy;
    clearBase.hidden = !plcMode;
    clearBase.disabled = busy;
    start.disabled = checkingBase || busy || plcMode === null || (plcMode && (!baseReady || !stationsReady));
    start.title = "";
    if (plcMode && !baseReady) {
      start.title = "Importe uma base de tempos para habilitar o Start.";
    } else if (plcMode && !stationsReady) {
      start.title = "Aguardando os 12 postos no estado 0 e todos os Andons livres.";
    }
  }

  document.addEventListener("line-telemetry", ({detail: opcua}) => {
    const previouslyReady = stationsReady;
    stationsReady = opcua?.connected === true && Array.from({length: 12}, (_, i) => i + 1).every((station) => {
      const data = opcua.stations?.[station];
      const andons = Object.values(data?.andon ?? {});
      return data?.process_status === 0 && andons.length === 4 && andons.every((value) => value === false);
    });
    if (stationsReady && !previouslyReady && plcMode && !checkingBase && !importing && !starting && !clearing) {
      void checkCycleBase();
    }
    updateProcessControls();
  });

  async function checkCycleBase() {
    checkingBase = true;
    try {
      const state = await request("/api/process/cycle-base");
      plcMode = state.available;
      baseReady = state.ready;
    } catch {
      baseReady = false;
    } finally {
      checkingBase = false;
      updateProcessControls();
    }
  }

  importBase.addEventListener("click", () => {
    if (!importing && !starting && !clearing && !dialog.open) cycleBaseFile.click();
  });

  cycleBaseFile.addEventListener("change", async () => {
    const file = cycleBaseFile.files[0];
    cycleBaseFile.value = "";
    if (!file || importing || starting || clearing || dialog.open) return;
    importing = true;
    updateProcessControls();
    notify("Enviando a base e conferindo os registradores do CLP…");
    try {
      const result = await request(`/api/process/cycle-base?filename=${encodeURIComponent(file.name)}`, {
        method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: file,
      });
      baseReady = result.ready;
      notify(result.message);
    } catch (error) {
      notify(error.message || "Não foi possível carregar a base no CLP.", true);
      await checkCycleBase();
    } finally {
      importing = false;
      updateProcessControls();
    }
  });

  /* Configuração de tempos e protótipos desativada na dashboard.
  for (let station = 1; station <= 12; station += 1) {
    const code = `P${String(station).padStart(2, "0")}`;
    const row = document.createElement("div");
    row.className = "configuration-row";
    const label = document.createElement("label");
    label.htmlFor = `cycle-${station}`;
    label.textContent = code;
    const input = document.createElement("input");
    input.id = `cycle-${station}`;
    input.name = `cycle-${station}`;
    input.type = "text";
    input.inputMode = "decimal";
    input.required = true;
    input.autocomplete = "off";
    input.pattern = "[0-9]+([,.][0-9]+)?";
    input.setAttribute("aria-label", `Tempo de ciclo do posto ${code}, em segundos`);
    input.addEventListener("beforeinput", (event) => {
      if (typeof event.data !== "string" || event.isComposing) return;
      const next = input.value.slice(0, input.selectionStart) + event.data + input.value.slice(input.selectionEnd);
      if (!decimalDraft.test(next)) event.preventDefault();
    });
    input.addEventListener("input", () => {
      // Also handles paste, drag/drop and browsers without beforeinput support.
      if (decimalDraft.test(input.value)) input.dataset.previous = input.value;
      else input.value = input.dataset.previous || "";
      input.setCustomValidity("");
    });
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = `prototype-${station}`;
    checkbox.setAttribute("aria-label", `Protótipo físico do posto ${code}`);
    row.append(label, input, checkbox);
    rows.appendChild(row);
  }

  configure.addEventListener("click", async () => {
    if (starting || importing || dialog.open) return;
    form.reset();
    formFeedback.hidden = true;
    fields.disabled = true;
    confirm.disabled = true;
    confirm.textContent = "Carregando…";
    dialog.showModal();
    const controller = new AbortController();
    loading = controller;
    try {
      const configuration = await request("/api/process/configuration", {signal: controller.signal});
      if (!dialog.open || controller !== loading) return;
      for (const item of configuration.stations) {
        const input = document.querySelector(`#cycle-${item.station}`);
        input.value = String(item.cycle_time_seconds).replace(".", ",");
        input.dataset.previous = input.value;
        input.setCustomValidity("");
        document.querySelector(`#prototype-${item.station}`).checked = item.has_prototype === 1;
      }
      fields.disabled = false;
      confirm.disabled = false;
      document.querySelector("#cycle-1").focus();
    } catch (error) {
      if (error.name !== "AbortError" && dialog.open && controller === loading) showFormError(error.message);
    } finally {
      if (controller === loading) confirm.textContent = "Confirmar";
    }
  });

  cancel.addEventListener("click", () => { if (!saving) dialog.close(); });
  dialog.addEventListener("cancel", (event) => { if (saving) event.preventDefault(); });
  dialog.addEventListener("close", () => {
    if (loading) loading.abort();
    loading = null;
    configure.focus();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving || fields.disabled) return;
    const stations = [];
    for (let station = 1; station <= 12; station += 1) {
      const input = document.querySelector(`#cycle-${station}`);
      const cycle = Number(input.value.replace(",", "."));
      if (!Number.isFinite(cycle) || cycle <= 0) {
        input.setCustomValidity("Informe um número maior que zero.");
        input.reportValidity();
        return;
      }
      stations.push({station, cycle_time_seconds: cycle,
        has_prototype: document.querySelector(`#prototype-${station}`).checked ? 1 : 0});
    }
    saving = true;
    fields.disabled = true;
    confirm.disabled = cancel.disabled = true;
    confirm.textContent = "Salvando…";
    formFeedback.hidden = true;
    try {
      await request("/api/process/configuration", {method: "PUT",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify({stations})});
      dialog.close();
      notify("Configuração dos 12 postos salva com sucesso.");
    } catch (error) {
      showFormError(error.message || "Não foi possível salvar. Confira sua conexão.");
    } finally {
      saving = false;
      fields.disabled = false;
      confirm.disabled = cancel.disabled = false;
      confirm.textContent = "Confirmar";
    }
  });

  */

  function setPlanDisabled(disabled) {
    fields.disabled = confirm.disabled = disabled;
  }

  editPlan.addEventListener("click", async () => {
    if (editPlan.disabled || dialog.open) return;
    form.reset();
    formFeedback.hidden = true;
    setPlanDisabled(true);
    confirm.textContent = "Carregando…";
    dialog.showModal();
    const controller = new AbortController();
    loading = controller;
    try {
      const plan = await request(planUrl, {signal: controller.signal});
      if (!dialog.open || controller !== loading) return;
      target.value = String(plan.production_target);
      minutes.value = String(plan.available_time_minutes).replace(".", ",");
      setPlanDisabled(false);
      target.focus();
    } catch (error) {
      if (error.name !== "AbortError" && dialog.open && controller === loading) showFormError(error.message);
    } finally {
      if (controller === loading) confirm.textContent = "Salvar";
    }
  });

  cancel.addEventListener("click", () => { if (!saving) dialog.close(); });
  dialog.addEventListener("cancel", (event) => { if (saving) event.preventDefault(); });
  dialog.addEventListener("close", () => {
    loading?.abort();
    loading = null;
    editPlan.focus();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving || fields.disabled) return;
    const pieces = Number(target.value);
    const availableMinutes = Number(minutes.value.replace(",", "."));
    if (!Number.isSafeInteger(pieces) || pieces < 1 ||
        !Number.isFinite(availableMinutes) || availableMinutes <= 0) {
      showFormError("Informe uma meta inteira positiva e um tempo disponível maior que zero.");
      return;
    }
    saving = true;
    setPlanDisabled(true);
    cancel.disabled = true;
    confirm.textContent = "Salvando…";
    formFeedback.hidden = true;
    try {
      await request(planUrl, {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({production_target: pieces, available_time_minutes: availableMinutes}),
      });
      dialog.close();
      notify("Plano do turno salvo.");
    } catch (error) {
      showFormError(error.message);
    } finally {
      saving = false;
      setPlanDisabled(false);
      cancel.disabled = false;
      confirm.textContent = "Salvar";
    }
  });

  clearBase.addEventListener("click", async () => {
    if (clearBase.disabled || !plcMode || dialog.open) return;
    if (!window.confirm("Confirma o reset dos postos? A operação interrompe os ciclos em andamento e remove os registros de produção, defeitos e paradas do dia.")) return;
    clearing = true;
    updateProcessControls();
    clearBase.textContent = "Limpando…";
    notify("Aguardando o reset do CLP…");
    try {
      const result = await request("/api/process/clear-base", {method: "POST"});
      notify(result.message);
      await checkCycleBase();
    } catch (error) {
      notify(error.message, true);
    } finally {
      clearing = false;
      clearBase.textContent = "Limpar base";
      updateProcessControls();
    }
  });

  start.addEventListener("click", async () => {
    if (start.disabled || dialog.open) return;
    starting = true;
    updateProcessControls();
    start.textContent = "Iniciando…";
    notify(plcMode ? "Aguardando confirmação do CLP…" : "Aguardando confirmação do desktop…");
    try {
      const result = await request("/api/process/start", {method: "POST"});
      notify(result.message, result.result !== 0);
    } catch (error) {
      notify(error.message || "Falha na conexão. Confira o processo antes de repetir o Start.", true);
      if (plcMode) await checkCycleBase();
    } finally {
      starting = false;
      start.textContent = "Start";
      updateProcessControls();
    }
  });
  checkCycleBase();
})();
