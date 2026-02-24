"""Configuration management for the backend."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    shutdown_timeout: int = 10  # seconds


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9
    top_k: int = 40
    system_prompt: str = "You are a helpful AI assistant."


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: Path = Path("data/chat.db")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    """Main configuration container."""
    server: ServerConfig = field(default_factory=ServerConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _get_env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes")


def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_env_list(key: str, default: list[str]) -> list[str]:
    """Get list from environment variable (comma-separated)."""
    value = os.environ.get(key)
    if value is None:
        return default
    return [v.strip() for v in value.split(",") if v.strip()]


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from environment variables and optional config file.

    Args:
        config_path: Optional path to YAML config file

    Returns:
        Config object with all settings
    """
    config = Config()

    # Server configuration
    config.server.host = os.environ.get("SERVER_HOST", config.server.host)
    config.server.port = _get_env_int("SERVER_PORT", config.server.port)
    config.server.debug = _get_env_bool("SERVER_DEBUG", config.server.debug)
    config.server.cors_origins = _get_env_list(
        "CORS_ORIGINS", config.server.cors_origins
    )
    config.server.shutdown_timeout = _get_env_int(
        "SHUTDOWN_TIMEOUT", config.server.shutdown_timeout
    )

    # LLM configuration
    config.llm.provider = os.environ.get("LLM_PROVIDER", config.llm.provider)
    config.llm.base_url = os.environ.get("LLM_BASE_URL", config.llm.base_url)
    config.llm.model = os.environ.get("LLM_MODEL", config.llm.model)
    config.llm.temperature = _get_env_float("LLM_TEMPERATURE", config.llm.temperature)
    config.llm.max_tokens = _get_env_int("LLM_MAX_TOKENS", config.llm.max_tokens)
    config.llm.top_p = _get_env_float("LLM_TOP_P", config.llm.top_p)
    config.llm.top_k = _get_env_int("LLM_TOP_K", config.llm.top_k)
    config.llm.system_prompt = os.environ.get(
        "LLM_SYSTEM_PROMPT", config.llm.system_prompt
    )

    # Database configuration
    db_path = os.environ.get("DATABASE_PATH")
    if db_path:
        config.database.path = Path(db_path)

    # Logging configuration
    config.logging.level = os.environ.get("LOG_LEVEL", config.logging.level)

    return config