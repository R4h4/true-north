"""Governance derivation over users.yaml + the semantic layer (Deliverable 2).

users.yaml is the single policy source (ADR 0007). Everything the harness
observes — denied metrics/dimensions, applied_permissions, whoami.permissions,
KG _access — is DERIVED here from role grants against physical objects
(schema.py) crossed with the semantic layer. Nothing downstream is authored.

Public API (the coordinator points Agent B's `_access` derivation at this):

    load_policy(users_yaml=?, semantic=?) -> Policy
    Policy.resolve_token(token) -> Persona | None
    Policy.access_for(role) -> RoleAccess
    RoleAccess.readable_tables            -> list[str] (sorted)
    RoleAccess.can_read_table(table)      -> bool
    RoleAccess.metric_denial(metric_key)  -> Denial | None      # None == allowed
    RoleAccess.dimension_denial(dim_key)  -> Denial | None
    RoleAccess.row_filters                -> list[RowFilter]    # attrs interpolated per-persona
    RoleAccess.permission_objects(persona)-> list[dict]         # typed CONTRACT §1 objects
    RoleAccess.applied_permissions(persona, tables, dims) -> list[dict]

`Denial` carries `code` (ACCESS_DENIED_TABLE|ACCESS_DENIED_METRIC|
ACCESS_DENIED_DIMENSION), `reason`, and the blocking `table`/`column`.
Denial precedence (CONTRACT): a metric blocked by an unreadable table returns
ACCESS_DENIED_TABLE (not ACCESS_DENIED_METRIC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from governance.semantic import Metric, SemanticLayer, load_semantic, schema_module

REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"


# --- typed value objects ----------------------------------------------------


@dataclass(frozen=True)
class Persona:
    token: str
    user_id: str
    name: str
    title: str
    role: str
    attributes: dict = field(default_factory=dict)

    @property
    def public(self) -> dict:
        """The {id, name, role} shape used in whoami result.user."""
        return {"id": self.user_id, "name": self.name, "role": self.role}

    def public_short(self) -> dict:
        """The {id, role} shape used in the top-level envelope `user` (§2)."""
        return {"id": self.user_id, "role": self.role}


@dataclass(frozen=True)
class Denial:
    code: str            # ACCESS_DENIED_TABLE | ACCESS_DENIED_METRIC | ACCESS_DENIED_DIMENSION
    reason: str
    table: str | None = None
    column: str | None = None


@dataclass(frozen=True)
class RowFilter:
    table: str           # dim table the disclosure names (from discloses_as)
    column: str
    operator: str
    value: str
    predicate: str       # interpolated SQL predicate, applied to grant `tables`
    apply_to: tuple[str, ...]  # physical tables the predicate is injected into
    display: str

    def as_permission(self) -> dict:
        return {
            "type": "row_filter",
            "table": self.table,
            "column": self.column,
            "operator": self.operator,
            "value": self.value,
            "display": self.display,
        }


# --- role access index ------------------------------------------------------


@dataclass
class RoleAccess:
    role: str
    _all_tables: frozenset[str]
    _readable: frozenset[str]
    _masked: frozenset[str]           # "table.column"
    _tokenized: tuple[str, ...]       # "table.column", grant order preserved
    _transformed: tuple[tuple[str, str], ...]  # (column, transform)
    _row_filter_templates: tuple[dict, ...]
    semantic: SemanticLayer

    # -- tables --
    @property
    def readable_tables(self) -> list[str]:
        return sorted(self._readable)

    def can_read_table(self, table: str) -> bool:
        return table in self._readable

    # -- columns --
    def is_masked(self, column: str) -> bool:
        return column in self._masked

    def is_tokenized(self, column: str) -> bool:
        return column in self._tokenized

    def transform_of(self, column: str) -> str | None:
        for col, tr in self._transformed:
            if col == column:
                return tr
        return None

    # -- metric denial (precedence: table before column) --
    def metric_denial(self, metric_key: str) -> Denial | None:
        metric = self.semantic.metric(metric_key)
        if metric is None:
            return None
        # 1) any measure table unreadable -> ACCESS_DENIED_TABLE (precedence)
        for table in metric.tables:
            if not self.can_read_table(table):
                return Denial(
                    code="ACCESS_DENIED_TABLE",
                    reason=f"{table} is not readable for role {self.role}",
                    table=table,
                )
        # 2) any measure expr/filters column masked -> ACCESS_DENIED_METRIC
        for measure in metric.measures:
            for col in _measure_columns(measure):
                qualified = f"{measure.table}.{col}"
                if self.is_masked(qualified):
                    return Denial(
                        code="ACCESS_DENIED_METRIC",
                        reason=f"uses masked column {col}",
                        column=col,
                    )
        return None

    def metric_reason_for_catalog(self, metric_key: str) -> str | None:
        """The `access.reason` string for metrics list/describe (None if allowed).

        Matches the golden phrasing: table-based denials say
        "uses table X, not readable for role R"; masked-column denials say
        "uses masked column C".
        """
        denial = self.metric_denial(metric_key)
        if denial is None:
            return None
        if denial.code == "ACCESS_DENIED_TABLE":
            return f"uses table {denial.table}, not readable for role {self.role}"
        return denial.reason

    # -- dimension denial --
    def dimension_denial(self, dim_key: str) -> Denial | None:
        dim = self.semantic.dimension(dim_key)
        if dim is None or dim.source is None:
            return None
        if self.is_masked(dim.source):
            return Denial(
                code="ACCESS_DENIED_DIMENSION",
                reason=f"dimension {dim_key} is backed by masked column {dim.source}",
                column=dim.source,
            )
        # a dimension whose source table is unreadable is also denied
        if dim.table and not self.can_read_table(dim.table):
            return Denial(
                code="ACCESS_DENIED_DIMENSION",
                reason=f"dimension {dim_key} is backed by unreadable table {dim.table}",
                table=dim.table,
            )
        return None

    # -- row filters (interpolated per persona) --
    def row_filters(self, persona: Persona) -> list[RowFilter]:
        out: list[RowFilter] = []
        for rf in self._row_filter_templates:
            predicate = _interpolate(rf.get("predicate", ""), persona.attributes)
            display = _interpolate(rf.get("discloses_as", ""), persona.attributes)
            table, column, operator, value = _parse_disclosure(display)
            out.append(
                RowFilter(
                    table=table,
                    column=column,
                    operator=operator,
                    value=value,
                    predicate=predicate,
                    apply_to=tuple(rf.get("tables") or ()),
                    display=display,
                )
            )
        return out

    # -- denied metrics list (for whoami) --
    def denied_metrics(self) -> list[dict]:
        out: list[dict] = []
        for key in self.semantic.metrics:
            reason = self.metric_reason_for_catalog(key)
            if reason is not None:
                out.append({"key": key, "reason": reason})
        return out

    # -- typed permission objects (CONTRACT §1) --
    def permission_objects(self, persona: Persona) -> list[dict]:
        """Full disclosure set for whoami.permissions — row filters, masks,
        bands, tokens, in a stable order (filters, masked, banded, tokenized)."""
        objs: list[dict] = []
        for rf in self.row_filters(persona):
            objs.append(rf.as_permission())
        for col in self._masked_in_grant_order():
            objs.append(
                {
                    "type": "column_masked",
                    "column": col,
                    "display": _masked_display(col, self.role),
                }
            )
        for col, transform in self._transformed:
            objs.append(
                {
                    "type": "column_banded",
                    "column": col,
                    "display": _banded_display(col, transform),
                }
            )
        for col in self._tokenized:
            objs.append(
                {
                    "type": "column_tokenized",
                    "column": col,
                    "display": "customer ids are stable tokens",
                }
            )
        return objs

    def applied_permissions(
        self,
        persona: Persona,
        touched_tables: set[str],
        touched_columns: set[str] | None = None,
    ) -> list[dict]:
        """The disclosure subset that actually touched a query: any row filter
        whose predicate applies to a touched table, plus token/transform
        disclosures for columns that could appear (tokenized id columns on
        touched tables). Order: row filters first, then tokenized."""
        objs: list[dict] = []
        for rf in self.row_filters(persona):
            if set(rf.apply_to) & touched_tables:
                objs.append(rf.as_permission())
        for col in self._tokenized:
            table = col.split(".", 1)[0]
            if table in touched_tables:
                objs.append(
                    {
                        "type": "column_tokenized",
                        "column": col,
                        "display": "customer ids are stable tokens",
                    }
                )
        return objs

    def _masked_in_grant_order(self) -> list[str]:
        return list(self._masked_order)

    _masked_order: tuple[str, ...] = ()


# --- helpers ----------------------------------------------------------------


def _measure_columns(measure) -> set[str]:
    """Bare column names a measure's expr + structured filters reference."""
    import sqlglot
    import sqlglot.expressions as exp

    cols: set[str] = set()
    if measure.expr:
        try:
            tree = sqlglot.parse_one(measure.expr, dialect="duckdb")
            cols |= {c.name for c in tree.find_all(exp.Column)}
        except Exception:
            pass
    for filt in measure.filters:
        if isinstance(filt, dict) and filt.get("column"):
            cols.add(filt["column"])
    return cols


def _interpolate(template: str, attributes: dict) -> str:
    out = template
    for k, v in (attributes or {}).items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _parse_disclosure(display: str) -> tuple[str, str, str, str]:
    """Split "dim_store.region = 'South'" into (table, column, operator, value)."""
    default = ("", "", "=", "")
    if "=" not in display:
        return default
    lhs, _, rhs = display.partition("=")
    lhs = lhs.strip()
    value = rhs.strip().strip("'").strip('"')
    if "." in lhs:
        table, _, column = lhs.partition(".")
    else:
        table, column = "", lhs
    return (table, column, "=", value)


def _masked_display(column: str, role: str) -> str:
    # Golden phrasing: cost_amount discloses as a role-scoped cost mask.
    if column.endswith(".cost_amount"):
        return f"cost columns are masked for role {role}"
    return f"{column} is masked"


def _banded_display(column: str, transform: str) -> str:
    if column.endswith(".birth_year"):
        return "birth year is disclosed as a 5-year band"
    return f"{column} is disclosed as a band ({transform})"


# --- top-level policy -------------------------------------------------------


@dataclass
class Policy:
    personas: dict[str, Persona]
    roles: dict[str, dict]
    tokenization: dict
    semantic: SemanticLayer
    _all_tables: frozenset[str]
    _access_cache: dict[str, "RoleAccess"] = field(default_factory=dict)

    def resolve_token(self, token: str) -> Persona | None:
        return self.personas.get(token)

    def access_for(self, role: str) -> RoleAccess:
        cached = self._access_cache.get(role)
        if cached is not None:
            return cached
        ra = self._build_access(role)
        self._access_cache[role] = ra
        return ra

    def _build_access(self, role: str) -> RoleAccess:
        rdef = self.roles[role]
        grant = rdef.get("tables")
        if grant == "all":
            readable = frozenset(self._all_tables)
        else:
            readable = frozenset(grant or ())
        masked_list = list(rdef.get("masked_columns") or [])
        tokenized = tuple(rdef.get("tokenized_columns") or ())
        transformed = tuple(
            (e["column"], e["transform"]) for e in (rdef.get("transformed_columns") or [])
        )
        ra = RoleAccess(
            role=role,
            _all_tables=frozenset(self._all_tables),
            _readable=readable,
            _masked=frozenset(masked_list),
            _tokenized=tokenized,
            _transformed=transformed,
            _row_filter_templates=tuple(rdef.get("row_filters") or ()),
            semantic=self.semantic,
        )
        ra._masked_order = tuple(masked_list)
        return ra


def load_policy(
    users_yaml: Path = USERS_YAML,
    semantic: SemanticLayer | None = None,
) -> Policy:
    doc = yaml.safe_load(Path(users_yaml).read_text())
    semantic = semantic or load_semantic()
    schema = schema_module()
    all_tables = frozenset(schema.TABLES.keys())

    personas: dict[str, Persona] = {}
    for u in doc.get("users") or []:
        personas[u["token"]] = Persona(
            token=u["token"],
            user_id=u["user_id"],
            name=u["name"],
            title=u.get("title", ""),
            role=u["role"],
            attributes=u.get("attributes") or {},
        )
    return Policy(
        personas=personas,
        roles=doc.get("roles") or {},
        tokenization=doc.get("tokenization") or {},
        semantic=semantic,
        _all_tables=all_tables,
    )
