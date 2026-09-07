"""Typed JSON response decoding shared by API clients and webhooks."""

from __future__ import annotations

import math
import re
import sys
import types
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

_NONE_TYPE = type(None)
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1


def _type_hints(target: type[Any]) -> dict[str, Any]:
    """Resolve annotations without letting dataclass fields shadow built-ins."""

    return get_type_hints(
        target,
        globalns=vars(sys.modules[target.__module__]),
        localns={},
        include_extras=True,
    )


def _decode_integral(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"Expected {name} to be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError(f"Expected {name} to be an integer")
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"Expected {name} to be an integer")
        return int(value)
    raise TypeError(f"Expected {name} to be an integer")


def _decode_java_long(value: Any) -> int:
    if isinstance(value, str):
        if not re.fullmatch(r"-?(?:0|[1-9]\d*)", value):
            raise ValueError("Expected Java Long to be a decimal integer string")
        result = int(value, 10)
    else:
        result = _decode_integral(value, "Java Long")
    if result < _INT64_MIN or result > _INT64_MAX:
        raise ValueError("Java Long is outside the signed 64-bit range")
    return result


def _decode_epoch_datetime(value: int | float | Decimal) -> datetime:
    if isinstance(value, bool):
        raise TypeError("Expected a datetime string or epoch timestamp")
    try:
        timestamp = Decimal(str(value))
    except ArithmeticError as exc:
        raise ValueError("Expected a finite epoch timestamp") from exc
    if not timestamp.is_finite():
        raise ValueError("Expected a finite epoch timestamp")
    if abs(timestamp) >= Decimal("1e14"):
        divisor = Decimal(1_000_000)
    elif abs(timestamp) >= Decimal("1e11"):
        divisor = Decimal(1_000)
    else:
        divisor = Decimal(1)
    try:
        return datetime.fromtimestamp(float(timestamp / divisor), tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("Epoch timestamp is outside datetime range") from exc


def _decode_date(value: Any) -> date:
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            raise ValueError("Expected a date array with year, month, and day")
        try:
            year = _decode_integral(value[0], "date year")
            month = _decode_integral(value[1], "date month")
            day = _decode_integral(value[2], "date day")
            return date(year, month, day)
        except (TypeError, ValueError) as exc:
            raise ValueError("Expected a valid date array with year, month, and day") from exc
    if not isinstance(value, str):
        raise TypeError("Expected an ISO-8601 date string or date array")
    return date.fromisoformat(value)


def decode_value(value: Any, target: Any) -> Any:
    """Decode JSON-compatible data into a typed SDK model."""

    if value is None:
        return None
    if target in (Any, object, None):
        return value
    origin = get_origin(target)
    args = get_args(target)
    if origin is Annotated:
        base_type = args[0] if args else Any
        if any(metadata == "java-long" for metadata in args[1:]):
            return _decode_java_long(value)
        return decode_value(value, base_type)
    if origin in (Union, types.UnionType):
        for option in args:
            if option is _NONE_TYPE:
                continue
            try:
                return decode_value(value, option)
            except (TypeError, ValueError):
                continue
        raise ValueError(f"Value does not match {target!r}")
    if origin is list:
        if not isinstance(value, list):
            raise ValueError("Expected a JSON array")
        item_type = args[0] if args else Any
        return [decode_value(item, item_type) for item in value]
    if origin is dict:
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        key_type, item_type = args if len(args) == 2 else (str, Any)
        return {
            decode_value(key, key_type): decode_value(item, item_type)
            for key, item in value.items()
        }
    if target is Decimal:
        if isinstance(value, bool):
            raise TypeError("Expected a decimal value")
        try:
            result = Decimal(str(value))
        except ArithmeticError as exc:
            raise ValueError("Expected a decimal value") from exc
        if not result.is_finite():
            raise ValueError("Decimal values must be finite")
        return result
    if target is datetime:
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return _decode_epoch_datetime(value)
        if not isinstance(value, str):
            raise TypeError("Expected an ISO-8601 datetime string or epoch timestamp")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if target is date:
        return _decode_date(value)
    if isinstance(target, type) and issubclass(target, Enum):
        return target(value)
    if isinstance(target, type) and is_dataclass(target):
        if not isinstance(value, dict):
            raise ValueError(f"Expected an object for {target.__name__}")
        hints = _type_hints(target)
        values = {}
        for field in fields(target):
            wire_name = field.name[:1] + re.sub(
                r"_([a-z])", lambda match: match.group(1).upper(), field.name[1:]
            )
            if wire_name in value:
                values[field.name] = decode_value(value[wire_name], hints.get(field.name, Any))
        return target(**values)
    if target is int:
        return _decode_integral(value, "integer")
    if target is float:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise TypeError("Expected a number")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Expected a finite number")
        return result
    if target is str:
        if not isinstance(value, str):
            raise TypeError("Expected a string")
        return value
    if target is bool:
        if not isinstance(value, bool):
            raise TypeError("Expected a JSON boolean")
        return value
    return value
