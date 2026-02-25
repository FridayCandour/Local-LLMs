"""Token estimation utilities for context window management.

Uses a simple heuristic-based approach (~4 chars per token) instead of tiktoken,
which avoids the Rust build dependency and works on all Python versions.
For local llama_cpp models, exact token counts aren't critical — the model
itself handles tokenization. This estimator is used only for context window
budgeting.
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Average characters per token for English text with common LLM tokenizers.
# GPT/Llama-family models average ~3.5-4.5 chars per token.
_CHARS_PER_TOKEN = 4.0


@dataclass
class TokenEstimatorConfig:
    """Configuration for the token estimator."""
    chars_per_token: float = _CHARS_PER_TOKEN
    safety_margin: float = 0.05


class TokenEstimator:
    """Provides approximate token counting for context window management.

    Uses a character-ratio heuristic rather than a real tokenizer.
    This is sufficient for sliding-window context building where
    the LLM itself performs actual tokenization at inference time.
    """

    def __init__(self, config: Optional[TokenEstimatorConfig] = None):
        self.config = config or TokenEstimatorConfig()

    def count_tokens(self, text: str, model: str = "default") -> int:
        """Estimate token count for a text string."""
        if not text:
            return 0
        return max(1, int(len(text) / self.config.chars_per_token + 0.5))

    def count_messages(self, messages: list[dict[str, str]], model: str = "default") -> int:
        """Estimate tokens for a list of chat messages including formatting overhead."""
        if not messages:
            return 0
        total = 0
        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            total += 3  # formatting tokens per message
            total += self.count_tokens(role, model)
            total += self.count_tokens(content, model)
        total += 3  # final separator
        return total

    def count_file_content(self, content: str, file_type: str = "text", model: str = "default") -> int:
        """Estimate tokens for file content."""
        if not content:
            return 0
        base = self.count_tokens(content, model)
        if file_type in ("code", "python", "javascript", "rust", "go"):
            return int(base * 1.05)
        elif file_type == "json":
            return int(base * 1.02)
        return base

    def estimate_tokens_for_limit(self, text: str, max_tokens: int, model: str = "default") -> tuple[int, bool]:
        """Estimate tokens and check if within limit."""
        count = self.count_tokens(text, model)
        return count, count <= max_tokens

    def get_encoding_for_model(self, model: str) -> str:
        """Return encoding name (kept for API compatibility)."""
        return "heuristic"

    def clear_cache(self) -> None:
        """No-op (kept for API compatibility)."""
        pass

    def close(self) -> None:
        """No-op (kept for API compatibility)."""
        pass


def count_tokens(text: str, model: str = "default") -> int:
    """Module-level convenience function."""
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN + 0.5))


def count_message_tokens(role: str, content: str, model: str = "default") -> int:
    """Count tokens for a single message."""
    if not content:
        return 0
    tokens = 3
    tokens += count_tokens(role, model)
    tokens += count_tokens(content, model)
    return tokens
