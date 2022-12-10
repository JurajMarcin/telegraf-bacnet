from dataclasses import field
import re

from bacpypes.pdu import Address
from bacpypes.primitivedata import ObjectIdentifier

from tomlconfig import configclass


@configclass
class ObjectConfig:
    object_identifier: ObjectIdentifier = \
        field(default_factory=ObjectIdentifier)
    read_interval: int | None = None
    cov: bool = False
    cov_lifetime: int | None = None
    properties: tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"<Object {self.object_identifier}>"

    def __repr__(self) -> str:
        return str(self)


@configclass
class DeviceConfig:
    address: Address = field(default_factory=Address)
    device_identifier: int | None = None
    device_name: str | None = None
    read_multiple: bool = True
    read_interval: int | None = None
    objects: tuple[ObjectConfig, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"<Device {self.device_identifier}[{self.device_name}]" \
            f"@{self.address}>"

    def __repr__(self) -> str:
        return str(self)


@configclass
class DiscoveryGroupConfig:
    """Class representing device discovery group config"""
    match_name: str | None = None
    device_ids: set[int] | None = None
    read_interval: int | None = None
    cov: bool = False
    cov_lifetime: int | None = None
    object_types: tuple[str, ...] | None = None
    properties: tuple[str, ...] | None = None


@configclass
class DiscoveryConfig:
    """Class representing device discovery config"""
    enabled: bool = False
    target: Address = field(
        default_factory=lambda: Address("*:*"))  # type: ignore
    discovery_interval: int = 60 * 60
    low_limit: int | None = None
    high_limit: int | None = None
    discovery_group: list[DiscoveryGroupConfig] = field(default_factory=list)

    def get_discovery_group(self, device: DeviceConfig) \
            -> DiscoveryGroupConfig | None:
        """
        Returns the discovery group matching the device or None if no group
        matches
        """
        for discovery_group in self.discovery_group:
            if device.device_name is not None \
                    and discovery_group.match_name is not None \
                    and re.search(discovery_group.match_name,
                                  device.device_name):
                return discovery_group
            if device.device_identifier is not None \
                    and discovery_group.device_ids is not None \
                    and device.device_identifier in discovery_group.device_ids:
                return discovery_group
        return None


@configclass
class Config:
    """Class representing main application config"""
    device_name: str = "TelegrafInput"
    device_identifier: int = 11
    network_number: int = 2000
    address: Address = field(default_factory=Address)
    max_apdu_length_accepted: int = 1024
    segmentation_supported: str = "segmentedBoth"
    vendor_identifier: int = 555

    debug: bool = False

    read_interval: int = 5
    cov_lifetime: int = 5 * 60
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    device: list[DeviceConfig] = field(default_factory=list)
