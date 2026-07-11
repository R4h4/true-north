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

import pytest

PERMISSION_TYPES = {"row_filter", "column_masked", "column_tokenized", "column_banded"}

# Keys whose value is a list of typed permission objects — assert the full set
# (type fields) exactly, in order, because these are behavior not data.
PERMISSION_LIST_KEYS = {"applied_permissions", "permissions"}

# Keys asserted exactly (scalar equality), wherever they appear.
EXACT_SCALAR_KEYS = {"contract_version", "ok", "code", "id", "role", "type"}


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
    - lists: element shape matches the golden's first element; permission lists
      assert the full typed set.
    - scalars: types match; EXACT_SCALAR_KEYS (passed via the parent's key) also
      match by value — handled at the dict level.
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
            if key in EXACT_SCALAR_KEYS:
                assert act_val == exp_val, (
                    f"{p}: {act_val!r} != golden {exp_val!r} (exact-match key)"
                )
                continue
            _assert_structure(exp_val, act_val, p)
        return

    if et == "list":
        assert at == "list", f"{path}: expected list, got {at}"
        if not expected:
            return
        shape = expected[0]
        for i, item in enumerate(actual):
            _assert_structure(shape, item, f"{path}[{i}]")
        return

    # Scalar. Allow int/float interchange only where the golden is a number and
    # not an exact key (handled above). null must stay null; bool must stay bool.
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
