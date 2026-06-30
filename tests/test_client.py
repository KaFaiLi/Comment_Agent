from comment_agent.config import AppConfig
from comment_agent.llm import client


def _cfg():
    return AppConfig(azure_endpoint="https://x.openai.azure.com/",
                     azure_deployment="dep", api_key="k", api_version="2024-10-21")


def test_build_chat_model_uses_config():
    model = client.build_chat_model(_cfg())
    assert model.deployment_name == "dep"
    assert model.temperature == 0.1
