"""Unit tests for the context builder module."""
import pytest
from unittest.mock import Mock, MagicMock

from backend.context_builder import (
    ContextBuilder,
    ContextBuilderConfig,
    ConversationContext,
    Message,
    SummarizationStrategy,
    create_context_builder,
)
from backend.llm_adapter import LLMResponse


class TestMessage:
    """Tests for the Message dataclass."""

    def test_message_creation(self):
        """Test basic message creation."""
        msg = Message(role="user", content="Hello, world!")
        assert msg.role == "user"
        assert msg.content == "Hello, world!"
        assert msg.token_count == 0
        assert msg.attachments == []

    def test_message_with_attachments(self):
        """Test message with attachments."""
        attachments = [{"id": "123", "filename": "test.txt"}]
        msg = Message(
            role="user",
            content="See attached",
            token_count=10,
            attachments=attachments,
        )
        assert msg.token_count == 10
        assert len(msg.attachments) == 1

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = Message(role="assistant", content="Response", token_count=5)
        data = msg.to_dict()
        assert data["role"] == "assistant"
        assert data["content"] == "Response"
        assert data["token_count"] == 5

    def test_message_from_dict(self):
        """Test message deserialization."""
        data = {"role": "user", "content": "Test", "token_count": 3, "attachments": []}
        msg = Message.from_dict(data)
        assert msg.role == "user"
        assert msg.content == "Test"


class TestContextBuilderConfig:
    """Tests for ContextBuilderConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ContextBuilderConfig()
        assert config.max_context_tokens == 8192
        assert config.summarization_threshold == 0.8
        assert config.min_window_tokens == 1024
        assert config.strategy == SummarizationStrategy.SUMMARIZE_OLDER

    def test_custom_config(self):
        """Test custom configuration."""
        config = ContextBuilderConfig(
            max_context_tokens=4096,
            strategy=SummarizationStrategy.SLIDING_WINDOW,
            model_name="llama3",
        )
        assert config.max_context_tokens == 4096
        assert config.strategy == SummarizationStrategy.SLIDING_WINDOW


class TestContextBuilder:
    """Tests for the ContextBuilder class."""

    @pytest.fixture
    def mock_token_estimator(self):
        """Create a mock token estimator."""
        estimator = Mock()
        estimator.count_tokens = Mock(side_effect=lambda text, model: max(1, len(text) // 4))
        estimator.count_messages = Mock(return_value=0)
        return estimator

    @pytest.fixture
    def builder(self, mock_token_estimator):
        """Create a context builder with mock dependencies."""
        config = ContextBuilderConfig(
            max_context_tokens=100,
            strategy=SummarizationStrategy.SLIDING_WINDOW,
            model_name="test",
        )
        return ContextBuilder(
            config=config,
            token_estimator=mock_token_estimator,
        )

    @pytest.fixture
    def sample_messages(self):
        """Create sample messages for testing."""
        return [
            Message(role="user", content="Hello", token_count=5),
            Message(role="assistant", content="Hi there!", token_count=5),
            Message(role="user", content="How are you?", token_count=6),
            Message(role="assistant", content="I'm doing well, thanks!", token_count=8),
        ]

    def test_count_message_tokens_with_precomputed(self, builder):
        """Test counting tokens when message has precomputed count."""
        msg = Message(role="user", content="Test", token_count=10)
        assert builder.count_message_tokens(msg) == 10

    def test_count_message_tokens_without_precomputed(self, builder, mock_token_estimator):
        """Test counting tokens when message needs estimation."""
        msg = Message(role="user", content="Hello world test message")
        # Mock returns len(text) // 4 = 22 // 4 = 5 (min 1)
        # Plus role tokens + formatting
        count = builder.count_message_tokens(msg)
        assert count > 0

    def test_count_context_tokens_empty(self, builder):
        """Test counting tokens for empty context."""
        count = builder.count_context_tokens([], "You are a helpful assistant.")
        assert count > 0  # System prompt tokens

    def test_count_context_tokens_with_messages(self, builder, sample_messages):
        """Test counting tokens for context with messages."""
        count = builder.count_context_tokens(
            sample_messages, "You are a helpful assistant."
        )
        assert count > 0

    def test_build_context_within_limit(self, builder, sample_messages):
        """Test building context when within token limit."""
        # Use a high limit
        builder.config.max_context_tokens = 1000

        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        assert len(context.messages) == len(sample_messages)
        assert context.total_tokens <= 1000
        assert not context.is_summarized

    def test_build_context_exceeds_limit_sliding_window(self, builder, sample_messages):
        """Test sliding window when context exceeds limit."""
        # Set low limit
        builder.config.max_context_tokens = 30

        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        assert context.total_tokens <= 30
        # Should keep most recent messages
        assert len(context.messages) <= len(sample_messages)

    def test_build_context_exceeds_limit_truncate(self, builder, sample_messages):
        """Test truncation strategy when context exceeds limit."""
        builder.config.strategy = SummarizationStrategy.TRUNCATE
        builder.config.max_context_tokens = 25

        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        assert context.total_tokens <= 25

    def test_build_context_exceeds_limit_summarize(self, builder, sample_messages):
        """Test summarization strategy when context exceeds limit."""
        builder.config.strategy = SummarizationStrategy.SUMMARIZE_OLDER

        # Create a mock summarizer
        mock_summarizer = Mock()
        mock_summarizer.generate = Mock(return_value=LLMResponse(
            content="Summary of conversation",
            model="test",
            usage={},
        ))

        builder.set_summarizer(mock_summarizer)
        builder.config.max_context_tokens = 50

        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        # Should have summary + recent messages
        assert context.is_summarized
        assert context.total_tokens <= 50

    def test_build_context_no_messages(self, builder):
        """Test building context with no messages."""
        context = builder.build_context(
            [], "You are a helpful assistant."
        )

        assert len(context.messages) == 0
        assert context.system_prompt == "You are a helpful assistant."

    def test_build_chatml_messages(self, builder, sample_messages):
        """Test building ChatML message format."""
        builder.config.max_context_tokens = 1000
        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        messages = builder.build_chatml_messages(context)

        assert len(messages) > 0
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."

    def test_build_chatml_prompt(self, builder, sample_messages):
        """Test building complete ChatML prompt."""
        builder.config.max_context_tokens = 1000
        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        prompt = builder.build_chatml_prompt(context, "New question?")

        assert "<|im_start|>system" in prompt
        assert "<|im_start|>user" in prompt
        assert "<|im_start|>assistant" in prompt
        assert "New question?" in prompt

    def test_get_context_usage(self, builder, sample_messages):
        """Test getting context usage statistics."""
        builder.config.max_context_tokens = 100
        context = builder.build_context(
            sample_messages, "You are a helpful assistant."
        )

        usage = builder.get_context_usage(context)

        assert "total_tokens" in usage
        assert "max_tokens" in usage
        assert "usage_percent" in usage
        assert "message_count" in usage
        assert usage["max_tokens"] == 100

    def test_update_config(self, builder):
        """Test updating configuration."""
        builder.update_config(max_context_tokens=2048)
        assert builder.config.max_context_tokens == 2048

    def test_set_summarizer(self, builder):
        """Test setting the summarizer provider."""
        mock_summarizer = Mock()
        builder.set_summarizer(mock_summarizer)
        assert builder.summarizer == mock_summarizer


class TestConversationContext:
    """Tests for ConversationContext dataclass."""

    def test_context_creation(self):
        """Test context creation."""
        messages = [Message(role="user", content="Hi")]
        context = ConversationContext(
            messages=messages,
            system_prompt="You are helpful.",
            total_tokens=50,
            max_tokens=100,
        )

        assert len(context.messages) == 1
        assert context.total_tokens == 50
        assert context.max_tokens == 100
        assert not context.is_summarized

    def test_context_to_dict(self):
        """Test context serialization."""
        messages = [Message(role="user", content="Test")]
        context = ConversationContext(
            messages=messages,
            system_prompt="System",
            total_tokens=20,
            max_tokens=100,
        )

        data = context.to_dict()
        assert data["system_prompt"] == "System"
        assert data["total_tokens"] == 20
        assert len(data["messages"]) == 1


class TestCreateContextBuilder:
    """Tests for the factory function."""

    def test_create_with_defaults(self):
        """Test creating builder with default values."""
        builder = create_context_builder()
        assert builder.config.max_context_tokens == 8192
        assert builder.config.strategy == SummarizationStrategy.SUMMARIZE_OLDER

    def test_create_with_custom_values(self):
        """Test creating builder with custom values."""
        builder = create_context_builder(
            max_context_tokens=4096,
            strategy="sliding_window",
            model_name="llama3",
        )
        assert builder.config.max_context_tokens == 4096
        assert builder.config.strategy == SummarizationStrategy.SLIDING_WINDOW
        assert builder.config.model_name == "llama3"


class TestContextWindowCompliance:
    """Tests for Property 6: Context Window Compliance.

    For any conversation context sent to the LLM, the total token count
    should not exceed the configured maximum context window.
    """

    @pytest.fixture
    def mock_token_estimator(self):
        """Create a mock token estimator."""
        estimator = Mock()
        estimator.count_tokens = Mock(side_effect=lambda text, model: max(1, len(text) // 4))
        return estimator

    def test_never_exceeds_limit_sliding_window(self, mock_token_estimator):
        """Test that sliding window strategy never exceeds limit."""
        config = ContextBuilderConfig(
            max_context_tokens=50,
            strategy=SummarizationStrategy.SLIDING_WINDOW,
        )
        builder = ContextBuilder(config=config, token_estimator=mock_token_estimator)

        # Generate many messages
        messages = [
            Message(role="user", content=f"Message {i}", token_count=10)
            for i in range(100)
        ]

        context = builder.build_context(
            messages, "You are a helpful assistant."
        )

        assert context.total_tokens <= config.max_context_tokens, (
            f"Context exceeded limit: {context.total_tokens} > {config.max_context_tokens}"
        )

    def test_never_exceeds_limit_truncate(self, mock_token_estimator):
        """Test that truncate strategy never exceeds limit."""
        config = ContextBuilderConfig(
            max_context_tokens=40,
            strategy=SummarizationStrategy.TRUNCATE,
        )
        builder = ContextBuilder(config=config, token_estimator=mock_token_estimator)

        messages = [
            Message(role="user", content=f"Message {i}", token_count=10)
            for i in range(50)
        ]

        context = builder.build_context(
            messages, "You are a helpful assistant."
        )

        assert context.total_tokens <= config.max_context_tokens, (
            f"Context exceeded limit: {context.total_tokens} > {config.max_context_tokens}"
        )

    def test_never_exceeds_limit_summarize(self, mock_token_estimator):
        """Test that summarize strategy never exceeds limit."""
        config = ContextBuilderConfig(
            max_context_tokens=60,
            strategy=SummarizationStrategy.SUMMARIZE_OLDER,
        )
        builder = ContextBuilder(config=config, token_estimator=mock_token_estimator)

        # Mock summarizer
        mock_summarizer = Mock()
        mock_summarizer.generate = Mock(return_value=LLMResponse(
            content="Summary",
            model="test",
            usage={},
        ))
        builder.set_summarizer(mock_summarizer)

        messages = [
            Message(role="user", content=f"Message {i}", token_count=10)
            for i in range(50)
        ]

        context = builder.build_context(
            messages, "You are a helpful assistant."
        )

        assert context.total_tokens <= config.max_context_tokens, (
            f"Context exceeded limit: {context.total_tokens} > {config.max_context_tokens}"
        )

    def test_respects_max_tokens_override(self, mock_token_estimator):
        """Test that max_tokens parameter overrides config."""
        config = ContextBuilderConfig(max_context_tokens=1000)
        builder = ContextBuilder(config=config, token_estimator=mock_token_estimator)

        messages = [
            Message(role="user", content=f"Message {i}", token_count=50)
            for i in range(50)
        ]

        # Override max_tokens
        context = builder.build_context(
            messages, "You are a helpful assistant.", max_tokens=100
        )

        assert context.total_tokens <= 100, (
            f"Context exceeded override limit: {context.total_tokens} > 100"
        )

    def test_empty_context_respects_limit(self, mock_token_estimator):
        """Test that empty context respects token limit."""
        config = ContextBuilderConfig(max_context_tokens=10)
        builder = ContextBuilder(config=config, token_estimator=mock_token_estimator)

        context = builder.build_context(
            [], "You are a helpful assistant."
        )

        assert context.total_tokens <= config.max_context_tokens


if __name__ == "__main__":
    pytest.main([__file__, "-v"])