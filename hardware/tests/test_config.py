from gateway.config import load_settings


def test_example_config_is_safe_and_portable() -> None:
    settings = load_settings("config.example.toml")

    assert settings.modbus.enabled is False
    assert settings.modbus.baudrate == 115200
    assert settings.modbus.bytesize == 8
    assert settings.modbus.parity == "N"
    assert settings.modbus.stopbits == 1
    assert settings.modbus.poll_interval_seconds == 0.25
    assert settings.ntp.enabled is True
    assert settings.ntp.server == "127.0.0.1"
    assert settings.ntp.port == 123
    assert settings.motor_output.enabled is False
    assert settings.motor_output.step_pin == 18
    assert settings.motor_output.dir_pin == 25
    assert settings.motor_output.en_pin == 15
    assert settings.motor_output.minimum_frequency == 100
    assert settings.motor_output.maximum_frequency == 5000
    assert settings.motor_output.ramp_seconds == 0.5
    assert settings.application.database_path.is_absolute()
