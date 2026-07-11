"""Vocabulary validator — enforces knowledge-graph/vocabulary/SCHEMA.md.

Checks authored Concept and Constraint files against the semantic layer and
schema.py. Returns a flat list of human-readable error strings; empty == valid.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tools.validators._schema_loader import load_schema as _load_schema

SEVERITIES = {"info", "warning", "critical"}
CONSTRAINT_TARGET_KINDS = {"metric", "dimension", "table"}
REQUIRED_CONCEPT_FIELDS = ("key", "name", "definition", "aliases")
REQUIRED_CONSTRAINT_FIELDS = ("key", "statement", "severity", "constrains")


def _load_yaml_dir(directory: Path) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    if not directory.is_dir():
        return docs
    for path in sorted(directory.glob("*.yml")):
        docs[path.stem] = yaml.safe_load(path.read_text())
    return docs


def validate_vocabulary(vocab_dir: Path, semantic_dir: Path, schema_py: Path) -> list[str]:
    vocab_dir = Path(vocab_dir)
    semantic_dir = Path(semantic_dir)
    schema = _load_schema(Path(schema_py))
    tables = set(schema.TABLES.keys())

    metric_keys = {p.stem for p in (semantic_dir / "metrics").glob("*.yml")}
    dimension_keys = {p.stem for p in (semantic_dir / "dimensions").glob("*.yml")}

    errors: list[str] = []

    concepts = _load_yaml_dir(vocab_dir / "concepts")
    constraints = _load_yaml_dir(vocab_dir / "constraints")

    # Which concepts are named as a parent by some variant.
    named_parents = {
        c.get("variant_of")
        for c in concepts.values()
        if isinstance(c, dict) and c.get("variant_of")
    }

    # --- Concepts ---------------------------------------------------------
    measured_by_owner: dict[str, str] = {}  # metric key -> first concept key claiming it
    # alias/name registry for case-insensitive uniqueness across all concepts
    seen_alias: dict[str, str] = {}  # lowercased -> owning concept key

    for stem, concept in concepts.items():
        if not isinstance(concept, dict):
            errors.append(f"concept {stem}.yml: not a mapping")
            continue
        key = concept.get("key")
        if key != stem:
            errors.append(f"concept {stem}.yml: key '{key}' does not match filename '{stem}'")
        for field in REQUIRED_CONCEPT_FIELDS:
            if field not in concept:
                errors.append(f"concept {stem}: missing required field '{field}'")

        variant_of = concept.get("variant_of")
        measured_by = concept.get("measured_by")
        is_parent = stem in named_parents

        if variant_of:
            if variant_of == stem:
                errors.append(f"concept {stem}: variant_of references itself")
            elif variant_of not in concepts:
                errors.append(f"concept {stem}: variant_of '{variant_of}' does not resolve")
            else:
                target = concepts[variant_of]
                if isinstance(target, dict) and target.get("variant_of"):
                    errors.append(
                        f"concept {stem}: variant chain — parent '{variant_of}' is itself a variant"
                    )
            # variant must have measured_by resolving to a semantic metric
            if not measured_by:
                errors.append(f"concept {stem}: variant requires measured_by")

        # measured_by resolution + 1:1 ownership applies to variants AND
        # standalone concepts alike (parents are rejected below).
        if measured_by:
            if measured_by not in metric_keys:
                errors.append(
                    f"concept {stem}: measured_by '{measured_by}' does not resolve to a semantic metric"
                )
            elif measured_by in measured_by_owner:
                errors.append(
                    f"concept {stem}: measured_by '{measured_by}' already claimed by "
                    f"'{measured_by_owner[measured_by]}' (must be 1:1)"
                )
            else:
                measured_by_owner[measured_by] = stem

        if is_parent and measured_by:
            errors.append(
                f"concept {stem}: parent concept must not have measured_by (got '{measured_by}')"
            )

        # alias + name uniqueness (case-insensitive) across concepts
        candidates = list(concept.get("aliases") or [])
        name = concept.get("name")
        if name:
            candidates.append(name)
        for cand in candidates:
            low = str(cand).lower()
            if low in seen_alias and seen_alias[low] != stem:
                errors.append(
                    f"concept {stem}: alias/name '{cand}' collides with concept "
                    f"'{seen_alias[low]}' (case-insensitive)"
                )
            else:
                seen_alias.setdefault(low, stem)

    # --- Cross-layer back-pointer ----------------------------------------
    # Each metric's `concept:` must name the vocabulary concept that claims it
    # via measured_by (field presence itself is the semantic validator's job).
    for path in sorted((semantic_dir / "metrics").glob("*.yml")):
        metric = yaml.safe_load(path.read_text()) or {}
        concept_key = metric.get("concept")
        if not concept_key:
            continue
        if concept_key not in concepts:
            errors.append(
                f"metric {path.stem}: concept '{concept_key}' does not exist in the vocabulary"
            )
        elif measured_by_owner.get(path.stem) != concept_key:
            errors.append(
                f"metric {path.stem}: concept back-pointer '{concept_key}' != measured_by "
                f"owner '{measured_by_owner.get(path.stem)}'"
            )

    # --- Constraints ------------------------------------------------------
    for stem, constraint in constraints.items():
        if not isinstance(constraint, dict):
            errors.append(f"constraint {stem}.yml: not a mapping")
            continue
        key = constraint.get("key")
        if key != stem:
            errors.append(f"constraint {stem}.yml: key '{key}' does not match filename '{stem}'")
        for field in REQUIRED_CONSTRAINT_FIELDS:
            if field not in constraint:
                errors.append(f"constraint {stem}: missing required field '{field}'")

        severity = constraint.get("severity")
        if severity is not None and severity not in SEVERITIES:
            errors.append(
                f"constraint {stem}: severity '{severity}' not in {sorted(SEVERITIES)}"
            )

        targets = constraint.get("constrains")
        if not targets:
            errors.append(f"constraint {stem}: constrains must be non-empty")
        for target in targets or []:
            if ":" not in str(target):
                errors.append(f"constraint {stem}: target '{target}' is not '<kind>:<key>'")
                continue
            kind, _, tkey = str(target).partition(":")
            if kind not in CONSTRAINT_TARGET_KINDS:
                errors.append(
                    f"constraint {stem}: target kind '{kind}' not in {sorted(CONSTRAINT_TARGET_KINDS)}"
                )
                continue
            if kind == "metric" and tkey not in metric_keys:
                errors.append(f"constraint {stem}: metric target '{tkey}' does not resolve")
            elif kind == "dimension" and tkey not in dimension_keys:
                errors.append(f"constraint {stem}: dimension target '{tkey}' does not resolve")
            elif kind == "table" and tkey not in tables:
                errors.append(f"constraint {stem}: table target '{tkey}' does not resolve")

    return errors
