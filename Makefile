# Project Human Redis - Makefile
# AI Assistant with STT, TTS, LLM, GUI, and Web Interface components

.PHONY: help setup start stop status clean gui gui-video stt tts llm all-components check-deps check-services logs web-interface

# Default target
help:
	@echo "Project Human Redis - AI Assistant"
	@echo ""
	@echo "Available targets:"
	@echo "  setup           - Initial setup (copy config, install deps)"
	@echo "  start           - Start all services and components"
	@echo "  stop            - Stop all services and components" 
	@echo "  status          - Check status of all services"
	@echo "  clean           - Stop services and clean up"
	@echo ""
	@echo "Individual components:"
	@echo "  gui             - Start GUI component only (original)"
	@echo "  gui-video       - Start GUI component with video support"
	@echo "  terminal        - Start terminal interface"
	@echo "  stt             - Start Speech-to-Text component only"
	@echo "  tts             - Start Text-to-Speech component only"
	@echo "  llm             - Start LLM component only"
	@echo "  web-interface   - Start Web Interface only"
	@echo "  stop-web-interface - Stop Web Interface only"
	@echo "  all-components  - Start all Python components (assumes services running)"
	@echo ""
	@echo "Services:"
	@echo "  start-services  - Start Docker services (Redis, Weaviate)"
	@echo "  start-whisper   - Start Whisper server"
	@echo "  stop-services   - Stop Docker services"
	@echo "  stop-whisper    - Stop Whisper server"
	@echo ""
	@echo "Utilities:"
	@echo "  check-deps      - Check dependencies"
	@echo "  check-services  - Check if services are running"
	@echo "  logs            - Show logs from all services"

# Setup and configuration
setup:
	@echo "Setting up Project Human Redis..."
	@if [ ! -f config.json ]; then \
		echo "Creating config.json from example..."; \
		cp config.json.example config.json; \
		echo "⚠️  Please edit config.json with your API keys and settings"; \
	fi
	@echo "Installing Python dependencies..."
	@if [ -f ".python-version" ]; then \
		echo "Using Python version from .python-version"; \
	fi
	@if command -v uv >/dev/null 2>&1; then \
		uv sync; \
	else \
		echo "UV not found, using pip..."; \
		source .venv/bin/activate && pip install -e .; \
	fi
	@echo "✅ Setup complete!"

# Check dependencies
check-deps:
	@echo "Checking dependencies..."
	@command -v docker >/dev/null 2>&1 || { echo "❌ Docker not found"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose not found"; exit 1; }
	@[ -f ".venv/bin/activate" ] || { echo "❌ Virtual environment not found"; exit 1; }
	@[ -f "config.json" ] || { echo "❌ config.json not found, run 'make setup'"; exit 1; }
	@[ -f "whisper.cpp/build/bin/whisper-server" ] || { echo "❌ Whisper server not found"; exit 1; }
	@[ -f "whisper.cpp/models/ggml-medium.en.bin" ] || { echo "❌ Whisper model not found"; exit 1; }
	@echo "✅ All dependencies found"

# Service management
start-services:
	@echo "Starting Docker services..."
	@docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@$(MAKE) check-services

stop-services:
	@echo "Stopping Docker services..."
	@docker-compose down

start-whisper:
	@echo "Starting Whisper server..."
	@mkdir -p logs
	@nohup ./whisper.cpp/build/bin/whisper-server \
		--model ./whisper.cpp/models/ggml-medium.en.bin \
		--host 0.0.0.0 \
		--port 8081 > logs/whisper.log 2>&1 & \
	echo $$! > logs/whisper.pid && \
	echo "Whisper server started (PID: $$(cat logs/whisper.pid))"

stop-whisper:
	@echo "Stopping Whisper server..."
	@if [ -f logs/whisper.pid ]; then \
		PID=$$(cat logs/whisper.pid); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID && echo "Whisper server stopped (PID: $$PID)"; \
		else \
			echo "Whisper server not running (stale PID file)"; \
		fi; \
		rm -f logs/whisper.pid; \
	else \
		echo "No Whisper PID file found"; \
		pkill -f "whisper-server" 2>/dev/null && echo "Killed any running whisper-server processes" || true; \
	fi

# Check services
check-services:
	@echo "Checking service status..."
	@echo -n "Redis: "
	@if docker-compose ps redis | grep -q "Up"; then \
		echo "✅ Running"; \
	else \
		echo "❌ Not running"; \
	fi
	@echo -n "Weaviate: "
	@if docker-compose ps weaviate | grep -q "Up"; then \
		echo "✅ Running"; \
	else \
		echo "❌ Not running"; \
	fi
	@echo -n "Whisper: "
	@if [ -f logs/whisper.pid ] && kill -0 $$(cat logs/whisper.pid) 2>/dev/null; then \
		echo "✅ Running (PID: $$(cat logs/whisper.pid))"; \
	else \
		echo "❌ Not running"; \
	fi

# Component management
gui:
	@echo "Starting GUI component (original)..."
	@source .venv/bin/activate && python src/gui_main.py

gui-video:
	@echo "Starting GUI component with video support..."
	@source .venv/bin/activate && python src/gui_main_video.py

terminal:
	@echo "Starting terminal interface..."
	@source .venv/bin/activate && python src/terminal_main.py

stt:
	@echo "Starting Speech-to-Text component..."
	@source .venv/bin/activate && python src/stt_component.py

tts:
	@echo "Starting Text-to-Speech component..."
	@source .venv/bin/activate && python src/tts_component.py

llm:
	@echo "Starting LLM component..."
	@source .venv/bin/activate && python src/llm_component.py

web-interface:
	@echo "Starting Web Interface..."
	@source .venv/bin/activate && python src/webinterface/app.py

stop-web-interface:
	@echo "Stopping Web Interface..."
	@if [ -f logs/webinterface.pid ]; then \
		PID=$$(cat logs/webinterface.pid); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID && echo "Web Interface stopped (PID: $$PID)"; \
		else \
			echo "Web Interface not running (stale PID file)"; \
		fi; \
		rm -f logs/webinterface.pid; \
	else \
		echo "No Web Interface PID file found"; \
		pkill -f "src/webinterface/app.py" 2>/dev/null && echo "Killed any running web interface processes" || echo "No web interface processes found"; \
	fi

start-components:
	@echo "Starting all Python components..."
	@mkdir -p logs
	@source .venv/bin/activate && python src/stt_component.py & echo $$! > logs/stt.pid
	@source .venv/bin/activate && python src/tts_component.py & echo $$! > logs/tts.pid  
	@source .venv/bin/activate && python src/llm_component.py & echo $$! > logs/llm.pid
	@source .venv/bin/activate && python src/webinterface/app.py & echo $$! > logs/webinterface.pid
	@echo "Background components started. Starting terminal interface..."
	@echo "💡 To use GUI instead: make gui"
	@source .venv/bin/activate && python src/terminal_main.py

all-components: stop-components start-services start-whisper start-components

# Main commands
start: check-deps
	@echo "🚀 Starting Project Human Redis..."
	@mkdir -p logs
	@$(MAKE) start-services
	@$(MAKE) start-whisper
	@echo "✅ Services started. Starting components..."
	@$(MAKE) all-components

stop-components: 
	@echo "Stopping Python components..."
	@pkill -f "python src/.*_component.py" 2>/dev/null || true
	@pkill -f "python src/gui_main.py" 2>/dev/null || true
	@pkill -f "python src/gui_main_video.py" 2>/dev/null || true
	@pkill -f "python src/terminal_main.py" 2>/dev/null || true
	@rm -f logs/*.pid 2>/dev/null || true

stop: stop-components stop-whisper stop-services
	@echo "✅ All stopped"

status:
	@echo "=== Project Human Redis Status ==="
	@$(MAKE) check-services
	@echo ""
	@echo "Python Components:"
	@for comp in stt tts llm webinterface gui terminal; do \
		echo -n "$$comp: "; \
		if [ -f logs/$$comp.pid ] && kill -0 $$(cat logs/$$comp.pid) 2>/dev/null; then \
			echo "✅ Running (PID: $$(cat logs/$$comp.pid))"; \
		else \
			echo "❌ Not running"; \
		fi; \
	done

clean: stop
	@echo "Cleaning up..."
	@docker-compose down -v
	@rm -rf logs/*.pid
	@echo "✅ Cleanup complete"

logs:
	@echo "=== Component Status ==="
	@echo "Whisper: PID $$(cat logs/whisper.pid 2>/dev/null || echo 'Not running')"
	@for comp in stt tts llm; do \
		echo "$$comp: PID $$(cat logs/$$comp.pid 2>/dev/null || echo 'Not running')"; \
	done
