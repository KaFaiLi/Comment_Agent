from langchain_openai import AzureChatOpenAI

from comment_agent.config import AppConfig


def build_chat_model(cfg: AppConfig) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=cfg.azure_endpoint,
        azure_deployment=cfg.azure_deployment,
        api_key=cfg.api_key,
        api_version=cfg.api_version,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


def structured(model, schema):
    """Bind a Pydantic schema using the modern strict JSON-schema method."""
    return model.with_structured_output(schema, method="json_schema")
