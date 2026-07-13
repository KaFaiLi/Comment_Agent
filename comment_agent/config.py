import os
from dataclasses import dataclass

from dotenv import load_dotenv

from comment_agent.logging_config import configure_logging, get_logger

load_dotenv()

logger = get_logger(__name__)


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
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file: str = "comment_agent.log"

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
            logger.error("Missing required Azure env vars: %s", missing)
            raise ValueError(f"Missing required Azure env vars: {missing}")

        cfg = cls(
            **required,
            max_tokens=int(os.environ.get("COMMENT_AGENT_MAX_TOKENS", 32768)),
            max_workers=int(os.environ.get("COMMENT_AGENT_MAX_WORKERS", 4)),
            max_retries=int(os.environ.get("COMMENT_AGENT_MAX_RETRIES", 3)),
            output_dir=os.environ.get("COMMENT_AGENT_OUTPUT_DIR", "Outputs"),
            log_level=os.environ.get("COMMENT_AGENT_LOG_LEVEL", "INFO"),
            log_dir=os.environ.get("COMMENT_AGENT_LOG_DIR", "logs"),
            log_file=os.environ.get("COMMENT_AGENT_LOG_FILE", "comment_agent.log"),
        )
        # Never log api_key. Deployment/endpoint are safe operational context.
        logger.info(
            "Loaded config | deployment=%s | api_version=%s | max_workers=%d | "
            "max_retries=%d | max_tokens=%d | output_dir=%s",
            cfg.azure_deployment, cfg.api_version, cfg.max_workers,
            cfg.max_retries, cfg.max_tokens, cfg.output_dir,
        )
        return cfg

    def configure_logging(self, *, force: bool = False):
        """Install backend log handlers from this config's log settings."""
        return configure_logging(
            level=self.log_level, log_dir=self.log_dir, log_file=self.log_file,
            force=force,
        )
