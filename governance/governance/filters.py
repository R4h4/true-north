"""--filter grammar parsing and canonical-value resolution.

Grammar (CONTRACT §3, v1): `<dim> = '<value>'` and `<dim> IN ('<v1>', ...)` on
categorical dimensions only; multiple filters AND together. Values are validated
against the dimension's canonical vocabulary; an unknown value raises with a
`did_you_mean` suggestion (business-synonym map first, then difflib fallback).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# Business synonyms the demo must map (CONTRACT/TRAPS trap 7). Keyed by dimension
# key -> {spoken form: canonical value}. "offline" -> in_store is asserted by the
# INVALID_DIMENSION_VALUE golden (did_you_mean == "in_store").
BUSINESS_SYNONYMS: dict[str, dict[str, str]] = {
    "channel": {
        "offline": "in_store",
        "in store": "in_store",
        "instore": "in_store",
        "retail": "in_store",
        "online": "web",       # ambiguous (web+app); single-value did_you_mean picks web
        "store": "in_store",
        "shop": "in_store",
        "wholesale": "b2b",
        "business": "b2b",
    },
    "province": {
        "hcmc": "Ho Chi Minh City",
        "hcm": "Ho Chi Minh City",
        "saigon": "Ho Chi Minh City",
        "tp hcm": "Ho Chi Minh City",
        "ho chi minh": "Ho Chi Minh City",
        "hanoi": "Ha Noi",
        "hn": "Ha Noi",
        "danang": "Da Nang",
    },
}


class FilterError(ValueError):
    """A filter clause failed to parse or a value is not canonical."""

    def __init__(self, code: str, message: str, details: dict):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class FilterClause:
    dimension: str
    values: tuple[str, ...]   # one for `=`, many for IN
    operator: str             # "=" | "IN"


_EQ_RE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*=\s*'([^']*)'\s*$")
_IN_RE = re.compile(r"^\s*([A-Za-z_][\w]*)\s+IN\s*\((.*)\)\s*$", re.IGNORECASE)
_VAL_RE = re.compile(r"'([^']*)'")


def parse_filter(raw: str) -> tuple[str, str, tuple[str, ...]]:
    """Parse one `--filter` string into (dimension, operator, values)."""
    m = _EQ_RE.match(raw)
    if m:
        return (m.group(1), "=", (m.group(2),))
    m = _IN_RE.match(raw)
    if m:
        values = tuple(_VAL_RE.findall(m.group(2)))
        if not values:
            raise FilterError(
                "INVALID_QUERY",
                f"could not parse filter values in {raw!r}",
                {"filter": raw},
            )
        return (m.group(1), "IN", values)
    raise FilterError(
        "INVALID_QUERY",
        f"filter {raw!r} is not `<dim> = '<value>'` or `<dim> IN ('a','b')`",
        {"filter": raw},
    )


def suggest_canonical(dimension_key: str, value: str, canonical: list[str]) -> str | None:
    """Best canonical suggestion for a non-canonical value, or None."""
    syn = BUSINESS_SYNONYMS.get(dimension_key, {})
    hit = syn.get(value.strip().lower())
    if hit is not None and hit in canonical:
        return hit
    # difflib fallback, case-insensitive
    lower_map = {c.lower(): c for c in canonical}
    close = difflib.get_close_matches(value.lower(), list(lower_map), n=1, cutoff=0.6)
    if close:
        return lower_map[close[0]]
    return None


def validate_value(dimension_key: str, value: str, canonical: list[str]) -> None:
    """Raise INVALID_DIMENSION_VALUE (with did_you_mean) if value is not canonical."""
    if value in canonical:
        return
    suggestion = suggest_canonical(dimension_key, value, canonical)
    details = {"canonical_values": sorted(canonical)}
    if suggestion is not None:
        details["did_you_mean"] = suggestion
    raise FilterError(
        "INVALID_DIMENSION_VALUE",
        f"'{value}' is not a canonical value of dimension '{dimension_key}'",
        details,
    )
