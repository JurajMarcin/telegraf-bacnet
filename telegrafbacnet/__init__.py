from argparse import ArgumentParser
import logging
from sys import stderr

from bacpypes.core import run

from tomlconfig import parse

from .app import TelegrafApplication
from .config import Config, DevicesConfig


def main():
    parser = ArgumentParser("Telegraf plugin for BACnet")
    parser.add_argument("--debug", help="Show debug output on stderr",
                        action="store_true", default=False)
    parser.add_argument("--config", help="Load config from file",
                        default="config.toml")
    parser.add_argument("--devices", help="Load devices from file",
                        default="devices.toml")
    parser.add_argument("--devices-d", help="Load devices from directory",
                        default="devices.d")
    args = parser.parse_args()

    config = parse(Config, args.config)
    if args.debug:
        config.debug = True
    devices = parse(DevicesConfig, args.devices, args.devices_d)

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        stream=stderr
    )

    app = TelegrafApplication(config)
    app.register_devices(*devices.device)

    run()


if __name__ == "__main__":
    main()
