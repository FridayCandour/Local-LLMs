"""Database module for session persistence using sqlite3."""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime

from .config import load_config
from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Session:
    """Represents a chat session."""
    id: str
    name: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    system_prompt: Optional[str] = None
    llm_config: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class Message:
    """Represents a chat message."""
    id: str
    session_id: str
    role: str
    content: Optional[str] = None
    token_count: Optional[int] = None
    attachments: Optional[str] = None
    created_at: Optional[float] = None


@dataclass
class Attachment:
    """Represents a file attachment."""
    id: str
    message_id: str
    filename: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    content_hash: Optional[str] = None
    storage_path: Optional[str] = None
    extracted_text: Optional[str] = None
    created_at: Optional[float] = None

# Database schema version for future migrations
SCHEMA_VERSION = 1


def get_connection() -> sqlite3.Connection:
    """Get a database connection with WAL mode enabled.

    Returns:
        sqlite3.Connection: Database connection configured with WAL mode
    """
    config = load_config()
    db_path = config.database.path

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    return conn


def close_connection(conn: sqlite3.Connection) -> None:
    """Close a database connection.

    Args:
        conn: Connection to close
    """
    if conn:
        conn.close()


@contextmanager
def connection_context():
    """Context manager for database connections.

    Yields:
        sqlite3.Connection: Database connection
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        close_connection(conn)


def init_db() -> None:
    """Initialize the database with tables and indexes.

    Creates:
    - sessions table: chat session metadata
    - messages table: conversation messages with FK to sessions
    - attachments table: file attachments with FK to messages
    - Indexes for common query patterns
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at REAL,
                updated_at REAL,
                system_prompt TEXT,
                llm_config TEXT,
                user_id TEXT
            )
        """)

        # Messages table with FK to sessions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                token_count INTEGER,
                attachments TEXT,
                created_at REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

        # Attachments table with FK to messages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                message_id TEXT,
                filename TEXT,
                file_type TEXT,
                file_size INTEGER,
                content_hash TEXT,
                storage_path TEXT,
                extracted_text TEXT,
                created_at REAL,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            )
        """)

        # Indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
            ON sessions(updated_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_created
            ON messages(session_id, created_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_message_id
            ON attachments(message_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attachments_content_hash
            ON attachments(content_hash)
        """)

        # Store schema version
        cursor.execute(
            "PRAGMA user_version = ?",
            (SCHEMA_VERSION,)
        )

        conn.commit()
        logger.info(f"Database initialized at {load_config().database.path}")
    finally:
        close_connection(conn)


# Session CRUD operations

def create_session(session: Session) -> Session:
    """Create a new session in the database.

    Args:
        session: Session object with id and other fields

    Returns:
        The created Session object

    Raises:
        sqlite3.IntegrityError: If session with same id exists
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO sessions (id, name, created_at, updated_at, system_prompt, llm_config, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session.id, session.name, session.created_at, session.updated_at,
             session.system_prompt, session.llm_config, session.user_id)
        )
        logger.debug(f"Created session: {session.id}")
        return session


def get_session(session_id: str) -> Optional[Session]:
    """Retrieve a session by ID.

    Args:
        session_id: The session UUID

    Returns:
        Session object if found, None otherwise
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            system_prompt=row["system_prompt"],
            llm_config=row["llm_config"],
            user_id=row["user_id"]
        )


def get_all_sessions(user_id: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[Session]:
    """Retrieve all sessions, optionally filtered by user.

    Args:
        user_id: Optional user ID filter
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        List of Session objects ordered by updated_at descending
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset)
            )
        else:
            cursor.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        return [
            Session(
                id=row["id"],
                name=row["name"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                system_prompt=row["system_prompt"],
                llm_config=row["llm_config"],
                user_id=row["user_id"]
            )
            for row in cursor.fetchall()
        ]


def update_session(session_id: str, name: Optional[str] = None, system_prompt: Optional[str] = None,
                   llm_config: Optional[str] = None) -> Optional[Session]:
    """Update session metadata.

    Args:
        session_id: The session UUID
        name: Optional new name
        system_prompt: Optional new system prompt
        llm_config: Optional new LLM config JSON

    Returns:
        Updated Session object if found, None otherwise
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        # Build dynamic update query
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if system_prompt is not None:
            updates.append("system_prompt = ?")
            params.append(system_prompt)
        if llm_config is not None:
            updates.append("llm_config = ?")
            params.append(llm_config)

        if not updates:
            return get_session(session_id)

        updates.append("updated_at = ?")
        params.append(datetime.now().timestamp())
        params.append(session_id)

        query = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)

        if cursor.rowcount == 0:
            return None

        logger.debug(f"Updated session: {session_id}")
        return get_session(session_id)


def delete_session(session_id: str) -> bool:
    """Delete a session and all associated messages and attachments.

    Uses cascade delete configured in the schema.

    Args:
        session_id: The session UUID

    Returns:
        True if session was deleted, False if not found
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Deleted session: {session_id}")
        return deleted


# Message CRUD operations

def create_message(message: Message) -> Message:
    """Create a new message in the database.

    Args:
        message: Message object with id and other fields

    Returns:
        The created Message object
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO messages (id, session_id, role, content, token_count, attachments, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (message.id, message.session_id, message.role, message.content,
             message.token_count, message.attachments, message.created_at)
        )
        logger.debug(f"Created message: {message.id}")
        return message


def get_messages(session_id: str, limit: int = 100, offset: int = 0) -> list[Message]:
    """Retrieve all messages for a session.

    Args:
        session_id: The session UUID
        limit: Maximum number of messages to return
        offset: Number of messages to skip

    Returns:
        List of Message objects ordered by created_at ascending
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (session_id, limit, offset)
        )
        return [
            Message(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                token_count=row["token_count"],
                attachments=row["attachments"],
                created_at=row["created_at"]
            )
            for row in cursor.fetchall()
        ]


def get_message(message_id: str) -> Optional[Message]:
    """Retrieve a message by ID.

    Args:
        message_id: The message UUID

    Returns:
        Message object if found, None otherwise
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            token_count=row["token_count"],
            attachments=row["attachments"],
            created_at=row["created_at"]
        )


def update_message(message_id: str, content: Optional[str] = None,
                   token_count: Optional[int] = None) -> Optional[Message]:
    """Update a message.

    Args:
        message_id: The message UUID
        content: Optional new content
        token_count: Optional new token count

    Returns:
        Updated Message object if found, None otherwise
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        updates = []
        params = []
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if token_count is not None:
            updates.append("token_count = ?")
            params.append(token_count)

        if not updates:
            return get_message(message_id)

        params.append(message_id)
        query = f"UPDATE messages SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)

        if cursor.rowcount == 0:
            return None

        logger.debug(f"Updated message: {message_id}")
        return get_message(message_id)


def delete_message(message_id: str) -> bool:
    """Delete a message and all associated attachments.

    Uses cascade delete configured in the schema.

    Args:
        message_id: The message UUID

    Returns:
        True if message was deleted, False if not found
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Deleted message: {message_id}")
        return deleted


# Attachment CRUD operations

def create_attachment(attachment: Attachment) -> Attachment:
    """Create a new attachment in the database.

    Args:
        attachment: Attachment object with id and other fields

    Returns:
        The created Attachment object
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO attachments (id, message_id, filename, file_type, file_size,
               content_hash, storage_path, extracted_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (attachment.id, attachment.message_id, attachment.filename, attachment.file_type,
             attachment.file_size, attachment.content_hash, attachment.storage_path,
             attachment.extracted_text, attachment.created_at)
        )
        logger.debug(f"Created attachment: {attachment.id}")
        return attachment


def get_attachment(attachment_id: str) -> Optional[Attachment]:
    """Retrieve an attachment by ID.

    Args:
        attachment_id: The attachment UUID

    Returns:
        Attachment object if found, None otherwise
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return Attachment(
            id=row["id"],
            message_id=row["message_id"],
            filename=row["filename"],
            file_type=row["file_type"],
            file_size=row["file_size"],
            content_hash=row["content_hash"],
            storage_path=row["storage_path"],
            extracted_text=row["extracted_text"],
            created_at=row["created_at"]
        )


def get_attachments_for_message(message_id: str) -> list[Attachment]:
    """Retrieve all attachments for a message.

    Args:
        message_id: The message UUID

    Returns:
        List of Attachment objects ordered by created_at ascending
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM attachments WHERE message_id = ? ORDER BY created_at ASC",
            (message_id,)
        )
        return [
            Attachment(
                id=row["id"],
                message_id=row["message_id"],
                filename=row["filename"],
                file_type=row["file_type"],
                file_size=row["file_size"],
                content_hash=row["content_hash"],
                storage_path=row["storage_path"],
                extracted_text=row["extracted_text"],
                created_at=row["created_at"]
            )
            for row in cursor.fetchall()
        ]


def delete_attachment(attachment_id: str) -> bool:
    """Delete an attachment.

    Args:
        attachment_id: The attachment UUID

    Returns:
        True if attachment was deleted, False if not found
    """
    with connection_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Deleted attachment: {attachment_id}")
        return deleted