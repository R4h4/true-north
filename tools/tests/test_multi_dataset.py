"""Phase-6 red spec: multi-dataset support (coordinator-authored, normative).

Architecture under test (ADR to be written by the implementer):

- ``semantic_layer.datasets`` is the ONE seam: a frozen registry mapping a
  dataset key to its bundle of paths and scopes. Everything that today
  hard-codes a retail path (warehouse data dir, semantic YAML dir, schema.py,
  KG vocabulary, users.yaml, Neo4j URI, Postgres schema) resolves through it.
- ``retail`` is the default and maps to the EXACT current paths — no file
  moves, no behavior change; every existing golden stays byte-identical.
- ``shinhan`` maps to a self-contained bundle under ``source/datasets/shinhan/``
  (content lands in a parallel branch; the registry entry must not require the
  files to exist until they are used).
- Postgres isolation is schema-per-dataset: retail == ``public`` (untouched),
  shinhan == ``tn_shinhan`` with the identical DDL via the same Alembic chain.
- Neo4j isolation is instance-per-dataset: retail on 7687 (unchanged), shinhan
  on bolt://localhost:7688, override via ``NEO4J_BOLT_URI_SHINHAN``.
- CLI: global ``--dataset`` option on ``tn`` (also env ``TN_DATASET``;
  explicit flag wins). Unknown key -> ok:false envelope with error code
  ``UNKNOWN_DATASET``, exit 1, and the message must list the valid keys.

Registry-only tests run everywhere; anything touching the CLI or a live
store is TN_E2E-gated like the rest of tools/tests.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E = pytest.mark.skipif(
    os.environ.get("TN_E2E") != "1", reason="TN_E2E=1 required (live stack)"
)


def _tn(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["uv", "run", "tn", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=full_env,
    )


# --- registry ----------------------------------------------------------------


def test_registry_default_is_retail_with_current_paths():
    from semantic_layer.datasets import get_dataset

    ds = get_dataset()
    assert ds.key == "retail"
    assert ds.data_dir == REPO_ROOT / "source" / "data"
    assert ds.semantic_dir == REPO_ROOT / "source" / "semantic"
    assert ds.schema_py == REPO_ROOT / "source" / "generator" / "schema.py"
    assert ds.vocab_dir == REPO_ROOT / "knowledge-graph" / "vocabulary"
    assert ds.users_yaml == REPO_ROOT / "governance" / "fixtures" / "users.yaml"
    assert ds.pg_schema == "public"
    # retail keeps today's Neo4j resolution (env NEO4J_BOLT_URI or 7687)
    assert "7687" in ds.bolt_uri()


def test_registry_shinhan_bundle_is_self_contained_and_isolated():
    from semantic_layer.datasets import get_dataset

    ds = get_dataset("shinhan")
    root = REPO_ROOT / "source" / "datasets" / "shinhan"
    assert ds.key == "shinhan"
    for p in (ds.data_dir, ds.semantic_dir, ds.schema_py, ds.vocab_dir, ds.users_yaml):
        assert root in Path(p).parents or Path(p) == root, p
    assert ds.pg_schema == "tn_shinhan"
    assert "7688" in ds.bolt_uri()


def test_registry_unknown_key_raises_with_valid_keys_named():
    from semantic_layer.datasets import UnknownDataset, get_dataset

    with pytest.raises(UnknownDataset) as exc:
        get_dataset("phongvu")
    assert "retail" in str(exc.value) and "shinhan" in str(exc.value)


def test_registry_env_default_and_explicit_override(monkeypatch):
    from semantic_layer.datasets import get_dataset

    monkeypatch.setenv("TN_DATASET", "shinhan")
    assert get_dataset().key == "shinhan"
    assert get_dataset("retail").key == "retail"  # explicit arg beats env


def test_shinhan_bolt_uri_env_override(monkeypatch):
    from semantic_layer.datasets import get_dataset

    monkeypatch.setenv("NEO4J_BOLT_URI_SHINHAN", "bolt://elsewhere:9999")
    assert get_dataset("shinhan").bolt_uri() == "bolt://elsewhere:9999"


# --- CLI surface --------------------------------------------------------------


@E2E
def test_cli_explicit_retail_flag_is_byte_identical_to_default():
    base = _tn("metrics", "list", "--token", "tok-analyst-binh")
    flagged = _tn("--dataset", "retail", "metrics", "list", "--token", "tok-analyst-binh")
    assert base.returncode == 0
    assert flagged.returncode == base.returncode
    assert flagged.stdout == base.stdout


@E2E
def test_cli_unknown_dataset_is_a_clean_envelope():
    res = _tn("--dataset", "nope", "whoami", "--token", "tok-analyst-binh")
    assert res.returncode == 1
    envelope = json.loads(res.stdout)  # stdout must stay valid JSON
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "UNKNOWN_DATASET"
    assert "retail" in envelope["error"]["message"]
    assert "shinhan" in envelope["error"]["message"]


@E2E
def test_cli_env_dataset_default_applies():
    """TN_DATASET=nope must fail the same way as the flag (proves env is read)."""
    res = _tn("whoami", "--token", "tok-analyst-binh", env={"TN_DATASET": "nope"})
    assert res.returncode == 1
    envelope = json.loads(res.stdout)
    assert envelope["error"]["code"] == "UNKNOWN_DATASET"


@E2E
def test_shinhan_query_carries_dataset_scoped_governance_metadata():
    """Caveats and freshness must come from the DATASET's vocabulary and schema —
    both were retail-bound seams once (constraints dir, _freshness schema_module).
    Requires the provisioned demo stack (make demo)."""
    res = _tn(
        "--dataset", "shinhan", "query",
        "--token", "tok-exec-sujin", "--metric", "npl_ratio", "--group-by", "product",
    )
    assert res.returncode == 0
    envelope = json.loads(res.stdout)
    assert envelope["ok"] is True
    prov = envelope["metadata"]["provenance"]
    assert prov["constraint_keys"], "shinhan constraints must attach (write-off caveat etc.)"
    assert envelope["metadata"]["as_of"], "freshness must resolve from the shinhan schema"
    assert envelope["metadata"]["freshness"].get("fact_loan_snapshots")


# --- Postgres schema isolation ------------------------------------------------


@E2E
def test_pg_loader_and_audit_are_schema_scoped():
    """Loading a dataset's policy must not touch public, and audit rows must land
    in the dataset's schema. Uses shinhan's OWN users.yaml so the (idempotent)
    load leaves a provisioned demo store correct rather than clobbering it.
    Known residual (accepted): the loader's prune step fails with an FK violation
    if a user is removed from users.yaml after accruing audit rows."""
    import psycopg

    from governance import pg as gpg
    from semantic_layer.datasets import get_dataset

    dsn = gpg.resolve_dsn()
    shinhan_yaml = get_dataset("shinhan").users_yaml

    with psycopg.connect(dsn) as conn:
        before_public_users = conn.execute("SELECT count(*) FROM public.users").fetchone()[0]
        before_public_audit = conn.execute("SELECT count(*) FROM public.audit_log").fetchone()[0]

    gpg.load_policy_to_db(users_yaml=shinhan_yaml, dataset="shinhan")
    gpg.write_audit(
        command="whoami",
        token="tok-exec-sujin",
        user_id="u_sujin",
        role="executive",
        request={},
        executed_query=None,
        ok=True,
        error_code=None,
        contract_version="0.3",
        dataset="shinhan",
    )

    with psycopg.connect(dsn) as conn:
        # shinhan schema exists, is hydrated, and received the audit row
        n_users = conn.execute("SELECT count(*) FROM tn_shinhan.users").fetchone()[0]
        assert n_users > 0
        n_audit = conn.execute(
            "SELECT count(*) FROM tn_shinhan.audit_log WHERE command = 'whoami'"
        ).fetchone()[0]
        assert n_audit >= 1
        # public (retail) is untouched by any of it
        assert conn.execute("SELECT count(*) FROM public.users").fetchone()[0] == before_public_users
        assert conn.execute("SELECT count(*) FROM public.audit_log").fetchone()[0] == before_public_audit


@E2E
def test_pg_policy_roundtrip_from_shinhan_schema():
    """load_policy_from_db(dataset='shinhan') reconstructs the policy loaded above —
    the same parity guarantee phase 5 pinned for retail, now per schema."""
    from governance import pg as gpg
    from semantic_layer.datasets import get_dataset

    gpg.load_policy_to_db(users_yaml=get_dataset("shinhan").users_yaml, dataset="shinhan")
    policy = gpg.load_policy_from_db(dataset="shinhan")
    assert "tok-exec-sujin" in policy.personas
    assert "tok-exec-mai" not in policy.personas  # retail personas must not leak in
