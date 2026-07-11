"""Read the sources of truth into the structures the compiler + access index consume.

- vocabulary: concepts + constraints (authored, knowledge-graph/vocabulary/) -> dicts
- semantic:   metrics + dimensions + tables (source/semantic/) -> typed SemanticLayer
- policy:     roles + users (governance/fixtures/users.yaml) -> dict
- schema.py:  physical tables (source/generator/schema.py)

The semantic layer is parsed by the ONE shared loader in the source package
(`semantic_layer.load_semantic`, ADR 0009) — this module no longer re-parses the
semantic YAML. Nothing here talks to Neo4j; the compiler turns these into
nodes/edges and the access index derives `_access` from governance.policy.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from semantic_layer import SemanticLayer, load_semantic as _load_semantic


def _load_yaml_dir(directory: Path) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    directory = Path(directory)
    if not directory.is_dir():
        return docs
    for path in sorted(directory.glob("*.yml")):
        docs[path.stem] = yaml.safe_load(path.read_text())
    return docs


def load_vocabulary(vocab_dir: Path) -> dict:
    vocab_dir = Path(vocab_dir)
    return {
        "concepts": _load_yaml_dir(vocab_dir / "concepts"),
        "constraints": _load_yaml_dir(vocab_dir / "constraints"),
    }


def load_semantic(semantic_dir: Path) -> SemanticLayer:
    """The shared typed semantic layer (metrics + dimensions + tables)."""
    return _load_semantic(Path(semantic_dir))


def load_policy(users_yaml: Path) -> dict:
    return yaml.safe_load(Path(users_yaml).read_text())


def load_schema(schema_py: Path):
    """Import source/generator/schema.py as a module (single source of truth for TABLES)."""
    import sys

    schema_py = Path(schema_py)
    spec = importlib.util.spec_from_file_location("_tn_schema", schema_py)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec so `from __future__ import annotations` dataclass field
    # resolution (which looks the module up in sys.modules) succeeds.
    sys.modules["_tn_schema"] = module
    spec.loader.exec_module(module)
    return module
