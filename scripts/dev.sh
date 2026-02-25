#!/bin/bash

# Development server startup script for Local LLM Chat Interface
# Starts the development server with debug mode enabled

echo "=== Local LLM Chat Interface - Development Server ==="

# Navigate to project root
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install dependencies if needed
echo "Checking dependencies..."
pip install -q -r requirements.txt 2>/dev/null || true

# Set debug environment
export DEBUG=1
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Ensure required directories exist
mkdir -p uploads
mkdir -p logs
mkdir -p static

# Copy frontend files to static directory for development
if [ -d "frontend" ]; then
    echo "Preparing static files..."
    cp -r frontend/* static/ 2>/dev/null || true
fi

# Initialize database
echo "Initializing database..."
python -c "from backend.database import init_db; init_db()" 2>/dev/null || echo "  Database initialization skipped"

# Start the development server
echo ""
echo "Starting development server..."
echo "  Debug mode: ENABLED"
echo "  Static files: static/"
echo "  Upload directory: uploads/"
echo ""
echo "Server will be available at: http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

# Start server with auto-reload capability using uvicorn
if command -v uvicorn &> /dev/null; then
    exec uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload --log-level debug
else
    # Fallback to basic Python HTTP server
    echo "Using basic HTTP server (uvicorn not available)"
    python -m http.server 8000 --directory static
fi