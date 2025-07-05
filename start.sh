#!/bin/bash

# Project Human Redis - Start Script
# AI Assistant with STT, TTS, LLM, and GUI components

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$PROJECT_DIR/logs"
WHISPER_BIN="$PROJECT_DIR/whisper.cpp/build/bin/whisper-server"
WHISPER_MODEL="$PROJECT_DIR/whisper.cpp/models/ggml-base.en.bin"
SRC_DIR="$PROJECT_DIR/src"

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

# Utility functions
log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1" >&2
}

# Check if a process is running
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        else
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Check dependencies
check_dependencies() {
    log "Checking dependencies..."
    
    local deps_ok=true
    
    if ! command -v docker &> /dev/null; then
        error "Docker not found. Please install Docker."
        deps_ok=false
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose not found. Please install Docker Compose."
        deps_ok=false
    fi
    
    if [ ! -f "$PROJECT_DIR/.venv/bin/activate" ]; then
        error "Virtual environment not found. Please run setup first."
        deps_ok=false
    fi
    
    if [ ! -f "$PROJECT_DIR/config.json" ]; then
        error "config.json not found. Please run setup first."
        deps_ok=false
    fi
    
    if [ ! -f "$WHISPER_BIN" ]; then
        error "Whisper server binary not found at $WHISPER_BIN"
        deps_ok=false
    fi
    
    if [ ! -f "$WHISPER_MODEL" ]; then
        error "Whisper model not found at $WHISPER_MODEL"
        deps_ok=false
    fi
    
    if [ "$deps_ok" = false ]; then
        error "Dependencies missing. Please run './start.sh setup' first."
        exit 1
    fi
    
    log "✅ All dependencies found"
}

# Setup function
setup() {
    log "🔧 Setting up Project Human Redis..."
    
    # Create config.json if it doesn't exist
    if [ ! -f "$PROJECT_DIR/config.json" ]; then
        log "Creating config.json from example..."
        cp "$PROJECT_DIR/config.json.example" "$PROJECT_DIR/config.json"
        warn "Please edit config.json with your API keys and settings"
    fi
    
    # Install Python dependencies
    log "Installing Python dependencies..."
    cd "$PROJECT_DIR"
    
    if command -v uv &> /dev/null; then
        log "Using UV package manager..."
        uv sync
    else
        log "Using pip..."
        source .venv/bin/activate
        pip install -e .
    fi
    
    log "✅ Setup complete!"
    log "Next steps:"
    log "1. Edit config.json with your API keys"
    log "2. Run './start.sh start' to start the system"
}

# Start Docker services
start_services() {
    log "🐳 Starting Docker services..."
    cd "$PROJECT_DIR"
    docker-compose up -d
    
    log "Waiting for services to be ready..."
    sleep 5
    
    # Check Redis
    if docker-compose ps redis | grep -q "Up"; then
        log "✅ Redis is running"
    else
        error "❌ Redis failed to start"
        return 1
    fi
    
    # Check Weaviate
    if docker-compose ps weaviate | grep -q "Up"; then
        log "✅ Weaviate is running"
    else
        error "❌ Weaviate failed to start"
        return 1
    fi
}

# Stop Docker services
stop_services() {
    log "🐳 Stopping Docker services..."
    cd "$PROJECT_DIR"
    docker-compose down
}

# Start Whisper server
start_whisper() {
    log "🎤 Starting Whisper server..."
    
    if is_running "$LOGS_DIR/whisper.pid"; then
        log "Whisper server already running"
        return 0
    fi
    
    cd "$PROJECT_DIR/whisper.cpp"
    ./build/bin/whisper-server \
        --model "models/ggml-base.en.bin" \
        --host 0.0.0.0 \
        --port 8081 \
        > "$LOGS_DIR/whisper.log" 2>&1 &
    
    echo $! > "$LOGS_DIR/whisper.pid"
    log "✅ Whisper server started (PID: $(cat "$LOGS_DIR/whisper.pid"))"
    
    # Wait a moment and check if it's still running
    sleep 2
    if ! is_running "$LOGS_DIR/whisper.pid"; then
        error "Whisper server failed to start. Check $LOGS_DIR/whisper.log"
        return 1
    fi
}

# Stop Whisper server
stop_whisper() {
    if is_running "$LOGS_DIR/whisper.pid"; then
        local pid=$(cat "$LOGS_DIR/whisper.pid")
        log "🎤 Stopping Whisper server (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        rm -f "$LOGS_DIR/whisper.pid"
    fi
}

# Start a Python component
start_component() {
    local component="$1"
    local script="${component}_component.py"
    
    if [ "$component" = "gui" ]; then
        script="gui_main.py"
    elif [ "$component" = "gui-video" ]; then
        script="gui_main_video.py"
    elif [ "$component" = "terminal" ]; then
        script="terminal_main.py"
    fi
    
    log "🐍 Starting $component component..."
    
    if is_running "$LOGS_DIR/${component}.pid"; then
        log "$component component already running"
        return 0
    fi
    
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    python "src/$script" > "$LOGS_DIR/${component}.log" 2>&1 &
    echo $! > "$LOGS_DIR/${component}.pid"
    
    log "✅ $component component started (PID: $(cat "$LOGS_DIR/${component}.pid"))"
}

# Stop a Python component
stop_component() {
    local component="$1"
    
    if is_running "$LOGS_DIR/${component}.pid"; then
        local pid=$(cat "$LOGS_DIR/${component}.pid")
        log "🐍 Stopping $component component (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        rm -f "$LOGS_DIR/${component}.pid"
    fi
}

# Start all Python components (assumes services are running)
start_components() {
    log "🚀 Starting all Python components..."
    
    # Start background components
    start_component "stt"
    start_component "tts"
    start_component "llm"
    
    # Start Terminal Interface (foreground) - change to "gui" if you prefer GUI
    log "🖥️ Starting Terminal Interface (foreground)..."
    log "💡 To use GUI instead, run: ./start.sh gui"
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    python src/terminal_main.py
}

# Start all Python components
start_all_components() {
    log "🚀 Starting complete system..."
    
    stop_all_components
    start_services
    start_whisper
    start_components
}

# Stop all components (Python only)
stop_all_components() {
    log "🛑 Stopping Python components..."
    
    # Stop any running Python processes
    pkill -f "python src/.*_component.py" 2>/dev/null || true
    pkill -f "python src/gui_main.py" 2>/dev/null || true
    pkill -f "python src/gui_main_video.py" 2>/dev/null || true
    pkill -f "python src/terminal_main.py" 2>/dev/null || true
    
    # Clean up PID files
    for component in stt tts llm gui terminal; do
        rm -f "$LOGS_DIR/${component}.pid"
    done
}

# Check status
status() {
    log "📊 Project Human Redis Status"
    echo
    
    # Docker services
    echo -e "${BLUE}Docker Services:${NC}"
    if docker-compose ps redis | grep -q "Up"; then
        echo "  Redis: ✅ Running"
    else
        echo "  Redis: ❌ Not running"
    fi
    
    if docker-compose ps weaviate | grep -q "Up"; then
        echo "  Weaviate: ✅ Running"
    else
        echo "  Weaviate: ❌ Not running"
    fi
    
    # Whisper server
    echo -e "${BLUE}Whisper Server:${NC}"
    if is_running "$LOGS_DIR/whisper.pid"; then
        echo "  Whisper: ✅ Running (PID: $(cat "$LOGS_DIR/whisper.pid"))"
    else
        echo "  Whisper: ❌ Not running"
    fi
    
    # Python components
    echo -e "${BLUE}Python Components:${NC}"
    for component in stt tts llm gui terminal; do
        if is_running "$LOGS_DIR/${component}.pid"; then
            echo "  $component: ✅ Running (PID: $(cat "$LOGS_DIR/${component}.pid"))"
        else
            echo "  $component: ❌ Not running"
        fi
    done
}

# Show logs
show_logs() {
    local component="$1"
    
    if [ -z "$component" ]; then
        log "📜 Recent logs from all components:"
        echo
        
        echo -e "${BLUE}=== Docker Services ===${NC}"
        docker-compose logs --tail=20
        
        echo -e "${BLUE}=== Whisper Server ===${NC}"
        if [ -f "$LOGS_DIR/whisper.log" ]; then
            tail -20 "$LOGS_DIR/whisper.log"
        else
            echo "No whisper logs found"
        fi
        
        echo -e "${BLUE}=== Python Components ===${NC}"
        for log_file in "$LOGS_DIR"/*.log; do
            if [ -f "$log_file" ] && [[ "$(basename "$log_file")" != "whisper.log" ]]; then
                echo -e "${YELLOW}--- $(basename "$log_file") ---${NC}"
                tail -10 "$log_file"
            fi
        done
    else
        if [ -f "$LOGS_DIR/${component}.log" ]; then
            log "📜 Logs for $component:"
            tail -50 "$LOGS_DIR/${component}.log"
        else
            error "No logs found for $component"
        fi
    fi
}

# Main start function
start_all() {
    log "🚀 Starting Project Human Redis..."
    
    check_dependencies
    start_services
    start_whisper
    start_components
}

# Main stop function
stop_all() {
    log "🛑 Stopping Project Human Redis..."
    
    stop_all_components
    stop_whisper
    stop_services
    
    log "✅ All services and components stopped"
}

# Clean up function
clean() {
    log "🧹 Cleaning up Project Human Redis..."
    
    stop_all
    
    # Remove Docker volumes
    cd "$PROJECT_DIR"
    docker-compose down -v
    
    # Clean up log files
    rm -rf "$LOGS_DIR"/*.log "$LOGS_DIR"/*.pid
    
    log "✅ Cleanup complete"
}

# Help function
show_help() {
    echo -e "${BLUE}Project Human Redis - AI Assistant${NC}"
    echo
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo
    echo -e "${YELLOW}Commands:${NC}"
    echo "  setup                 - Initial setup (copy config, install deps)"
    echo "  start                 - Start all services and components"
    echo "  stop                  - Stop all services and components"
    echo "  status                - Check status of all services"
    echo "  clean                 - Stop services and clean up"
    echo "  logs [component]      - Show logs (all or specific component)"
    echo
    echo -e "${YELLOW}Individual Services:${NC}"
    echo "  start-services        - Start Docker services (Redis, Weaviate)"
    echo "  stop-services         - Stop Docker services"
    echo "  start-whisper         - Start Whisper server"
    echo "  stop-whisper          - Stop Whisper server"
    echo
    echo -e "${YELLOW}Python Components:${NC}"
    echo "  start-components      - Start Python components only (assumes services running)"
    echo "  stop-components       - Stop Python components only"
    echo "  all-components        - Start everything (services + whisper + components)"
    echo
    echo -e "${YELLOW}Individual Components:${NC}"
    echo "  gui                   - Start GUI component only (original)"
    echo "  gui-video             - Start GUI component with video support"
    echo "  terminal              - Start terminal interface only"
    echo "  stt                   - Start Speech-to-Text component only"
    echo "  tts                   - Start Text-to-Speech component only"
    echo "  llm                   - Start LLM component only"
    echo "  all-components        - Start all Python components (assumes services running)"
    echo
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 setup              # Initial setup"
    echo "  $0 start-services     # Start just Redis + Weaviate"
    echo "  $0 start-components   # Start just Python components"
    echo "  $0 all-components     # Start everything"
    echo "  $0 start              # Start everything"
    echo "  $0 gui                # Start only GUI"
    echo "  $0 gui-video          # Start only GUI with video"
    echo "  $0 terminal           # Start only terminal interface"
    echo "  $0 logs stt           # Show STT component logs"
    echo "  $0 status             # Check what's running"
    echo "  $0 stop-components    # Stop just Python components"
    echo "  $0 stop               # Stop everything"
}

# Signal handlers for clean shutdown
trap 'stop_all; exit 0' SIGINT SIGTERM

# Main script logic
case "${1:-help}" in
    setup)
        setup
        ;;
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    status)
        status
        ;;
    clean)
        clean
        ;;
    logs)
        show_logs "$2"
        ;;
    start-services)
        check_dependencies
        start_services
        ;;
    stop-services)
        stop_services
        ;;
    start-whisper)
        check_dependencies
        start_whisper
        ;;
    stop-whisper)
        stop_whisper
        ;;
    gui)
        check_dependencies
        start_component "gui"
        ;;
    gui-video)
        check_dependencies
        start_component "gui-video"
        ;;
    terminal)
        check_dependencies
        start_component "terminal"
        ;;
    stt)
        check_dependencies
        start_component "stt"
        ;;
    tts)
        check_dependencies
        start_component "tts"
        ;;
    llm)
        check_dependencies
        start_component "llm"
        ;;
    start-components)
        check_dependencies
        start_components
        ;;
    stop-components)
        stop_all_components
        ;;
    all-components)
        check_dependencies
        start_all_components
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        error "Unknown command: $1"
        echo
        show_help
        exit 1
        ;;
esac
