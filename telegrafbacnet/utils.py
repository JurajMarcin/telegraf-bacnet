from typing import TypeVar


T = TypeVar('T')
Tdef = TypeVar('Tdef')
def first(*args: T | None, default: Tdef = None) -> T | Tdef:
    try:
        return next(value for value in args if value is not None)
    except StopIteration:
        return default
