#!/bin/bash
# Run a demo agency
# Usage: ./scripts/run_demo.sh [pack_name] [port]

set -e

PACK=${1:-saas_support}
PORT=${2:-8000}
OUTPUT_DIR="./demo_output"

echo "🔨 Forge Demo Runner"
echo "   Pack: $PACK"
echo "   Port: $PORT"
echo ""

# Generate agency from pack
echo "📦 Generating agency from '$PACK' pack..."
forge create --pack "$PACK" --output "$OUTPUT_DIR" --overwrite

# Find the generated directory
AGENCY_DIR=$(ls -d "$OUTPUT_DIR"/*/ 2>/dev/null | head -1)

if [ -z "$AGENCY_DIR" ]; then
    echo "❌ No agency generated"
    exit 1
fi

echo "✅ Agency generated at $AGENCY_DIR"

# Copy runtime into generated agency
echo "📦 Packaging runtime..."
if [ -d "forge/runtime" ]; then
    mkdir -p "$AGENCY_DIR/forge"
    cp -r forge/runtime "$AGENCY_DIR/forge/"
    cp forge/__init__.py "$AGENCY_DIR/forge/" 2>/dev/null || true
fi

# Start the API server
echo ""
echo "🚀 Starting agency API server on port $PORT..."
echo "   API: http://localhost:$PORT/docs"
echo "   Health: http://localhost:$PORT/health"
echo "   Status: http://localhost:$PORT/api/status"
echo ""
cd "$AGENCY_DIR"
python -m uvicorn api_server:app --host 0.0.0.0 --port "$PORT"
