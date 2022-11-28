from typing import Any, Callable, Protocol

from bacpypes.iocb import IOCB

from .config import DeviceConfig


TomlDict = dict[str, Any]
ResponseProcessor = Callable[[IOCB], None]


class DeviceRegisterCallback(Protocol):
    def __call__(self, *devices: DeviceConfig) -> None:
        pass
