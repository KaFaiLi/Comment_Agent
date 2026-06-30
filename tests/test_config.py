import pytest
from comment_agent.config import AppConfig


def test_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "dep")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_VERSION", "2024-10-21")
    cfg = AppConfig.from_env()
    assert cfg.azure_deployment == "dep"
    assert cfg.max_workers == 4  # default


def test_from_env_missing_required_raises(monkeypatch):
    for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT",
              "AZURE_OPENAI_API_KEY", "OPENAI_API_VERSION"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError):
        AppConfig.from_env()
