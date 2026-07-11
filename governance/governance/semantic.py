"""Load the semantic layer (source/semantic/*.yml) into typed objects.

The YAML schema is source/semantic/SCHEMA.md (frozen). This module is the one
place that parses it; the compiler, the policy derivation, and the catalog
commands all consume these dataclasses rather than re-reading YAML.

Physical truth (tables/columns/vocabularies) is source/generator/schema.py; we
load it via the same file-path loader tools/ uses, so there is a single source
of truth for what columns exist.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_DIR = REPO_ROOT / "source" / "semantic"
SCHEMA_PY = REPO_ROOT / "source" / "generator" / "schema.py"


def _load_schema_module(schema_py: Path = SCHEMA_PY):
    mod_name = "_tn_schema"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, schema_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Measure:
    name: str
    table: str
    expr: str
    agg: str
    time_column: str | None = None
    filters: tuple[dict, ...] = ()
    joins: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    short_description: str
    description: str
    concept: str
    type: str
    unit: str
    version: str
    formula: str
    time_dimension: str
    dimensions: tuple[str, ...]
    measures: tuple[Measure, ...]
    expr: str
    template: str | None = None

    @property
    def tables(self) -> list[str]:
        """Measure tables in first-seen order (join-only dim tables excluded)."""
        seen: list[str] = []
        for m in self.measures:
            if m.table not in seen:
                seen.append(m.table)
        return seen


@dataclass(frozen=True)
class Dimension:
    key: str
    name: str
    description: str
    type: str
    source: str | None
    canonical_values: tuple[str, ...] = ()
    grains: tuple[str, ...] = ()

    @property
    def table(self) -> str | None:
        return self.source.split(".", 1)[0] if self.source else None

    @property
    def column(self) -> str | None:
        return self.source.split(".", 1)[1] if self.source else None


@dataclass(frozen=True)
class SemanticLayer:
    metrics: dict[str, Metric]
    dimensions: dict[str, Dimension]

    def metric(self, key: str) -> Metric | None:
        return self.metrics.get(key)

    def dimension(self, key: str) -> Dimension | None:
        return self.dimensions.get(key)


def _load_dir(directory: Path) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    if not directory.is_dir():
        return docs
    for path in sorted(directory.glob("*.yml")):
        docs[path.stem] = yaml.safe_load(path.read_text())
    return docs


def _measure(name: str, raw: dict) -> Measure:
    return Measure(
        name=name,
        table=raw["table"],
        expr=raw.get("expr", ""),
        agg=raw.get("agg", "sum"),
        time_column=raw.get("time_column"),
        filters=tuple(raw.get("filters") or ()),
        joins=tuple(raw.get("joins") or ()),
    )


def _metric(stem: str, raw: dict) -> Metric:
    compute = raw.get("compute") or {}
    measures = tuple(
        _measure(mname, mraw) for mname, mraw in (compute.get("measures") or {}).items()
    )
    return Metric(
        key=raw["key"],
        name=raw["name"],
        short_description=raw["short_description"],
        description=" ".join(str(raw["description"]).split()),
        concept=raw["concept"],
        type=raw["type"],
        unit=raw["unit"],
        version=str(raw["version"]),
        formula=raw["formula"],
        time_dimension=raw["time_dimension"],
        dimensions=tuple(raw.get("dimensions") or ()),
        measures=measures,
        expr=compute.get("expr", ""),
        template=compute.get("template"),
    )


def _dimension(stem: str, raw: dict) -> Dimension:
    return Dimension(
        key=raw["key"],
        name=raw["name"],
        description=raw["description"],
        type=raw["type"],
        source=raw.get("source"),
        canonical_values=tuple(raw.get("canonical_values") or ()),
        grains=tuple(raw.get("grains") or ()),
    )


@lru_cache(maxsize=None)
def load_semantic(semantic_dir: Path = SEMANTIC_DIR) -> SemanticLayer:
    metrics_raw = _load_dir(Path(semantic_dir) / "metrics")
    dims_raw = _load_dir(Path(semantic_dir) / "dimensions")
    metrics = {stem: _metric(stem, raw) for stem, raw in metrics_raw.items()}
    dimensions = {stem: _dimension(stem, raw) for stem, raw in dims_raw.items()}
    return SemanticLayer(metrics=metrics, dimensions=dimensions)


def schema_module():
    return _load_schema_module()
