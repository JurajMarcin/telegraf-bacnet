"""Module for parsing TOML configuration to a configclass"""
from dataclasses import dataclass, fields
import os
from types import UnionType
from typing import Any, Callable, Type, TypeVar

import tomli

IS_DUNDER = "__is_configclass__"
VALIDATE_DUNDER = "__configclass__validate__"
SET_ATTRS_DUNDER = "__configclass__set_attrs__"


TomlDict = dict[str, Any]
T = TypeVar("T", bound=object)


class ConfigError(Exception):
    """
    Raised when the config file could not be parsed or serialized correctly
    """


def _update(self: object, toml_dict: TomlDict) -> None:
    config_fields = { field.name: field for field in fields(self) }
    for key, value in toml_dict.items():
        if key not in config_fields:
            raise KeyError(f"Unknown key {key}")
        value_t = config_fields[key].type
        # handle case "T | None"
        if isinstance(value_t, UnionType):
            value_t = value_t.__args__[0]
        try:
            if getattr(value_t, "__origin__", None) == list:
                item_t = getattr(value_t, "__args__")[0]
                current_list = getattr(self, key, [])
                current_list.extend(map(item_t, value))
                setattr(self, key, current_list)
            elif getattr(value_t, "__origin__", None) == tuple:
                item_t = getattr(value_t, "__args__")[0]
                setattr(self, key, tuple(map(item_t, value)))
            elif getattr(value_t, "__origin__", None) == set:
                item_t = getattr(value_t, "__args__")[0]
                setattr(self, key, set(map(item_t, value)))
            elif getattr(value_t, "__origin__", None) == dict:
                dk_t, dv_t = getattr(value_t, "__args__")
                current_dict = getattr(self, key, {})
                current_dict.update({
                    dk_t(k): dv_t(v) for k, v in value.items()
                })
                setattr(self, key, current_dict)
            else:
                setattr(self, key, value_t(value))
            getattr(self, SET_ATTRS_DUNDER).add(key)
        except ConfigError as ex:
            raise ConfigError(f"{key}.{ex}") from ex
        except (KeyError, ValueError) as ex:
            raise ConfigError(f"{key}: {ex}") from ex


def parse(cls: Type[T], conf_path: str, conf_d_path: str | None = None) -> T:
    """
    Parses config file into configclass of type cls
    """
    if not getattr(cls, IS_DUNDER, False):
        raise TypeError("parse() requires configclass type")
    self = cls()
    file_path = conf_path
    try:
        with open(conf_path, "rb") as file:
            _update(self, tomli.load(file))
        if conf_d_path:
            for file_path in os.listdir(conf_d_path):
                with open(os.path.join(conf_d_path, file_path), "rb") as file:
                    _update(self, tomli.load(file))
        validator = getattr(self, VALIDATE_DUNDER, None)
        if validator is not None:
            validator(self)
    except FileNotFoundError:
        pass
    except ConfigError as ex:
        raise ConfigError(f"In file {file_path}: {ex}") from ex
    except tomli.TOMLDecodeError as ex:
        raise ConfigError(f"Error parsing the file {file_path}: {ex}") from ex
    return self


def configclass(cls: T = None, /, *,
                validator: Callable[[T], None] | None = None) -> T:
    """
    Decorator to make the class parsable configclass, similar to dataclass

    cls:        class to decorate

    validator:  optional validation function to which class instance is passed
                after parsing, on error it should raise an ConfigError
                exception
    """
    def _configclass(cls: T) -> T:
        cls = dataclass(cls)  # type: ignore

        old_init = getattr(cls, "__init__")
        def _config_init(self: T, toml_dict: TomlDict | None = None,
                         *args: Any, **kwargs: Any) -> None:
            setattr(self, SET_ATTRS_DUNDER, set())
            old_init(self, *args, **kwargs)
            if toml_dict is not None:
                _update(self, toml_dict)
        setattr(cls, "__init__", _config_init)
        setattr(cls, IS_DUNDER, True)
        setattr(cls, VALIDATE_DUNDER, validator)

        return cls

    return _configclass if cls is None else _configclass(cls)  # type: ignore


def configclass_set_attrs(cfg: object) -> frozenset[str]:
    """Returns a frozenset of attributes explicitely set by parse()"""
    if not getattr(cfg.__class__, IS_DUNDER, False):
        raise TypeError("configclass_has_set() requires configclass instance")
    return frozenset(getattr(cfg, SET_ATTRS_DUNDER, set()))


__all__ = [
    "configclass",
    "parse",
    "configclass_set_attrs",
    "ConfigError",
]
