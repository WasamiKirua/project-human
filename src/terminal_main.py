#!/usr/bin/env python3
"""
Project Human - Terminal Interface
Replaces the GUI with a terminal-based dashboard and keyboard controls.
No macOS permissions required - uses terminal-focused input.
"""

import sys
import os
import select
import threading
import time
import json
import requests
import signal
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from redis_state import RedisState
from redis_client import create_redis_client
from listening_controller import ListeningController

# Try to import colorama for colored output
try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    # Fallback if colorama not available
    class MockColor:
        def __getattr__(self, name):
            return ""
    Fore = Back = Style = MockColor()
    COLORAMA_AVAILABLE = False

# Redis config & state
r = create_redis_client()
state = RedisState(r)
CHANNEL = "channel:state"

class ServiceHealthChecker:
    """Port of health checker from GUI component"""
    
    def __init__(self):
        self.config = self.load_config()
        self.last_check = None
    
    def load_config(self):
        """Load configuration for health checks"""
        try:
            # Look for config.json in current directory or parent
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
            
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Health] ⚠️ Could not load config: {e}")
            return {}
    
    def check_redis(self):
        """Check if Redis is accessible"""
        try:
            r.ping()
            return {"status": "healthy", "message": "Connected"}
        except Exception as e:
            return {"status": "unhealthy", "message": "Connection failed"}
    
    def check_weaviate(self):
        """Check if Weaviate is accessible"""
        try:
            response = requests.get("http://localhost:8080/v1/.well-known/ready", timeout=3)
            if response.status_code == 200:
                return {"status": "healthy", "message": "Connected"}
            else:
                return {"status": "unhealthy", "message": f"HTTP {response.status_code}"}
        except Exception:
            return {"status": "unhealthy", "message": "Connection failed"}
    
    def check_whisper_server(self):
        """Check if Whisper server is accessible"""
        try:
            whisper_health_url = self.config.get("stt", {}).get("whisper_health_url", "http://localhost:8081/health")
            response = requests.get(whisper_health_url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "ok":
                    return {"status": "healthy", "message": "Ready"}
            return {"status": "unhealthy", "message": "Server not ready"}
        except Exception:
            return {"status": "unhealthy", "message": "Connection failed"}
    
    def check_services_for_stt(self):
        """Check services needed for speech-to-text"""
        redis_status = self.check_redis()
        whisper_status = self.check_whisper_server()
        
        redis_ok = redis_status["status"] == "healthy"
        whisper_ok = whisper_status["status"] == "healthy"
        
        if redis_ok and whisper_ok:
            return True, "STT Ready"
        else:
            missing = []
            if not redis_ok: missing.append("Redis")
            if not whisper_ok: missing.append("Whisper")
            error_msg = f"STT unavailable: {', '.join(missing)} down"
            return False, error_msg
    
    def check_all_services(self):
        """Full system health check"""
        redis_status = self.check_redis()
        weaviate_status = self.check_weaviate()
        whisper_status = self.check_whisper_server()
        
        services = [
            ("Redis", redis_status),
            ("Weaviate", weaviate_status), 
            ("Whisper", whisper_status)
        ]
        
        all_healthy = True
        for name, status in services:
            if status["status"] != "healthy":
                all_healthy = False
        
        if all_healthy:
            return True, "All Systems Healthy"
        else:
            unhealthy = [name for name, status in services if status["status"] != "healthy"]
            error_msg = f"Issues: {', '.join(unhealthy)}"
            return False, error_msg


class TerminalInterface:
    """Terminal-based interface for Project Human"""
    
    def __init__(self):
        self.running = True
        self.current_state = "ready"
        self.last_status = ""
        self.health_status = "checking"
        self.listening_status = "listening"
        self.continuous_mode = True
        
        # Auto-restart timer (like GUI)
        self.auto_restart_timer = None
        
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.health_checker = ServiceHealthChecker()
        
        # Initialize listening controller to check current status
        try:
            listening_controller = ListeningController()
            self.listening_status = listening_controller.get_listening_status()
        except Exception as e:
            print(f"[Terminal] ⚠️ Could not initialize listening status: {e}")
            self.listening_status = "listening"
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Start Redis listener thread
        self.redis_thread = threading.Thread(target=self.redis_listener, daemon=True)
        self.redis_thread.start()
        
        # Start display update thread (less frequent updates)
        self.display_thread = threading.Thread(target=self.display_loop, daemon=True)
        self.display_thread.start()
        
        print("[Terminal] Starting up...")
        
        # Initial health check
        self.executor.submit(self.startup_health_check)
    
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C and other signals"""
        print(f"\n[Terminal] Received signal {signum}, shutting down...")
        self.running = False
        sys.exit(0)
    
    def clear_screen(self):
        """Clear terminal screen"""
        # Use ANSI escape codes for better compatibility
        print('\033[2J\033[H', end='', flush=True)
    
    def render_dashboard(self):
        """Render the main dashboard"""
        # Get current time
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Status colors and icons
        if self.current_state == "ready":
            status_color = Fore.GREEN
            status_icon = "✅"
        elif self.current_state in ["listening", "requesting"]:
            status_color = Fore.BLUE
            status_icon = "🎤"
        elif self.current_state in ["speaking", "processing"]:
            status_color = Fore.YELLOW
            status_icon = "⚡"
        elif self.current_state in ["thinking", "ai_thinking"]:
            status_color = Fore.MAGENTA
            status_icon = "🧠"
        elif self.current_state == "ai_speaking":
            status_color = Fore.CYAN
            status_icon = "🤖"
        else:
            status_color = Fore.RED
            status_icon = "❌"
        
        # Health status
        if self.health_status == "healthy" or "Healthy" in str(self.health_status):
            health_color = Fore.GREEN
            health_icon = "🟢"
        elif self.health_status == "checking":
            health_color = Fore.YELLOW
            health_icon = "🟡"
        else:
            health_color = Fore.RED
            health_icon = "🔴"
        
        # Listening status
        if self.listening_status == "listening":
            listen_color = Fore.GREEN
            listen_icon = "✨"
            listen_text = "Active"
        else:
            listen_color = Fore.YELLOW
            listen_icon = "⏸️"
            listen_text = "Paused (say 'samantha wake up')"
        
        # Build simplified dashboard
        lines = []
        lines.append("=" * 65)
        lines.append(f"{Fore.CYAN}{Style.BRIGHT}            🤖 Project Human Assistant{Style.RESET_ALL}")
        lines.append("=" * 65)
        lines.append("")
        lines.append(f"  {status_color}{Style.BRIGHT}Status: {status_icon} {self.last_status}{Style.RESET_ALL}")
        lines.append(f"  {health_color}{Style.BRIGHT}Health: {health_icon} {self.health_status}{Style.RESET_ALL}")
        lines.append(f"  {Fore.BLUE}{Style.BRIGHT}Mode:   🔄 Continuous listening enabled{Style.RESET_ALL}")
        lines.append(f"  {listen_color}{Style.BRIGHT}Listen: {listen_icon} {listen_text}{Style.RESET_ALL}")
        lines.append("")
        lines.append(f"  {Fore.WHITE}{Style.BRIGHT}⚠️  Focus this terminal window, then:{Style.RESET_ALL}")
        lines.append(f"  {Fore.GREEN}[SPACE] Start listening{Style.RESET_ALL}")
        lines.append(f"  {Fore.RED}[Q]     Quit{Style.RESET_ALL}")
        lines.append("")
        lines.append(f"  {Fore.WHITE}Time: {current_time}  State: {self.current_state}{Style.RESET_ALL}")
        lines.append("=" * 65)
        lines.append("")
        
        return '\n'.join(lines)
    
    def display_loop(self):
        """Minimal display loop - no continuous printing"""
        while self.running:
            try:
                # Just keep the thread alive, no printing
                time.sleep(5.0)
            except Exception as e:
                print(f"[Terminal] Display error: {e}")
                time.sleep(1)
    
    def setup_terminal_input(self):
        """Setup terminal input handling (simplified approach)"""
        
        try:
            while self.running:
                try:
                    # Simple input approach that works with display updates
                    print(f"\n{Fore.CYAN}Enter command:{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[s] or [space]{Style.RESET_ALL} = Start listening")
                    print(f"  {Fore.RED}[q]{Style.RESET_ALL} = Quit")
                    
                    choice = input(f"{Fore.WHITE}> {Style.RESET_ALL}").lower().strip()
                    
                    if choice in ['s', 'space', '', ' ']:
                        print(f"{Fore.BLUE}[Terminal] 🎙️ You chose to start listening...{Style.RESET_ALL}")
                        self.trigger_listening()
                    elif choice == 'q':
                        print(f"{Fore.RED}[Terminal] 👋 Quitting...{Style.RESET_ALL}")
                        self.handle_key_press('q')
                    else:
                        print(f"{Fore.YELLOW}Unknown command: {choice}{Style.RESET_ALL}")
                        
                except (EOFError, KeyboardInterrupt):
                    self.quit_application()
                    break
                except Exception as e:
                    print(f"[Terminal] Input error: {e}")
                    time.sleep(1)
                        
        except Exception as e:
            print(f"[Terminal] Fatal input error: {e}")
            self.quit_application()
    
    def handle_key_press(self, key):
        """Handle keyboard input"""
        try:
            if key == ' ':  # SPACE key or 's' command mapped to space
                self.trigger_listening()
            elif key.lower() == 'q':
                self.quit_application()
            elif ord(key) == 3:  # Ctrl+C
                self.quit_application()
            # Ignore other keys
        except Exception as e:
            print(f"[Terminal] Key handling error: {e}")
    
    def trigger_listening(self):
        """Trigger STT process (same as GUI button)"""
        print(f"\n{Fore.CYAN}[Terminal] 🎙️ Triggering listening - State: {self.current_state}{Style.RESET_ALL}")
        
        # Check if listening is paused - but still allow STT for control commands
        listening_paused = state.get_value("listening_paused") 
        if listening_paused == "True":
            print(f"{Fore.YELLOW}[Terminal] 🎯 Starting STT in PAUSED mode - control commands only{Style.RESET_ALL}")
        
        if self.current_state == "ready":
            self.current_state = "requesting"
            print(f"{Fore.GREEN}[Terminal] 📢 Starting listening with health check...{Style.RESET_ALL}")
            
            # Run health check and STT trigger in executor
            self.executor.submit(self._check_and_start_stt)
        else:
            print(f"{Fore.RED}[Terminal] ❌ Cannot start talking - wrong state: {self.current_state}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[Terminal] 💡 Wait for current operation to complete or restart the system{Style.RESET_ALL}")
    
    def _check_and_start_stt(self):
        """Check health and start STT if prerequisites are met"""
        try:
            print(f"{Fore.BLUE}[Terminal] 🔍 Checking system health...{Style.RESET_ALL}")
            
            # Check STT prerequisites
            stt_ready, stt_message = self.health_checker.check_services_for_stt()
            
            if not stt_ready:
                print(f"{Fore.RED}[Terminal] ❌ Health check failed: {stt_message}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}[Terminal] 💡 Please start services first:{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}   1. ./start.sh start-services  # Start Redis + Weaviate{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}   2. ./start.sh start-whisper   # Start Whisper server{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}   3. Then try listening again{Style.RESET_ALL}")
                self.last_status = f"❌ {stt_message}"
                self.current_state = "ready"
                return
            
            # Prerequisites OK, proceed with STT
            print(f"{Fore.GREEN}[Terminal] ✅ Health check passed, starting STT...{Style.RESET_ALL}")
            self.last_status = "Listening for speech..."
            
            # Check current Redis state
            current_user_wants = state.get_value("user_wants_to_talk")
            current_ai_speaking = state.get_value("ai_speaking")
            current_human_speaking = state.get_value("human_speaking")
            
            print(f"{Fore.CYAN}[Terminal]    user_wants_to_talk: {current_user_wants}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[Terminal]    ai_speaking: {current_ai_speaking}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[Terminal]    human_speaking: {current_human_speaking}{Style.RESET_ALL}")
            
            # Use priority 38 - same as GUI
            print(f"{Fore.GREEN}[Terminal] 🚀 Setting user_wants_to_talk = True with source=terminal, priority=38{Style.RESET_ALL}")
            result = state.set_value("user_wants_to_talk", "True", source="terminal", priority=38)
            print(f"{Fore.CYAN}[Terminal] 📊 State update result: {result}{Style.RESET_ALL}")
            
            if result:
                print(f"{Fore.GREEN}[Terminal] ✅ Successfully triggered user_wants_to_talk{Style.RESET_ALL}")
                print(f"{Fore.GREEN}[Terminal] 🎤 STT should now be listening for speech...{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[Terminal] ❌ Failed to set user_wants_to_talk - check rules{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}[Terminal] 💡 This usually means config.json rules need 'terminal' as allowed source{Style.RESET_ALL}")
                self.last_status = "❌ State management error"
                self.current_state = "ready"
                
        except Exception as e:
            print(f"{Fore.RED}[Terminal] ❌ Error in health check/STT trigger: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.last_status = "❌ Error - Ready"
            self.current_state = "ready"
    
    def startup_health_check(self):
        """Health check when terminal starts"""
        healthy, message = self.health_checker.check_all_services()
        
        if healthy:
            self.health_status = "All Systems Healthy"
            self.last_status = "Ready - Press [SPACE] to start listening"
        else:
            self.health_status = message
            self.last_status = f"⚠️ {message}"
    
    def start_auto_restart_timer(self):
        """Start auto-restart timer (same as GUI continuous_timer)"""
        # Cancel any existing timer
        if self.auto_restart_timer:
            self.auto_restart_timer.cancel()
        
        print(f"{Fore.CYAN}[Terminal] 🕐 Auto-restart timer started (2 seconds)...{Style.RESET_ALL}")
        
        # Start new timer for 2 seconds (same as GUI)
        self.auto_restart_timer = threading.Timer(2.0, self.auto_start_listening)
        self.auto_restart_timer.start()
    
    def auto_start_listening(self):
        """Automatically start listening in continuous mode (same as GUI)"""
        if self.continuous_mode and self.current_state == "ready":
            # Check if listening is paused (same logic as GUI)
            listening_paused = state.get_value("listening_paused")
            if listening_paused == "True":
                print(f"{Fore.YELLOW}[Terminal] ⏸️ PAUSED mode - no auto-restart, waiting for manual trigger{Style.RESET_ALL}")
                self.last_status = "Paused (listening for 'start listening') ⏸️"
                # DO NOT auto-restart when paused - wait for manual trigger or start command
                return
            else:
                print(f"{Fore.GREEN}[Terminal] 🔄 Auto-starting listening in continuous mode{Style.RESET_ALL}")
                self.last_status = "Auto-listening..."
                self.trigger_listening()
        else:
            print(f"{Fore.YELLOW}[Terminal] ⚠️ Auto-restart skipped - continuous_mode: {self.continuous_mode}, state: {self.current_state}{Style.RESET_ALL}")
    
    def quit_application(self):
        """Quit the terminal application"""
        print(f"\n[Terminal] 👋 Shutting down...")
        
        # Cancel any pending auto-restart timer
        if self.auto_restart_timer:
            self.auto_restart_timer.cancel()
            print(f"[Terminal] 🕐 Cancelled auto-restart timer")
        
        self.running = False
        sys.exit(0)
    
    def redis_listener(self):
        """Listen for Redis pub/sub messages and update status accordingly"""
        pubsub = r.pubsub()
        pubsub.subscribe(CHANNEL)
        print("[Terminal] Listening to Redis state changes...")
        
        try:
            for message in pubsub.listen():
                if not self.running:
                    break
                    
                if message["type"] != "message":
                    continue
                    
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                
                if isinstance(data, str) and "=" in data:
                    key, value = data.split("=", 1)
                    self.handle_state_change(key, value)
        except Exception as e:
            print(f"[Terminal] Error in Redis listener: {e}")
    
    def handle_state_change(self, key, value):
        """Handle different state changes from Redis"""
        print(f"[Terminal] State change: {key} = {value}")
        
        if key == "human_speaking":
            if value == "True":
                self.current_state = "speaking"
                self.last_status = "Speaking..."
            else:
                if self.current_state == "speaking":
                    self.current_state = "processing"
                    self.last_status = "Processing speech..."
                
        elif key == "ai_thinking":
            if value == "True":
                self.current_state = "thinking"
                self.last_status = "AI thinking..."
                
        elif key == "ai_speaking":
            if value == "True":
                self.current_state = "ai_speaking"
                self.last_status = "AI speaking..."
            else:
                # AI finished speaking - auto-restart listening in continuous mode (same as GUI)
                print(f"{Fore.GREEN}[Terminal] 🎤 AI finished speaking. Starting auto-restart...{Style.RESET_ALL}")
                self.current_state = "ready"
                self.last_status = "AI Done - Auto-listening soon..."
                
                # Start auto-restart timer (2 seconds delay like GUI)
                self.start_auto_restart_timer()
                
        elif key == "stt_ready":
            if value == "True":
                self.current_state = "stt_complete"
                self.last_status = "Speech recognized ✅"
            elif value == "False" and self.current_state == "processing":
                # STT explicitly saying no speech detected - auto-restart (same as GUI)
                print(f"{Fore.YELLOW}[Terminal] 🚫 STT reports no speech detected - auto-restarting{Style.RESET_ALL}")
                self.current_state = "ready"
                self.last_status = "No speech - Auto-listening soon..."
                
                # Auto-restart listening in continuous mode after brief delay (same as GUI)
                self.start_auto_restart_timer()
                
        elif key == "tts_ready":
            if value == "True":
                self.current_state = "preparing_speech"
                self.last_status = "Preparing speech..."
                
        elif key == "terminal_listening_status" or key == "gui_listening_status":
            # Handle listening status updates
            self.listening_status = value
            
        elif key == "listening_paused":
            if value == "True":
                self.listening_status = "paused"
            else:
                self.listening_status = "listening"
    
    def run(self):
        """Main run loop"""
        try:
            print(f"[Terminal] 🚀 Project Human Terminal Interface Starting...")
            print(f"[Terminal] 📱 Web interface available at: http://localhost:5001")
            
            # Give display thread time to start and show initial dashboard
            time.sleep(2)
            
            # Show initial dashboard
            self.clear_screen()
            print(self.render_dashboard())
            
            # Start input handling in a separate thread
            self.input_thread = threading.Thread(target=self.setup_terminal_input, daemon=True)
            self.input_thread.start()
            
            # Keep main thread alive
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print(f"\n[Terminal] Interrupted by user")
                
        except KeyboardInterrupt:
            print(f"\n[Terminal] Interrupted by user")
        except Exception as e:
            print(f"[Terminal] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            print(f"[Terminal] 👋 Goodbye!")


def main():
    """Main entry point"""
    try:
        terminal = TerminalInterface()
        terminal.run()
    except KeyboardInterrupt:
        print("\n[Terminal] Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"[Terminal] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
