"""
LLM Provider Abstraction Layer

This module provides a unified interface for interacting with local LLM runtimes.
It wraps llama_cpp.Llama and provides a provider-agnostic response format.

Design follows Requirement 7.1: Abstraction layer supporting multiple LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, List, Dict, Any
from pathlib import Path
import threading
import time


# =============================================================================
# Response Dataclasses - Provider-agnostic response format
# =============================================================================

@dataclass
class LLMConfig:
    """Inference parameters for LLM generation."""
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 40
    stop_tokens: List[str] = field(default_factory=lambda: ["<|im_start|>", "<|im_end|>"])
    n_ctx: int = 4096
    n_batch: int = 512
    n_threads: int = 8
    n_gpu_layers: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for provider-specific parameters."""
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "stop": self.stop_tokens,
            "n_ctx": self.n_ctx,
            "n_batch": self.n_batch,
        }


@dataclass
class ModelInfo:
    """Model metadata for provider model listings."""
    id: str
    name: str
    size: Optional[int] = None
    parameters: Optional[str] = None
    quantization: Optional[str] = None
    context_length: int = 4096
    provider: str = "local"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "parameters": self.parameters,
            "quantization": self.quantization,
            "context_length": self.context_length,
            "provider": self.provider,
        }


@dataclass
class ProviderStatus:
    """Connection status for LLM provider."""
    connected: bool
    provider_name: str
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    model_loaded: bool = False
    model_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "provider": self.provider_name,
            "latency_ms": self.latency_ms,
            "error": self.error_message,
            "model_loaded": self.model_loaded,
            "model_name": self.model_name,
        }


@dataclass
class StreamToken:
    """Token for streaming responses."""
    text: str
    token_id: Optional[int] = None
    logprob: Optional[float] = None
    is_complete: bool = False
    finish_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "token_id": self.token_id,
            "logprob": self.logprob,
            "is_complete": self.is_complete,
            "finish_reason": self.finish_reason,
        }


@dataclass
class LLMResponse:
    """Normalized response from LLM generation."""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    response_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "response_time_ms": self.response_time_ms,
        }


# =============================================================================
# Abstract Base Class - LLM Provider Interface
# =============================================================================

class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    This interface defines the contract that all LLM providers must implement,
    enabling provider-agnostic code throughout the application.

    Methods:
        connect(): Initialize the provider connection
        generate(): Non-streaming response generation
        stream(): Streaming response generation (async iterator)
        cancel(): Cancel ongoing generation
        get_models(): List available models
        get_status(): Check provider availability
    """

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """Initialize the provider connection and load the model.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate a non-streaming response.

        Args:
            prompt: The user input prompt
            system_prompt: Optional system context
            config: Optional inference parameters

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[StreamToken]:
        """Generate a streaming response.

        Args:
            prompt: The user input prompt
            system_prompt: Optional system context
            config: Optional inference parameters

        Yields:
            StreamToken objects for each token generated
        """
        pass

    @abstractmethod
    def cancel(self) -> bool:
        """Cancel an ongoing generation.

        Returns:
            True if cancellation successful, False otherwise
        """
        pass

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        """List available models from the provider.

        Returns:
            List of ModelInfo objects
        """
        pass

    @abstractmethod
    def get_status(self) -> ProviderStatus:
        """Check provider connectivity and status.

        Returns:
            ProviderStatus with connection details
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up provider resources and close connections."""
        pass


# =============================================================================
# Local Model Provider - Wraps llama_cpp.Llama
# =============================================================================

class LocalModelProvider(LLMProvider):
    """
    LLM provider for local llama_cpp models.

    This provider wraps the llama_cpp.Llama class directly, providing
    a unified interface for local model inference.

    Example:
        provider = LocalModelProvider(
            model_path="~/.ollama/models/blobs/sha256-...",
            system_prompt="You are a helpful assistant."
        )
        provider.connect()
        response = provider.generate("Hello, how are you?")
        async for token in provider.stream("Tell me a story"):
            print(token.text, end="", flush=True)
        provider.disconnect()
    """

    def __init__(
        self,
        model_path: str,
        system_prompt: str = "You are a helpful AI assistant.",
        config: Optional[LLMConfig] = None
    ):
        """Initialize the local model provider.

        Args:
            model_path: Path to the GGUF model file
            system_prompt: Default system prompt for conversations
            config: Optional default inference configuration
        """
        self.model_path = Path(model_path).expanduser()
        self.system_prompt = system_prompt
        self.config = config or LLMConfig()

        # Internal state
        self._llm = None
        self._connected = False
        self._cancel_requested = False
        self._lock = threading.Lock()

    def connect(self, **kwargs) -> bool:
        """Initialize the llama_cpp model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        try:
            # Import here to allow graceful handling if llama_cpp not installed
            from llama_cpp import Llama

            # Get config values (allow override via kwargs)
            n_ctx = kwargs.get("n_ctx", self.config.n_ctx)
            n_threads = kwargs.get("n_threads", self.config.n_threads)
            n_gpu_layers = kwargs.get("n_gpu_layers", self.config.n_gpu_layers)
            n_batch = kwargs.get("n_batch", self.config.n_batch)

            # Initialize the llama_cpp model
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                n_batch=n_batch,
                verbose=False
            )

            self._connected = True
            return True

        except ImportError:
            raise ImportError(
                "llama_cpp package is required for LocalModelProvider. "
                "Install it with: pip install llama-cpp-python"
            )
        except Exception as e:
            self._connected = False
            raise RuntimeError(f"Failed to load model: {e}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate a non-streaming response.

        Args:
            prompt: The user input prompt
            system_prompt: Optional system context (overrides default)
            config: Optional inference parameters

        Returns:
            LLMResponse with generated content
        """
        if not self._connected or self._llm is None:
            raise RuntimeError("Provider not connected. Call connect() first.")

        cfg = config or self.config

        # If prompt is already ChatML-formatted, use it directly
        if prompt.startswith("<|im_start|>"):
            full_prompt = prompt
        else:
            system = system_prompt or self.system_prompt
            full_prompt = self._build_chatml_prompt(system, prompt)

        start_time = time.time()

        # Generate response
        response = self._llm(
            full_prompt,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            stop=cfg.stop_tokens,
            stream=False
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Extract content from response
        content = response["choices"][0]["text"]

        # Get finish reason
        finish_reason = response["choices"][0].get("finish_reason", None)

        return LLMResponse(
            content=content,
            model=self.model_path.name,
            usage={
                "prompt_tokens": response.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": response.get("usage", {}).get("completion_tokens", 0),
                "total_tokens": response.get("usage", {}).get("total_tokens", 0),
            },
            finish_reason=finish_reason,
            response_time_ms=response_time_ms,
        )

    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[StreamToken]:
        """Generate a streaming response.

        Args:
            prompt: The user input prompt
            system_prompt: Optional system context (overrides default)
            config: Optional inference parameters

        Yields:
            StreamToken objects for each token generated
        """
        if not self._connected or self._llm is None:
            raise RuntimeError("Provider not connected. Call connect() first.")

        cfg = config or self.config

        # If prompt is already ChatML-formatted, use it directly
        if prompt.startswith("<|im_start|>"):
            full_prompt = prompt
        else:
            system = system_prompt or self.system_prompt
            full_prompt = self._build_chatml_prompt(system, prompt)

        # Reset cancel flag
        self._cancel_requested = False

        # Start streaming generation
        stream = self._llm(
            full_prompt,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            stop=cfg.stop_tokens,
            stream=True
        )

        accumulated_content = ""
        token_id = 0

        for chunk in stream:
            # Check for cancellation
            if self._cancel_requested:
                break

            # Extract token from chunk
            text = chunk["choices"][0]["text"]
            token_id += 1

            accumulated_content += text

            # Check if this is the final chunk
            finish_reason = chunk["choices"][0].get("finish_reason", None)
            is_complete = finish_reason is not None

            yield StreamToken(
                text=text,
                token_id=token_id,
                logprob=chunk["choices"][0].get("logprob", None),
                is_complete=is_complete,
                finish_reason=finish_reason,
            )

        # Yield final completion signal
        if not self._cancel_requested:
            yield StreamToken(
                text="",
                token_id=token_id + 1,
                is_complete=True,
                finish_reason=finish_reason,
            )

    def cancel(self) -> bool:
        """Cancel an ongoing generation.

        Returns:
            True if cancellation flag set, False if no generation in progress
        """
        with self._lock:
            if self._llm is not None:
                self._cancel_requested = True
                return True
            return False

    def get_models(self) -> List[ModelInfo]:
        """List available models from the provider.

        For local models, returns info about the loaded model.

        Returns:
            List containing ModelInfo for the loaded model
        """
        if not self._connected:
            return []

        # Get model file size
        model_size = None
        if self.model_path.exists():
            model_size = self.model_path.stat().st_size

        return [
            ModelInfo(
                id=self.model_path.name,
                name=self.model_path.stem,
                size=model_size,
                context_length=self.config.n_ctx,
                provider="llama_cpp",
            )
        ]

    def get_status(self) -> ProviderStatus:
        """Check provider connectivity and status.

        Returns:
            ProviderStatus with connection details
        """
        start_time = time.time()

        try:
            # Test basic connectivity by checking if model is loaded
            if self._connected and self._llm is not None:
                latency_ms = int((time.time() - start_time) * 1000)
                return ProviderStatus(
                    connected=True,
                    provider_name="llama_cpp",
                    latency_ms=latency_ms,
                    model_loaded=True,
                    model_name=self.model_path.name,
                )
            else:
                return ProviderStatus(
                    connected=False,
                    provider_name="llama_cpp",
                    error_message="Model not loaded",
                    model_loaded=False,
                )
        except Exception as e:
            return ProviderStatus(
                connected=False,
                provider_name="llama_cpp",
                error_message=str(e),
                model_loaded=False,
            )

    def disconnect(self) -> None:
        """Clean up provider resources and close connections."""
        self._cancel_requested = False
        self._connected = False
        # Note: llama_cpp.Llama doesn't have an explicit close method
        # The object will be garbage collected
        self._llm = None

    # =============================================================================
    # Helper Methods
    # =============================================================================

    def _build_chatml_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Build ChatML formatted prompt.

        Args:
            system_prompt: System context
            user_prompt: User input

        Returns:
            Formatted prompt string
        """
        return (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    @property
    def is_connected(self) -> bool:
        """Check if provider is connected."""
        return self._connected and self._llm is not None


# =============================================================================
# Provider Factory
# =============================================================================

def create_local_provider(
    model_path: str,
    system_prompt: str = "You are a helpful AI assistant.",
    config: Optional[LLMConfig] = None
) -> LocalModelProvider:
    """Factory function to create a local model provider.

    Args:
        model_path: Path to the GGUF model file
        system_prompt: Default system prompt
        config: Optional inference configuration

    Returns:
        Configured LocalModelProvider instance
    """
    return LocalModelProvider(
        model_path=model_path,
        system_prompt=system_prompt,
        config=config,
    )