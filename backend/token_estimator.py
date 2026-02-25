"""Token estimation utilities using tiktoken for accurate token counting."""
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import tiktoken

logger = logging.getLogger(__name__)


# Mapping of model names to their tiktoken encoding names
MODEL_ENCODING_MAP: dict[str, str] = {
    # OpenAI models
    "gpt-4": "cl100k_base",
    "gpt-4-32k": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5-turbo-16k": "cl100k_base",
    # Anthropic models (use cl100k_base as approximation)
    "claude": "cl100k_base",
    "claude-2": "cl100k_base",
    # Meta/Llama models
    "llama3": "cl100k_base",
    "llama2": "llama2",
    "llama2-70b": "llama2",
    # Mistral models
    "mistral": "cl100k_base",
    "mixtral": "cl100k_base",
    # Generic fallbacks
    "default": "cl100k_base",
}


@dataclass
class TokenEstimatorConfig:
    """Configuration for the token estimator."""
    # Default encoding to use when model is not in the mapping
    default_encoding: str = "cl100k_base"
    # Cache size for encoding models (number of different encodings to cache)
    cache_size: int = 8
    # Safety margin for token estimation (percentage)
    safety_margin: float = 0.05


class TokenEstimator:
    """Provides accurate token counting for various text inputs using tiktoken.

    This class supports different encodings for different LLM models and
    caches encoding models for performance.
    """

    def __init__(self, config: Optional[TokenEstimatorConfig] = None):
        """Initialize the token estimator.

        Args:
            config: Optional configuration for the estimator
        """
        self.config = config or TokenEstimatorConfig()
        self._encoding_cache: dict[str, tiktoken.Encoding] = {}

    def _get_encoding(self, encoding_name: str) -> tiktoken.Encoding:
        """Get or create an encoding model with caching.

        Args:
            encoding_name: The name of the encoding to use

        Returns:
            The tiktoken Encoding object
        """
        if encoding_name not in self._encoding_cache:
            try:
                self._encoding_cache[encoding_name] = tiktoken.get_encoding(
                    encoding_name
                )
            except ValueError:
                logger.warning(
                    f"Encoding '{encoding_name}' not found, falling back to 'cl100k_base'"
                )
                self._encoding_cache[encoding_name] = tiktoken.get_encoding(
                    "cl100k_base"
                )
        return self._encoding_cache[encoding_name]

    def _get_encoding_for_model(self, model: str) -> str:
        """Get the appropriate encoding name for a given model.

        Args:
            model: The model name

        Returns:
            The encoding name to use
        """
        # Check for exact match
        if model in MODEL_ENCODING_MAP:
            return MODEL_ENCODING_MAP[model]

        # Check for partial match (e.g., "llama3.1" matches "llama3")
        for known_model, encoding in MODEL_ENCODING_MAP.items():
            if known_model in model.lower() or model.lower() in known_model:
                return encoding

        # Fall back to default
        return self.config.default_encoding

    def count_tokens(self, text: str, model: str = "default") -> int:
        """Count the number of tokens in a text string.

        Args:
            text: The text to count tokens for
            model: The model name to use for encoding selection

        Returns:
            The estimated token count
        """
        if not text:
            return 0

        encoding_name = self._get_encoding_for_model(model)
        encoding = self._get_encoding(encoding_name)

        # Encode the text and count tokens
        tokens = encoding.encode(text)
        return len(tokens)

    def count_messages(
        self, messages: list[dict[str, str]], model: str = "default"
    ) -> int:
        """Count tokens for a list of messages in conversational format.

        This accounts for the formatting tokens that LLMs typically expect
        for chat messages.

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            model: The model name to use for encoding selection

        Returns:
            The estimated token count including message formatting
        """
        if not messages:
            return 0

        encoding_name = self.get_encoding_for_model(model)
        encoding = self._get_encoding(encoding_name)

        total_tokens = 0

        for message in messages:
            # Count tokens in the role
            role = message.get("role", "")
            content = message.get("content", "")

            # Add tokens for role formatting (approximate)
            # Most chat formats use: <|role|>\ncontent\n<|end|>
            total_tokens += 3  # Formatting tokens

            # Count role tokens
            if role:
                total_tokens += len(encoding.encode(role))

            # Count content tokens
            if content:
                total_tokens += len(encoding.encode(content))

        # Add tokens for message separators (between messages)
        total_tokens += 3  # Final formatting tokens

        return total_tokens

    def count_file_content(
        self, content: str, file_type: str = "text", model: str = "default"
    ) -> int:
        """Count tokens for file content with type-specific adjustments.

        Args:
            content: The file content to count
            file_type: The type of file (text, markdown, json, code, etc.)
            model: The model name to use for encoding selection

        Returns:
            The estimated token count
        """
        if not content:
            return 0

        # For most file types, use standard token counting
        # Some file types might have different token density
        base_count = self.count_tokens(content, model)

        # Apply type-specific adjustments
        # Code files often have more tokens per character due to punctuation
        if file_type in ("code", "python", "javascript", "rust", "go"):
            # Add small overhead for code
            return int(base_count * 1.05)
        elif file_type == "json":
            # JSON can be token-heavy due to punctuation
            return int(base_count * 1.02)

        return base_count

    def estimate_tokens_for_limit(
        self, text: str, max_tokens: int, model: str = "default"
    ) -> tuple[int, bool]:
        """Estimate tokens and check if within limit.

        Args:
            text: The text to check
            max_tokens: The maximum token limit
            model: The model name to use for encoding selection

        Returns:
            Tuple of (token_count, is_within_limit)
        """
        count = self.count_tokens(text, model)
        return count, count <= max_tokens

    def get_encoding_for_model(self, model: str) -> str:
        """Get the encoding name for a given model.

        Args:
            model: The model name

        Returns:
            The encoding name
        """
        return self._get_encoding_for_model(model)

    def clear_cache(self) -> None:
        """Clear the encoding model cache."""
        self._encoding_cache.clear()
        logger.info("Token estimator cache cleared")

    def close(self) -> None:
        """Clean up resources and release encoding models."""
        self.clear_cache()


@lru_cache(maxsize=8)
def get_encoding(encoding_name: str) -> tiktoken.Encoding:
    """Get a cached tiktoken encoding.

    This is a module-level convenience function that uses LRU caching.

    Args:
        encoding_name: The name of the encoding

    Returns:
        The tiktoken Encoding object
    """
    try:
        return tiktoken.get_encoding(encoding_name)
    except ValueError:
        logger.warning(f"Encoding '{encoding_name}' not found, using 'cl100k_base'")
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "default") -> int:
    """Count tokens in a text string.

    This is a convenience function for simple token counting.

    Args:
        text: The text to count tokens for
        model: The model name for encoding selection

    Returns:
        The estimated token count
    """
    if not text:
        return 0

    encoding_name = _get_encoding_for_model_global(model)
    encoding = get_encoding(encoding_name)
    return len(encoding.encode(text))


def count_message_tokens(
    role: str, content: str, model: str = "default"
) -> int:
    """Count tokens for a single message.

    Args:
        role: The message role (user, assistant, system)
        content: The message content
        model: The model name for encoding selection

    Returns:
        The estimated token count including formatting
    """
    if not content:
        return 0

    encoding_name = _get_encoding_for_model_global(model)
    encoding = get_encoding(encoding_name)

    # Approximate formatting tokens
    tokens = 3  # Role and content markers
    tokens += len(encoding.encode(role))
    tokens += len(encoding.encode(content))

    return tokens


def _get_encoding_for_model_global(model: str) -> str:
    """Get the encoding name for a model (module-level helper)."""
    if model in MODEL_ENCODING_MAP:
        return MODEL_ENCODING_MAP[model]

    for known_model, encoding in MODEL_ENCODING_MAP.items():
        if known_model in model.lower() or model.lower() in known_model:
            return encoding

    return "cl100k_base"