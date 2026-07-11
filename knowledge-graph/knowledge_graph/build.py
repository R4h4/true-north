"""Pure graph construction: sources of truth -> node/edge lists + invariant checks.

This module has NO Neo4j dependency — it turns the loaded dicts into plain node/edge
records and asserts the CONTRACT §4.2 invariants. `compile.py` writes these into Neo4j;
tests exercise the invariants without a running database.

Node/edge property shapes match the replay-fixture instances exactly (CONTRACT §3/§4.1):
- Concept:    {key, name, definition, aliases}
- Metric:     {key, name, description, type, unit, formula, version}
- Dimension:  {key, name, description, canonical_values}   (no `type` yet — see change 5)
- Table:      {key, description, grain, freshness_note}
- Constraint: {key, statement, severity}
- Role:       {key, description}

The semantic layer arrives as the shared typed `SemanticLayer` (ADR 0009): metrics
and dimensions are dataclasses, not dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from knowledge_graph.table_semantics import TABLE_SEMANTICS


@dataclass
class Node:
    label: str
    key: str
    props: dict


@dataclass
class Edge:
    type: str
    from_label: str
    from_key: str
    to_label: str
    to_key: str


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# --- node property extraction (fixture-exact shapes) ----------------------

def _concept_props(c: dict) -> dict:
    return {
        "key": c["key"],
        "name": c["name"],
        "definition": (c.get("definition") or "").strip(),
        "aliases": list(c.get("aliases") or []),
    }


def _metric_props(m) -> dict:
    return {
        "key": m.key,
        "name": m.name,
        "description": (m.description or "").strip(),
        "type": m.type,
        "unit": m.unit,
        "formula": m.formula or "",
        "version": str(m.version or ""),
    }


def _dimension_props(d) -> dict:
    return {
        "key": d.key,
        "name": d.name,
        "description": (d.description or "").strip(),
        "canonical_values": list(d.canonical_values or []),
    }


def _table_props(table_key: str) -> dict:
    sem = TABLE_SEMANTICS[table_key]
    return {
        "key": table_key,
        "description": sem["description"],
        "grain": sem["grain"],
        "freshness_note": sem["freshness_note"],
    }


def _constraint_props(k: dict) -> dict:
    return {
        "key": k["key"],
        "statement": (k.get("statement") or "").strip(),
        "severity": k["severity"],
    }


def _role_props(role_key: str, role: dict) -> dict:
    return {"key": role_key, "description": role.get("description", "")}


# --- build ----------------------------------------------------------------

def build_graph(vocabulary: dict, semantic, policy: dict, schema, access_index) -> Graph:
    """Assemble the full node/edge list. Deterministic: sorted iteration throughout.

    `semantic` is the shared typed SemanticLayer (ADR 0009); `.metrics`/`.dimensions`
    are dicts of typed Metric/Dimension objects.
    """
    g = Graph()
    concepts = vocabulary["concepts"]
    constraints = vocabulary["constraints"]
    metrics = semantic.metrics
    dimensions = semantic.dimensions
    all_tables = list(schema.TABLES.keys())

    # Only tables actually reachable (a COMPUTED_FROM target, a dimension source, or
    # a constraint target) become Table nodes — but the graph invariants and CAN_READ
    # want every physical table. Emit all physical tables (they exist in the warehouse).
    for table_key in sorted(all_tables):
        g.nodes.append(Node("Table", table_key, _table_props(table_key)))

    for key in sorted(metrics):
        g.nodes.append(Node("Metric", key, _metric_props(metrics[key])))

    for key in sorted(dimensions):
        g.nodes.append(Node("Dimension", key, _dimension_props(dimensions[key])))

    for key in sorted(concepts):
        g.nodes.append(Node("Concept", key, _concept_props(concepts[key])))

    for key in sorted(constraints):
        g.nodes.append(Node("Constraint", key, _constraint_props(constraints[key])))

    roles = policy.get("roles", {})
    for role_key in sorted(roles):
        g.nodes.append(Node("Role", role_key, _role_props(role_key, roles[role_key])))

    # --- edges ---
    # VARIANT_OF + MEASURED_BY from the vocabulary side (concept.variant_of / measured_by).
    for key in sorted(concepts):
        c = concepts[key]
        parent = c.get("variant_of")
        if parent:
            g.edges.append(Edge("VARIANT_OF", "Concept", key, "Concept", parent))
        measured_by = c.get("measured_by")
        if measured_by:
            g.edges.append(Edge("MEASURED_BY", "Concept", key, "Metric", measured_by))

    # HAS_DIMENSION + COMPUTED_FROM from the semantic metrics.
    for key in sorted(metrics):
        m = metrics[key]
        for dim in m.dimensions:
            g.edges.append(Edge("HAS_DIMENSION", "Metric", key, "Dimension", dim))
        for table in m.tables:
            g.edges.append(Edge("COMPUTED_FROM", "Metric", key, "Table", table))

    # DEFINED_IN from each dimension's source table (skip virtual time dims: source null).
    for key in sorted(dimensions):
        table = dimensions[key].table
        if table:
            g.edges.append(Edge("DEFINED_IN", "Dimension", key, "Table", table))

    # CONSTRAINS from constraint targets.
    label_by_kind = {"metric": "Metric", "dimension": "Dimension", "table": "Table"}
    for key in sorted(constraints):
        for target in constraints[key].get("constrains", []):
            kind, _, tkey = str(target).partition(":")
            g.edges.append(Edge("CONSTRAINS", "Constraint", key, label_by_kind[kind], tkey))

    # CAN_READ / CAN_COMPUTE = positive image of the access derivation.
    for role_key in sorted(roles):
        for table_key in access_index.can_read_tables(role_key, sorted(all_tables)):
            g.edges.append(Edge("CAN_READ", "Role", role_key, "Table", table_key))
        for metric_key in sorted(access_index.can_compute_metrics(role_key)):
            g.edges.append(Edge("CAN_COMPUTE", "Role", role_key, "Metric", metric_key))

    return g


# --- invariants (CONTRACT §4.2) -------------------------------------------

def assert_invariants(graph: Graph, semantic) -> None:
    """Raise AssertionError if any CONTRACT §4.2 invariant is violated.

    `semantic` is the shared typed SemanticLayer (ADR 0009).
    """
    concept_keys = {n.key for n in graph.nodes if n.label == "Concept"}
    metric_keys = {n.key for n in graph.nodes if n.label == "Metric"}

    variant_of = {(e.from_key, e.to_key) for e in graph.edges if e.type == "VARIANT_OF"}
    parents = {to for _, to in variant_of}
    variants = {frm for frm, _ in variant_of}

    measured_by: dict[str, list[str]] = {}
    for e in graph.edges:
        if e.type == "MEASURED_BY":
            measured_by.setdefault(e.from_key, []).append(e.to_key)

    # Invariant 1: a variant Concept has exactly one MEASURED_BY edge.
    for v in sorted(variants):
        n = len(measured_by.get(v, []))
        assert n == 1, f"invariant 1: variant concept '{v}' has {n} MEASURED_BY edges (want 1)"

    # Invariant 2: a parent Concept has no MEASURED_BY of its own.
    for p in sorted(parents):
        assert p not in measured_by, f"invariant 2: parent concept '{p}' has a MEASURED_BY edge"

    # MEASURED_BY targets must be real metrics; every referenced concept must exist.
    for src, targets in measured_by.items():
        assert src in concept_keys, f"MEASURED_BY from unknown concept '{src}'"
        for t in targets:
            assert t in metric_keys, f"MEASURED_BY '{src}' -> unknown metric '{t}'"

    # Invariant 3: every Metric node key exists in the semantic layer (1:1).
    sem_metric_keys = set(semantic.metrics.keys())
    assert metric_keys == sem_metric_keys, (
        f"invariant 3: Metric nodes {sorted(metric_keys)} != semantic metrics {sorted(sem_metric_keys)}"
    )

    # Invariant 4: a metric's HAS_DIMENSION targets are exactly its semantic `dimensions`.
    has_dim: dict[str, set[str]] = {}
    for e in graph.edges:
        if e.type == "HAS_DIMENSION":
            has_dim.setdefault(e.from_key, set()).add(e.to_key)
    for key, m in semantic.metrics.items():
        want = set(m.dimensions)
        got = has_dim.get(key, set())
        assert got == want, (
            f"invariant 4: metric '{key}' HAS_DIMENSION {sorted(got)} != declared {sorted(want)}"
        )
