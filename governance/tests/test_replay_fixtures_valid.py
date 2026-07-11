"""Validity test for the authored replay fixtures.

Every file in governance/fixtures/replay/ must parse, carry request.argv and a
response with contract_version == "0.3", and use only the four allowed
permission-object types wherever a typed permission list appears.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPLAY_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "replay"
PERMISSION_TYPES = {"row_filter", "column_masked", "column_tokenized", "column_banded"}
PERMISSION_LIST_KEYS = {"applied_permissions", "permissions"}


def replay_files():
    return sorted(REPLAY_DIR.glob("*.json"))


def _collect_permission_lists(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in PERMISSION_LIST_KEYS and isinstance(v, list):
                acc.append(v)
            _collect_permission_lists(v, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_permission_lists(item, acc)


@pytest.mark.parametrize("path", replay_files(), ids=lambda p: p.stem)
def test_replay_fixture_valid(path):
    data = json.loads(path.read_text())
    assert "request" in data and "response" in data, f"{path.name}: missing request/response"
    argv = data["request"]["argv"]
    assert isinstance(argv, list) and argv and argv[0] == "tn", (
        f"{path.name}: request.argv must be a list starting with 'tn'"
    )
    resp = data["response"]
    assert resp.get("contract_version") == "0.3", (
        f"{path.name}: response.contract_version must be '0.3'"
    )
    assert "ok" in resp, f"{path.name}: response missing 'ok'"

    perm_lists: list = []
    _collect_permission_lists(resp, perm_lists)
    for plist in perm_lists:
        for obj in plist:
            assert isinstance(obj, dict) and "type" in obj, (
                f"{path.name}: permission entries must be typed objects"
            )
            assert obj["type"] in PERMISSION_TYPES, (
                f"{path.name}: permission type {obj['type']!r} not in {PERMISSION_TYPES}"
            )


def test_replay_dir_nonempty():
    assert replay_files(), "no replay fixtures authored yet"
