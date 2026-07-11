"""Policy validator — enforces governance/POLICY.md against governance/fixtures/users.yaml.

Returns a flat list of human-readable error strings; empty == valid.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools.validators._schema_loader import load_schema as _load_schema

CONTRACT_ROLES = {"executive", "regional_manager", "marketing_ops", "data_analyst"}
CONTRACT_TOKENS = {"tok-exec-mai", "tok-rm-south-duc", "tok-mkt-lan", "tok-analyst-binh"}
TRANSFORMS = {"band_5y"}
TREATMENT_FIELDS = ("masked_columns", "tokenized_columns", "transformed_columns")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _resolve_column(ref: str, tables, table_columns) -> str | None:
    """Return an error string if a 'table.column' reference does not resolve, else None."""
    if "." not in str(ref):
        return f"column reference '{ref}' is not table.column"
    tbl, _, col = str(ref).partition(".")
    if tbl not in tables:
        return f"unknown table '{tbl}' in column reference '{ref}'"
    if col not in table_columns[tbl]:
        return f"unknown column '{ref}'"
    return None


def validate_policy(users_yaml: Path, schema_py: Path) -> list[str]:
    users_yaml = Path(users_yaml)
    if not users_yaml.is_file():
        return [f"policy file '{users_yaml}' not found"]

    schema = _load_schema(Path(schema_py))
    tables = set(schema.TABLES.keys())
    table_columns = {t: {c.name for c in cols} for t, cols in schema.TABLES.items()}

    doc = yaml.safe_load(users_yaml.read_text())
    errors: list[str] = []

    users = doc.get("users") or []
    roles = doc.get("roles") or {}

    # --- Contract roles/tokens present ------------------------------------
    for role in sorted(CONTRACT_ROLES):
        if role not in roles:
            errors.append(f"contract role '{role}' is not declared under roles")
    present_tokens = {u.get("token") for u in users if isinstance(u, dict)}
    for tok in sorted(CONTRACT_TOKENS):
        if tok not in present_tokens:
            errors.append(f"contract token '{tok}' is missing from users")

    # --- Users: role declared; collect attributes per role ----------------
    attrs_by_role: dict[str, list[dict]] = {}
    for user in users:
        if not isinstance(user, dict):
            errors.append("user entry is not a mapping")
            continue
        role = user.get("role")
        if role not in roles:
            errors.append(
                f"user '{user.get('token')}': role '{role}' is not declared under roles"
            )
        attrs_by_role.setdefault(role, []).append(user.get("attributes") or {})

    # --- Roles ------------------------------------------------------------
    for role_key, role in roles.items():
        if not isinstance(role, dict):
            errors.append(f"role '{role_key}': not a mapping")
            continue

        # tables: 'all' or subset of real tables
        grant_tables = role.get("tables")
        if grant_tables != "all":
            for tbl in grant_tables or []:
                if tbl not in tables:
                    errors.append(f"role '{role_key}': grants unknown table '{tbl}'")

        # column-treatment references resolve, and each column in at most one treatment
        seen_columns: dict[str, str] = {}  # column -> first treatment field
        for field in TREATMENT_FIELDS:
            for entry in role.get(field) or []:
                col = entry.get("column") if isinstance(entry, dict) else entry
                err = _resolve_column(col, tables, table_columns)
                if err:
                    errors.append(f"role '{role_key}' {field}: {err}")
                    continue
                if col in seen_columns and seen_columns[col] != field:
                    errors.append(
                        f"role '{role_key}': column '{col}' appears in both "
                        f"{seen_columns[col]} and {field} (at most one treatment)"
                    )
                else:
                    seen_columns.setdefault(col, field)

                if field == "transformed_columns":
                    transform = entry.get("transform") if isinstance(entry, dict) else None
                    if transform not in TRANSFORMS:
                        errors.append(
                            f"role '{role_key}': transform '{transform}' on '{col}' "
                            f"not in {sorted(TRANSFORMS)}"
                        )

        # row_filters: placeholders resolve from every holder's attributes
        placeholders: set[str] = set()
        for rf in role.get("row_filters") or []:
            if not isinstance(rf, dict):
                errors.append(f"role '{role_key}': row_filter is not a mapping")
                continue
            for tbl in rf.get("tables") or []:
                if tbl not in tables:
                    errors.append(f"role '{role_key}' row_filter: unknown table '{tbl}'")
            for tmpl_field in ("predicate", "discloses_as"):
                tmpl = rf.get(tmpl_field)
                if tmpl:
                    placeholders |= set(_PLACEHOLDER.findall(str(tmpl)))

        if placeholders:
            for user_attrs in attrs_by_role.get(role_key, []):
                for ph in sorted(placeholders):
                    if ph not in user_attrs:
                        errors.append(
                            f"role '{role_key}': predicate placeholder '{{{ph}}}' has no "
                            f"matching attribute on a user holding this role"
                        )

    return errors
