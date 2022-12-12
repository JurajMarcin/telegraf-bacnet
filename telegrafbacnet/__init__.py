from argparse import ArgumentParser
import logging
from os.path import isdir
from sys import stderr

from bacpypes.core import run

from tomlconfig import ConfigError, parse

from .app import TelegrafApplication
from .config import Config


_logger = logging.getLogger(__name__)


def main() -> None:
    parser = ArgumentParser("Telegraf plugin for BACnet")
    parser.add_argument("--debug", help="Show debug output on stderr",
                        action="store_true", default=False)
    parser.add_argument("--config",
                        help="Load config from the file CONFIG or load config "
                        "from files in the directory CONFIG in alphabetical "
                        "order")
    args = parser.parse_args()

    if args.config is None:
        config = parse(Config, conf_d_path=args.config)
    else:
        try:
            config = parse(Config, conf_d_path=args.config) \
                if isdir(args.config) else parse(Config, conf_path=args.config)
        except FileNotFoundError as ex:
            raise ConfigError("No configuration!") from ex
    if args.debug:
        config.debug = True

    log_handler = logging.StreamHandler(stderr)
    log_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
    )
    _logger.addHandler(log_handler)
    _logger.setLevel(logging.DEBUG if config.debug else logging.INFO)

    app = TelegrafApplication(config)
    app.register_devices(*config.device)

    run()
