import logging
from os import getpid
from random import randint
from time import time
from typing import Iterable

from bacpypes.apdu import (
    ConfirmedRequestSequence,
    ReadAccessSpecification,
    ReadPropertyMultipleRequest,
    ReadPropertyRequest,
    SubscribeCOVRequest,
)
from bacpypes.basetypes import PropertyReference
from bacpypes.core import deferred
from bacpypes.iocb import IOCB, IOController
from bacpypes.service.device import WhoIsIAmServices
from bacpypes.task import OneShotTask

from .utils import first

from .config import Config, DeviceConfig, DiscoveryConfig, ObjectConfig
from .types import ResponseProcessor


_logger = logging.getLogger(__name__)


class _BaseRecurringTask(OneShotTask):
    def __init__(self, interval: int | None, offset: float | None = None) \
            -> None:
        self.interval = interval
        self.offset = offset
        self.cancelled = False
        super().__init__()
        _logger.debug("Init %r", self)

    def install_task(self, when: float | None = None,
                     delta: float | None = None) -> None:
        if self.cancelled:
            return
        offset = self.offset if self.offset is not None else 0
        super().install_task(when=time() + offset)

    def process_task(self) -> None:
        _logger.debug("Pocess task %r", self)
        if self.interval and not self.cancelled:
            super().install_task(delta=self.interval)

    def cancel_task(self) -> None:
        _logger.debug("Canceled task %r", self)
        self.cancelled = True



class _BaseIOTask(_BaseRecurringTask):
    def __init__(self, io_controller: IOController, interval: int,
                 offset: float | None = None,
                 callback: ResponseProcessor | None = None) -> None:
        if offset is None:
            offset = randint(0, interval * 1000 - 1) / 1000.0
        self.io_controller = io_controller
        self.callback = callback
        super().__init__(interval, offset)

    def _add_callback(self, iocb: IOCB) -> None:
        if self.callback is not None:
            iocb.add_callback(self.callback)

    def process_task(self) -> None:
        super().process_task()
        for request in self._build_requests():
            iocb = IOCB(request)
            self._add_callback(iocb)
            deferred(self.io_controller.request_io, iocb, str(self))

    def _build_requests(self) -> Iterable[ConfirmedRequestSequence]:
        raise NotImplementedError()


class DeviceReadTask(_BaseIOTask):
    def __init__(self, io_controller: IOController, device: DeviceConfig,
                 config: Config, callback: ResponseProcessor) -> None:
        interval = first(device.interval, config.interval)
        assert interval is not None
        self.device = device
        super().__init__(io_controller, interval, callback=callback)

    def _build_requests(self) -> Iterable[ReadPropertyMultipleRequest]:
        yield ReadPropertyMultipleRequest(
            destination=self.device.address,
            listOfReadAccessSpecs=[
                ReadAccessSpecification(
                    objectIdentifier=object.object_identifier,
                    listOfPropertyReferences=[
                        PropertyReference(propertyIdentifier=prop)
                        for prop in object.properties
                    ],
                ) for object in self.device.objects
            ]
        )

    def __str__(self) -> str:
        return f"<DeviceReadTask for {self.device}>"

    def __repr__(self) -> str:
        return str(self)


class ObjectReadTask(_BaseIOTask):
    def __init__(self, io_controller: IOController, object: ObjectConfig,
                 device: DeviceConfig, config: Config,
                 callback: ResponseProcessor) -> None:
        interval = first(object.interval, device.interval, config.interval)
        assert interval is not None
        self.object = object
        self.device = device
        super().__init__(io_controller, interval, callback=callback)

    def _build_requests(self) -> Iterable[ConfirmedRequestSequence]:
        for prop in self.object.properties:
            yield ReadPropertyRequest(
                destination=self.device.address,
                objectIdentifier=self.object.object_identifier,
                propertyIdentifier=prop,
            )

    def __str__(self) -> str:
        return f"<ObjectReadTask for {self.object}@{self.device}>"

    def __repr__(self) -> str:
        return str(self)


class SubscribeCOVTask(_BaseIOTask):
    def __init__(self, io_controller: IOController,
                 object: ObjectConfig, device: DeviceConfig, config: Config) \
            -> None:
        lifetime = first(object.cov_lifetime, config.cov_lifetime)
        assert lifetime is not None
        self.object = object
        self.device = device
        self.config = config
        self.lifetime = lifetime
        self.error_count = 0
        super().__init__(io_controller, lifetime, 0)

    def _build_requests(self) -> Iterable[ConfirmedRequestSequence]:
        yield SubscribeCOVRequest(
            destination=self.device.address,
            subscriberProcessIdentifier=getpid(),
            monitoredObjectIdentifier=self.object.object_identifier,
            issueConfirmedNotifications=False,
            lifetime=self.lifetime
        )

    def process_subscribe_ack(self, iocb: IOCB, device: DeviceConfig,
                              object: ObjectConfig) -> None:
        if iocb.ioError:
            _logger.error("Failed to subscribe to %r@%r: %r", object, device,
                          iocb.ioError)
            self.error_count += 1
        else:
            _logger.debug("Subsribed to %r@%r", object, device)
            self.error_count = 0

    def _add_callback(self, iocb: IOCB) -> None:
        iocb.add_callback(self.process_subscribe_ack, self.device, self.object)

    def __str__(self) -> str:
        return f"<SubscribeCOVTask for {self.object}@{self.device}>"

    def __repr__(self) -> str:
        return str(self)


class DiscoveryTask(_BaseRecurringTask):
    def __init__(self, who_is_service: WhoIsIAmServices,
                 config: DiscoveryConfig) -> None:
        self.who_is_service = who_is_service
        self.config = config
        super().__init__(self.config.discovery_interval)

    def process_task(self) -> None:
        super().process_task()
        self.who_is_service.who_is(self.config.low_limit,
                                   self.config.high_limit, self.config.target)
        _logger.debug("Sending WhoIsRequest lo=%r hi=%r addr=%r",
                      self.config.low_limit, self.config.high_limit,
                      self.config.target)
