from __future__ import annotations

import argparse
from pathlib import Path

from gateway.application import (
    GatewayApplication,
    configure_logging,
    install_signal_handlers,
)
from gateway.config import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="LS XGK industrial gateway")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--stop-file")
    args = parser.parse_args()
    settings = load_settings(args.config)
    configure_logging(settings.application.log_path)
    stop_file = Path(args.stop_file).resolve() if args.stop_file else None
    application = GatewayApplication(settings, stop_file=stop_file)
    install_signal_handlers(application)
    return application.run()


if __name__ == "__main__":
    raise SystemExit(main())
