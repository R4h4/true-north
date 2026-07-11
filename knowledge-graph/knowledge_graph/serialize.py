"""Recursive serialization of Cypher results per CONTRACT §3.

Wherever a graph entity appears — top level, inside collect() lists, maps, or paths —
the same rules apply:

- Node        -> {_label, key, ...properties}; Metric/Table/Dimension additionally
                 carry _access: {readable, reason?} for the calling role (computed here
                 from the AccessIndex, NEVER stored on the node).
- Relationship -> {_type, _from, _to, ...properties} (_from/_to are node keys).
- Path         -> {nodes: [...], relationships: [...]}.
- Scalars/lists/maps -> plain JSON (scalar rules of §2: DATE/TIMESTAMP as strings,
                 NaN/Infinity -> None, neo4j temporal/int/float mapped to JSON).

The neo4j driver's graph types are duck-typed (labels/type/nodes/relationships/start_node
/end_node attributes) so this module has no hard import dependency on a running driver.
"""

from __future__ import annotations

import math
from datetime import date, datetime

# Labels that carry per-role _access (governed resources). Concept/Constraint/Role
# are knowledge, not governed resources — no _access (CONTRACT §3).
_ACCESS_LABELS = ("Metric", "Table", "Dimension")


class Serializer:
    def __init__(self, access_index, role: str) -> None:
        self._access = access_index
        self._role = role

    # --- entity dispatch --------------------------------------------------

    def value(self, obj):
        """Serialize any Cypher return value recursively."""
        if _is_node(obj):
            return self._node(obj)
        if _is_relationship(obj):
            return self._relationship(obj)
        if _is_path(obj):
            return self._path(obj)
        if isinstance(obj, dict):
            return {k: self.value(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.value(v) for v in obj]
        return _scalar(obj)

    def record(self, record) -> dict:
        """A driver Record (or dict) keyed by RETURN aliases -> serialized dict."""
        items = record.items() if hasattr(record, "items") else dict(record).items()
        return {key: self.value(val) for key, val in items}

    # --- node/rel/path ----------------------------------------------------

    def _node(self, node) -> dict:
        labels = list(getattr(node, "labels", []) or [])
        label = labels[0] if labels else None
        props = dict(node)
        out = {"_label": label}
        out.update({k: _scalar(v) if not isinstance(v, (list, dict)) else self.value(v)
                    for k, v in props.items()})
        if label in _ACCESS_LABELS:
            out["_access"] = self._node_access(label, props.get("key"))
        return out

    def _relationship(self, rel) -> dict:
        rel_type = getattr(rel, "type", None)
        start = getattr(rel, "start_node", None)
        end = getattr(rel, "end_node", None)
        out = {
            "_type": rel_type,
            "_from": _node_key(start),
            "_to": _node_key(end),
        }
        for k, v in dict(rel).items():
            out[k] = _scalar(v) if not isinstance(v, (list, dict)) else self.value(v)
        return out

    def _path(self, path) -> dict:
        return {
            "nodes": [self._node(n) for n in path.nodes],
            "relationships": [self._relationship(r) for r in path.relationships],
        }

    def _node_access(self, label: str, key) -> dict:
        if key is None:
            return {"readable": True}
        if label == "Metric":
            return self._access.metric_access(key, self._role)
        if label == "Table":
            return self._access.table_access(key, self._role)
        if label == "Dimension":
            return self._access.dimension_access(key, self._role)
        return {"readable": True}


# --- duck-typing helpers --------------------------------------------------

def _is_node(obj) -> bool:
    return hasattr(obj, "labels") and hasattr(obj, "items") and not hasattr(obj, "type")


def _is_relationship(obj) -> bool:
    return hasattr(obj, "type") and hasattr(obj, "start_node") and hasattr(obj, "end_node")


def _is_path(obj) -> bool:
    return hasattr(obj, "nodes") and hasattr(obj, "relationships") and not hasattr(obj, "labels")


def _node_key(node):
    if node is None:
        return None
    try:
        return node["key"]
    except (KeyError, TypeError):
        return None


def _scalar(v):
    """CONTRACT §2 scalar rules."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    # neo4j DateTime/Date temporal types expose to_native(); fall back to str.
    if hasattr(v, "to_native"):
        return _scalar(v.to_native())
    return v
