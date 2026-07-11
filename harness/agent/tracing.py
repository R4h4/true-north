"""Langfuse tracing via Strands' OTel exporter.

Langfuse acts as an OTLP backend at <host>/api/public/otel with Basic auth built
from the public/secret key pair. No-op (returns False) when keys are absent so
local runs work without a Langfuse project.
"""

import base64
import os


def init_tracing() -> bool:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        return False

    host = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", f"{host}/api/public/otel")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic {auth}")
    os.environ.setdefault("OTEL_SERVICE_NAME", "true-north-harness")

    from strands.telemetry import StrandsTelemetry

    StrandsTelemetry().setup_otlp_exporter()
    return True
