"""Load source/generator/schema.py by file path (it is not on sys.path).

The module must be registered in sys.modules before exec: schema.py uses a
frozen @dataclass, and dataclass processing looks up sys.modules[__module__]
to resolve string annotations (raises AttributeError otherwise on 3.14).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_schema(schema_py: Path):
    schema_py = Path(schema_py)
    mod_name = "_tn_schema"
    spec = importlib.util.spec_from_file_location(mod_name, schema_py)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module
