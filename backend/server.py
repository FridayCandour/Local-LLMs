"""HTTP server entry point for the backend."""
import json
import signal
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from backend.config import Config, load_config
from backend.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

# Global server instance for shutdown handling
_server: HTTPServer | None = None
_shutdown_event = threading.Event()


class ChatRequestHandler(BaseHTTPRequestHandler):
    """Custom HTTP request handler with CORS and security headers."""

    # Response content type for JSON responses
    JSON_CONTENT_TYPE = "application/json"

    def log_message(self, format: str, *args) -> None:
        """Override to use structured logging."""
        logger.info(f"{self.address_string()} - {format % args}")

    def _set_cors_headers(self) -> None:
        """Set CORS headers for frontend communication."""
        config = getattr(self, "_config", load_config())
        origin = self.headers.get("Origin", "*")
        if origin != "*" and origin not in config.server.cors_origins:
            origin = config.server.cors_origins[0] if config.server.cors_origins else "*"

        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        self.send_header("Access-Control-Max-Age", "86400")

    def _set_security_headers(self) -> None:
        """Set security headers for protection against common attacks."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    def _set_response_headers(self) -> None:
        """Set common response headers."""
        self._set_cors_headers()
        self._set_security_headers()

    def _send_json_response(
        self, status_code: int, data: dict[str, Any] | list[Any]
    ) -> None:
        """Send a JSON response with proper headers."""
        self.send_response(status_code)
        self._set_response_headers()
        self.send_header("Content-Type", self.JSON_CONTENT_TYPE)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error_response(
        self, status_code: int, error: str, message: str
    ) -> None:
        """Send a JSON error response."""
        self._send_json_response(
            status_code, {"error": error, "message": message}
        )

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.path.split("?")[0]  # Remove query string

        if path == "/health":
            self._handle_health()
        elif path == "/":
            self._handle_root()
        else:
            self._send_error_response(404, "not_found", "Resource not found")

    def do_POST(self) -> None:
        """Handle POST requests."""
        path = self.path.split("?")[0]

        if path == "/api/v1/sessions":
            self._handle_create_session()
        elif path == "/api/v1/sessions/":
            self._handle_create_session()
        else:
            self._send_error_response(404, "not_found", "Resource not found")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        path = self.path.split("?")[0]
        self._send_error_response(404, "not_found", "Resource not found")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        path = self.path.split("?")[0]
        self._send_error_response(404, "not_found", "Resource not found")

    def _handle_health(self) -> None:
        """Handle health check endpoint.

        Returns system status for load balancer integration.
        Requirement 14.6: Implement health check endpoints that report system status
        """
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "components": {
                "server": "up",
                "database": "unknown",
                "llm_provider": "unknown",
            },
        }

        # TODO: Add actual health checks for database and LLM provider
        # For now, just report server as healthy
        self._send_json_response(200, health_status)

    def _handle_root(self) -> None:
        """Handle root endpoint - return API info."""
        api_info = {
            "name": "Local LLM Chat Interface API",
            "version": "1.0.0",
            "endpoints": {
                "health": "GET /health",
                "sessions": "GET/POST /api/v1/sessions",
                "messages": "GET/POST /api/v1/sessions/{id}/messages",
            },
        }
        self._send_json_response(200, api_info)

    def _handle_create_session(self) -> None:
        """Handle session creation - placeholder for Phase 4."""
        self._send_json_response(201, {"id": "placeholder", "name": "New Chat"})


def _run_server(config: Config) -> None:
    """Run the HTTP server.

    Args:
        config: Configuration object
    """
    global _server

    # Create server instance
    server_address = (config.server.host, config.server.port)
    _server = HTTPServer(server_address, lambda *args, **kwargs: ChatRequestHandler(*args, config=config, **kwargs))

    # Make socket reusable
    _server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    logger.info(f"Server starting on {config.server.host}:{config.server.port}")
    logger.info(f"Debug mode: {config.server.debug}")

    try:
        # Start server in main thread
        _server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    finally:
        _shutdown_event.set()


def _signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals for graceful shutdown.

    Requirement 14.7: Implement graceful shutdown that properly closes
    connections and saves state within 10 seconds
    """
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    if _server:
        _server.shutdown()


def _setup_signal_handlers() -> None:
    """Register signal handlers for graceful shutdown.

    Note: This must be called from the main thread.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def run_server(config: Config | None = None) -> None:
    """Run the HTTP server with graceful shutdown handling.

    Args:
        config: Optional configuration object (loads from env if not provided)
    """
    global _shutdown_event
    _shutdown_event = threading.Event()

    # Load configuration if not provided
    if config is None:
        config = load_config()

    # Setup logging
    setup_logging(level=config.logging.level)
    logger.info("Starting Local LLM Chat Interface server")

    # Register signal handlers for graceful shutdown (must be in main thread)
    _setup_signal_handlers()

    try:
        _run_server(config)
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        logger.info("Server stopped")


if __name__ == "__main__":
    run_server()