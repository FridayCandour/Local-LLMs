"""HTTP server entry point for the backend."""
import json
import mimetypes
import os
import signal
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse, parse_qs

from backend.config import Config, load_config
from backend.database import init_db
from backend.logging_config import get_logger, setup_logging
from backend.router import Router, create_api_router

logger = get_logger(__name__)

# Global server instance for shutdown handling
_server: HTTPServer | None = None
_shutdown_event = threading.Event()

# Project root for resolving frontend static files
_PROJECT_ROOT = Path(__file__).parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"

# Content type mapping for static files
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json",
}


def _make_handler_class(router: Router, config: Config):
    """Factory that creates a handler class with router and config baked in."""

    class ChatRequestHandler(BaseHTTPRequestHandler):
        """Custom HTTP request handler with CORS, security headers, routing, and static file serving."""

        _router = router
        _config = config
        JSON_CONTENT_TYPE = "application/json"

        def log_message(self, format: str, *args) -> None:
            """Override to use structured logging."""
            logger.info(f"{self.address_string()} - {format % args}")

        def _set_cors_headers(self) -> None:
            """Set CORS headers for frontend communication."""
            origin = self.headers.get("Origin", "*")
            if origin != "*" and origin not in self._config.server.cors_origins:
                origin = self._config.server.cors_origins[0] if self._config.server.cors_origins else "*"

            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Max-Age", "86400")

        def _set_security_headers(self) -> None:
            """Set security headers for protection against common attacks."""
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-XSS-Protection", "1; mode=block")
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        def _set_response_headers(self) -> None:
            """Set common response headers."""
            self._set_cors_headers()
            self._set_security_headers()

        def _send_json_response(self, status_code: int, data: dict[str, Any] | list[Any]) -> None:
            """Send a JSON response with proper headers."""
            self.send_response(status_code)
            self._set_response_headers()
            self.send_header("Content-Type", self.JSON_CONTENT_TYPE)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        def _send_error_response(self, status_code: int, error: str, message: str) -> None:
            """Send a JSON error response."""
            self._send_json_response(status_code, {"error": error, "message": message})

        def _parse_request_path(self) -> tuple[str, Dict[str, Any]]:
            """Parse the URL into path and query dict."""
            parsed = urlparse(self.path)
            path = parsed.path
            query = {}
            for key, values in parse_qs(parsed.query).items():
                query[key] = values[0] if len(values) == 1 else values
            return path, query

        def _route_request(self, method: str) -> None:
            """Route an API request through the router, or serve static files."""
            path, query = self._parse_request_path()

            # Health check (special route)
            if self._router.match_health(method, path):
                health_route = self._router._health_route
                if health_route:
                    health_route.handler(self, {}, query)
                    return

            # API routes
            if path.startswith("/api/"):
                match = self._router.match(method, path)
                if match:
                    match.route.handler(self, match.params, query)
                else:
                    # Check if path exists but method not allowed
                    allowed = self._router.get_allowed_methods(path)
                    if allowed:
                        self._send_error_response(405, "method_not_allowed",
                                                  f"Method {method} not allowed. Allowed: {', '.join(allowed)}")
                    else:
                        self._send_error_response(404, "not_found", "Resource not found")
                return

            # Non-API paths: serve static files (GET only)
            if method == "GET":
                self._serve_static(path)
            else:
                self._send_error_response(404, "not_found", "Resource not found")

        def _serve_static(self, path: str) -> None:
            """Serve static files from the frontend directory."""
            # Map root to index.html
            if path == "/":
                path = "/index.html"

            # Resolve the file path safely
            # Remove leading slash and normalize
            relative_path = path.lstrip("/")
            file_path = (_FRONTEND_DIR / relative_path).resolve()

            # Security: ensure the resolved path is within the frontend directory
            try:
                file_path.relative_to(_FRONTEND_DIR.resolve())
            except ValueError:
                self._send_error_response(403, "forbidden", "Access denied")
                return

            if not file_path.is_file():
                self._send_error_response(404, "not_found", f"File not found: {path}")
                return

            # Determine content type
            ext = file_path.suffix.lower()
            content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

            try:
                with open(file_path, "rb") as f:
                    content = f.read()

                self.send_response(200)
                self._set_security_headers()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except OSError as e:
                logger.error(f"Error serving static file {file_path}: {e}")
                self._send_error_response(500, "server_error", "Failed to read file")

        def do_OPTIONS(self) -> None:
            """Handle CORS preflight requests."""
            self.send_response(204)
            self._set_cors_headers()
            self.end_headers()

        def do_GET(self) -> None:
            """Handle GET requests."""
            self._route_request("GET")

        def do_POST(self) -> None:
            """Handle POST requests."""
            self._route_request("POST")

        def do_PUT(self) -> None:
            """Handle PUT requests."""
            self._route_request("PUT")

        def do_DELETE(self) -> None:
            """Handle DELETE requests."""
            self._route_request("DELETE")

    return ChatRequestHandler


def _run_server(config: Config) -> None:
    """Run the HTTP server.

    Args:
        config: Configuration object
    """
    global _server

    # Create the router
    router = create_api_router()

    # Create handler class with router and config
    handler_class = _make_handler_class(router, config)

    # Create server instance
    server_address = (config.server.host, config.server.port)
    _server = HTTPServer(server_address, handler_class)

    # Make socket reusable
    _server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    logger.info(f"Server starting on {config.server.host}:{config.server.port}")
    logger.info(f"Debug mode: {config.server.debug}")
    logger.info(f"Serving frontend from {_FRONTEND_DIR}")

    try:
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


def _run_websocket_server(config: Config) -> None:
    """Run the WebSocket server for streaming responses.

    Args:
        config: Configuration object
    """
    from backend.handlers import start_websocket_server

    ws_port = config.server.websocket_port if hasattr(config.server, 'websocket_port') else 8765
    start_websocket_server(port=ws_port)


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

    # Initialize the database
    init_db()
    logger.info("Database initialized")

    # Register signal handlers for graceful shutdown (must be in main thread)
    _setup_signal_handlers()

    # Start WebSocket server in a separate thread
    ws_thread = threading.Thread(
        target=_run_websocket_server,
        args=(config,),
        daemon=True
    )
    ws_thread.start()
    logger.info("WebSocket server started in background thread")

    try:
        _run_server(config)
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        logger.info("Server stopped")


if __name__ == "__main__":
    run_server()
