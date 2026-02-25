"""Request Handlers for Local LLM Chat Interface API.

This module implements HTTP request handlers for all API endpoints.
Handlers use dataclasses for request/response objects and implement
consistent error handling with JSON error responses.

Design follows Requirements 14.7, 14.6.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from http.server import BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
import hashlib
import uuid

from .config import load_config
from .database import (
    Session, Message, Attachment,
    create_session, get_session, get_all_sessions, update_session, delete_session,
    create_message, get_messages, get_message, update_message, delete_message,
    create_attachment, get_attachment, get_attachments_for_message, delete_attachment,
    init_db
)
from .llm_adapter import (
    LLMProvider, LLMConfig, ModelInfo, ProviderStatus, LLMResponse,
    LocalModelProvider, create_local_provider
)
from .context_builder import ContextBuilder, Message as ContextMessage, ConversationContext
from .token_estimator import TokenEstimator
from .file_parser import FileParser

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class ErrorResponse:
    """Standard error response format."""
    error: str
    message: str
    code: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionCreateRequest:
    """Request body for creating a session."""
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "SessionCreateRequest":
        return cls(
            name=data.get("name"),
            system_prompt=data.get("system_prompt"),
            llm_config=data.get("llm_config"),
        )


@dataclass
class SessionResponse:
    """Response for session operations."""
    id: str
    name: Optional[str]
    created_at: Optional[float]
    updated_at: Optional[float]
    system_prompt: Optional[str]
    llm_config: Optional[Dict[str, Any]]
    message_count: int = 0

    @classmethod
    def from_session(cls, session: Session, message_count: int = 0) -> "SessionResponse":
        config_dict = None
        if session.llm_config:
            try:
                config_dict = json.loads(session.llm_config)
            except json.JSONDecodeError:
                pass
        return cls(
            id=session.id,
            name=session.name,
            created_at=session.created_at,
            updated_at=session.updated_at,
            system_prompt=session.system_prompt,
            llm_config=config_dict,
            message_count=message_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionListResponse:
    """Response for listing sessions."""
    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessions": [s.to_dict() for s in self.sessions],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass
class MessageCreateRequest:
    """Request body for creating a message."""
    content: str
    role: str = "user"
    attachments: Optional[List[str]] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "MessageCreateRequest":
        return cls(
            content=data.get("content", ""),
            role=data.get("role", "user"),
            attachments=data.get("attachments"),
        )


@dataclass
class MessageResponse:
    """Response for message operations."""
    id: str
    session_id: str
    role: str
    content: Optional[str]
    token_count: Optional[int]
    attachments: Optional[List[Dict[str, Any]]]
    created_at: Optional[float]

    @classmethod
    def from_message(cls, message: Message, attachments: Optional[List[Attachment]] = None) -> "MessageResponse":
        attachments_list = None
        if attachments:
            attachments_list = [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "file_type": a.file_type,
                    "file_size": a.file_size,
                }
                for a in attachments
            ]
        elif message.attachments:
            try:
                attachments_list = json.loads(message.attachments)
            except json.JSONDecodeError:
                attachments_list = None
        return cls(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            token_count=message.token_count,
            attachments=attachments_list,
            created_at=message.created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MessageListResponse:
    """Response for listing messages."""
    messages: List[MessageResponse]
    total: int
    limit: int
    offset: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": [m.to_dict() for m in self.messages],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass
class ChatRequest:
    """Request body for chat message with streaming option."""
    content: str
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "ChatRequest":
        return cls(
            content=data.get("content", ""),
            stream=data.get("stream", True),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
        )


@dataclass
class ChatResponse:
    """Response for chat message."""
    message: MessageResponse
    response: MessageResponse
    usage: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message.to_dict(),
            "response": self.response.to_dict(),
            "usage": self.usage,
        }


@dataclass
class FileUploadRequest:
    """Request for file upload (multipart handled separately)."""
    filename: str
    file_type: str
    content_hash: Optional[str] = None

    @classmethod
    def from_data(cls, filename: str, file_type: str, content_hash: Optional[str] = None) -> "FileUploadRequest":
        return cls(filename=filename, file_type=file_type, content_hash=content_hash)


@dataclass
class FileResponse:
    """Response for file operations."""
    id: str
    filename: str
    file_type: str
    file_size: Optional[int]
    content_hash: Optional[str]
    extracted_text_length: Optional[int]
    created_at: Optional[float]

    @classmethod
    def from_attachment(cls, attachment: Attachment) -> "FileResponse":
        return cls(
            id=attachment.id,
            filename=attachment.filename,
            file_type=attachment.file_type,
            file_size=attachment.file_size,
            content_hash=attachment.content_hash,
            extracted_text_length=len(attachment.extracted_text) if attachment.extracted_text else None,
            created_at=attachment.created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelResponse:
    """Response for model listing."""
    id: str
    name: str
    size: Optional[int]
    parameters: Optional[str]
    quantization: Optional[str]
    context_length: int
    provider: str

    @classmethod
    def from_model_info(cls, model: ModelInfo) -> "ModelResponse":
        return cls(
            id=model.id,
            name=model.name,
            size=model.size,
            parameters=model.parameters,
            quantization=model.quantization,
            context_length=model.context_length,
            provider=model.provider,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderResponse:
    """Response for provider listing."""
    id: str
    name: str
    status: Dict[str, Any]
    models: List[ModelResponse]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "models": [m.to_dict() for m in self.models],
        }


@dataclass
class LLMConfigResponse:
    """Response for LLM configuration."""
    provider: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    top_p: float
    top_k: int
    system_prompt: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HealthResponse:
    """Response for health check."""
    status: str
    version: str
    database: str
    llm_provider: str
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    """Single search result."""
    session_id: str
    session_name: Optional[str]
    message_id: str
    content: str
    created_at: Optional[float]
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResponse:
    """Response for search operations."""
    query: str
    results: List[SearchResult]
    total: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
        }


# =============================================================================
# Global Instances (lazy initialization)
# =============================================================================

_config = None
_token_estimator = None
_file_parser = None
_context_builder = None
_llm_provider: Optional[LLMProvider] = None


def get_config():
    """Get or create config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_token_estimator():
    """Get or create token estimator instance."""
    global _token_estimator
    if _token_estimator is None:
        _token_estimator = TokenEstimator()
    return _token_estimator


def get_file_parser():
    """Get or create file parser instance."""
    global _file_parser
    if _file_parser is None:
        _file_parser = FileParser()
    return _file_parser


def get_context_builder():
    """Get or create context builder instance."""
    global _context_builder
    if _context_builder is None:
        _context_builder = ContextBuilder(
            token_estimator=get_token_estimator()
        )
    return _context_builder


def get_llm_provider() -> LLMProvider:
    """Get or create LLM provider instance."""
    global _llm_provider
    if _llm_provider is None:
        config = get_config()
        _llm_provider = create_local_provider(
            model_path=config.llm.model,
            system_prompt=config.llm.system_prompt,
            config=LLMConfig(
                max_tokens=config.llm.max_tokens,
                temperature=config.llm.temperature,
                top_p=config.llm.top_p,
                top_k=config.llm.top_k,
            )
        )
        try:
            _llm_provider.connect()
            logger.info(f"Connected to local LLM: {config.llm.model}")
        except Exception as e:
            logger.warning(f"Failed to connect to LLM: {e}")
    return _llm_provider


# =============================================================================
# Helper Functions
# =============================================================================

def json_response(handler: BaseHTTPRequestHandler, status: int, data: Dict[str, Any]) -> None:
    """Send a JSON response."""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode("utf-8"))


def error_response(handler: BaseHTTPRequestHandler, status: int, error: str, message: str) -> None:
    """Send a JSON error response."""
    json_response(handler, status, ErrorResponse(
        error=error,
        message=message,
        code=status
    ).to_dict())
    logger.warning(f"Error {status}: {error} - {message}")


def parse_json_body(handler: BaseHTTPRequestHandler) -> Optional[Dict[str, Any]]:
    """Parse JSON request body."""
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return {}
    try:
        body = handler.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        return None


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def get_timestamp() -> float:
    """Get current timestamp."""
    return datetime.now().timestamp()


# =============================================================================
# Health Check Handler
# =============================================================================

def health_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle health check requests (GET /health)."""
    try:
        config = get_config()
        db_path = config.database.path
        db_exists = db_path.exists()
        
        response = HealthResponse(
            status="healthy" if db_exists else "degraded",
            version="1.0.0",
            database="ok" if db_exists else "not initialized",
            llm_provider=get_config().llm.provider,
            timestamp=get_timestamp()
        )
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        error_response(handler, 500, "health_check_failed", str(e))


# =============================================================================
# Session Management Handlers
# =============================================================================

def create_session_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle session creation (POST /api/v1/sessions)."""
    body = parse_json_body(handler)
    if body is None:
        error_response(handler, 400, "invalid_json", "Request body must be valid JSON")
        return

    try:
        request = SessionCreateRequest.from_json(body)
        config = get_config()

        session = Session(
            id=generate_id(),
            name=request.name or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            created_at=get_timestamp(),
            updated_at=get_timestamp(),
            system_prompt=request.system_prompt or config.llm.system_prompt,
            llm_config=json.dumps(request.llm_config) if request.llm_config else None,
        )

        created = create_session(session)
        response = SessionResponse.from_session(created)
        json_response(handler, 201, response.to_dict())
        logger.info(f"Created session: {created.id}")
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        error_response(handler, 500, "creation_failed", str(e))


def list_sessions_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle session listing (GET /api/v1/sessions)."""
    try:
        limit = int(query.get("limit", 100))
        offset = int(query.get("offset", 0))

        sessions = get_all_sessions(limit=limit, offset=offset)
        total = len(sessions)

        response = SessionListResponse(
            sessions=[SessionResponse.from_session(s) for s in sessions],
            total=total,
            limit=limit,
            offset=offset
        )
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        error_response(handler, 500, "list_failed", str(e))


def get_session_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle session retrieval (GET /api/v1/sessions/{id})."""
    session_id = params.get("id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    try:
        session = get_session(session_id)
        if session is None:
            error_response(handler, 404, "not_found", f"Session {session_id} not found")
            return

        messages = get_messages(session_id)
        response = SessionResponse.from_session(session, message_count=len(messages))
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        error_response(handler, 500, "retrieval_failed", str(e))


def update_session_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle session update (PUT /api/v1/sessions/{id})."""
    session_id = params.get("id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    body = parse_json_body(handler)
    if body is None:
        error_response(handler, 400, "invalid_json", "Request body must be valid JSON")
        return

    try:
        llm_config = None
        if "llm_config" in body:
            llm_config = json.dumps(body["llm_config"])

        updated = update_session(
            session_id,
            name=body.get("name"),
            system_prompt=body.get("system_prompt"),
            llm_config=llm_config
        )

        if updated is None:
            error_response(handler, 404, "not_found", f"Session {session_id} not found")
            return

        response = SessionResponse.from_session(updated)
        json_response(handler, 200, response.to_dict())
        logger.info(f"Updated session: {session_id}")
    except Exception as e:
        logger.error(f"Failed to update session: {e}")
        error_response(handler, 500, "update_failed", str(e))


def delete_session_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle session deletion (DELETE /api/v1/sessions/{id})."""
    session_id = params.get("id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    try:
        deleted = delete_session(session_id)
        if not deleted:
            error_response(handler, 404, "not_found", f"Session {session_id} not found")
            return

        json_response(handler, 200, {"deleted": session_id})
        logger.info(f"Deleted session: {session_id}")
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        error_response(handler, 500, "deletion_failed", str(e))


# =============================================================================
# Message Handlers
# =============================================================================

def get_messages_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle message listing (GET /api/v1/sessions/{id}/messages)."""
    session_id = params.get("id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    try:
        limit = int(query.get("limit", 100))
        offset = int(query.get("offset", 0))

        # Verify session exists
        session = get_session(session_id)
        if session is None:
            error_response(handler, 404, "not_found", f"Session {session_id} not found")
            return

        messages = get_messages(session_id, limit=limit, offset=offset)

        response = MessageListResponse(
            messages=[MessageResponse.from_message(m) for m in messages],
            total=len(messages),
            limit=limit,
            offset=offset
        )
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        error_response(handler, 500, "retrieval_failed", str(e))


def create_message_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle message creation and chat response (POST /api/v1/sessions/{id}/messages)."""
    session_id = params.get("id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    body = parse_json_body(handler)
    if body is None:
        error_response(handler, 400, "invalid_json", "Request body must be valid JSON")
        return

    try:
        # Verify session exists
        session = get_session(session_id)
        if session is None:
            error_response(handler, 404, "not_found", f"Session {session_id} not found")
            return

        request = ChatRequest.from_json(body)

        # Get existing messages for context
        existing_messages = get_messages(session_id)

        # Create user message
        user_message = Message(
            id=generate_id(),
            session_id=session_id,
            role="user",
            content=request.content,
            token_count=get_token_estimator().count_tokens(request.content),
            created_at=get_timestamp(),
        )
        create_message(user_message)

        # Build context for LLM
        context_messages = [
            ContextMessage(
                role=m.role,
                content=m.content or "",
                token_count=m.token_count or 0,
                created_at=m.created_at or 0,
            )
            for m in existing_messages
        ]
        context_messages.append(ContextMessage(
            role="user",
            content=request.content,
            token_count=user_message.token_count or 0,
            created_at=user_message.created_at or 0,
        ))

        context_builder = get_context_builder()
        context = context_builder.build_context(
            context_messages,
            system_prompt=session.system_prompt
        )

        # Get LLM response
        llm = get_llm_provider()
        llm_config = LLMConfig(
            max_tokens=request.max_tokens or get_config().llm.max_tokens,
            temperature=request.temperature or get_config().llm.temperature,
        )

        response = llm.generate(
            prompt=context_builder.format_for_llm(context),
            config=llm_config
        )

        # Create assistant message
        assistant_message = Message(
            id=generate_id(),
            session_id=session_id,
            role="assistant",
            content=response.content,
            token_count=get_token_estimator().count_tokens(response.content),
            created_at=get_timestamp(),
        )
        create_message(assistant_message)

        # Update session timestamp
        update_session(session_id)

        chat_response = ChatResponse(
            message=MessageResponse.from_message(user_message),
            response=MessageResponse.from_message(assistant_message),
            usage=response.usage
        )
        json_response(handler, 200, chat_response.to_dict())
        logger.info(f"Chat response for session {session_id}: {len(response.content)} chars")
    except Exception as e:
        logger.error(f"Failed to create message: {e}")
        error_response(handler, 500, "creation_failed", str(e))


def delete_message_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle message deletion (DELETE /api/v1/sessions/{id}/messages/{message_id})."""
    session_id = params.get("id")
    message_id = params.get("message_id")

    if not session_id or not message_id:
        error_response(handler, 400, "missing_id", "Session ID and Message ID are required")
        return

    try:
        deleted = delete_message(message_id)
        if not deleted:
            error_response(handler, 404, "not_found", f"Message {message_id} not found")
            return

        json_response(handler, 200, {"deleted": message_id})
        logger.info(f"Deleted message: {message_id}")
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")
        error_response(handler, 500, "deletion_failed", str(e))


def edit_message_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle message editing (PUT /api/v1/sessions/{id}/messages/{message_id})."""
    session_id = params.get("id")
    message_id = params.get("message_id")

    if not session_id or not message_id:
        error_response(handler, 400, "missing_id", "Session ID and Message ID are required")
        return

    body = parse_json_body(handler)
    if body is None:
        error_response(handler, 400, "invalid_json", "Request body must be valid JSON")
        return

    try:
        content = body.get("content")
        if content is None:
            error_response(handler, 400, "missing_content", "Content is required")
            return

        token_count = get_token_estimator().count_tokens(content)
        updated = update_message(message_id, content=content, token_count=token_count)

        if updated is None:
            error_response(handler, 404, "not_found", f"Message {message_id} not found")
            return

        response = MessageResponse.from_message(updated)
        json_response(handler, 200, response.to_dict())
        logger.info(f"Edited message: {message_id}")
    except Exception as e:
        logger.error(f"Failed to edit message: {e}")
        error_response(handler, 500, "edit_failed", str(e))


# =============================================================================
# File Handlers
# =============================================================================

def upload_file_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle file upload (POST /api/v1/files)."""
    try:
        content_length = int(handler.headers.get("Content-Length", 0))
        if content_length == 0:
            error_response(handler, 400, "empty_file", "No file content provided")
            return

        filename = query.get("filename", "uploaded_file")
        file_type = query.get("file_type", "text/plain")

        content = handler.rfile.read(content_length)
        content_hash = hashlib.sha256(content).hexdigest()

        # Check for duplicate
        existing = None
        # Note: Would need a get_attachment_by_hash function for true deduplication

        # Parse file content
        file_parser = get_file_parser()
        extracted_text = file_parser.parse_content(content, filename)

        # Create attachment
        attachment = Attachment(
            id=generate_id(),
            message_id="",  # Will be linked when message is created
            filename=filename,
            file_type=file_type,
            file_size=len(content),
            content_hash=content_hash,
            storage_path="",  # For now, store content directly
            extracted_text=extracted_text,
            created_at=get_timestamp(),
        )
        create_attachment(attachment)

        response = FileResponse.from_attachment(attachment)
        json_response(handler, 201, response.to_dict())
        logger.info(f"Uploaded file: {filename} ({len(content)} bytes)")
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        error_response(handler, 500, "upload_failed", str(e))


def get_file_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle file retrieval (GET /api/v1/files/{id})."""
    file_id = params.get("id")
    if not file_id:
        error_response(handler, 400, "missing_id", "File ID is required")
        return

    try:
        attachment = get_attachment(file_id)
        if attachment is None:
            error_response(handler, 404, "not_found", f"File {file_id} not found")
            return

        response = FileResponse.from_attachment(attachment)
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Failed to get file: {e}")
        error_response(handler, 500, "retrieval_failed", str(e))


def delete_file_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle file deletion (DELETE /api/v1/files/{id})."""
    file_id = params.get("id")
    if not file_id:
        error_response(handler, 400, "missing_id", "File ID is required")
        return

    try:
        deleted = delete_attachment(file_id)
        if not deleted:
            error_response(handler, 404, "not_found", f"File {file_id} not found")
            return

        json_response(handler, 200, {"deleted": file_id})
        logger.info(f"Deleted file: {file_id}")
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        error_response(handler, 500, "deletion_failed", str(e))


# =============================================================================
# LLM Configuration Handlers
# =============================================================================

def list_llm_providers_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle LLM provider listing (GET /api/v1/llm/providers)."""
    try:
        llm = get_llm_provider()
        status = llm.get_status()
        models = llm.get_models()

        response = ProviderResponse(
            id="local",
            name="Local LLM (llama_cpp)",
            status=status.to_dict(),
            models=[ModelResponse.from_model_info(m) for m in models]
        )
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        error_response(handler, 500, "list_failed", str(e))


def list_models_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle model listing (GET /api/v1/llm/providers/{id}/models)."""
    try:
        llm = get_llm_provider()
        models = llm.get_models()

        response = [ModelResponse.from_model_info(m).to_dict() for m in models]
        json_response(handler, 200, {"models": response})
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        error_response(handler, 500, "list_failed", str(e))


def get_llm_status_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle LLM status check (GET /api/v1/llm/status)."""
    try:
        llm = get_llm_provider()
        status = llm.get_status()
        json_response(handler, 200, status.to_dict())
    except Exception as e:
        logger.error(f"Failed to get LLM status: {e}")
        error_response(handler, 500, "status_failed", str(e))


def update_llm_config_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle LLM config update (PUT /api/v1/llm/config)."""
    body = parse_json_body(handler)
    if body is None:
        error_response(handler, 400, "invalid_json", "Request body must be valid JSON")
        return

    try:
        config = get_config()
        if "temperature" in body:
            config.llm.temperature = float(body["temperature"])
        if "max_tokens" in body:
            config.llm.max_tokens = int(body["max_tokens"])
        if "top_p" in body:
            config.llm.top_p = float(body["top_p"])
        if "top_k" in body:
            config.llm.top_k = int(body["top_k"])
        if "system_prompt" in body:
            config.llm.system_prompt = body["system_prompt"]

        response = LLMConfigResponse(
            provider=config.llm.provider,
            base_url=config.llm.base_url,
            model=config.llm.model,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            top_p=config.llm.top_p,
            top_k=config.llm.top_k,
            system_prompt=config.llm.system_prompt,
        )
        json_response(handler, 200, response.to_dict())
        logger.info("Updated LLM configuration")
    except Exception as e:
        logger.error(f"Failed to update LLM config: {e}")
        error_response(handler, 500, "update_failed", str(e))


# =============================================================================
# Search Handlers
# =============================================================================

def search_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle global search (GET /api/v1/search)."""
    search_query = query.get("q", "")
    if not search_query:
        error_response(handler, 400, "missing_query", "Search query 'q' is required")
        return

    try:
        sessions = get_all_sessions(limit=100)
        results = []
        search_lower = search_query.lower()

        for session in sessions:
            messages = get_messages(session.id)
            for msg in messages:
                if msg.content and search_lower in msg.content.lower():
                    results.append(SearchResult(
                        session_id=session.id,
                        session_name=session.name,
                        message_id=msg.id,
                        content=msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                        created_at=msg.created_at,
                        score=1.0  # Simple scoring for now
                    ))

        response = SearchResponse(
            query=search_query,
            results=results[:50],  # Limit results
            total=len(results)
        )
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Search failed: {e}")
        error_response(handler, 500, "search_failed", str(e))


def search_session_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle session-specific search (GET /api/v1/sessions/{id}/search)."""
    session_id = params.get("id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    search_query = query.get("q", "")
    if not search_query:
        error_response(handler, 400, "missing_query", "Search query 'q' is required")
        return

    try:
        # Verify session exists
        session = get_session(session_id)
        if session is None:
            error_response(handler, 404, "not_found", f"Session {session_id} not found")
            return

        messages = get_messages(session_id)
        results = []
        search_lower = search_query.lower()

        for msg in messages:
            if msg.content and search_lower in msg.content.lower():
                results.append(SearchResult(
                    session_id=session_id,
                    session_name=session.name,
                    message_id=msg.id,
                    content=msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                    created_at=msg.created_at,
                    score=1.0
                ))

        response = SearchResponse(
            query=search_query,
            results=results,
            total=len(results)
        )
        json_response(handler, 200, response.to_dict())
    except Exception as e:
        logger.error(f"Session search failed: {e}")
        error_response(handler, 500, "search_failed", str(e))


# =============================================================================
# WebSocket Handler (placeholder)
# =============================================================================

# =============================================================================
# WebSocket Handler
# =============================================================================

import asyncio
import websockets
from websockets.server import serve
from websockets.exceptions import ConnectionClosed
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class StreamingSession:
    """Tracks streaming state for a session."""
    session_id: str
    message_id: str
    accumulated_content: str = ""
    last_token_time: float = 0.0
    token_count: int = 0
    is_streaming: bool = False
    cancel_requested: bool = False
    created_at: float = field(default_factory=get_timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "accumulated_content": self.accumulated_content,
            "last_token_time": self.last_token_time,
            "token_count": self.token_count,
            "is_streaming": self.is_streaming,
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at,
        }


# Global state for WebSocket sessions
_streaming_sessions: Dict[str, StreamingSession] = {}
_active_connections: Dict[str, Set[Any]] = field(default_factory=dict)


async def websocket_handler(websocket) -> None:
    """Handle WebSocket connections for streaming LLM responses.

    WebSocket endpoint at /api/v1/ws/{session_id}

    Message types received:
        - send_message: Send a new message to the LLM for streaming
        - cancel_stream: Cancel ongoing generation
        - get_status: Get current streaming status

    Event types sent:
        - token: Single token in streaming response
        - complete: Streaming completed successfully
        - error: Error occurred during streaming

    Requirements: 3.1, 3.2, 3.6, 3.9
    """
    session_id = None

    try:
        # Wait for initial message to get session_id
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "send_message":
                    session_id = data.get("session_id")
                    if not session_id:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "error": "missing_session_id",
                            "message": "Session ID is required"
                        }))
                        continue

                    content = data.get("content", "")
                    if not content:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "error": "missing_content",
                            "message": "Content is required"
                        }))
                        continue

                    # Start streaming
                    asyncio.create_task(
                        _stream_llm_response(websocket, session_id, content)
                    )

                elif msg_type == "cancel_stream":
                    if session_id and session_id in _streaming_sessions:
                        session = _streaming_sessions[session_id]
                        session.cancel_requested = True
                        await websocket.send(json.dumps({
                            "type": "complete",
                            "message_id": session.message_id,
                            "accumulated_content": session.accumulated_content,
                            "token_count": session.token_count,
                            "cancelled": True
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "error": "no_active_stream",
                            "message": "No active stream to cancel"
                        }))

                elif msg_type == "get_status":
                    if session_id and session_id in _streaming_sessions:
                        session = _streaming_sessions[session_id]
                        await websocket.send(json.dumps({
                            "type": "status",
                            "session_id": session_id,
                            "is_streaming": session.is_streaming,
                            "token_count": session.token_count,
                            "accumulated_content": session.accumulated_content[:100]  # Truncate for efficiency
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "status",
                            "session_id": session_id,
                            "is_streaming": False,
                            "token_count": 0,
                            "accumulated_content": ""
                        }))

                else:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "error": "unknown_message_type",
                        "message": f"Unknown message type: {msg_type}"
                    }))

            except json.JSONDecodeError as e:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "invalid_json",
                    "message": f"Invalid JSON: {str(e)}"
                }))

    except ConnectionClosed:
        logger.info(f"WebSocket connection closed for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if session_id and session_id in _streaming_sessions:
            session = _streaming_sessions[session_id]
            await websocket.send(json.dumps({
                "type": "error",
                "error": "internal_error",
                "message": str(e)
            }))


async def _stream_llm_response(websocket, session_id: str, content: str) -> None:
    """Stream LLM response tokens to the client.

    Args:
        websocket: The WebSocket connection
        session_id: The session ID
        content: The user message content
    """
    session = StreamingSession(
        session_id=session_id,
        message_id=generate_id(),
        accumulated_content="",
        last_token_time=get_timestamp(),
        token_count=0,
        is_streaming=True,
        cancel_requested=False
    )

    _streaming_sessions[session_id] = session

    try:
        # Get session from database
        db_session = get_session(session_id)
        if db_session is None:
            await websocket.send(json.dumps({
                "type": "error",
                "error": "session_not_found",
                "message": f"Session {session_id} not found"
            }))
            return

        # Get existing messages for context
        existing_messages = get_messages(session_id)

        # Create user message
        user_message = Message(
            id=generate_id(),
            session_id=session_id,
            role="user",
            content=content,
            token_count=get_token_estimator().count_tokens(content),
            created_at=get_timestamp(),
        )
        create_message(user_message)

        # Build context for LLM
        context_messages = [
            ContextMessage(
                role=m.role,
                content=m.content or "",
                token_count=m.token_count or 0,
                created_at=m.created_at or 0,
            )
            for m in existing_messages
        ]
        context_messages.append(ContextMessage(
            role="user",
            content=content,
            token_count=user_message.token_count or 0,
            created_at=user_message.created_at or 0,
        ))

        context_builder = get_context_builder()
        context = context_builder.build_context(
            context_messages,
            system_prompt=db_session.system_prompt
        )

        # Get LLM provider
        llm = get_llm_provider()
        llm_config = LLMConfig(
            max_tokens=get_config().llm.max_tokens,
            temperature=get_config().llm.temperature,
        )

        # Start streaming
        prompt = context_builder.format_for_llm(context)

        async for token in llm.stream(prompt=prompt, config=llm_config):
            # Check for cancellation
            if session.cancel_requested:
                break

            # Send token to client
            await websocket.send(json.dumps({
                "type": "token",
                "token": token.text,
                "message_id": session.message_id,
                "token_index": session.token_count,
                "timestamp": get_timestamp()
            }))

            # Update session state
            session.accumulated_content += token.text
            session.token_count += 1
            session.last_token_time = get_timestamp()

            # Send status update every 10 tokens for visual feedback
            if session.token_count % 10 == 0:
                await websocket.send(json.dumps({
                    "type": "status",
                    "session_id": session_id,
                    "is_streaming": True,
                    "token_count": session.token_count,
                    "accumulated_content": session.accumulated_content[:200]
                }))

        # Check if cancelled
        if session.cancel_requested:
            await websocket.send(json.dumps({
                "type": "complete",
                "message_id": session.message_id,
                "accumulated_content": session.accumulated_content,
                "token_count": session.token_count,
                "cancelled": True
            }))
            return

        # Create assistant message
        assistant_message = Message(
            id=generate_id(),
            session_id=session_id,
            role="assistant",
            content=session.accumulated_content,
            token_count=get_token_estimator().count_tokens(session.accumulated_content),
            created_at=get_timestamp(),
        )
        create_message(assistant_message)

        # Update session timestamp
        update_session(session_id)

        # Send completion event
        await websocket.send(json.dumps({
            "type": "complete",
            "message_id": session.message_id,
            "accumulated_content": session.accumulated_content,
            "token_count": session.token_count,
            "timestamp": get_timestamp()
        }))

        logger.info(f"Streaming completed for session {session_id}: {session.token_count} tokens")

    except Exception as e:
        logger.error(f"Streaming error for session {session_id}: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "error": "streaming_error",
            "message": str(e)
        }))
    finally:
        # Clean up session
        if session_id in _streaming_sessions:
            del _streaming_sessions[session_id]


def start_websocket_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Start the WebSocket server for streaming responses.

    Args:
        host: Host to bind to
        port: Port to listen on
    """
    logger.info(f"Starting WebSocket server on {host}:{port}")

    async def handler(websocket):
        await websocket_handler(websocket)

    # Start server
    start_server = serve(handler, host, port)

    try:
        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logger.info("WebSocket server stopped by user")
    finally:
        start_server.close()
        asyncio.get_event_loop().run_until_complete(start_server.wait_closed())


# =============================================================================
# WebSocket Handler (placeholder - kept for backwards compatibility)
# =============================================================================

def websocket_http_handler(handler: BaseHTTPRequestHandler, params: Dict[str, str], query: Dict[str, Any]) -> None:
    """Handle WebSocket upgrade requests via HTTP (fallback).

    This is a placeholder - actual WebSocket support requires websockets library
    and should use the start_websocket_server function instead.
    """
    session_id = params.get("session_id")
    if not session_id:
        error_response(handler, 400, "missing_id", "Session ID is required")
        return

    error_response(handler, 400, "websocket_not_supported",
                   "WebSocket support requires websockets library. Use start_websocket_server() instead.")
