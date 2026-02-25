"""Configuration management for the backend."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    websocket_port: int = 8765
    debug: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    shutdown_timeout: int = 10  # seconds


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3"
    model_path: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9
    top_k: int = 40
    system_prompt: str = "You are a helpful AI assistant."
    n_ctx: int = 4096
    n_threads: int = 8
    n_gpu_layers: int = 0
    n_batch: int = 512
    stop: list[str] = field(default_factory=lambda: ["<|im_start|>", "<|im_end|>"])


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


def _load_yaml_config(config: Config, config_dict: dict) -> None:
    """Apply YAML config dict to Config object, preserving nested structure."""
    if not config_dict:
        return

    # Server configuration
    if "server" in config_dict:
        server_dict = config_dict["server"]
        if "host" in server_dict:
            config.server.host = server_dict["host"]
        if "port" in server_dict:
            config.server.port = server_dict["port"]
        if "websocket_port" in server_dict:
            config.server.websocket_port = server_dict["websocket_port"]
        if "debug" in server_dict:
            config.server.debug = server_dict["debug"]
        if "cors_origins" in server_dict:
            config.server.cors_origins = server_dict["cors_origins"]
        if "shutdown_timeout" in server_dict:
            config.server.shutdown_timeout = server_dict["shutdown_timeout"]

    # LLM configuration
    if "llm" in config_dict:
        llm_dict = config_dict["llm"]
        if "provider" in llm_dict:
            config.llm.provider = llm_dict["provider"]
        if "base_url" in llm_dict:
            config.llm.base_url = llm_dict["base_url"]
        if "model" in llm_dict:
            config.llm.model = llm_dict["model"]
        if "model_path" in llm_dict:
            config.llm.model_path = llm_dict["model_path"]
        if "temperature" in llm_dict:
            config.llm.temperature = llm_dict["temperature"]
        if "max_tokens" in llm_dict:
            config.llm.max_tokens = llm_dict["max_tokens"]
        if "top_p" in llm_dict:
            config.llm.top_p = llm_dict["top_p"]
        if "top_k" in llm_dict:
            config.llm.top_k = llm_dict["top_k"]
        if "system_prompt" in llm_dict:
            config.llm.system_prompt = llm_dict["system_prompt"]
        if "n_ctx" in llm_dict:
            config.llm.n_ctx = llm_dict["n_ctx"]
        if "n_threads" in llm_dict:
            config.llm.n_threads = llm_dict["n_threads"]
        if "n_gpu_layers" in llm_dict:
            config.llm.n_gpu_layers = llm_dict["n_gpu_layers"]
        if "n_batch" in llm_dict:
            config.llm.n_batch = llm_dict["n_batch"]
        if "stop" in llm_dict:
            config.llm.stop = llm_dict["stop"]

    # Database configuration
    if "database" in config_dict:
        db_dict = config_dict["database"]
        if "path" in db_dict:
            config.database.path = Path(db_dict["path"])

    # Logging configuration
    if "logging" in config_dict:
        log_dict = config_dict["logging"]
        if "level" in log_dict:
            config.logging.level = log_dict["level"]
        if "format" in log_dict:
            config.logging.format = log_dict["format"]


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML files and environment variables.

    Configuration precedence (lowest to highest):
    1. Default values in dataclasses
    2. config/default.yaml
    3. config/development.yaml (if debug=True)
    4. Environment variables

    Args:
        config_path: Optional path to YAML config file (deprecated, uses config/ dir)

    Returns:
        Config object with all settings
    """
    config = Config()

    # Determine config directory
    if config_path is not None:
        config_dir = config_path.parent
    else:
        # Look for config directory relative to project root
        config_dir = Path(__file__).parent.parent / "config"

    # Load default.yaml
    default_config_path = config_dir / "default.yaml"
    if default_config_path.exists():
        try:
            with open(default_config_path, "r") as f:
                default_dict = yaml.safe_load(f)
                _load_yaml_config(config, default_dict or {})
        except Exception:
            pass  # Skip if YAML loading fails

    # Load development.yaml if debug mode is enabled
    dev_config_path = config_dir / "development.yaml"
    if dev_config_path.exists():
        try:
            with open(dev_config_path, "r") as f:
                dev_dict = yaml.safe_load(f)
                _load_yaml_config(config, dev_dict or {})
        except Exception:
            pass  # Skip if YAML loading fails

    # Apply environment variable overrides (highest precedence)
    # Server configuration
    config.server.host = os.environ.get("SERVER_HOST", config.server.host)
    config.server.port = _get_env_int("SERVER_PORT", config.server.port)
    config.server.websocket_port = _get_env_int("WEBSOCKET_PORT", config.server.websocket_port)
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
    config.llm.model_path = os.environ.get("LLM_MODEL_PATH", config.llm.model_path)
    config.llm.temperature = _get_env_float("LLM_TEMPERATURE", config.llm.temperature)
    config.llm.max_tokens = _get_env_int("LLM_MAX_TOKENS", config.llm.max_tokens)
    config.llm.top_p = _get_env_float("LLM_TOP_P", config.llm.top_p)
    config.llm.top_k = _get_env_int("LLM_TOP_K", config.llm.top_k)
    config.llm.system_prompt = os.environ.get(
        "LLM_SYSTEM_PROMPT", config.llm.system_prompt
    )
    config.llm.n_ctx = _get_env_int("LLM_N_CTX", config.llm.n_ctx)
    config.llm.n_threads = _get_env_int("LLM_N_THREADS", config.llm.n_threads)
    config.llm.n_gpu_layers = _get_env_int("LLM_N_GPU_LAYERS", config.llm.n_gpu_layers)
    config.llm.n_batch = _get_env_int("LLM_N_BATCH", config.llm.n_batch)
    config.llm.stop = _get_env_list("LLM_STOP", config.llm.stop)

    # Database configuration
    db_path = os.environ.get("DATABASE_PATH")
    if db_path:
        config.database.path = Path(db_path)

    # Logging configuration
    config.logging.level = os.environ.get("LOG_LEVEL", config.logging.level)

    return config