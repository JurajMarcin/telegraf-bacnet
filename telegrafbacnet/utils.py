from typing import TypeVar


T = TypeVar('T')


def first(*args: T | None, default: T | None = None) -> T | None:
    """Returns the first non-None argument or default if all are None"""
    try:
        return next(value for value in args if value is not None)
    except StopIteration:
        return default
