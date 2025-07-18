# Project Human Redis - AI Assistant

A sophisticated multi-component AI assistant system featuring speech-to-text, text-to-speech, language model processing, and multiple interfaces (GUI, terminal, web). The system uses Redis for state management, Weaviate for vector storage, and Whisper.cpp for high-performance speech recognition.

## 🚀 Key Features

- **Multiple Interfaces**: Desktop GUI, terminal interface, and modern web dashboard
- **Real-time Speech Processing**: Advanced STT/TTS capabilities with Whisper.cpp
- **Distributed Architecture**: Component-based design with Redis coordination
- **Vector Memory**: Weaviate integration for intelligent context storage
- **Multiple LLM Backends**: Support for OpenAI, Groq, Ollama, LMStudio, llamafile, and OpenRouter
- **Intelligent Tools**: Weather, news, finance, movies, and entertainment tools
- **Production Ready**: Docker containerization and process management
- **Voice Control**: Wake words and voice commands for hands-free operation

## 🏗️ Architecture

The system consists of several independent components that communicate via Redis:

- **Docker Services**: Redis (state management) + Weaviate (vector database) + Contextionary
- **Whisper.cpp Server**: High-performance C++ binary for speech recognition (port 8081)
- **Python Components**:
  - **GUI** (`gui_main.py`) - Desktop graphical user interface
  - **GUI Video** (`gui_main_video.py`) - Video-enabled GUI variant
  - **Terminal** (`terminal_main.py`) - Terminal-based interface for headless operation
  - **Web Interface** (`webinterface/app.py`) - FastAPI web dashboard (port 5001)
  - **STT** (`stt_component.py`) - Speech-to-text processing component
  - **TTS** (`tts_component.py`) - Text-to-speech synthesis component
  - **LLM** (`llm_component.py`) - Language model processing (port 8082)
  - **Memory** (`memory_component.py`) - Vector memory management
  - **Listening Controller** (`listening_controller.py`) - Audio input coordination

## 📋 Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.11.6** (managed via `.python-version`)
- **UV package manager** (recommended) or pip
- **Git** for cloning the repository

### System Requirements
- **macOS**: Tested and optimized for macOS systems
- **Memory**: At least 4GB RAM (8GB+ recommended for optimal performance)
- **Disk Space**: ~2GB for whisper models and dependencies
- **Microphone**: Required for speech-to-text functionality
- **Speakers**: Required for text-to-speech output

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
cp config.json.gui.example config.json    # For GUI mode
# OR
cp config.json.terminal.example config.json  # For terminal mode
```

### 3. Configure API Keys
Edit `config.json` and add your API keys:
```json
{
  "api_keys": {
    "openai_api_key": "your-openai-key-here",
    "groq_api_key": "your-groq-key-here",
    "replicate_api_key": "your-replicate-key-here",
    "tavily_api_key": "your-tavily-key-here"
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
| `./start.sh terminal` | `make terminal` | Start terminal interface only |
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
| `./start.sh status` | `make status` | Show component status/logs |
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

# OR start with terminal interface (headless)
./start.sh terminal
```

### **Development Workflow (Granular Control)**
```bash
# Start infrastructure first
./start.sh start-services    # Redis + Weaviate
./start.sh start-whisper     # Speech recognition

# Start individual components for testing
./start.sh gui              # Desktop GUI only
# or: make terminal          # Terminal interface only
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
python src/terminal_main.py
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
  terminal: ❌ Not running
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
./start.sh logs terminal
```

## 🖥️ Interface Options

### 1. Desktop GUI (`gui_main.py`)
A modern graphical interface built with PySide6 featuring:
- Visual conversation display
- Real-time status indicators
- Audio level visualization
- Control buttons for voice activation
- System tray integration

### 2. Terminal Interface (`terminal_main.py`)
A full-featured terminal-based interface perfect for headless systems:
- Real-time status dashboard
- Keyboard shortcuts for all functions
- No macOS permissions required
- Colored output with status indicators
- Ideal for remote servers or development

**Terminal Interface Controls:**
- `SPACE` - Start/stop voice recording
- `q` - Quit application
- `s` - Show current status
- `c` - Clear conversation history
- `p` - Pause/resume listening
- `Enter` - Type message directly

### 3. Web Interface (`webinterface/app.py`)
A modern FastAPI-based web application featuring:
- Real-time system monitoring dashboard
- Component management interface
- Interactive API documentation
- WebSocket support for live updates
- Responsive design for desktop and mobile

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

## 🤖 LLM Backend Configuration

The system supports multiple Large Language Model backends. Configure in the `llm` section of `config.json`:

### Supported Backends

1. **OpenAI** (via API keys)
2. **Groq** (via API keys)
3. **OpenRouter** (via router configuration)
4. **Ollama** (local installation)
   ```json
   "ollama": {
     "enabled": "true",
     "port": "11434"
   }
   ```

5. **LMStudio** (local installation)
   ```json
   "lmstudio": {
     "enabled": "true",
     "port": "1234"
   }
   ```

6. **Llama.cpp** (local binary)
   ```json
   "llama_cpp": {
     "enabled": "true",
     "port": "8084",
     "api_key": "not-needed",
     "model": "local-model"
   }
   ```

7. **vLLM** (remote inference)
   ```json
   "vllm": {
     "enabled": "true",
     "bearer": "your-token",
     "model": "your-model", 
     "vast_ai_ip": "ip-address",
     "vast_ai_port": "port"
   }
   ```

## 🛠️ Intelligent Tools

The system includes several built-in tools that the AI can use:

### Available Tools

1. **Weather Tool** (`utils/tools/weather_tool.py`)
   - Real-time weather information
   - Configurable default location
   - Uses WeatherStack API

2. **News Tool** (`utils/tools/news_tool.py`)
   - Latest news articles
   - Powered by Tavily API
   - Configurable news categories

3. **Finance Tool** (`utils/tools/finance_tool.py`)
   - Stock prices and financial data
   - Cryptocurrency information
   - Market analysis

4. **Movies Tool** (`utils/tools/movies_tool.py`)
   - Movie recommendations
   - Box office information
   - Film reviews and ratings

5. **Otaku Tool** (`utils/tools/otaku_tool.py`)
   - Anime and manga information
   - Character details and recommendations
   - Entertainment industry news

### Tool Configuration

Tools are configured in the `tools` section of `config.json`:

```json
{
  "tools": {
    "weather": {
      "api_key": "your-weatherstack-key",
      "base_url": "https://api.weatherstack.com/",
      "default_location": "Tokyo, Japan"
    },
    "news": {
      "tavily_api_key": "your-tavily-key",
      "default_news": "Latest world news",
      "max_results": 3
    },
    "finance": {
      "default_finance": "Latest price of Bitcoin",
      "max_results": 2
    }
  }
}
```

## 🎙️ Whisper.cpp Integration

This project uses whisper.cpp for high-performance speech recognition. The C++ implementation provides faster inference compared to the Python whisper library, especially for real-time applications.

### Setup and Compilation

The whisper.cpp server provides:
- Real-time speech recognition
- Multiple model support
- Hardware acceleration
- Low latency inference

### Model Management
Models are stored in `whisper.cpp/models/`:
- `ggml-base.en.bin` - English-only base model (default)
- Other models can be downloaded as needed

## 🔊 Text-to-Speech Configuration

The system supports multiple TTS providers:

### Replicate (Default)
High-quality neural voice synthesis using Kokoro model:
```json
{
  "tts": {
    "tts_provider": "replicate",
    "replicate_model": "jaaari/kokoro-82m:f559560eb822dc509045f3921a1921234918b91739db4bf3daab2169b71c7a13"
  }
}
```

### OpenAI TTS
```json
{
  "tts": {
    "tts_provider": "openai"
  }
}
```

## 🎯 Voice Control & Wake Words

The system supports hands-free voice control with configurable wake words and stop phrases:

### Configuration
```json
{
  "listening_control": {
    "enabled": true,
    "user_name": "Simon",
    "stop_phrases": ["samantha stop listening", "Samantha stop listening"],
    "start_phrases": ["Samantha wake up", "samantha wake up", "samantha start", "Samantha start"],
    "stop_acknowledgment": "Ok {user_name} I stop listening",
    "start_acknowledgment": "Ok {user_name} I'm listening again"
  }
}
```

### Usage
- Say wake phrases to activate listening
- Say stop phrases to pause listening
- The AI will acknowledge voice commands with audio feedback
- User name is personalized in responses

## 📊 Memory & Context Management

The system uses Weaviate for intelligent context storage and retrieval:

### Memory Configuration
```json
{
  "memory": {
    "db_store": "shortmemdb",
    "collection_name": "ConversationMemory",
    "cluster_url": "http://localhost:8080"
  }
}
```

### Lorebook (User Profile)
Customize the AI's knowledge about the user:
```json
{
  "lorebook": {
    "creator": "Creator's name is ....",
    "likes": "User likes ...",
    "hobbies": "",
    "mangas_artists": "",
    "mangas": "",
    "gaming": ""
  }
}
```

## 🌐 Service Endpoints

When running, the system exposes these endpoints:

- **Redis**: `localhost:6379` (password: `rhost21`)
- **Weaviate**: `http://localhost:8080`
- **Contextionary**: `http://localhost:9999`
- **Whisper Server**: `http://localhost:8081`
- **LLM HTTP API**: `http://localhost:8082/process_transcript`
- **Web Dashboard**: `http://localhost:5001`

## 📁 Project Structure

```
project-human/
├── src/                       # Python source code
│   ├── gui_main.py           # Desktop GUI application
│   ├── gui_main_video.py     # Video-enabled GUI variant
│   ├── terminal_main.py      # Terminal interface (headless)
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
│       ├── prompts.py       # AI prompt templates
│       ├── animation/       # GUI animation utilities
│       └── tools/           # Intelligent tools
│           ├── weather_tool.py    # Weather information
│           ├── news_tool.py       # News articles
│           ├── finance_tool.py    # Financial data
│           ├── movies_tool.py     # Movie information
│           └── otaku_tool.py      # Anime/manga content
├── whisper.cpp/             # Whisper C++ binaries (if compiled)
│   ├── build/bin/           # Compiled binaries
│   └── models/              # Whisper models
├── logs/                    # Runtime logs and PID files
├── redis/                   # Redis data persistence
├── weaviate_data/           # Weaviate vector database
├── docker-compose.yaml      # Docker service definitions
├── config.json             # Configuration (create from .example)
├── config.json.gui.example  # GUI configuration template
├── config.json.terminal.example # Terminal configuration template
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

# Check Redis status
docker ps | grep redis
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

# Download base model if missing
cd whisper.cpp
make base.en
```

**4. Components Won't Start**
```bash
# Check dependencies
./start.sh setup

# Verify virtual environment
source .venv/bin/activate
python --version

# Check configuration
cat config.json | jq .api_keys
```

**5. Audio Issues (macOS)**
```bash
# Check microphone permissions
# Go to System Preferences > Security & Privacy > Privacy > Microphone
# Ensure Terminal/Python has microphone access

# Test audio device
python -c "import sounddevice as sd; print(sd.query_devices())"
```

**6. Missing Dependencies**
```bash
# Reinstall with UV
uv sync --dev

# Or with pip
pip install -e .[dev]

# Check specific packages
python -c "import redis, weaviate, openai"
```

### Reset Everything
```bash
# Complete cleanup and restart
./start.sh clean
./start.sh start

# Or nuclear option
docker-compose down -v
rm -rf logs/*.pid
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

# Check ports
lsof -i :6379  # Redis
lsof -i :8080  # Weaviate
lsof -i :8081  # Whisper
lsof -i :8082  # LLM
lsof -i :5001  # Web Interface
```

### Debug Mode
```bash
# Run components in foreground for debugging
python src/gui_main.py --debug
python src/terminal_main.py --verbose
python src/stt_component.py --log-level DEBUG
```

### Configuration Validation
```bash
# Validate JSON syntax
python -m json.tool config.json

# Test Redis connection
python -c "
import redis
r = redis.Redis(host='localhost', port=6379, password='rhost21', decode_responses=True)
print(r.ping())
"

# Test Weaviate connection
python -c "
import weaviate
client = weaviate.Client('http://localhost:8080')
print(client.is_ready())
"
```

## 🔧 Advanced Configuration

### Modifying Ports
Edit `config.json` and `docker-compose.yaml` to change default ports. The web interface port can be modified in `src/webinterface/app.py`.

### Interface-Specific Configuration
The system supports different configurations for different interfaces:
- `config.json.gui.example` - For desktop GUI interface
- `config.json.terminal.example` - For terminal interface

Key differences:
- `allowed_sources` in rules differ between "gui" and "terminal"
- Some GUI-specific settings are not applicable to terminal mode

### Web Interface Customization
The web interface is built with FastAPI and includes:
- Templates in `src/webinterface/templates/`
- Static assets in `src/webinterface/static/`
- API routes in `src/webinterface/routers/`

### Adding New Components
1. Create new Python file in `src/`
2. Add start/stop logic to both `Makefile` and `start.sh`
3. Update Redis state rules in config
4. Update this README

### Development Mode
For development, you can run components individually in foreground mode to see output directly:

```bash
# Start services first
./start.sh start-services
./start.sh start-whisper

# Run components in terminal (foreground)
python src/gui_main.py              # Desktop GUI
python src/terminal_main.py         # Terminal Interface
cd src/webinterface && python app.py # Web Interface
python src/stt_component.py         # STT  
python src/llm_component.py         # LLM
python src/tts_component.py         # TTS
```

### Custom Prompts
AI prompts can be customized in `src/utils/prompts.py`:
- System prompts
- Tool usage instructions
- Personality configuration

### Audio Configuration
Fine-tune audio settings in config.json:
```json
{
  "stt": {
    "sampling_rate": 16000,
    "chunk_size": 512,
    "vad_threshold": 0.5,
    "amplitude_threshold": 0.05,
    "silence_duration": 2.0,
    "min_audio_length": 1.0,
    "max_recording_duration": 180,
    "temporal_smoothing": {
      "enabled": true,
      "confidence_buffer_size": 5,
      "start_threshold_ratio": 0.7,
      "continue_threshold_ratio": 0.9
    }
  }
}
```

## 🔒 Security Considerations

### API Keys
- Store API keys securely in `config.json`
- Never commit `config.json` to version control
- Use environment variables for production deployment

### Network Security
- Redis requires password authentication
- Web interface runs on localhost by default
- Consider VPN for remote access

### Data Privacy
- Conversation data stored locally in Redis and Weaviate
- Audio data processed locally via Whisper.cpp
- Some TTS providers may send audio data externally

## 📦 Dependencies

### Core Dependencies
- **Python 3.11.6** (exact version required)
- **Redis** (for state management)
- **Weaviate** (for vector storage)
- **FastAPI** (for web interface)
- **PySide6** (for desktop GUI)
- **OpenAI/Groq** (for LLM backends)

### Audio Dependencies
- **sounddevice** (audio I/O)
- **openai-whisper** (speech recognition fallback)
- **silero-vad** (voice activity detection)

### Optional Dependencies
- **pygame** (audio playback)
- **colorama** (terminal colors)
- **onnxruntime** (model optimization)
- **coremltools** (macOS acceleration)

## 📝 Notes

- **Interface Options**: Choose between desktop GUI, terminal interface, or web interface based on your needs and environment
- **Headless Operation**: Terminal interface is perfect for servers and remote systems
- **Logging**: Components started individually output to terminal. Components started via `start-components` run in background with logs in `logs/` directory
- **Process Management**: PID files are stored in `logs/` directory for process tracking
- **State Persistence**: Redis and Weaviate data persists between restarts via Docker volumes
- **Dependencies**: The system automatically checks dependencies before starting
- **Web Development**: The web interface supports hot reload during development for rapid iteration
- **Cross-Platform**: While optimized for macOS, the system can run on Linux with minor modifications

## 🤝 Contributing

1. Follow the established component architecture
2. Update both `Makefile` and `start.sh` for new commands
3. Test both management interfaces
4. Update configuration examples for new features
5. Add tool documentation for new tools
6. Update this README for new features

### Code Style
- Follow PEP 8 for Python code
- Use type hints where applicable
- Add docstrings for new functions and classes
- Maintain consistent logging throughout components

---

For issues or questions, check the troubleshooting section or examine logs with `./start.sh logs [component]`
