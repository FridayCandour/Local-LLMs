"""JWT Authentication Module for Local LLM Chat Interface.

This module implements JWT-based authentication using python-jose.
It provides functions for token generation, validation, and user
extraction from Bearer tokens in Authorization headers.

Design follows Requirements 11.1, 11.2 for security.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import jwt, JWTError

from .config import load_config

logger = logging.getLogger(__name__)


@dataclass
class TokenPayload:
    """Represents the payload of a JWT token."""
    user_id: str
    username: str
    exp: datetime
    iat: datetime = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenPayload":
        """Create TokenPayload from dictionary."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(data.get("iat"), tz=timezone.utc) if data.get("iat") else None,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TokenPayload to dictionary for JWT encoding."""
        result = {
            "user_id": self.user_id,
            "username": self.username,
            "exp": int(self.exp.timestamp()),
        }
        if self.iat:
            result["iat"] = int(self.iat.timestamp())
        return result


# Token configuration
TOKEN_ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRY_MINUTES = 60  # 1 hour default


def get_secret_key() -> str:
    """Get the secret key for JWT signing.
    
    Returns:
        Secret key from configuration or environment variable.
        Falls back to a default for development.
    """
    config = load_config()
    # Use the configured secret key or fall back to development default
    secret = getattr(config.security, "jwt_secret_key", None) if hasattr(config, "security") else None
    if secret:
        return secret
    # Development fallback - in production, this should be set
    return "dev-secret-key-change-in-production"


def create_token(user_id: str, username: str, expires_minutes: int = DEFAULT_TOKEN_EXPIRY_MINUTES) -> str:
    """Create a new JWT token for a user.
    
    Args:
        user_id: Unique user identifier
        username: User's display name
        expires_minutes: Token expiration time in minutes
        
    Returns:
        JWT token string
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=expires_minutes)
    
    payload = TokenPayload(
        user_id=user_id,
        username=username,
        exp=expiry,
        iat=now,
    )
    
    secret_key = get_secret_key()
    token = jwt.encode(
        payload.to_dict(),
        secret_key,
        algorithm=TOKEN_ALGORITHM
    )
    
    logger.debug(f"Created token for user {username} (expires in {expires_minutes} minutes)")
    return token


def validate_token(token: str) -> Optional[TokenPayload]:
    """Validate a JWT token and extract payload.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenPayload if valid, None if invalid or expired
    """
    try:
        secret_key = get_secret_key()
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[TOKEN_ALGORITHM]
        )
        
        token_payload = TokenPayload.from_dict(payload)
        
        # Check if token is expired
        if token_payload.exp < datetime.now(timezone.utc):
            logger.warning(f"Token expired for user {token_payload.username}")
            return None
        
        return token_payload
        
    except JWTError as e:
        logger.warning(f"Token validation failed: {e}")
        return None


def extract_user_from_header(authorization_header: Optional[str]) -> Optional[TokenPayload]:
    """Extract user information from Authorization header.
    
    Args:
        authorization_header: Value of Authorization header (e.g., "Bearer <token>")
        
    Returns:
        TokenPayload with user info if valid, None otherwise
    """
    if not authorization_header:
        return None
    
    # Parse Bearer token format
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Invalid Authorization header format")
        return None
    
    token = parts[1]
    return validate_token(token)


def verify_request_auth(handler) -> Optional[TokenPayload]:
    """Verify authentication for an HTTP request.
    
    Args:
        handler: BaseHTTPRequestHandler instance
        
    Returns:
        TokenPayload with user info if authenticated, None otherwise
    """
    auth_header = handler.headers.get("Authorization")
    return extract_user_from_header(auth_header)


def require_auth(handler) -> bool:
    """Check if request is authenticated, send 401 if not.
    
    Args:
        handler: BaseHTTPRequestHandler instance
        
    Returns:
        True if authenticated, False otherwise
    """
    payload = verify_request_auth(handler)
    if payload is None:
        from .handlers import error_response
        error_response(handler, 401, "unauthorized", "Authentication required")
        return False
    return True
