from dataclasses import fields, is_dataclass
from typing import Any, Type


def get_field_names(cls: Type[Any]) -> list[str]:
    if not is_dataclass(cls):
        raise TypeError("Expected a dataclass type")
    return [f.name for f in fields(cls)]
