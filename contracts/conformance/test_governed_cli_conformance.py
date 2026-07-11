"""Conformance suite: every golden in contracts/examples/ vs the governed CLI.

Structure asserts only (the contract's own rule: row/aggregate VALUES are
illustrative and would break across dataset scales). We assert:

- exit code: 0 when response.ok is true, 1 when false;
- stdout parses as a single JSON object;
- recursive structure match: same keys, same JSON types per value;
- exact match for contract_version, ok, error.code, user.id/user.role, and every
  permission-object `type` (must be one of the four disclosure types);
- applied_permissions / permissions / denied_metrics assert the FULL typed set
  (behavior, not data); other lists assert element shape against the first
  element (values illustrative, including data-row list lengths).

We do NOT assert row values, aggregate numbers, or free-text messages.
"""

from __future__ import annotations

import re

import pytest

PERMISSION_TYPES = {"row_filter", "column_masked", "column_tokenized", "column_banded"}

# Keys whose value is a list of typed permission objects — assert the full set
# (type fields) exactly, in order, because these are behavior not data.
PERMISSION_LIST_KEYS = {"applied_permissions", "permissions"}

# Paths asserted by exact value (not just type). Everything else is structure /
# type only — row values, aggregate numbers, column/metric `type` enums, and
# free-text messages are illustrative per the contract. Permission-object `type`
# fields are handled in _assert_permission_list, not here.
EXACT_VALUE_PATHS = {
    "$.contract_version",
    "$.ok",
    "$.error.code",
    "$.user.id",
    "$.user.role",
}

_LIST_INDEX = re.compile(r"\[\d+\]")


def _canonical_path(path: str) -> str:
    """Drop list indices so `$.x[0].y` and `$.x[3].y` compare equal."""
    return _LIST_INDEX.sub("", path)


def _json_type(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _assert_permission_list(expected: list, actual, path: str):
    assert isinstance(actual, list), f"{path}: expected list, got {_json_type(actual)}"
    assert len(actual) == len(expected), (
        f"{path}: expected {len(expected)} permission objects, got {len(actual)}"
    )
    for i, (exp, act) in enumerate(zip(expected, actual)):
        p = f"{path}[{i}]"
        assert isinstance(act, dict), f"{p}: expected object, got {_json_type(act)}"
        assert act.get("type") == exp.get("type"), (
            f"{p}: type {act.get('type')!r} != golden {exp.get('type')!r}"
        )
        assert act.get("type") in PERMISSION_TYPES, (
            f"{p}: type {act.get('type')!r} not in {PERMISSION_TYPES}"
        )
        # Same keys and types within each permission object.
        _assert_structure(exp, act, p)


def _assert_structure(expected, actual, path: str = "$"):
    """Recursively assert `actual` matches `expected`'s structure.

    - dicts: identical key sets; recurse per key.
    - lists: data grids (`rows`) match arity with illustrative cell values;
      equal-length object lists (`records`) match positionally so variant shapes
      are each checked; other lists template every element off the golden's
      first; permission lists assert the full typed set.
    - scalars: types match (null is nullable, int/float interchange); the
      EXACT_VALUE_PATHS also match by value — handled at the dict level.
    """
    et = _json_type(expected)
    at = _json_type(actual)

    if et == "dict":
        assert at == "dict", f"{path}: expected dict, got {at}"
        assert set(actual.keys()) == set(expected.keys()), (
            f"{path}: key mismatch. golden={sorted(expected)} actual={sorted(actual)}"
        )
        for key, exp_val in expected.items():
            p = f"{path}.{key}"
            act_val = actual[key]
            if key in PERMISSION_LIST_KEYS and isinstance(exp_val, list):
                _assert_permission_list(exp_val, act_val, p)
                continue
            if _canonical_path(p) in EXACT_VALUE_PATHS:
                assert act_val == exp_val, (
                    f"{p}: {act_val!r} != golden {exp_val!r} (exact-match path)"
                )
                continue
            _assert_structure(exp_val, act_val, p)
        return

    if et == "list":
        assert at == "list", f"{path}: expected list, got {at}"
        if not expected:
            return
        # A data grid (list whose elements are themselves lists, e.g. `rows`)
        # is matched positionally per row: same arity, cells compared position by
        # position. Cell VALUES and per-cell types are illustrative (§2 nullable,
        # tokenized/banded columns can shift a cell's type), so cell mismatches
        # fall through to the nullable/number-tolerant scalar rules below.
        if _json_type(expected[0]) == "list":
            for i, row in enumerate(actual):
                assert _json_type(row) == "list", f"{path}[{i}]: expected list row"
                assert len(row) == len(expected[0]), (
                    f"{path}[{i}]: row arity {len(row)} != golden {len(expected[0])}"
                )
                for j, cell in enumerate(row):
                    # Cell values (and thus their scalar types) are illustrative;
                    # only assert a cell is a scalar, not a nested container.
                    assert _json_type(cell) not in ("list", "dict"), (
                        f"{path}[{i}][{j}]: data cell must be a scalar, got {_json_type(cell)}"
                    )
            return
        # A list of objects whose members legitimately vary in shape — KG
        # `records` (nodes of different labels; `_access.reason` present only when
        # not readable). When the golden enumerates exactly as many elements as
        # the response, match positionally so each variant is checked against its
        # own golden. Otherwise (illustrative-length lists) template every element
        # off the golden's first.
        if _json_type(expected[0]) == "dict" and len(actual) == len(expected):
            for i, (exp_item, act_item) in enumerate(zip(expected, actual)):
                _assert_structure(exp_item, act_item, f"{path}[{i}]")
            return
        shape = expected[0]
        for i, item in enumerate(actual):
            _assert_structure(shape, item, f"{path}[{i}]")
        return

    # Scalar. Nullable fields are legitimate (§2: NULL is a real serialization,
    # e.g. a `unit` that is null for categorical columns but a string for money).
    # The goldens give only one list element as the shape template, so a null in
    # the template means "nullable" and a null actual is accepted against any
    # scalar template. Numbers accept int/float interchangeably.
    if et == "null" or at == "null":
        return
    if et in ("int", "float"):
        assert at in ("int", "float"), f"{path}: expected number, got {at}"
        return
    assert at == et, f"{path}: expected {et}, got {at}"


def test_golden_conformance(golden):
    from conftest import invoke_cli

    result = invoke_cli(golden.argv)

    assert result.envelope is not None, (
        f"stdout is not a single JSON object.\nstdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )

    expected = golden.response
    expected_ok = expected["ok"]

    # Exit code follows ok: 0 success, 1 handled error.
    expected_exit = 0 if expected_ok else 1
    assert result.exit_code == expected_exit, (
        f"exit code {result.exit_code} != {expected_exit} for ok={expected_ok}.\n"
        f"stderr={result.stderr!r}"
    )

    _assert_structure(expected, result.envelope)
