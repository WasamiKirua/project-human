# Project Human Redis - AI Assistant

A sophisticated multi-component AI assistant system featuring speech-to-text, text-to-speech, language model processing, and both graphical and web interfaces. The system uses Redis for state management, Weaviate for vector storage, and Whisper.cpp for high-performance speech recognition.

## 🚀 Key Features

- **Multi-modal Interface**: Desktop GUI and modern web dashboard
- **Real-time Speech Processing**: Advanced STT/TTS capabilities with Whisper.cpp
- **Distributed Architecture**: Component-based design with Redis coordination
- **Vector Memory**: Weaviate integration for intelligent context storage
- **Production Ready**: Docker containerization and process management

## 🏗️ Architecture

The system consists of several independent components that communicate via Redis:

- **Docker Services**: Redis (state management) + Weaviate (vector database) + Contextionary
- **Whisper.cpp Server**: High-performance C++ binary for speech recognition (port 8081)
- **Python Components**:
  - **GUI** (`gui_main.py`) - Desktop graphical user interface
  - **Web Interface** (`webinterface/app.py`) - FastAPI web dashboard (port 5001)
  - **STT** (`stt_component.py`) - Speech-to-text processing component
  - **TTS** (`tts_component.py`) - Text-to-speech synthesis component
  - **LLM** (`llm_component.py`) - Language model processing (port 8082)
  - **Memory** (`memory_component.py`) - Vector memory management
  - **Listening Controller** (`listening_controller.py`) - Audio input coordination

## 📋 Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.11+** (managed via `.python-version`)
- **UV package manager** (recommended) or pip
- **Git** for cloning the repository

## 🚀 Initial Setup

### 1. Clone and Navigate to Project
```bash
git clone <repository-url>
cd project-human
```

### 2. Setup Project Dependencies

**Option A: Using the start script (recommended)**
```bash
./start.sh setup
```

**Option B: Using Makefile**
```bash
make setup
```

**Option C: Manual setup**
```bash
# Install Python dependencies
uv sync  # or: source .venv/bin/activate && pip install -e .

# Create configuration
cp config.json.example config.json
```

### 3. Configure API Keys
Edit `config.json` and add your API keys:
```json
{
  "api_keys": {
    "openai_api_key": "your-openai-key-here",
    "groq_api_key": "your-groq-key-here"
  }
}
```

## 🎮 Management Commands

The project provides two management interfaces with identical functionality:

### Using start.sh Script (Recommended)
```bash
./start.sh [command]
```

### Using Makefile
```bash
make [target]
```

## 📖 Command Reference

### 🔧 **Setup & Configuration**
| start.sh | Makefile | Description |
|----------|----------|-------------|
| `./start.sh setup` | `make setup` | Initial project setup |
| `./start.sh status` | `make status` | Check status of all components |
| `./start.sh clean` | `make clean` | Stop everything and cleanup |

### 🐳 **Service Management** (Infrastructure)
| start.sh | Makefile | Description |
|----------|----------|-------------|
| `./start.sh start-services` | `make start-services` | Start Redis + Weaviate containers |
| `./start.sh stop-services` | `make stop-services` | Stop Docker containers |
| `./start.sh start-whisper` | `make start-whisper` | Start Whisper speech recognition server |
| `./start.sh stop-whisper` | `make stop-whisper` | Stop Whisper server |

### 🐍 **Component Management** (Python Applications)
| start.sh | Makefile | Description |
|----------|----------|-------------|
| `./start.sh start-components` | `make start-components` | Start all Python components |
| `./start.sh stop-components` | `make stop-components` | Stop Python components only |
| `./start.sh gui` | `make gui` | Start GUI component only |
| N/A | `make gui-video` | Start GUI component with video support |
| `./start.sh stt` | `make stt` | Start STT component only |
| `./start.sh tts` | `make tts` | Start TTS component only |
| `./start.sh llm` | `make llm` | Start LLM component only |
| N/A | `make web-interface` | Start Web Interface only |
| N/A | `make stop-web-interface` | Stop Web Interface only |

### 🎯 **Complete System Management**
| start.sh | Makefile | Description |
|----------|----------|-------------|
| `./start.sh start` | `make start` | Start everything (services + components) |
| `./start.sh all-components` | `make all-components` | Start everything (alternative) |
| `./start.sh stop` | `make stop` | Stop everything |

### 📊 **Monitoring & Debugging**
| start.sh | Makefile | Description |
|----------|----------|-------------|
| `./start.sh logs` | `make logs` | Show component status/logs |
| `./start.sh logs [component]` | N/A | Show logs for specific component |

## 🔄 Common Workflows

### **Quick Start (Everything at Once)**
```bash
# Setup (first time only)
./start.sh setup
# Edit config.json with your API keys

# Start complete system with desktop GUI
./start.sh start
# or: make start

# OR start with web interface instead
./start_webui.sh
```

### **Development Workflow (Granular Control)**
```bash
# Start infrastructure first
./start.sh start-services    # Redis + Weaviate
./start.sh start-whisper     # Speech recognition

# Start individual components for testing
./start.sh gui              # Desktop GUI only
# or: make web-interface     # Web interface only
# or: ./start.sh stt         # STT only
# or: ./start.sh llm         # LLM only

# Stop just components (keep services running)
./start.sh stop-components

# Restart components
./start.sh start-components

# Stop everything when done
./start.sh stop
```

### **Service-Only Mode (For External Development)**
```bash
# Start just the infrastructure
./start.sh start-services
./start.sh start-whisper

# Now you can run Python components manually:
python src/gui_main.py
python src/stt_component.py
cd src/webinterface && python app.py
# etc.
```

## 🔍 System Status & Monitoring

### Check What's Running
```bash
./start.sh status
# or: make status
```

Example output:
```
📊 Project Human Redis Status

Docker Services:
  Redis: ✅ Running
  Weaviate: ✅ Running

Whisper Server:
  Whisper: ✅ Running (PID: 12345)

Python Components:
  stt: ✅ Running (PID: 12346)
  tts: ✅ Running (PID: 12347)  
  llm: ✅ Running (PID: 12348)
  gui: ❌ Not running
  web-interface: ✅ Running (PID: 12349)
```

### View Logs (start.sh only)
```bash
# All component logs
./start.sh logs

# Specific component logs  
./start.sh logs stt
./start.sh logs whisper
./start.sh logs llm
```

## 🌐 Web Application

The project includes a modern web-based dashboard built with FastAPI that provides a user-friendly interface for monitoring and controlling all system components.

### Features
- **Real-time System Monitoring**: Live status dashboard showing the health of all services and components
- **Component Management**: Start, stop, and restart individual components through the web interface
- **Interactive Controls**: Web-based interface for interacting with the AI assistant
- **API Documentation**: Built-in FastAPI documentation and testing interface
- **WebSocket Support**: Real-time updates and live communication with the system

### Starting the Web Interface

**Quick Start:**
```bash
# Start web interface (automatically starts required services)
./start_webui.sh
```

**Manual Start:**
```bash
# Ensure infrastructure is running first
./start.sh start-services

# Start web interface
source .venv/bin/activate
cd src/webinterface && python app.py
```

### Web Endpoints
- **Dashboard**: `http://localhost:5001` - Main control interface
- **API Documentation**: `http://localhost:5001/docs` - Interactive API documentation
- **Health Check**: `http://localhost:5001/health` - System health endpoint

> **⚠️ Development Status**: The web application is currently under active development. Features and interfaces may change frequently. Some functionality may be experimental or incomplete.

## 🎙️ Whisper.cpp Integration

This project uses whisper.cpp for high-performance speech recognition. The C++ implementation provides faster inference compared to the Python whisper library, especially for real-time applications.

### Setup and Compilation

*This section will be expanded with detailed Mac compilation instructions.*

## 🌐 Service Endpoints

When running, the system exposes these endpoints:

- **Redis**: `localhost:6379` (password: `rhost21`)
- **Weaviate**: `http://localhost:8080`
- **Whisper Server**: `http://localhost:8081`
- **LLM HTTP API**: `http://localhost:8082/process_transcript`
- **Web Dashboard**: `http://localhost:5001`

## 📁 Project Structure

```
project-human/
├── src/                       # Python source code
│   ├── gui_main.py           # Desktop GUI application
│   ├── gui_main_video.py     # Video-enabled GUI variant
│   ├── stt_component.py      # Speech-to-text component
│   ├── tts_component.py      # Text-to-speech component  
│   ├── llm_component.py      # Language model component
│   ├── memory_component.py   # Vector memory management
│   ├── listening_controller.py # Audio input coordination
│   ├── redis_client.py       # Redis client utilities
│   ├── redis_state.py        # Redis state management
│   ├── webinterface/         # FastAPI web application
│   │   ├── app.py           # Main FastAPI application
│   │   ├── routers/         # API route handlers
│   │   ├── static/          # Web assets (CSS, JS)
│   │   ├── templates/       # HTML templates
│   │   └── utils/           # Web utility modules
│   └── utils/               # Shared utility modules
├── whisper.cpp/             # Whisper C++ binaries (if compiled)
│   ├── build/bin/           # Compiled binaries
│   └── models/              # Whisper models
├── logs/                    # Runtime logs and PID files
├── docker-compose.yaml      # Docker service definitions
├── config.json             # Configuration (create from .example)
├── config.json.example     # Configuration template
├── Makefile                # Make-based automation
├── start.sh                # Bash script automation
├── start_webui.sh          # Web interface startup script
├── pyproject.toml          # Python dependencies
├── uv.lock                 # UV lockfile
└── README.md               # This file
```

## 🛠️ Troubleshooting

### Common Issues

**1. Redis Connection Refused**
```bash
# Ensure Docker services are running
./start.sh start-services
```

**2. Port Already in Use (8082, 8081, 5001, etc.)**
```bash
# Stop any existing components
./start.sh stop-components

# Or kill specific processes
lsof -ti:8082 | xargs kill -9  # LLM component
lsof -ti:8081 | xargs kill -9  # Whisper server
lsof -ti:5001 | xargs kill -9  # Web interface
```

**3. Whisper Server Won't Start**
```bash
# Check if whisper binary exists
ls -la whisper.cpp/build/bin/whisper-server

# Check if model exists  
ls -la whisper.cpp/models/ggml-base.en.bin
```

**4. Components Won't Start**
```bash
# Check dependencies
./start.sh setup

# Verify virtual environment
source .venv/bin/activate
python --version
```

### Reset Everything
```bash
# Complete cleanup and restart
./start.sh clean
./start.sh start
```

### Manual Process Management
```bash
# View running processes
ps aux | grep python
ps aux | grep whisper

# Kill specific processes
pkill -f "python src/"
pkill -f whisper-server
```

## 🔧 Advanced Configuration

### Modifying Ports
Edit `config.json` and `docker-compose.yaml` to change default ports. The web interface port can be modified in `src/webinterface/app.py`.

### Web Interface Customization
The web interface is built with FastAPI and includes:
- Templates in `src/webinterface/templates/`
- Static assets in `src/webinterface/static/`
- API routes in `src/webinterface/routers/`

### Adding New Components
1. Create new Python file in `src/`
2. Add start/stop logic to both `Makefile` and `start.sh`
3. Update this README

### Development Mode
For development, you can run components individually in foreground mode to see output directly:

```bash
# Start services first
./start.sh start-services
./start.sh start-whisper

# Run components in terminal (foreground)
python src/gui_main.py              # Desktop GUI
cd src/webinterface && python app.py # Web Interface
python src/stt_component.py         # STT  
python src/llm_component.py         # LLM
python src/tts_component.py         # TTS
```

## 📝 Notes

- **Interface Options**: Choose between desktop GUI (`gui_main.py`) or web interface (`./start_webui.sh`) based on your preference
- **Logging**: Components started individually (`make gui`, `./start.sh stt`) output to terminal. Components started via `start-components` run in background.
- **Process Management**: PID files are stored in `logs/` directory for process tracking.
- **State Persistence**: Redis and Weaviate data persists between restarts via Docker volumes.
- **Dependencies**: The system automatically checks dependencies before starting.
- **Web Development**: The web interface supports hot reload during development for rapid iteration.

## 🤝 Contributing

1. Follow the established component architecture
2. Update both `Makefile` and `start.sh` for new commands
3. Test both management interfaces
4. Update this README for new features

---

For issues or questions, check the troubleshooting section or examine logs with `./start.sh logs`.
