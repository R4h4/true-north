"""Envelope assembly and scalar serialization (CONTRACT §2).

One place builds the JSON envelope every `tn` command returns, and one place
enforces the scalar rules: money is integer VND with a 2^53 guard, ratios are
0–1 numbers, dates are ISO strings, NULL/NaN -> null (+ warning).
"""

from __future__ import annotations

import datetime as _dt
import math

CONTRACT_VERSION = "0.3"
MAX_SAFE_INT = 2 ** 53 - 1


def ok_envelope(user: dict | None, result, metadata: dict, warnings: list[dict]) -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "ok": True,
        "user": user,
        "result": result,
        "metadata": metadata or {},
        "warnings": warnings or [],
        "error": None,
    }


def error_envelope(user: dict | None, code: str, message: str, details: dict | None) -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "ok": False,
        "user": user,
        "result": None,
        "metadata": {},
        "warnings": [],
        "error": {"code": code, "message": message, "details": details},
    }


class NumberTooLarge(ValueError):
    pass


def coerce_money(value, warnings: list[dict]):
    """Round to integer VND; guard the 2^53 exact-representation limit."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        warnings.append({"code": "NULL_RESULT", "message": "aggregate was NaN/Infinity; returned null"})
        return None
    ivalue = int(round(value))
    if abs(ivalue) > MAX_SAFE_INT:
        raise NumberTooLarge(
            f"aggregate {ivalue} exceeds 2^53-1 and cannot be represented exactly as JSON number"
        )
    return ivalue


def coerce_ratio(value, warnings: list[dict]):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        warnings.append({"code": "NULL_RESULT", "message": "ratio was NaN/Infinity; returned null"})
        return None
    return float(value)


def coerce_count(value, warnings: list[dict]):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        warnings.append({"code": "NULL_RESULT", "message": "value was NaN/Infinity; returned null"})
        return None
    # count-typed metric values may be fractional averages (e.g. basket items avg,
    # inventory days). Keep whole numbers as ints, fractional as numbers.
    if isinstance(value, float) and not value.is_integer():
        return float(value)
    return int(value)


def coerce_scalar(value, warnings: list[dict]):
    """Generic scalar coercion for dimension cells and dates."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            warnings.append({"code": "NULL_RESULT", "message": "value was NaN/Infinity; returned null"})
            return None
        return value
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, _dt.date):
        return value.isoformat()
    return value


def coerce_by_unit(value, unit: str | None, warnings: list[dict]):
    if unit == "VND":
        return coerce_money(value, warnings)
    if unit == "ratio":
        return coerce_ratio(value, warnings)
    if unit == "count":
        return coerce_count(value, warnings)
    return coerce_scalar(value, warnings)
