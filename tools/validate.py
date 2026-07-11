"""Repo validator entrypoint: runs the semantic, vocabulary, and policy validators.

    uv run python -m tools.validate    # runs all three against repo defaults
    make validate

Exit 0 when clean, 1 when any validator reports errors. Missing semantic or
vocabulary directories are SKIPPED with a notice (they land in parallel PRs);
a missing users.yaml is an error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tools.validators.policy import validate_policy
from tools.validators.semantic import validate_semantic
from tools.validators.vocabulary import validate_vocabulary

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_DIR = REPO_ROOT / "source" / "semantic"
VOCAB_DIR = REPO_ROOT / "knowledge-graph" / "vocabulary"
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"
SCHEMA_PY = REPO_ROOT / "source" / "generator" / "schema.py"


def main(argv: list[str] | None = None) -> int:
    errors: list[str] = []

    # The layer is "authored" once its content subdirs exist; until then it lands
    # in a parallel PR and is skipped (SCHEMA.md alone is just the spec).
    if (SEMANTIC_DIR / "metrics").is_dir():
        errors += validate_semantic(SEMANTIC_DIR, SCHEMA_PY)
    else:
        print(f"notice: skipping semantic — {SEMANTIC_DIR}/metrics does not exist yet", file=sys.stderr)

    if (VOCAB_DIR / "concepts").is_dir():
        errors += validate_vocabulary(VOCAB_DIR, SEMANTIC_DIR, SCHEMA_PY)
    else:
        print(f"notice: skipping vocabulary — {VOCAB_DIR}/concepts does not exist yet", file=sys.stderr)

    errors += validate_policy(USERS_YAML, SCHEMA_PY)

    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print(f"\n{len(errors)} validation error(s)", file=sys.stderr)
        return 1
    print("ok: all validators passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
