#!/bin/bash

# Project Human Redis - Web Interface Startup Script

echo "🚀 Starting Project Human Redis Web Interface..."

# Check if config.json exists
if [ ! -f "config.json" ]; then
    echo "❌ config.json not found. Please run 'make setup' first."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run 'make setup' first."
    exit 1
fi

# Start with dependencies check
echo "🔍 Checking dependencies..."

# Check if Docker services are running
echo "📊 Checking Docker services..."
if docker-compose ps redis | grep -q "Up" && docker-compose ps weaviate | grep -q "Up"; then
    echo "✅ Infrastructure services are running"
else
    echo "⚠️  Infrastructure services not running. Starting them..."
    docker-compose up -d redis weaviate contextionary
    echo "⏳ Waiting for services to be ready..."
    sleep 10
fi

# Activate virtual environment and start web interface
echo "🌐 Starting Web Interface..."
source .venv/bin/activate

# Start in development mode with hot reload
echo "📱 Web Interface starting at http://localhost:5001"
echo "📖 API Documentation at http://localhost:5001/docs"
echo ""
echo "💡 Use Ctrl+C to stop the web interface"
echo ""

cd src/webinterface && python app.py
