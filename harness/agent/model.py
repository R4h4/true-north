"""Model factory: one Responses-API provider, env-selected backend.

GPT-5.5 on Bedrock supports only the Responses API (no Chat Completions/Converse),
so both backends go through OpenAIResponsesModel:

- Dev (OpenAI platform):  set OPENAI_API_KEY (and optionally MODEL_ID, default gpt-5.5).
- Prod (Bedrock Mantle):  set BEDROCK_MANTLE_REGION (+ standard AWS credential chain)
  and MODEL_ID=openai.gpt-5.5. Bearer tokens are minted per request by the provider.

Setting both backends at once is a config error we fail loudly on.
"""

import os

from strands.models.openai_responses import OpenAIResponsesModel

DEFAULT_OPENAI_MODEL_ID = "gpt-5.5"
DEFAULT_MANTLE_MODEL_ID = "openai.gpt-5.5"


def build_model() -> OpenAIResponsesModel:
    mantle_region = os.getenv("BEDROCK_MANTLE_REGION")
    openai_key = os.getenv("OPENAI_API_KEY")

    if mantle_region and openai_key:
        raise RuntimeError(
            "Both BEDROCK_MANTLE_REGION and OPENAI_API_KEY are set - "
            "unset one so the model backend is unambiguous."
        )

    if mantle_region:
        return OpenAIResponsesModel(
            bedrock_mantle_config={"region": mantle_region},
            model_id=os.getenv("MODEL_ID", DEFAULT_MANTLE_MODEL_ID),
            stateful=False,
        )

    if openai_key:
        client_args: dict = {"api_key": openai_key}
        if base_url := os.getenv("OPENAI_BASE_URL"):
            client_args["base_url"] = base_url
        return OpenAIResponsesModel(
            client_args=client_args,
            model_id=os.getenv("MODEL_ID", DEFAULT_OPENAI_MODEL_ID),
            stateful=False,
        )

    raise RuntimeError(
        "No model backend configured: set OPENAI_API_KEY (dev) or "
        "BEDROCK_MANTLE_REGION (Bedrock). See harness/.env.example."
    )
