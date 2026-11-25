from __future__ import annotations

from dataclasses import replace
from threading import get_ident
import time

import pytest

from gateway.config import MotorOutputSettings
from gateway.motor_output import MotorDC, RaspberryMotorOutput


class FakeMotor:
    def __init__(self) -> None:
        self.frequency = 0.0
        self.enabled = False
        self.closed = False
        self.calls = []
        self.threads = set()

    def enable(self) -> None:
        self.threads.add(get_ident())
        self.enabled = True

    def set_frequency(self, frequency: float) -> None:
        self.threads.add(get_ident())
        self.frequency = frequency
        self.calls.append(("frequency", frequency))

    def disable(self) -> None:
        self.threads.add(get_ident())
        self.enabled = False
        self.frequency = 0.0
        self.calls.append(("disable", 0))

    def close(self) -> None:
        self.disable()
        self.closed = True


def settings(**overrides) -> MotorOutputSettings:
    return replace(
        MotorOutputSettings(enabled=True, ramp_seconds=0.04, retry_interval_seconds=0.01),
        **overrides,
    )


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.002)
    raise AssertionError("condition was not reached before timeout")


def test_applies_d112_and_d1200_with_ramps_and_disables_on_shutdown() -> None:
    motor = FakeMotor()
    output = RaspberryMotorOutput(settings(), lambda _status: None, lambda _settings: motor)
    output.start()
    try:
        wait_until(lambda: motor.calls == [("disable", 0)])
        output.set_motor_state(True, 50)
        wait_until(lambda: motor.frequency == 2550)
        assert motor.enabled is True
        assert any(0 < value < 2550 for operation, value in motor.calls if operation == "frequency")

        output.set_motor_state(True, 100)
        wait_until(lambda: motor.frequency == 5000)
        output.set_motor_state(False, 100)
        wait_until(lambda: motor.frequency == 0 and not motor.enabled)

        output.set_motor_state(True, 25)
        wait_until(lambda: motor.frequency == 1325)
        output.set_motor_state(True, 0)
        wait_until(lambda: motor.frequency == 0 and not motor.enabled)
    finally:
        output.stop()

    assert motor.closed
    assert len(motor.threads) == 1
    assert get_ident() not in motor.threads


def test_repeated_snapshot_does_not_restart_ramp_or_repeat_output() -> None:
    motor = FakeMotor()
    output = RaspberryMotorOutput(settings(), lambda _status: None, lambda _settings: motor)
    output.start()
    try:
        output.set_motor_state(True, 50)
        wait_until(lambda: motor.frequency == 2550)
        calls = list(motor.calls)
        for _ in range(10):
            output.set_motor_state(True, 50)
        time.sleep(0.05)
        assert motor.calls == calls
    finally:
        output.stop()


def test_new_target_interrupts_ramp_without_applying_obsolete_target() -> None:
    motor = FakeMotor()
    output = RaspberryMotorOutput(
        # The Windows clock ticks every 15.6 ms; a short ramp can skip the 0-1000 Hz window.
        settings(ramp_seconds=1.0), lambda _status: None, lambda _settings: motor
    )
    output.start()
    try:
        output.set_motor_state(True, 100)
        wait_until(lambda: 0 < motor.frequency < 1000)
        output.set_motor_state(True, 25)
        wait_until(lambda: motor.frequency == 1325, timeout=3.0)
        assert ("frequency", 5000) not in motor.calls
    finally:
        output.stop()


def test_plc_fault_interrupts_ramp_and_waits_for_fresh_state() -> None:
    motor = FakeMotor()
    output = RaspberryMotorOutput(
        settings(ramp_seconds=0.5), lambda _status: None, lambda _settings: motor
    )
    output.start()
    try:
        output.set_motor_state(True, 100)
        wait_until(lambda: motor.frequency > 0)
        output.disable()
        wait_until(lambda: not motor.enabled, timeout=0.2)
        calls = list(motor.calls)
        time.sleep(0.05)
        assert motor.calls == calls
        assert motor.frequency == 0

        output.set_motor_state(True, 50)
        wait_until(lambda: motor.frequency == 2550)
    finally:
        output.stop()


def test_shutdown_interrupts_ramp_and_rejects_late_commands() -> None:
    motor = FakeMotor()
    output = RaspberryMotorOutput(
        settings(ramp_seconds=5), lambda _status: None, lambda _settings: motor
    )
    output.start()
    output.set_motor_state(True, 100)
    wait_until(lambda: motor.frequency > 0)
    started = time.monotonic()
    output.stop()
    assert time.monotonic() - started < 0.5
    assert motor.closed and not motor.enabled
    calls = list(motor.calls)
    output.set_motor_state(True, 100)
    assert motor.calls == calls


def test_retries_initialization_and_applies_latest_command() -> None:
    motor = FakeMotor()
    attempts = []

    def factory(_settings):
        attempts.append(True)
        if len(attempts) == 1:
            raise ConnectionError("pigpio unavailable")
        return motor

    output = RaspberryMotorOutput(settings(), lambda _status: None, factory)
    output.set_motor_state(True, 73)
    output.start()
    try:
        wait_until(lambda: motor.frequency == 3677)
        assert len(attempts) == 2
    finally:
        output.stop()


@pytest.mark.parametrize("speed", [-1, 101, True, 1.5])
def test_rejects_invalid_speed(speed) -> None:
    output = RaspberryMotorOutput(settings(), lambda _status: None)
    with pytest.raises(ValueError, match="speed"):
        output.set_motor_state(True, speed)


def test_gpio_driver_starts_disabled_and_releases_pins() -> None:
    pytest.importorskip("gpiozero")
    from gpiozero.pins.mock import MockFactory, MockPWMPin

    factory = MockFactory(pin_class=MockPWMPin)
    motor = MotorDC(settings(), pin_factory=factory)
    try:
        assert factory.pin(15).state == 1  # Active-low EN is disabled.
        assert factory.pin(18).state == 0
        assert factory.pin(25).state == 1
        motor.enable()
        motor.set_frequency(2550)
        assert factory.pin(15).state == 0
        assert factory.pin(18).frequency == 2550
        assert factory.pin(18).state == 0.5
        motor.disable()
        assert factory.pin(15).state == 1
        assert factory.pin(18).state == 0
    finally:
        motor.close()

    assert factory.pin(15).function == "input"
    assert factory.pin(18).function == "input"
    assert factory.pin(25).function == "input"
    factory.close()


def test_gpio_cleanup_continues_after_one_device_close_fails(monkeypatch) -> None:
    pytest.importorskip("gpiozero")
    from gpiozero.pins.mock import MockFactory, MockPWMPin

    factory = MockFactory(pin_class=MockPWMPin)
    motor = MotorDC(settings(), pin_factory=factory)
    step = motor._step

    def failed_close():
        raise IOError("STEP close failed")

    monkeypatch.setattr(step, "close", failed_close)
    with pytest.raises(IOError, match="STEP close failed"):
        motor.close()

    assert motor._en.closed
    assert motor._dir.closed
    monkeypatch.undo()
    step.close()
    factory.close()
