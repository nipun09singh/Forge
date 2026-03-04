#!/bin/bash
# Forge Setup Script
# Installs Forge and generates a demo agency

set -e

echo "🔨 Setting up Forge..."

# Install Forge in development mode
pip install -e .

echo "✅ Forge installed"

# Check for API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set. You can still use --pack mode (no API key needed)."
    echo ""
    echo "Generate a demo agency without API key:"
    echo "  forge create --pack saas_support"
    echo ""
    echo "Set your API key for full LLM-powered generation:"
    echo "  export OPENAI_API_KEY='your-key-here'"
    echo "  forge create 'your domain description'"
else
    echo "✅ OPENAI_API_KEY detected"
fi

echo ""
echo "🚀 Quick Start:"
echo "  forge packs                           # List available domain packs"
echo "  forge create --pack saas_support      # Generate SaaS support agency (no API key needed)"
echo "  forge create 'your domain'            # Generate custom agency (needs API key)"
echo "  forge list                            # List generated agencies"
echo "  forge inspect generated/saas-support-pro  # View agency details"
echo "  forge run generated/saas-support-pro  # Run agency API server"
