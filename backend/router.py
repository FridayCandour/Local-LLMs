"""
Router Module for HTTP Request Routing

This module implements simple dictionary-based routing for the API.
It maps URL paths and HTTP methods to handler functions, parses route
parameters from URL paths, and handles 404/405 responses for unmatched
routes and methods.

Design follows Requirement 14.7.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, List, Tuple
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """Defines a single route with method, path pattern, and handler."""
    method: str
    path_pattern: str
    handler: Callable[[BaseHTTPRequestHandler, Dict[str, str], Dict[str, Any]], None]
    # Compiled regex pattern for route matching (set after initialization)
    regex_pattern: re.Pattern = field(init=False, repr=False)
    # Parameter names extracted from path pattern
    param_names: List[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Compile regex pattern and extract parameter names from path."""
        # Convert path pattern like /api/v1/sessions/{id} to regex
        # Escape special regex characters except { and }
        escaped = re.escape(self.path_pattern)
        # Replace {param_name} with named capture group
        param_names: List[str] = []
        regex = escaped
        # Find all {param} patterns and replace with named groups
        def replace_param(match: re.Match) -> str:
            param_name = match.group(1)
            param_names.append(param_name)
            return r'(?P<' + param_name + r'>[^/]+)'
        
        regex = re.sub(r'\{(\w+)\}', replace_param, regex)
        # Anchor the pattern to match full path
        regex = '^' + regex + '$'
        self.regex_pattern = re.compile(regex)
        self.param_names = param_names


@dataclass
class RouteMatch:
    """Result of a route match operation."""
    route: Route
    params: Dict[str, str]


class Router:
    """
    Simple dictionary-based HTTP request router.
    
    The router maps URL paths and HTTP methods to handler functions.
    It supports route parameters in paths (e.g., {id}, {session_id}) that
    are parsed and passed to handlers.
    
    Example:
        router = Router()
        router.add_route("GET", "/api/v1/sessions/{id}", get_session_handler)
        router.add_route("POST", "/api/v1/sessions", create_session_handler)
        
        match = router.match("GET", "/api/v1/sessions/123")
        if match:
            handler = match.route.handler
            params = match.params
    """

    def __init__(self) -> None:
        """Initialize the router with empty routes dictionary."""
        # Dictionary mapping (method, path) -> Route
        # For parameter matching, we use a separate list of routes
        self._routes: Dict[Tuple[str, str], Route] = {}
        # List of routes for pattern matching with parameters
        self._pattern_routes: List[Route] = []
        # Health check route (no prefix matching)
        self._health_route: Optional[Route] = None

    def add_route(
        self,
        method: str,
        path_pattern: str,
        handler: Callable[[BaseHTTPRequestHandler, Dict[str, str], Dict[str, Any]], None]
    ) -> None:
        """
        Add a route to the router.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path_pattern: URL path pattern with optional {param} placeholders
            handler: Handler function to call when route matches
        """
        route = Route(method=method, path_pattern=path_pattern, handler=handler)
        
        # Check if path has parameters
        if '{' in path_pattern:
            self._pattern_routes.append(route)
            # Sort by number of static parts (more static = higher priority)
            self._pattern_routes.sort(
                key=lambda r: len(r.path_pattern.split('/')) - len(r.param_names),
                reverse=True
            )
        else:
            self._routes[(method.upper(), path_pattern)] = route
        
        logger.debug(f"Added route: {method} {path_pattern}")

    def match(self, method: str, path: str) -> Optional[RouteMatch]:
        """
        Match a request method and path to a route.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: URL path to match
            
        Returns:
            RouteMatch if route found, None otherwise
        """
        method_upper = method.upper()
        
        # Check for exact match first (faster)
        route = self._routes.get((method_upper, path))
        if route:
            return RouteMatch(route=route, params={})
        
        # Check for pattern match with parameters
        for pattern_route in self._pattern_routes:
            if pattern_route.method != method_upper:
                continue
            match = pattern_route.regex_pattern.match(path)
            if match:
                params = match.groupdict()
                return RouteMatch(route=pattern_route, params=params)
        
        return None

    def get_allowed_methods(self, path: str) -> List[str]:
        """
        Get list of allowed HTTP methods for a given path.
        
        Args:
            path: URL path to check
            
        Returns:
            List of allowed HTTP method strings
        """
        allowed: List[str] = []
        
        # Check exact match routes
        for (method, route_path), route in self._routes.items():
            if route_path == path:
                allowed.append(method)
        
        # Check pattern routes
        for pattern_route in self._pattern_routes:
            if pattern_route.regex_pattern.match(path):
                allowed.append(pattern_route.method)
        
        return allowed

    def add_health_route(
        self,
        handler: Callable[[BaseHTTPRequestHandler, Dict[str, str], Dict[str, Any]], None]
    ) -> None:
        """
        Add the health check route.
        
        Args:
            handler: Handler function for health endpoint
        """
        self._health_route = Route(
            method="GET",
            path_pattern="/health",
            handler=handler
        )
        logger.debug("Added health route: GET /health")

    def match_health(self, method: str, path: str) -> bool:
        """
        Check if request matches health endpoint.
        
        Args:
            method: HTTP method
            path: URL path
            
        Returns:
            True if matches health endpoint, False otherwise
        """
        if self._health_route and method.upper() == "GET" and path == "/health":
            return True
        return False


def create_api_router() -> Router:
    """
    Create and configure the API router with all endpoints.
    
    Returns:
        Configured Router instance with all API routes
    """
    from .handlers import (
        create_session_handler, list_sessions_handler, get_session_handler,
        update_session_handler, delete_session_handler,
        get_messages_handler, create_message_handler,
        delete_message_handler, edit_message_handler,
        upload_file_handler, get_file_handler, delete_file_handler,
        list_llm_providers_handler, list_models_handler,
        get_llm_status_handler, update_llm_config_handler,
        search_handler, search_session_handler,
        health_handler
    )
    
    router = Router()
    
    # Health check endpoint
    router.add_health_route(health_handler)
    
    # Session Management Endpoints
    router.add_route("POST", "/api/v1/sessions", create_session_handler)
    router.add_route("GET", "/api/v1/sessions", list_sessions_handler)
    router.add_route("GET", "/api/v1/sessions/{id}", get_session_handler)
    router.add_route("PUT", "/api/v1/sessions/{id}", update_session_handler)
    router.add_route("DELETE", "/api/v1/sessions/{id}", delete_session_handler)
    
    # Message Endpoints
    router.add_route("GET", "/api/v1/sessions/{id}/messages", get_messages_handler)
    router.add_route("POST", "/api/v1/sessions/{id}/messages", create_message_handler)
    router.add_route("DELETE", "/api/v1/sessions/{id}/messages/{message_id}", delete_message_handler)
    router.add_route("PUT", "/api/v1/sessions/{id}/messages/{message_id}", edit_message_handler)
    
    # File Endpoints
    router.add_route("POST", "/api/v1/files", upload_file_handler)
    router.add_route("GET", "/api/v1/files/{id}", get_file_handler)
    router.add_route("DELETE", "/api/v1/files/{id}", delete_file_handler)
    
    # LLM Configuration Endpoints
    router.add_route("GET", "/api/v1/llm/providers", list_llm_providers_handler)
    router.add_route("GET", "/api/v1/llm/providers/{id}/models", list_models_handler)
    router.add_route("GET", "/api/v1/llm/status", get_llm_status_handler)
    router.add_route("PUT", "/api/v1/llm/config", update_llm_config_handler)
    
    # Search Endpoints
    router.add_route("GET", "/api/v1/search", search_handler)
    router.add_route("GET", "/api/v1/sessions/{id}/search", search_session_handler)
    
    logger.info("API router initialized with all endpoints")
    return router


def create_websocket_router() -> Router:
    """
    Create router for WebSocket endpoint.
    
    Returns:
        Router with WebSocket route
    """
    from .handlers import websocket_handler
    
    router = Router()
    router.add_route("GET", "/api/v1/ws/{session_id}", websocket_handler)
    
    return router