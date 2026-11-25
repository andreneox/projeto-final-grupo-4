from domain.models import AndonCategory
from domain.runtime_events import AndonRuntime, CycleRuntime, ResetRuntime


def handle_runtime_event(database, telemetry, event) -> dict:
    result = database.apply_runtime(event)
    if result["result"] != "applied":
        return result
    if isinstance(event, ResetRuntime):
        telemetry.reset_day()
    elif isinstance(event, AndonRuntime) and result.get("andon_result") != "ATRASADO":
        category = AndonCategory.from_button_id(event.button_id)
        telemetry.update(f"P{event.station:02d}/Andon/{category.label}", event.is_on)
    elif isinstance(event, CycleRuntime):
        telemetry.update(f"P{event.station:02d}/TaktTime", event.takt_time_seconds)
        telemetry.update(f"P{event.station:02d}/UltimoCiclo", event.cycle_time_seconds)
    return result
