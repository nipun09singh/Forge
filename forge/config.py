"""Centralized configuration for Forge — loads from environment variables and .env files."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    """Load .env file if it exists (no external dependency needed)."""
    env_paths = [Path(".env"), Path(__file__).parent.parent / ".env"]
    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and not os.getenv(key):
                            os.environ[key] = value
                logger.debug(f"Loaded .env from {env_path}")
                return
            except Exception as e:
                logger.warning(f"Failed to load .env: {e}")


# Load .env on import
_load_dotenv()


@dataclass
class ForgeConfig:
    """
    Central configuration for the Forge system.
    
    All settings can be overridden via environment variables.
    
    Usage:
        config = ForgeConfig.from_env()
        config.model  # "gpt-4"
        config.api_key  # from OPENAI_API_KEY
    """

    # LLM
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_retries: int = 3

    # Agent defaults
    max_iterations: int = 20
    max_reflections: int = 5
    quality_threshold: float = 0.8
    enable_reflection: bool = True

    # Smart model routing
    smart_routing: bool = False
    fast_model: str = "gpt-4o-mini"
    standard_model: str = "gpt-4o"

    # Cost controls
    max_cost_per_task: float = 0.0  # 0 = unlimited
    max_concurrent_tasks: int = 0   # 0 = unlimited
    cost_alert_threshold: float = 0.8  # Alert at 80% of budget

    # Refinement loop
    max_refinement_iterations: int = 10
    min_quality_score: float = 0.8

    # Memory
    db_path: str = "./data/agency_memory.db"
    data_dir: str = "./data"

    # Logging
    log_level: str = "INFO"

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    # Output
    output_dir: str = "generated"

    @classmethod
    def from_env(cls) -> "ForgeConfig":
        """Create config from environment variables."""
        return cls(
            model=os.getenv("FORGE_MODEL", "gpt-4"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", ""),
            temperature=float(os.getenv("FORGE_TEMPERATURE", "0.7")),
            max_retries=int(os.getenv("FORGE_MAX_RETRIES", "3")),
            max_iterations=int(os.getenv("FORGE_MAX_ITERATIONS", "20")),
            max_reflections=int(os.getenv("FORGE_MAX_REFLECTIONS", "5")),
            quality_threshold=float(os.getenv("FORGE_QUALITY_THRESHOLD", "0.8")),
            enable_reflection=os.getenv("FORGE_ENABLE_REFLECTION", "true").lower() == "true",
            smart_routing=os.getenv("FORGE_SMART_ROUTING", "false").lower() == "true",
            fast_model=os.getenv("FORGE_FAST_MODEL", "gpt-4o-mini"),
            standard_model=os.getenv("FORGE_STANDARD_MODEL", "gpt-4o"),
            max_cost_per_task=float(os.getenv("FORGE_MAX_COST_PER_TASK", "0")),
            max_concurrent_tasks=int(os.getenv("FORGE_MAX_CONCURRENT_TASKS", "0")),
            cost_alert_threshold=float(os.getenv("FORGE_COST_ALERT_THRESHOLD", "0.8")),
            max_refinement_iterations=int(os.getenv("FORGE_MAX_REFINEMENTS", "10")),
            min_quality_score=float(os.getenv("FORGE_MIN_QUALITY", "0.8")),
            db_path=os.getenv("AGENCY_DB_PATH", "./data/agency_memory.db"),
            data_dir=os.getenv("AGENCY_DATA_DIR", "./data"),
            log_level=os.getenv("FORGE_LOG_LEVEL", "INFO"),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_pass=os.getenv("SMTP_PASS", ""),
            smtp_from=os.getenv("SMTP_FROM", ""),
            output_dir=os.getenv("FORGE_OUTPUT_DIR", "generated"),
        )

    def has_api_key(self) -> bool:
        """Check if an API key is configured."""
        return bool(self.api_key)

    def has_smtp(self) -> bool:
        """Check if SMTP is configured."""
        return bool(self.smtp_host)

    def to_dict(self) -> dict[str, Any]:
        """Export config as dict (redact sensitive values)."""
        d = {}
        for k, v in self.__dict__.items():
            if k in ("api_key", "smtp_pass"):
                d[k] = "***" if v else ""
            else:
                d[k] = v
        return d


# Global config singleton
_config: ForgeConfig | None = None


def get_config() -> ForgeConfig:
    """Get the global ForgeConfig (creates from env on first call)."""
    global _config
    if _config is None:
        _config = ForgeConfig.from_env()
    return _config


def reset_config() -> None:
    """Reset config (forces re-read from env on next get_config call)."""
    global _config
    _config = None
