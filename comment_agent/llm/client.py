import warnings

from langchain_openai import AzureChatOpenAI

from comment_agent.config import AppConfig
from comment_agent.logging_config import get_logger

logger = get_logger(__name__)

# langchain-openai's json_schema structured output returns a response whose
# `parsed` field is declared Optional but is populated with the bound schema,
# so pydantic emits a benign "serialized value may not be as expected" warning
# on every structured call. Parsing succeeds; suppress the upstream noise.
warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
)


def build_chat_model(cfg: AppConfig) -> AzureChatOpenAI:
    logger.info(
        "Building Azure chat model | deployment=%s | api_version=%s | "
        "temperature=%s | max_tokens=%d",
        cfg.azure_deployment, cfg.api_version, cfg.temperature, cfg.max_tokens,
    )
    return AzureChatOpenAI(
        azure_endpoint=cfg.azure_endpoint,
        azure_deployment=cfg.azure_deployment,
        api_key=cfg.api_key,
        api_version=cfg.api_version,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


def structured(model, schema):
    """Bind a Pydantic schema using strict JSON-schema. include_raw keeps the
    raw model output on parse failure so invoke_structured can repair it."""
    logger.debug("Binding structured output schema | %s", getattr(schema, "__name__", schema))
    return model.with_structured_output(schema, method="json_schema", include_raw=True)
