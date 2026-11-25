from __future__ import annotations

from collections.abc import Callable
from threading import Condition, Thread
import time
from typing import Protocol

from gateway.config import MotorOutputSettings


class MotorDriver(Protocol):
    frequency: float

    def enable(self) -> None: ...

    def set_frequency(self, frequency: float) -> None: ...

    def disable(self) -> None: ...

    def close(self) -> None: ...


class MotorDC:
    """STEP/DIR/EN interface adapted from the local MotorDC controller.

    The worker owns ramps and serializes all GPIO access. EN is active LOW,
    STEP uses a 50% duty cycle, and DIR stays in the configured clockwise state.
    """

    def __init__(self, settings: MotorOutputSettings, pin_factory=None) -> None:
        from gpiozero import OutputDevice, PWMOutputDevice

        self.frequency = 0.0
        self._enabled = False
        self._owns_factory = pin_factory is None
        self._pin_factory = pin_factory
        self._en = self._dir = self._step = None
        try:
            if self._pin_factory is None:
                from gpiozero.pins.pigpio import PiGPIOFactory

                self._pin_factory = PiGPIOFactory()
            self._en = OutputDevice(
                settings.en_pin, active_high=False, initial_value=False,
                pin_factory=self._pin_factory,
            )
            self._dir = OutputDevice(
                settings.dir_pin, initial_value=settings.clockwise_high,
                pin_factory=self._pin_factory,
            )
            self._step = PWMOutputDevice(
                settings.step_pin, initial_value=0,
                frequency=settings.minimum_frequency, pin_factory=self._pin_factory,
            )
        except BaseException:
            try:
                self.close()
            except Exception:
                pass  # Preserve the initialization error after attempting cleanup.
            raise

    def enable(self) -> None:
        if not self._enabled:
            self._en.on()
            self._enabled = True
            time.sleep(0.001)

    def set_frequency(self, frequency: float) -> None:
        if frequency <= 0:
            self._step.value = 0
            self.frequency = 0.0
            return
        self._step.frequency = frequency
        self._step.value = 0.5
        self.frequency = frequency

    def disable(self) -> None:
        try:
            if self._en is not None:
                self._en.off()
        finally:
            try:
                if self._step is not None:
                    self._step.value = 0
            finally:
                self._enabled = False
                self.frequency = 0.0

    def close(self) -> None:
        error = None
        try:
            self.disable()
        except Exception as exc:
            error = exc
        devices = [self._step, self._dir, self._en]
        if self._owns_factory:
            devices.append(self._pin_factory)
        for device in devices:
            if device is not None:
                try:
                    device.close()
                except Exception as exc:
                    if error is None:
                        error = exc
        if error is not None:
            raise error


StatusCallback = Callable[[str], None]
DriverFactory = Callable[[MotorOutputSettings], MotorDriver]


class RaspberryMotorOutput:
    """Applies D112 and D1200 on one worker, with interruptible speed ramps."""

    def __init__(
        self,
        settings: MotorOutputSettings,
        status_callback: StatusCallback,
        driver_factory: DriverFactory = MotorDC,
    ) -> None:
        self._settings = settings
        self._status_callback = status_callback
        self._driver_factory = driver_factory
        self._condition = Condition()
        self._desired_speed = 0
        self._immediate_stop = False
        self._revision = 0
        self._stopping = False
        self._thread = Thread(target=self._run, name="motor-output", daemon=True)
        self._driver: MotorDriver | None = None
        self._last_status: str | None = None

    def start(self) -> None:
        if not self._settings.enabled:
            self._set_status("disabled")
            return
        self._thread.start()

    def set_motor_state(self, motor_on: bool, speed: int) -> None:
        if not isinstance(motor_on, bool):
            raise ValueError("Motor state must be boolean")
        if isinstance(speed, bool) or not isinstance(speed, int) or not 0 <= speed <= 100:
            raise ValueError("Motor speed must be an integer between 0 and 100")
        desired_speed = speed if motor_on else 0
        with self._condition:
            if self._stopping or not self._settings.enabled:
                return
            if desired_speed == self._desired_speed and not self._immediate_stop:
                return
            self._desired_speed = desired_speed
            self._immediate_stop = False
            self._revision += 1
            self._condition.notify_all()

    def disable(self) -> None:
        """Cancel a ramp and disable EN on the worker after a PLC read fault."""
        with self._condition:
            if self._stopping or not self._settings.enabled:
                return
            if self._immediate_stop:
                return
            self._desired_speed = 0
            self._immediate_stop = True
            self._revision += 1
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise RuntimeError("Motor worker did not finish shutdown")

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    if self._stopping:
                        return
                    speed = self._desired_speed
                    immediate_stop = self._immediate_stop
                    revision = self._revision
                try:
                    if self._driver is None:
                        self._driver = self._driver_factory(self._settings)
                    if immediate_stop:
                        self._driver.disable()
                    elif not self._ramp(speed, revision):
                        continue
                    self._set_status(
                        f"speed {speed}%, commanded frequency {self._driver.frequency:g} Hz"
                    )
                except Exception as exc:
                    self._close_driver()
                    self._set_status(f"unavailable: {exc}")
                    with self._condition:
                        if self._stopping:
                            return
                        if self._revision == revision:
                            self._condition.wait(self._settings.retry_interval_seconds)
                    continue
                with self._condition:
                    while not self._stopping and self._revision == revision:
                        self._condition.wait()
        finally:
            self._close_driver()

    def _ramp(self, speed: int, revision: int) -> bool:
        driver = self._driver
        target = 0.0
        if speed > 0:
            target = self._settings.minimum_frequency + (
                self._settings.maximum_frequency - self._settings.minimum_frequency
            ) * speed / 100.0
        origin = driver.frequency
        with self._condition:
            if self._stopping or self._revision != revision:
                return False
            if speed > 0:
                driver.enable()
            if origin == target:
                if speed == 0:
                    driver.disable()
                return True
        started = time.monotonic()
        while True:
            with self._condition:
                if self._stopping or self._revision != revision:
                    return False
                elapsed = time.monotonic() - started
                self._condition.wait(min(
                    0.01, max(0.0, self._settings.ramp_seconds - elapsed)
                ))
                if self._stopping or self._revision != revision:
                    return False
                fraction = min(
                    (time.monotonic() - started) / self._settings.ramp_seconds, 1.0
                )
                driver.set_frequency(origin + (target - origin) * fraction)
                if fraction == 1.0:
                    if speed == 0:
                        driver.disable()
                    return True

    def _close_driver(self) -> None:
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                driver.close()
            except Exception as exc:
                self._set_status(f"failed to disable or release motor GPIOs: {exc}")

    def _set_status(self, status: str) -> None:
        if status != self._last_status:
            self._last_status = status
            self._status_callback(status)
