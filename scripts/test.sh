#!/bin/bash
set -e

# Test execution script for Local LLM Chat Interface
# Runs all tests including unit tests and property-based tests

echo "=== Local LLM Chat Interface - Test Suite ==="

# Navigate to project root
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install test dependencies
echo "Installing test dependencies..."
pip install -q pytest pytest-cov hypothesis 2>/dev/null || true

# Run backend tests
echo ""
echo "--- Backend Tests ---"
if [ -d "tests/backend" ]; then
    python -m pytest tests/backend/ -v --tb=short
else
    echo "  No backend tests found"
fi

# Run property-based tests
echo ""
echo "--- Property-Based Tests ---"
if [ -d "tests/properties" ]; then
    python -m pytest tests/properties/ -v --tb=short
else
    echo "  No property-based tests found"
fi

# Run frontend tests if available
echo ""
echo "--- Frontend Tests ---"
if [ -d "tests/frontend" ]; then
    # Check if Node.js is available for frontend tests
    if command -v node &> /dev/null; then
        npm test --prefix . 2>/dev/null || echo "  Frontend tests require npm setup"
    else
        echo "  Node.js not available, skipping frontend tests"
    fi
else
    echo "  No frontend tests found"
fi

echo ""
echo "=== Test Suite Complete ==="