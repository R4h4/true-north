"""Repo validator entrypoint: runs the semantic, vocabulary, and policy validators
for EVERY registered dataset (retail, shinhan, ...).

    uv run python -m tools.validate    # sweeps the whole dataset registry
    make validate

Exit 0 when clean, 1 when any validator reports errors. Missing semantic or
vocabulary directories are SKIPPED with a notice (they land in parallel PRs);
a missing users.yaml is an error. Until 2026-07-12 this validated only the
retail paths — the unvalidated shinhan bundle is how a metric declaring a
builder-less compute.template (fpd_rate) reached demo day.
"""

from __future__ import annotations

import sys
from pathlib import Path

from semantic_layer.datasets import all_datasets
from tools.validators.policy import validate_policy
from tools.validators.semantic import CONTRACT_METRIC_KEYS, validate_semantic
from tools.validators.vocabulary import validate_vocabulary

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    errors: list[str] = []

    for ds in all_datasets():
        tag = f"[{ds.key}]"
        # CONTRACT.md pins metric keys for the retail tenant only; other
        # datasets are validated structurally without a required-key list.
        required = CONTRACT_METRIC_KEYS if ds.key == "retail" else set()

        # The layer is "authored" once its content subdirs exist; until then it
        # lands in a parallel PR and is skipped (SCHEMA.md alone is just the spec).
        if (ds.semantic_dir / "metrics").is_dir():
            errors += [
                f"{tag} {e}"
                for e in validate_semantic(ds.semantic_dir, ds.schema_py, required_metric_keys=required)
            ]
        else:
            print(f"notice: {tag} skipping semantic — {ds.semantic_dir}/metrics does not exist yet", file=sys.stderr)

        if (ds.vocab_dir / "concepts").is_dir():
            errors += [
                f"{tag} {e}"
                for e in validate_vocabulary(ds.vocab_dir, ds.semantic_dir, ds.schema_py)
            ]
        else:
            print(f"notice: {tag} skipping vocabulary — {ds.vocab_dir}/concepts does not exist yet", file=sys.stderr)

        # persona pinning mirrors the metric-key rule: CONTRACT.md §1 names
        # retail's demo users only
        persona_kwargs = {} if ds.key == "retail" else {"required_roles": set(), "required_tokens": set()}
        errors += [f"{tag} {e}" for e in validate_policy(ds.users_yaml, ds.schema_py, **persona_kwargs)]

    validated = ", ".join(ds.key for ds in all_datasets())
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print(f"\n{len(errors)} validation error(s) across datasets: {validated}", file=sys.stderr)
        return 1
    print(f"ok: all validators passed for datasets: {validated}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
