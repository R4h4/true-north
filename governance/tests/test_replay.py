"""Unit tests for the stub replay engine (TDD core).

Covers: request normalization (flag order / spacing invariant), fixture lookup
precedence (goldens before replay dir), unmatched -> INTERNAL, and the shape of
the replay index. CLI-level exit-code / stdout tests live in test_cli.py.
"""

from __future__ import annotations

import pytest

from governance import replay


def test_normalize_key_ignores_flag_order():
    a = replay.normalize_request(
        ["query", "--token", "tok-exec-mai", "--metric", "net_revenue", "--group-by", "channel"]
    )
    b = replay.normalize_request(
        ["query", "--group-by", "channel", "--metric", "net_revenue", "--token", "tok-exec-mai"]
    )
    assert a == b


def test_normalize_key_preserves_command_path():
    a = replay.normalize_request(["kg", "query", "--token", "t", "MATCH (n) RETURN n"])
    b = replay.normalize_request(["query", "--token", "t", "MATCH (n) RETURN n"])
    assert a != b


def test_normalize_key_stable_for_positional_args():
    # metrics describe <key> — the positional key participates in the key.
    a = replay.normalize_request(["metrics", "describe", "gross_margin", "--token", "tok-mkt-lan"])
    b = replay.normalize_request(["metrics", "describe", "net_revenue", "--token", "tok-mkt-lan"])
    assert a != b


def test_lookup_precedence_goldens_before_replay(tmp_path, monkeypatch):
    # Build a fake index where the same normalized key exists in both a golden
    # and a replay fixture; the golden must win.
    golden_argv = ["whoami", "--token", "tok-dup"]
    key = replay.normalize_request(golden_argv)

    engine = replay.ReplayEngine(
        goldens={key: {"contract_version": "0.3", "ok": True, "source": "golden"}},
        replays={key: {"contract_version": "0.3", "ok": True, "source": "replay"}},
    )
    env = engine.lookup(golden_argv)
    assert env["source"] == "golden"


def test_unmatched_request_returns_none():
    engine = replay.ReplayEngine(goldens={}, replays={})
    assert engine.lookup(["whoami", "--token", "tok-nope"]) is None


def test_internal_envelope_shape():
    env = replay.internal_error_envelope()
    assert env["ok"] is False
    assert env["contract_version"] == "0.3"
    assert env["error"]["code"] == "INTERNAL"
    assert env["result"] is None


def test_load_fixture_index_from_dir(tmp_path):
    import json

    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "request": {"argv": ["tn", "whoami", "--token", "tok-x"]},
                "response": {"contract_version": "0.3", "ok": True},
            }
        )
    )
    index = replay.load_fixture_dir(tmp_path)
    key = replay.normalize_request(["whoami", "--token", "tok-x"])
    assert key in index
    assert index[key]["ok"] is True


def test_leading_tn_is_stripped_on_load(tmp_path):
    import json

    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "request": {"argv": ["tn", "metrics", "list", "--token", "tok-x"]},
                "response": {"contract_version": "0.3", "ok": True},
            }
        )
    )
    index = replay.load_fixture_dir(tmp_path)
    # Lookup argv has no leading "tn" (the CLI receives args after the entrypoint).
    key = replay.normalize_request(["metrics", "list", "--token", "tok-x"])
    assert key in index
