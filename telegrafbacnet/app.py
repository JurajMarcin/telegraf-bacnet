import logging
from os import getpid
from typing import Any

from bacpypes.apdu import (
    ConfirmedCOVNotificationRequest,
    IAmRequest,
    ReadPropertyACK,
    ReadPropertyMultipleACK,
    ReadPropertyRequest,
)
from bacpypes.app import BIPSimpleApplication
from bacpypes.constructeddata import Array, ArrayOf
from bacpypes.core import deferred
from bacpypes.iocb import IOCB
from bacpypes.local.device import LocalDeviceObject
from bacpypes.object import get_datatype, get_object_class
from bacpypes.pdu import Address
from bacpypes.primitivedata import ObjectIdentifier, Unsigned

from .config import Config, DeviceConfig, DiscoveryGroupConfig, ObjectConfig
from .influx import InfluxLPR
from .tasks import (
    DeviceReadTask,
    DiscoveryTask,
    ObjectReadTask,
    SubscribeCOVTask,
)


_logger = logging.getLogger(__name__)


class TelegrafApplication(BIPSimpleApplication):
    def __init__(self, config: Config):
        local_device = LocalDeviceObject(
            objectName=config.object_name,
            objectIdentifier=config.object_identifier,
            maxApduLengthAccepted=config.max_apdu_length_accepted,
            segmentationSupported=config.segmentation_supported,
            vendorIdentifier=config.vendor_identifier,
        )
        super().__init__(local_device, config.address)
        self.config = config
        self.devices: dict[Address, DeviceConfig] = dict()
        self.influx_lpr = InfluxLPR()
        if self.config.discovery.enabled:
            DiscoveryTask(self, self.config.discovery).install_task()

    def _print_measurement(self, address: Address,
                           object_identifier: tuple[str, int],
                           property: str, value: Any,
                           index: int | None = None) -> None:
        if address not in self.devices:
            _logger.warn("Skipping measurement from unknown device %r",
                         address)
            return
        device = self.devices[address]
        if device.device_name is None and device.device_identifier is None:
            _logger.error("%r has neither identifier or name, skipping",
                          device)
            return
        tags: list[tuple[str, str | int | float]] = [
            ("deviceAddress", str(address)),
            ("objectType", object_identifier[0]),
            ("objectInstanceNumber", object_identifier[1]),
        ]
        if device.device_identifier is not None:
            tags.append(("deviceIdentifier", device.device_identifier))
        if device.device_name is not None:
            tags.append(("deviceName", device.device_name))
        if index is not None:
            tags.append(("propertyArrayIndex", index))
        self.influx_lpr.print(property, value, *tags)

    # Measurements reading

    def _process_read_property_ack(self, apdu: ReadPropertyACK) -> None:
        datatype = get_datatype(apdu.objectIdentifier[0],
                                apdu.propertyIdentifier)
        if not datatype:
            _logger.error("unknown datatype in a response from %r",
                          apdu.pduSource)
            return

        if issubclass(datatype, Array) and apdu.propertyArrayIndex is not None:
            if apdu.propertyArrayIndex == 0:
                value = apdu.propertyValue.cast_out(Unsigned)
            else:
                value = apdu.propertyValue.cast_out(datatype.subtype)
        else:
            value = apdu.propertyValue.cast_out(datatype)

        self._print_measurement(apdu.pduSource, apdu.objectIdentifier,
                                apdu.propertyIdentifier, value)

    def _process_read_property_multiple_ack(self,
                                            apdu: ReadPropertyMultipleACK) \
            -> None:
        for result in apdu.listOfReadAccessResults:
            for element in result.listOfResults:
                if element.readResult.propertyAccessError is not None:
                    _logger.error("Error while ReadingPropertyMultiple %r",
                                  element.readResult.propertyAccessError)
                    continue

                datatype = get_datatype(result.objectIdentifier[0],
                                        element.propertyIdentifier)
                if not datatype:
                    _logger.error("unknown datatype in a response from %r",
                                  apdu.pduSource)
                    continue

                if issubclass(datatype, Array) \
                        and element.propertyArrayIndex is not None:
                    if element.propertyArrayIndex == 0:
                        value = element.readResult.propertyValue.cast_out(
                            Unsigned)
                    else:
                        value = element.readResult.propertyValue.cast_out(
                            datatype.subtype,
                        )
                else:
                    value = element.readResult.propertyValue.cast_out(datatype)

                self._print_measurement(apdu.pduSource, apdu.objectIdentifier,
                                        apdu.propertyIdentifier, value,
                                        element.propertyArrayIndex)

    def _process_response_iocb(self, iocb: IOCB, **kwargs: Any) -> None:
        if iocb.ioError:
            _logger.error("Response IOCB error: %r", iocb.ioError)
            return
        if not iocb.ioResponse:
            _logger.error("No error nor response in IOCB response")
            return

        apdu = iocb.ioResponse
        _logger.debug("Received %r from %r", type(apdu), apdu.pduSource)
        if isinstance(apdu, ReadPropertyACK):
            self._process_read_property_ack(apdu)
        elif isinstance(apdu, ReadPropertyMultipleACK):
            self._process_read_property_multiple_ack(apdu)
        else:
            _logger.debug("Unhandled response type %r", type(apdu))

    def do_UnconfirmedCOVNotificationRequest(
            self, apdu: ConfirmedCOVNotificationRequest,
    ) -> None:
        if apdu.subscriberProcessIdentifier != getpid():
            _logger.debug("Ignoring COV notification not intended to me")
            return
        _logger.debug("Received COV notification from %r", apdu.pduSource)

        for element in apdu.listOfValues:
            element_value = element.value.tagList
            if len(element_value) == 1:
                element_value = element_value[0].app_to_object().value
            self._print_measurement(apdu.pduSource,
                                    apdu.monitoredObjectIdentifier,
                                    element.propertyIdentifier, element_value)

    # Device discovery

    def _process_read_object_list_response(
        self, iocb: IOCB, device: DeviceConfig,
        discovery_group: DiscoveryGroupConfig,
    ) -> None:
        if iocb.ioError:
            _logger.error("Error reading object list of %r: %r", device,
                          iocb.ioError)
            return
        if not iocb.ioResponse:
            _logger.error("No error nor response in IOCB response")
            return

        apdu = iocb.ioResponse
        _logger.debug("Received %r from %r", type(apdu), apdu.pduSource)
        if not isinstance(apdu, ReadPropertyACK):
            _logger.error("APDU has invalid type %r", apdu)
            return
        if apdu.pduSource in self.devices:
            _logger.debug("Device @%r is already known, skipping",
                          apdu.pduSource)
            return
        object_list = apdu.propertyValue.cast_out(ArrayOf(ObjectIdentifier))
        objects: list[ObjectConfig] = []
        for object_identifier in object_list:
            if object_identifier[0] == "device":
                continue
            if discovery_group.object_types is not None \
                    and object_identifier[0] not in \
                    discovery_group.object_types:
                continue
            object = ObjectConfig()
            object.object_identifier = ObjectIdentifier(object_identifier)
            object.interval = discovery_group.read_interval
            object.cov = discovery_group.cov
            object.cov_lifetime = discovery_group.cov_lifetime
            object.properties = tuple(
                prop.identifier for prop
                in get_object_class(object_identifier[0]).properties
                if discovery_group.properties is None \
                    or str(prop.identifier) in discovery_group.properties
            )
            objects.append(object)
        device.objects = tuple(objects)
        self.register_devices(device)

    def _process_read_device_name_response(self, iocb: IOCB,
                                           device: DeviceConfig) -> None:
        if iocb.ioError:
            _logger.error("Error reading name of %r: %r", device,
                          iocb.ioError)
            return
        if not iocb.ioResponse:
            _logger.error("No error nor response in IOCB response")
            return

        apdu: ReadPropertyACK = iocb.ioResponse
        datatype = get_datatype(apdu.objectIdentifier[0],
                                apdu.propertyIdentifier)
        if not datatype:
            _logger.error("unknown datatype in a response from %r",
                          apdu.pduSource)
            return

        device.device_name = apdu.propertyValue.cast_out(datatype)
        discovery_group = self.config.discovery.get_discovery_group(device)
        if discovery_group is None:
            _logger.debug("No discovery group for %r", device)
            return

        read_object_list_request = ReadPropertyRequest(
            destination=apdu.pduSource,
            objectIdentifier=ObjectIdentifier("device",
                                              device.device_identifier),
            propertyIdentifier="objectList",
        )
        iocb = IOCB(read_object_list_request)
        iocb.add_callback(self._process_read_object_list_response, device,
                          discovery_group)
        deferred(self.request_io, iocb, "_process_read_device_name_response")

    def do_IAmRequest(self, apdu: IAmRequest) -> None:
        if apdu.pduSource in self.devices:
            _logger.debug("Device @%r is already known, skipping",
                          apdu.pduSource)
            return
        device = DeviceConfig()
        device.address = apdu.pduSource
        device.device_identifier = apdu.iAmDeviceIdentifier[1]
        device.read_multiple = False
        read_object_list_request = ReadPropertyRequest(
            destination=apdu.pduSource,
            objectIdentifier=apdu.iAmDeviceIdentifier,
            propertyIdentifier="objectName",
        )
        iocb = IOCB(read_object_list_request)
        iocb.add_callback(self._process_read_device_name_response, device)
        deferred(self.request_io, iocb, "do_IAmRequest")

    def request_io(self, iocb: IOCB, source: str = "(unknown)"):
        _logger.debug(f"Sending IOCB %r for %r", iocb.args, source)
        return super().request_io(iocb)

    def register_devices(self, *devices: DeviceConfig) -> None:
        for device in devices:
            if device.read_multiple \
                    and any(not object.cov for object in device.objects):
                DeviceReadTask(self, device, self.config,
                               self._process_response_iocb).install_task()
            for object in device.objects:
                if object.cov:
                    SubscribeCOVTask(self, object,
                                     device, self.config).install_task()
                elif not device.read_multiple:
                    ObjectReadTask(self, object, device, self.config,
                                   self._process_response_iocb).install_task()
            self.devices[device.address] = device
