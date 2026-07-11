"""The static `tn kg schema` payload (CONTRACT §4.1/§4.2/§4.4).

Structure matches governance/fixtures/replay/kg-schema.json['response']['result'] exactly.
This is the graph's self-description — labels, relationship patterns, invariants, and the
canonical example queries the harness bootstraps from. It is content, not derived from the
live graph, so `tn kg schema` needs no token and no database round-trip.
"""

from __future__ import annotations

NODE_LABELS = [
    {"label": "Concept", "properties": ["key", "name", "definition", "aliases"],
     "meaning": "Glossary / business knowledge. May be a parent of variant concepts."},
    {"label": "Metric", "properties": ["key", "name", "description", "type", "unit", "formula", "version"],
     "meaning": "Governed metric, 1:1 with a semantic-layer definition."},
    {"label": "Dimension", "properties": ["key", "name", "description", "type", "canonical_values"],
     "meaning": "Governed dimension."},
    {"label": "Table", "properties": ["key", "description", "grain", "freshness_note"],
     "meaning": "Warehouse table (key is the physical name)."},
    {"label": "Constraint", "properties": ["key", "statement", "severity"],
     "meaning": "Caveat scoping a metric/dimension/table's validity."},
    {"label": "Role", "properties": ["key", "description"],
     "meaning": "Permission principal."},
]

RELATIONSHIPS = [
    {"pattern": "(:Concept)-[:VARIANT_OF]->(:Concept)", "meaning": "variant concept -> parent concept"},
    {"pattern": "(:Concept)-[:MEASURED_BY]->(:Metric)", "meaning": "variant concept -> exactly one governed metric"},
    {"pattern": "(:Metric)-[:HAS_DIMENSION]->(:Dimension)", "meaning": "queryable dimensions of a metric"},
    {"pattern": "(:Metric)-[:COMPUTED_FROM]->(:Table)", "meaning": "tables a metric reads"},
    {"pattern": "(:Dimension)-[:DEFINED_IN]->(:Table)", "meaning": "dimension source table"},
    {"pattern": "(:Constraint)-[:CONSTRAINS]->(:Metric|:Dimension|:Table)", "meaning": "caveat attachment"},
    {"pattern": "(:Role)-[:CAN_READ]->(:Table)", "meaning": "table access"},
    {"pattern": "(:Role)-[:CAN_COMPUTE]->(:Metric)", "meaning": "metric access"},
]

INVARIANTS = [
    "A variant Concept has exactly one MEASURED_BY edge.",
    "A parent Concept (target of VARIANT_OF) has no MEASURED_BY of its own — resolving a term to a parent means the question is ambiguous and the variants are the candidates.",
    "Every Metric node's key also exists in `tn metrics list`, with identical descriptions/types.",
    "Every metric's queryable dimensions are exactly its HAS_DIMENSION targets.",
]

CANONICAL_QUERIES = [
    {
        "purpose": "resolve a business term to governed metrics (the ambiguity path)",
        "cypher": "MATCH (c:Concept) WHERE c.name =~ '(?i).*retention.*' OR any(a IN c.aliases WHERE a =~ '(?i).*retention.*') OPTIONAL MATCH (c)<-[:VARIANT_OF]-(v:Concept)-[:MEASURED_BY]->(m:Metric) RETURN c, v, m",
    },
    {
        "purpose": "everything needed to query a metric correctly",
        "cypher": "MATCH (m:Metric {key: 'net_revenue'}) OPTIONAL MATCH (m)-[:HAS_DIMENSION]->(d:Dimension) OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) OPTIONAL MATCH (m)-[:COMPUTED_FROM]->(t:Table) RETURN m, collect(DISTINCT d) AS dims, collect(DISTINCT k) AS caveats, collect(DISTINCT t) AS tables",
    },
    {
        "purpose": "what can this role see?",
        "cypher": "MATCH (r:Role {key: 'marketing_ops'})-[:CAN_COMPUTE]->(m:Metric) RETURN m.key",
    },
]


def schema_result() -> dict:
    return {
        "node_labels": NODE_LABELS,
        "relationships": RELATIONSHIPS,
        "invariants": INVARIANTS,
        "canonical_queries": CANONICAL_QUERIES,
    }
