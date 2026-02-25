"""
Context Builder for Conversation Context Construction

This module constructs conversation context windows for LLM requests.
It implements token counting using the tiktoken library, applies the
configured context window size limit, and implements intelligent
summarization when approaching token limits.

Design follows Requirements 6.2, 6.3 and Property 6 (Context Window Compliance).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

from .token_estimator import TokenEstimator
from .llm_adapter import LLMProvider, LLMConfig, LocalModelProvider

logger = logging.getLogger(__name__)


@dataclass
class ContextBuilderConfig:
    """Configuration for context building behavior."""
    # Maximum tokens in the context window
    max_context_tokens: int = 8192
    # Percentage of context window at which to trigger summarization
    summarization_threshold: float = 0.80
    # Minimum tokens to preserve when summarizing
    min_preserved_tokens: int = 1024
    # Maximum number of messages to keep before summarization
    max_messages_before_summary: int = 20
    # Whether to use summarization when approaching limits
    enable_summarization: bool = True
    # Model to use for summarization
    summarization_model: str = "default"
    # Number of tokens to reserve for the response
    response_reserve_tokens: int = 1024


@dataclass
class Message:
    """A conversation message."""
    role: str  # 'system', 'user', 'assistant'
    content: str
    token_count: int = 0
    created_at: float = 0.0
    attachments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "token_count": self.token_count,
            "created_at": self.created_at,
            "attachments": self.attachments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            token_count=data.get("token_count", 0),
            created_at=data.get("created_at", 0.0),
            attachments=data.get("attachments", []),
        )


@dataclass
class ConversationContext:
    """A constructed conversation context for LLM requests."""
    messages: List[Message]
    total_tokens: int
    max_tokens: int
    was_summarized: bool = False
    summary: Optional[str] = None

    @property
    def is_within_limit(self) -> bool:
        """Check if context is within token limit."""
        return self.total_tokens <= self.max_tokens

    @property
    def usage_percentage(self) -> float:
        """Get context usage as a percentage."""
        if self.max_tokens == 0:
            return 0.0
        return (self.total_tokens / self.max_tokens) * 100


class SummarizationResult:
    """Result of a summarization operation."""

    def __init__(
        self,
        success: bool,
        summary: Optional[str] = None,
        original_tokens: int = 0,
        summarized_tokens: int = 0,
        error: Optional[str] = None,
    ):
        self.success = success
        self.summary = summary
        self.original_tokens = original_tokens
        self.summarized_tokens = summarized_tokens
        self.error = error

    @property
    def compression_ratio(self) -> float:
        """Get the compression ratio of the summarization."""
        if self.original_tokens == 0:
            return 0.0
        return self.summarized_tokens / self.original_tokens


class ContextBuilder:
    """
    Constructs conversation context windows for LLM requests.

    This class manages the conversation context by:
    1. Counting tokens using the token_estimator
    2. Applying sliding window to keep most recent messages
    3. Implementing intelligent summarization when approaching limits

    Example:
        builder = ContextBuilder(
            config=ContextBuilderConfig(max_context_tokens=8192),
            token_estimator=TokenEstimator()
        )
        context = builder.build_context(messages, system_prompt)
    """

    # ChatML template components for formatting
    CHATML_ROLES = {
        "system": "<|im_start|>system\n{content}<|im_end|>\n",
        "user": "<|im_start|>user\n{content}<|im_end|>\n",
        "assistant": "<|im_start|>assistant\n{content}<|im_end|>\n",
    }

    def __init__(
        self,
        config: Optional[ContextBuilderConfig] = None,
        token_estimator: Optional[TokenEstimator] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        """Initialize the context builder.

        Args:
            config: Optional configuration for context building
            token_estimator: Optional token estimator instance
            llm_provider: Optional LLM provider for summarization
        """
        self.config = config or ContextBuilderConfig()
        self.token_estimator = token_estimator or TokenEstimator()
        self._llm_provider = llm_provider
        self._summarization_cache: Dict[str, str] = {}

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """Set the LLM provider for summarization.

        Args:
            provider: The LLM provider to use
        """
        self._llm_provider = provider

    def count_message_tokens(self, message: Message, model: str = "default") -> int:
        """Count tokens for a single message including formatting.

        Args:
            message: The message to count
            model: The model for encoding selection

        Returns:
            Token count including ChatML formatting
        """
        # Count the content tokens
        content_tokens = self.token_estimator.count_tokens(
            message.content, model
        )

        # Add formatting tokens for ChatML
        # Format: <|im_start|>role\ncontent<|im_end|>\n
        format_tokens = 3  # <|im_start|>, \n, <|im_end|>
        role_tokens = self.token_estimator.count_tokens(message.role, model)

        return content_tokens + role_tokens + format_tokens

    def count_context_tokens(
        self, messages: List[Message], system_prompt: Optional[str] = None
    ) -> int:
        """Count total tokens for a list of messages.

        Args:
            messages: List of messages to count
            system_prompt: Optional system prompt to include

        Returns:
            Total token count
        """
        total = 0

        # Count system prompt tokens
        if system_prompt:
            total += self.token_estimator.count_tokens(system_prompt)
            total += 3  # System message formatting

        # Count each message
        for message in messages:
            total += self.count_message_tokens(message)

        return total

    def build_context(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        model: str = "default",
    ) -> ConversationContext:
        """Build a conversation context within token limits.

        This method:
        1. Calculates total tokens for all messages
        2. If within limit, returns all messages
        3. If approaching limit, applies sliding window
        4. If still over limit, uses summarization

        Args:
            messages: List of conversation messages (oldest to newest)
            system_prompt: Optional system prompt to include
            model: The model for token encoding

        Returns:
            ConversationContext with appropriate messages
        """
        max_tokens = self.config.max_context_tokens - self.config.response_reserve_tokens

        # Count current tokens
        total_tokens = self.count_context_tokens(messages, system_prompt)

        # If within limit, return all messages
        if total_tokens <= max_tokens:
            return ConversationContext(
                messages=messages,
                total_tokens=total_tokens,
                max_tokens=max_tokens,
                was_summarized=False,
            )

        # Apply sliding window to keep most recent messages
        windowed_messages = self._apply_sliding_window(messages, max_tokens, system_prompt, model)

        # Recount tokens after sliding window
        total_tokens = self.count_context_tokens(windowed_messages, system_prompt)

        # If still over limit and summarization is enabled, summarize
        if total_tokens > max_tokens and self.config.enable_summarization:
            return self._build_with_summarization(
                messages, system_prompt, model, max_tokens
            )

        return ConversationContext(
            messages=windowed_messages,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            was_summarized=False,
        )

    def _apply_sliding_window(
        self,
        messages: List[Message],
        max_tokens: int,
        system_prompt: Optional[str],
        model: str,
    ) -> List[Message]:
        """Apply sliding window to keep most recent messages within limit.

        Args:
            messages: All messages (oldest to newest)
            max_tokens: Maximum tokens allowed
            system_prompt: Optional system prompt
            model: Model for token encoding

        Returns:
            Subset of messages that fit within limit
        """
        # Reserve tokens for system prompt
        system_tokens = 0
        if system_prompt:
            system_tokens = self.token_estimator.count_tokens(system_prompt) + 3

        available_tokens = max_tokens - system_tokens

        # Start from the newest messages and work backwards
        result: List[Message] = []
        current_tokens = 0

        # Process messages in reverse (newest first)
        for message in reversed(messages):
            message_tokens = self.count_message_tokens(message, model)

            if current_tokens + message_tokens <= available_tokens:
                # Add to the beginning (older in conversation)
                result.insert(0, message)
                current_tokens += message_tokens
            else:
                # Stop once we can't fit more messages
                break

        # If we have too many messages, limit to the most recent ones
        if len(result) > self.config.max_messages_before_summary:
            result = result[-self.config.max_messages_before_summary:]

        logger.debug(
            f"Sliding window: kept {len(result)} messages, "
            f"{current_tokens} tokens (limit: {available_tokens})"
        )

        return result

    def _build_with_summarization(
        self,
        messages: List[Message],
        system_prompt: Optional[str],
        model: str,
        max_tokens: int,
    ) -> ConversationContext:
        """Build context with summarization of older messages.

        Args:
            messages: All messages (oldest to newest)
            system_prompt: Optional system prompt
            model: Model for token encoding
            max_tokens: Maximum tokens allowed

        Returns:
            ConversationContext with summarized older messages
        """
        # Reserve tokens for system prompt and summary
        system_tokens = 0
        if system_prompt:
            system_tokens = self.token_estimator.count_tokens(system_prompt) + 3

        # Reserve tokens for the summary
        summary_reserve = self.config.min_preserved_tokens

        available_tokens = max_tokens - system_tokens - summary_reserve

        # Keep the most recent messages that fit
        recent_messages: List[Message] = []
        recent_tokens = 0

        for message in reversed(messages):
            message_tokens = self.count_message_tokens(message, model)

            if recent_tokens + message_tokens <= available_tokens:
                recent_messages.insert(0, message)
                recent_tokens += message_tokens
            else:
                break

        # Summarize the older messages
        older_messages = [m for m in messages if m not in recent_messages]

        summary = None
        was_summarized = False

        if older_messages and self._llm_provider is not None:
            summary_result = self._summarize_messages(older_messages, system_prompt)

            if summary_result.success and summary_result.summary:
                summary = summary_result.summary
                was_summarized = True

                # Calculate summary tokens
                summary_tokens = self.token_estimator.count_tokens(
                    summary_result.summary, model
                ) + 3  # Formatting tokens

                # Adjust if summary is too large
                if system_tokens + summary_tokens + recent_tokens > max_tokens:
                    # Reduce recent messages to fit summary
                    target_recent = max_tokens - system_tokens - summary_tokens
                    recent_messages = self._trim_to_tokens(
                        recent_messages, target_recent, model
                    )
                    recent_tokens = self.count_context_tokens(
                        recent_messages, None
                    )

        # Build final context
        final_messages = recent_messages
        if summary:
            # Add summary as a system message
            summary_message = Message(
                role="system",
                content=f"Previous conversation summary: {summary}",
                token_count=self.token_estimator.count_tokens(
                    summary, model
                ) + 3,
            )
            final_messages = [summary_message] + recent_messages

        total_tokens = self.count_context_tokens(final_messages, system_prompt)

        logger.info(
            f"Context with summarization: {len(final_messages)} messages, "
            f"{total_tokens} tokens (limit: {max_tokens})"
        )

        return ConversationContext(
            messages=final_messages,
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            was_summarized=was_summarized,
            summary=summary,
        )

    def _trim_to_tokens(
        self,
        messages: List[Message],
        max_tokens: int,
        model: str,
    ) -> List[Message]:
        """Trim messages to fit within token limit.

        Args:
            messages: Messages to trim (newest first)
            max_tokens: Maximum tokens allowed
            model: Model for token encoding

        Returns:
            Trimmed list of messages
        """
        result: List[Message] = []
        current_tokens = 0

        for message in messages:
            message_tokens = self.count_message_tokens(message, model)

            if current_tokens + message_tokens <= max_tokens:
                result.append(message)
                current_tokens += message_tokens
            else:
                break

        return result

    def _summarize_messages(
        self,
        messages: List[Message],
        system_prompt: Optional[str],
    ) -> SummarizationResult:
        """Summarize a list of older messages using the LLM.

        Args:
            messages: Messages to summarize (oldest first)
            system_prompt: Optional system prompt for context

        Returns:
            SummarizationResult with the summary
        """
        if not messages:
            return SummarizationResult(success=True, summary="", original_tokens=0, summarized_tokens=0)

        # Check cache for this set of messages
        cache_key = self._get_cache_key(messages)
        if cache_key in self._summarization_cache:
            cached = self._summarization_cache[cache_key]
            return SummarizationResult(
                success=True,
                summary=cached,
                original_tokens=self.count_context_tokens(messages, None),
                summarized_tokens=self.token_estimator.count_tokens(cached),
            )

        if self._llm_provider is None:
            logger.warning("No LLM provider set, cannot summarize")
            return SummarizationResult(
                success=False,
                error="No LLM provider configured for summarization",
                original_tokens=self.count_context_tokens(messages, None),
                summarized_tokens=0,
            )

        try:
            # Build the summarization prompt
            conversation_text = self._format_messages_for_summary(messages)

            summarization_prompt = (
                "Please summarize the following conversation history. "
                "Focus on:\n"
                "1. Key topics discussed\n"
                "2. Important decisions or conclusions\n"
                "3. Any constraints or preferences mentioned\n\n"
                "Keep the summary concise but comprehensive enough to maintain "
                "context for future conversation.\n\n"
                f"Conversation to summarize:\n{conversation_text}"
            )

            # Use a minimal config for summarization
            summary_config = LLMConfig(
                max_tokens=self.config.min_preserved_tokens,
                temperature=0.3,  # Lower temperature for consistent summaries
            )

            # Generate summary
            response = self._llm_provider.generate(
                prompt=summarization_prompt,
                system_prompt=system_prompt or "You are a helpful assistant that summarizes conversations.",
                config=summary_config,
            )

            summary = response.content.strip()

            # Cache the result
            self._summarization_cache[cache_key] = summary

            original_tokens = self.count_context_tokens(messages, None)
            summarized_tokens = self.token_estimator.count_tokens(summary)

            logger.info(
                f"Summarized {len(messages)} messages: "
                f"{original_tokens} -> {summarized_tokens} tokens "
                f"({summarized_tokens/original_tokens*100:.1f}%)"
            )

            return SummarizationResult(
                success=True,
                summary=summary,
                original_tokens=original_tokens,
                summarized_tokens=summarized_tokens,
            )

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return SummarizationResult(
                success=False,
                error=str(e),
                original_tokens=self.count_context_tokens(messages, None),
                summarized_tokens=0,
            )

    def _format_messages_for_summary(self, messages: List[Message]) -> str:
        """Format messages for summarization prompt.

        Args:
            messages: Messages to format

        Returns:
            Formatted text for summarization
        """
        lines = []
        for msg in messages:
            role = msg.role.upper()
            content = msg.content[:500] if len(msg.content) > 500 else msg.content
            lines.append(f"[{role}]: {content}")

        return "\n".join(lines)

    def _get_cache_key(self, messages: List[Message]) -> str:
        """Generate a cache key for a set of messages.

        Args:
            messages: Messages to generate key for

        Returns:
            Cache key string
        """
        # Use message IDs and content hashes for cache key
        import hashlib

        content = "".join(
            f"{m.id or m.role}:{m.content[:100]}"
            for m in messages
        )
        return hashlib.md5(content.encode()).hexdigest()

    def format_for_llm(
        self,
        context: ConversationContext,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Format a conversation context as a ChatML prompt string.

        Args:
            context: The conversation context
            system_prompt: Optional system prompt to include

        Returns:
            Formatted prompt string ready for LLM
        """
        parts = []

        # Add system prompt
        if system_prompt:
            parts.append(self.CHATML_ROLES["system"].format(content=system_prompt))

        # Add summary as system message if present
        if context.summary:
            parts.append(
                self.CHATML_ROLES["system"].format(
                    content=f"Previous conversation summary: {context.summary}"
                )
            )

        # Add all messages
        for message in context.messages:
            role = message.role if message.role in self.CHATML_ROLES else "assistant"
            parts.append(self.CHATML_ROLES[role].format(content=message.content))

        # Add assistant start token
        parts.append("<|im_start|>assistant\n")

        return "".join(parts)

    def clear_cache(self) -> None:
        """Clear the summarization cache."""
        self._summarization_cache.clear()
        logger.info("Context builder cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the context builder.

        Returns:
            Dictionary with builder statistics
        """
        return {
            "config": {
                "max_context_tokens": self.config.max_context_tokens,
                "summarization_threshold": self.config.summarization_threshold,
                "min_preserved_tokens": self.config.min_preserved_tokens,
                "enable_summarization": self.config.enable_summarization,
            },
            "cache_size": len(self._summarization_cache),
        }


def create_context_builder(
    max_context_tokens: int = 8192,
    enable_summarization: bool = True,
    token_estimator: Optional[TokenEstimator] = None,
    llm_provider: Optional[LLMProvider] = None,
) -> ContextBuilder:
    """Factory function to create a configured context builder.

    Args:
        max_context_tokens: Maximum tokens in context window
        enable_summarization: Whether to use summarization
        token_estimator: Optional token estimator instance
        llm_provider: Optional LLM provider for summarization

    Returns:
        Configured ContextBuilder instance
    """
    config = ContextBuilderConfig(
        max_context_tokens=max_context_tokens,
        enable_summarization=enable_summarization,
    )

    return ContextBuilder(
        config=config,
        token_estimator=token_estimator,
        llm_provider=llm_provider,
    )