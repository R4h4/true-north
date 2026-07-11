"""The Policy table universe (_all_tables) must come from the DATASET's schema.py.

Regression pin for a real bug: governance.policy.load_policy() derived _all_tables
from schema_module() with no dataset awareness, so a Policy built for a non-retail
dataset validated table grants against the RETAIL table set. Neither Postgres nor a
live graph is needed — a tmp schema.py fixture registered as a throwaway dataset
proves the seam without depending on the shinhan-content branch.
"""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RETAIL_USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"

# Distinct table names that do NOT exist in the retail schema, so a leak of the
# retail universe would be unmistakable.
_FIXTURE_TABLES = {"loan_book", "fpd_events", "dim_borrower"}

_SCHEMA_PY = textwrap.dedent(
    '''
    """Throwaway schema.py fixture for the table-universe test."""
    from dataclasses import dataclass


    @dataclass(frozen=True)
    class Column:
        name: str
        dtype: str
        description: str = ""


    TABLES = {
        "loan_book": [Column("loan_id", "string")],
        "fpd_events": [Column("event_id", "string")],
        "dim_borrower": [Column("borrower_id", "string")],
    }
    '''
)


@pytest.fixture
def fixture_dataset(tmp_path, monkeypatch):
    """Register a throwaway dataset whose schema.py has _FIXTURE_TABLES.

    Points semantic_dir/users_yaml at real-enough content: an empty semantic dir
    (load_semantic tolerates it) and the retail users.yaml (content parity is
    irrelevant — the table universe comes from schema.py, which is the point)."""
    from semantic_layer import datasets as ds_mod

    (tmp_path / "generator").mkdir()
    schema_py = tmp_path / "generator" / "schema.py"
    schema_py.write_text(_SCHEMA_PY)
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()

    key = "fixtureds"
    entry = replace(
        ds_mod.get_dataset("retail"),
        key=key,
        data_dir=tmp_path / "data",
        semantic_dir=semantic_dir,
        schema_py=schema_py,
        vocab_dir=tmp_path / "vocabulary",
        users_yaml=RETAIL_USERS_YAML,
        pg_schema="tn_fixtureds",
    )
    monkeypatch.setitem(ds_mod._REGISTRY, key, entry)
    return key


def test_load_policy_table_universe_is_dataset_scoped(fixture_dataset):
    from governance.policy import load_policy

    policy = load_policy(RETAIL_USERS_YAML, dataset=fixture_dataset)

    assert policy._all_tables == frozenset(_FIXTURE_TABLES)
    # The retail table set must NOT leak in.
    assert "fact_sales_lines" not in policy._all_tables
    assert "dim_store" not in policy._all_tables


def test_load_policy_default_is_retail_table_universe():
    """The default path is unchanged: retail's real table set."""
    from governance.policy import load_policy

    policy = load_policy()
    assert "fact_sales_lines" in policy._all_tables
    assert "dim_store" in policy._all_tables
    assert _FIXTURE_TABLES.isdisjoint(policy._all_tables)
