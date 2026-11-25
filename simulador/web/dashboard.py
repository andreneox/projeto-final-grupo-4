from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from threading import Thread

import uvicorn
from asyncua import ua
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from communications.desktop_start import DesktopStartClient, DesktopStartError
from communications.opcua_client import OpcUaClientWorker
from config.settings import DashboardSettings
from domain.production_plan import ProductionPlan
from domain.runtime_events import RuntimeEvent
from services.analytics import CALCULATION_REVISION, synchronize_dashboard_performance
from domain.work_instruction import cover_state
from services.base_import import BaseImportError, load_cycle_base
from services.process_configuration import (
    ProcessConfiguration,
    ProcessConfigurationStore,
)

SnapshotProvider = Callable[[], dict]
MAX_CYCLE_BASE_BYTES = 1024 * 1024


def create_dashboard_app(
    snapshot_provider: SnapshotProvider,
    configuration_store: ProcessConfigurationStore | None = None,
    desktop_start: DesktopStartClient | None = None,
    runtime_handler: Callable | None = None,
    instruction_provider: Callable[[], dict] | None = None,
    plc_control: OpcUaClientWorker | None = None,
    plc_session_started: Callable[[datetime], None] | None = None,
    read_plan: Callable[[], ProductionPlan] | None = None,
    save_plan: Callable[[ProductionPlan], None] | None = None,
    plc_base_cleared: Callable[[datetime], None] | None = None,
    cycle_base_imported: Callable[[str, list[float]], None] | None = None,
) -> FastAPI:
    base = Path(__file__).resolve().parent
    app = FastAPI(title="Dashboard da Linha", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=base / "static"), name="static")
    start_client = desktop_start or DesktopStartClient()
    plc_operation = asyncio.Lock()

    @app.middleware("http")
    async def current_dashboard(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["X-Lean-Revision"] = CALCULATION_REVISION
        return response

    def current_snapshot() -> dict:
        data = snapshot_provider()
        if "analytics" not in data:
            return data
        return {
            **data,
            "analytics": synchronize_dashboard_performance(data["analytics"]),
        }

    @app.get("/api/version")
    async def version() -> dict:
        return {
            "revision": CALCULATION_REVISION,
            "features": [
                "station_time_chart",
                "reconciled_downtime",
                "digital_work_instruction_e07",
            ],
            "performance_formula": "production_current / estimated_production * 100",
            "estimated_production": "integer part of current expected production",
        }

    @app.post("/api/runtime/events")
    def runtime_event(event: RuntimeEvent) -> dict:
        if runtime_handler is None:
            raise HTTPException(503, "O receptor de produção não está disponível.")
        try:
            return runtime_handler(event)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                503, "Não foi possível persistir o evento de produção."
            ) from exc

    def require_store() -> ProcessConfigurationStore:
        if configuration_store is None:
            raise HTTPException(503, "Banco de configuração não disponível.")
        return configuration_store

    @app.get("/api/process/configuration")
    def get_configuration() -> dict:
        try:
            return require_store().read()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                503, "Não foi possível consultar a configuração no banco."
            ) from exc

    @app.put("/api/process/configuration")
    def save_configuration(configuration: ProcessConfiguration) -> dict:
        try:
            return require_store().save(configuration)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                503,
                "Não foi possível salvar a configuração. Nenhum sucesso foi confirmado; tente consultar novamente.",
            ) from exc

    def require_plc_request(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Abra a dashboard para executar este comando do CLP.")
        if plc_operation.locked():
            raise HTTPException(409, "Há outro comando do CLP em andamento.")

    async def plc_result(command):
        try:
            return await asyncio.wrap_future(command)
        except TimeoutError as exc:
            raise HTTPException(504, "O Gateway não confirmou o comando. Confira o CLP antes de repetir.") from exc
        except (RuntimeError, OSError, ua.UaError) as exc:
            raise HTTPException(503, f"Comando do CLP indisponível: {exc}") from exc

    @app.get("/api/process/cycle-base")
    async def cycle_base_status() -> dict:
        if plc_control is None:
            return {"available": False, "ready": False}
        if plc_operation.locked():
            return {"available": True, "ready": False}
        try:
            ready = await plc_result(plc_control.request_cycle_base_ready())
        except HTTPException:
            ready = False
        return {"available": True, "ready": ready}

    @app.get("/api/process/production-plan")
    async def read_production_plan() -> ProductionPlan:
        if read_plan is None:
            raise HTTPException(503, "Plano do turno indisponível.")
        return await asyncio.to_thread(read_plan)

    @app.put("/api/process/production-plan")
    async def save_production_plan(plan: ProductionPlan) -> ProductionPlan:
        if save_plan is None:
            raise HTTPException(503, "Plano do turno indisponível.")
        try:
            await asyncio.to_thread(save_plan, plan)
        except Exception as exc:
            raise HTTPException(503, "Não foi possível salvar o plano do turno.") from exc
        return plan

    @app.post("/api/process/cycle-base")
    async def upload_cycle_base(request: Request, filename: str) -> dict:
        if plc_control is None:
            raise HTTPException(503, "Controle do CLP por OPC UA indisponível.")
        require_plc_request(request)
        async with plc_operation:
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_CYCLE_BASE_BYTES:
                    raise HTTPException(413, "A planilha deve ter até 1 MB.")
                data.extend(chunk)
            try:
                source_name = PureWindowsPath(filename).name
                imported = await asyncio.to_thread(load_cycle_base, bytes(data), source_name)
            except BaseImportError as exc:
                raise HTTPException(422, str(exc)) from exc
            await plc_result(plc_control.request_cycle_base(imported.cycle_times))
            if cycle_base_imported is not None:
                try:
                    await asyncio.to_thread(cycle_base_imported, source_name, imported.initial_takt_times)
                except Exception as exc:
                    raise HTTPException(503, "Base conferida no CLP. Falha ao salvar o nome e os valores de Takt.") from exc
        return {"ready": True, "message": "Base carregada e conferida no CLP."}

    @app.post("/api/process/start")
    async def start_process(request: Request) -> dict:
        if plc_control is not None:
            require_plc_request(request)
            async with plc_operation:
                confirmed_at = await plc_result(plc_control.request_simulation_start())
                if confirmed_at is None:
                    return {
                        "result": 0, "confirmed": False,
                        "message": "Pulso de Start enviado. Início da simulação ainda sem confirmação do Ladder.",
                    }
                if plc_session_started is not None:
                    await asyncio.to_thread(plc_session_started, confirmed_at)
            return {"result": 0, "confirmed": True, "message": "Início confirmado pelo CLP."}
        try:
            result = await start_client.start()
        except DesktopStartError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        return {
            "result": result,
            "message": (
                "Start confirmado pelo desktop."
                if result == 0
                else "O desktop recusou o Start (retorno 1)."
            ),
        }

    @app.post("/api/process/clear-base")
    async def clear_base(request: Request) -> dict:
        if plc_control is None or plc_base_cleared is None:
            raise HTTPException(503, "Limpeza pelo CLP indisponível.")
        require_plc_request(request)
        async with plc_operation:
            confirmed_at = await plc_result(plc_control.request_base_reset())
            try:
                await asyncio.to_thread(plc_base_cleared, confirmed_at)
            except Exception as exc:
                raise HTTPException(
                    503, "O CLP retornou ao estado de reset, mas a limpeza dos registros falhou."
                ) from exc
        return {"message": "Base do dia limpa. Aguardando o próximo Start confirmado."}

    def render_page(template: str) -> HTMLResponse:
        page = (base / "templates" / template).read_text(encoding="utf-8")
        for name in (
            "styles.css",
            "dashboard.js",
            "process.js",
            "station-chart.js",
            "instruction.js",
        ):
            digest = sha256((base / "static" / name).read_bytes()).hexdigest()[:16]
            page = page.replace(f"/static/{name}?v=REV09", f"/static/{name}?v={digest}")
        return HTMLResponse(page)

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return render_page("dashboard.html")

    @app.get("/graficos", include_in_schema=False)
    async def station_charts() -> HTMLResponse:
        return render_page("station_chart.html")

    @app.get("/instrucao/e07", include_in_schema=False)
    async def work_instruction() -> HTMLResponse:
        return render_page("instruction.html")

    def instruction_state() -> dict:
        return (
            instruction_provider()
            if instruction_provider
            else cover_state("disconnected")
        )

    @app.get("/api/instruction/e07")
    async def get_instruction_state() -> dict:
        return await asyncio.to_thread(instruction_state)

    @app.websocket("/ws/instruction/e07")
    async def instruction_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(await asyncio.to_thread(instruction_state))
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return await asyncio.to_thread(current_snapshot)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                data = await asyncio.to_thread(current_snapshot)
                await websocket.send_json(data)
                await asyncio.sleep(1)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app


class DashboardServerWorker:
    def __init__(
        self,
        settings: DashboardSettings,
        snapshot_provider: SnapshotProvider,
        status_callback: Callable[[str], None],
        configuration_store: ProcessConfigurationStore | None = None,
        desktop_start: DesktopStartClient | None = None,
        runtime_handler: Callable | None = None,
        instruction_provider: Callable[[], dict] | None = None,
        plc_control: OpcUaClientWorker | None = None,
        plc_session_started: Callable[[datetime], None] | None = None,
        read_plan: Callable[[], ProductionPlan] | None = None,
        save_plan: Callable[[ProductionPlan], None] | None = None,
        plc_base_cleared: Callable[[datetime], None] | None = None,
        cycle_base_imported: Callable[[str, list[float]], None] | None = None,
    ) -> None:
        self._settings = settings
        self._status_callback = status_callback
        self._app = create_dashboard_app(
            snapshot_provider,
            configuration_store,
            desktop_start,
            runtime_handler,
            instruction_provider,
            plc_control,
            plc_session_started,
            read_plan=read_plan,
            save_plan=save_plan,
            plc_base_cleared=plc_base_cleared,
            cycle_base_imported=cycle_base_imported,
        )
        self._server = uvicorn.Server(
            uvicorn.Config(
                self._app,
                host=settings.host,
                port=settings.port,
                log_level="warning",
                access_log=False,
            )
        )
        self._thread = Thread(target=self._run, name="web-dashboard", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def _run(self) -> None:
        try:
            self._status_callback(f"http://{self._settings.host}:{self._settings.port}")
            asyncio.run(self._server.serve())
        except Exception as exc:
            self._status_callback(f"indisponivel: {exc}")
