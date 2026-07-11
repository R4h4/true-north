"""Deterministic PII tokenization and value-preserving transforms.

Tokenization is HMAC-SHA256 with a prefix (scheme in users.yaml). The salt is
stable within a process/data build (cached module-level), so the same raw value
always maps to the same token within one demo run — counts, distincts, and joins
over tokenized columns still work, but the raw value is unrecoverable.

Banding (band_5y) buckets an integer year into a 5-year band label
("1990" -> "1990-1994"), a value-preserving disclosure, not a mask.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _run_salt() -> bytes:
    """A salt stable for the lifetime of the process (one demo run).

    Determinism requirement (ADR: identical call twice -> byte-identical stdout)
    is satisfied because the salt is fixed within a process; across processes the
    tokens differ, which the contract permits ("deterministic within a demo run").
    Overridable via TN_TOKEN_SALT so a whole demo (multiple `tn` invocations) can
    share tokens when reproducibility across calls is wanted.
    """
    override = os.environ.get("TN_TOKEN_SALT")
    if override is not None:
        return override.encode("utf-8")
    return b"true-north-demo-salt-v1"


def tokenize(raw: object, prefix: str = "cust_tok_", length: int = 12) -> str | None:
    """Stable token for a raw value. NULL -> None (nulls are not tokenized)."""
    if raw is None:
        return None
    digest = hmac.new(_run_salt(), str(raw).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}{digest[:length]}"


def band_5y(year: object) -> str | None:
    """Bucket a year into an inclusive 5-year band label. NULL -> None."""
    if year is None:
        return None
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    low = (y // 5) * 5
    return f"{low}-{low + 4}"


# Transform-name -> callable, for transformed_columns dispatch.
TRANSFORMS = {"band_5y": band_5y}
