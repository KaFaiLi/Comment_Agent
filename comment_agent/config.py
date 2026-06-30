import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    azure_endpoint: str
    azure_deployment: str
    api_key: str
    api_version: str
    max_tokens: int = 32768
    temperature: float = 0.1
    max_workers: int = 4
    max_retries: int = 3
    output_dir: str = "Outputs"

    @classmethod
    def from_env(cls) -> "AppConfig":
        required = {
            "azure_endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            "api_key": os.environ.get("AZURE_OPENAI_API_KEY"),
            "api_version": os.environ.get("OPENAI_API_VERSION"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required Azure env vars: {missing}")

        return cls(
            **required,
            max_tokens=int(os.environ.get("COMMENT_AGENT_MAX_TOKENS", 32768)),
            max_workers=int(os.environ.get("COMMENT_AGENT_MAX_WORKERS", 4)),
            max_retries=int(os.environ.get("COMMENT_AGENT_MAX_RETRIES", 3)),
            output_dir=os.environ.get("COMMENT_AGENT_OUTPUT_DIR", "Outputs"),
        )
