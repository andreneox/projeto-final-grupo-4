from domain.work_instruction import SEQUENCE_SECONDS, STEP_ENDS, WorkInstructionState


class PlcWorkInstruction:
    """Follow observed P07 transitions using the receiver's monotonic clock."""

    def __init__(self) -> None:
        self._cycle_sequence = 0
        self.reset()

    def reset(self) -> None:
        self.process_status: int | None = None
        self._started_at: float | None = None
        self._completed_seconds: float | None = None
        self._interrupted = False

    def update_status(
        self, status: int | None, now: float, *, connected: bool, stopped: bool
    ) -> None:
        previous = self.process_status
        if status == previous:
            return
        self.process_status = status
        self._completed_seconds = (
            now - self._started_at
            if status == 3 and self._started_at is not None
            else None
        )
        self._started_at = None
        self._interrupted = False
        # A first reading of 2 gives no indication of when that cycle began.
        if status == 2 and previous is not None and connected:
            if stopped:
                self._interrupted = True
            else:
                self._cycle_sequence += 1
                self._started_at = now

    def interrupt(self) -> None:
        if self.process_status == 2:
            self._started_at = None
            self._interrupted = True

    def snapshot(self, now: float) -> dict:
        state = WorkInstructionState(source="plc", sequence=self._cycle_sequence)
        if self._interrupted:
            state.status = "interrupted"
        elif self._started_at is not None:
            elapsed = now - self._started_at
            state.cycle_id = f"plc-p07-{self._cycle_sequence}"
            state.elapsed_seconds = min(elapsed, SEQUENCE_SECONDS)
            for slide, end in enumerate(STEP_ENDS, start=2):
                if elapsed < end:
                    state.status = "running"
                    state.slide = slide
                    break
            else:
                state.status = "complete"
        elif self._completed_seconds is not None:
            state.status = "complete"
            state.cycle_id = f"plc-p07-{self._cycle_sequence}"
            state.cycle_time_seconds = self._completed_seconds
            state.elapsed_seconds = min(self._completed_seconds, SEQUENCE_SECONDS)
            state.short_cycle = self._completed_seconds < SEQUENCE_SECONDS
        return state.model_dump()
