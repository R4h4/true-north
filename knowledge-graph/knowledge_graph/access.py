"""Per-role access annotations for KG `_access` (CONTRACT §3), single-sourced.

This is a thin adapter over `governance.policy`: the access DERIVATION (which tables
a role can read, which metrics/dimensions are denied and why) lives in one place —
`governance.policy.RoleAccess` (POLICY.md rules, ADR 0007). This module only projects
those results into the `{readable, reason?}` dicts the serializer puts on Metric/Table/
Dimension nodes, and into the positive-image lists build.py turns into CAN_READ/
CAN_COMPUTE edges. Reconciling the two derivations here (rather than reimplementing the
rules for the graph surface) was always the plan; the e2e suite guards the seam.

`_access` is computed at serialization time from this index, never stored on nodes.
"""

from __future__ import annotations

from governance.policy import Policy


class AccessIndex:
    """Answers readable/reason for Table, Metric, Dimension keys per role by delegating
    to governance.policy.RoleAccess — no rules reimplemented here.

    Built once per compile from a governance Policy; the serializer holds one and calls
    it with the calling role.
    """

    def __init__(self, policy: Policy) -> None:
        self._policy = policy
        self._metrics = policy.semantic.metrics
        self._dimensions = policy.semantic.dimensions

    # --- role helpers -----------------------------------------------------

    def roles(self) -> list[str]:
        return list(self._policy.roles.keys())

    def _access(self, role: str):
        return self._policy.access_for(role)

    # --- access answers (thin projections of RoleAccess) ------------------

    def table_access(self, table_key: str, role: str) -> dict:
        if self._access(role).can_read_table(table_key):
            return {"readable": True}
        return {"readable": False, "reason": f"{table_key} is not readable for role {role}"}

    def metric_access(self, metric_key: str, role: str) -> dict:
        acc = self._access(role)
        if metric_key not in self._metrics:
            # The compiler only emits real metric nodes; be defensive rather than crash.
            return {"readable": False, "reason": f"metric {metric_key} is not defined"}
        reason = acc.metric_reason_for_catalog(metric_key)
        if reason is None:
            return {"readable": True}
        return {"readable": False, "reason": reason}

    def dimension_access(self, dimension_key: str, role: str) -> dict:
        acc = self._access(role)
        if dimension_key not in self._dimensions:
            return {"readable": False, "reason": f"dimension {dimension_key} is not defined"}
        denial = acc.dimension_denial(dimension_key)
        if denial is None:
            return {"readable": True}
        if denial.column is not None:
            # graph phrasing names the bare masked column ("uses masked column birth_year")
            bare = denial.column.split(".", 1)[-1]
            return {"readable": False, "reason": f"uses masked column {bare}"}
        return {"readable": False, "reason": denial.reason}

    # --- positive image, for CAN_READ / CAN_COMPUTE edges -----------------

    def can_read_tables(self, role: str, all_tables: list[str]) -> list[str]:
        acc = self._access(role)
        return [t for t in all_tables if acc.can_read_table(t)]

    def can_compute_metrics(self, role: str) -> list[str]:
        return [m for m in self._metrics if self.metric_access(m, role)["readable"]]
