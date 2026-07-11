"""Session KG-context subgraph: what the agent has learned so far.

Parses `tn kg query` envelopes (contract §4 record shapes - every node dict
carries `_label`, denied nodes carry `_access.readable: false`) into a
cumulative {nodes, edges} graph per AG-UI thread. Emitted as shared state so
the frontend renders the "context building up" side panel.

Parsing is defensive by design: unknown shapes are skipped, never raised -
a sidebar gap must not break a turn.
"""

from typing import Any

# Edge semantics between record variables of the canonical queries
# (resolve: c/v/m; detail: m/dims/caveats/tables; access check: m/caveats).
_EDGE_RULES = [
    ("v", "c", "VARIANT_OF"),
    ("v", "m", "MEASURED_BY"),
    ("m", "dims", "HAS_DIMENSION"),
    ("caveats", "m", "CONSTRAINS"),
    ("m", "tables", "COMPUTED_FROM"),
]


def _node_id(node: dict) -> str | None:
    key = node.get("key") or node.get("name")
    label = node.get("_label")
    return f"{label}:{key}" if key and label else None


def _as_nodes(value: Any) -> list[dict]:
    if isinstance(value, dict) and value.get("_label"):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict) and v.get("_label")]
    return []


def empty_graph() -> dict:
    return {"nodes": [], "edges": []}


def merge_envelope(graph: dict, envelope: Any) -> dict:
    """Merge one kg-query envelope into the graph. Returns the graph (mutated)."""
    if not isinstance(envelope, dict) or not envelope.get("ok"):
        return graph
    records = ((envelope.get("result") or {}).get("records")) or []
    known = {n["id"] for n in graph["nodes"]}
    known_edges = {(e["source"], e["target"], e["label"]) for e in graph["edges"]}

    for node in graph["nodes"]:
        node["new"] = False

    for record in records:
        if not isinstance(record, dict):
            continue
        ids_by_var: dict[str, list[str]] = {}
        for var, value in record.items():
            for node in _as_nodes(value):
                node_id = _node_id(node)
                if not node_id:
                    continue
                ids_by_var.setdefault(var, []).append(node_id)
                if node_id in known:
                    continue
                known.add(node_id)
                graph["nodes"].append(
                    {
                        "id": node_id,
                        "label": node["_label"],
                        "name": node.get("name") or node.get("key"),
                        "locked": (node.get("_access") or {}).get("readable") is False,
                        "new": True,
                    }
                )
        for src_var, dst_var, rel in _EDGE_RULES:
            for src in ids_by_var.get(src_var, []):
                for dst in ids_by_var.get(dst_var, []):
                    edge = (src, dst, rel)
                    if edge not in known_edges:
                        known_edges.add(edge)
                        graph["edges"].append({"source": src, "target": dst, "label": rel})
    return _prune_to_decision_path(graph)


def _prune_to_decision_path(graph: dict) -> dict:
    """Scratchpad semantics: once the agent commits to a metric (loads its
    context - dims/caveats/tables edges appear), drop the branches it is NOT
    using. Before any commit, everything stays visible: the ambiguity itself
    is the decision in progress. Locked nodes always stay - a denied metric is
    an explicit decision the user should see."""
    detail_rels = {"HAS_DIMENSION", "CONSTRAINS", "COMPUTED_FROM"}
    chosen = {
        e["source"] if e["label"] != "CONSTRAINS" else e["target"]
        for e in graph["edges"]
        if e["label"] in detail_rels
    }
    if not chosen:
        return graph

    keep = set(chosen) | {n["id"] for n in graph["nodes"] if n["locked"]}
    # Direct neighbors of chosen metrics: dims, caveats, tables, and the
    # variant Concept measuring it.
    variants = set()
    for e in graph["edges"]:
        if e["source"] in chosen:
            keep.add(e["target"])
        if e["target"] in chosen:
            keep.add(e["source"])
            if e["label"] == "MEASURED_BY":
                variants.add(e["source"])
    # The kept variants' parent Concepts (the user's original term) - but not
    # the parents' OTHER variants: those are the rejected branches.
    for e in graph["edges"]:
        if e["label"] == "VARIANT_OF" and e["source"] in variants:
            keep.add(e["target"])

    graph["nodes"] = [n for n in graph["nodes"] if n["id"] in keep]
    graph["edges"] = [
        e for e in graph["edges"] if e["source"] in keep and e["target"] in keep
    ]
    return graph
