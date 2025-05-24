import sys
import random
import redis
import threading
from concurrent.futures import ThreadPoolExecutor
from utils.sqlite_vector import create_db

from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel
from PySide6.QtCore import QTimer, Qt, Signal, QObject
from PySide6.QtGui import QPainter, QColor
from redis_state import RedisState

# Redis state
r = redis.Redis(host='localhost', port=6379, password='rhost21', decode_responses=True)
state = RedisState(r)
CHANNEL = "channel:state"

# Signal bridge for thread-safe Qt updates
class SignalBridge(QObject):
    update_status = Signal(str)
    update_button = Signal(str, bool)  # text, enabled
    start_animation = Signal()
    stop_animation = Signal()
    start_auto_listening = Signal()  # New signal for auto-restart

bridge = SignalBridge()

class KawaiiWaveWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.amplitudes = [0] * 20
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_wave)
        self.is_active = False

    def start_animation(self):
        self.is_active = True
        self.timer.start(100)

    def stop_animation(self):
        self.is_active = False
        self.timer.stop()
        self.amplitudes = [0] * 20
        self.update()

    def update_wave(self):
        if self.is_active:
            self.amplitudes = [random.randint(2, 10) for _ in self.amplitudes]
        else:
            self.amplitudes = [max(0, amp - 1) for amp in self.amplitudes]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        height = self.height()
        
        if not self.amplitudes:
            return
            
        bar_width = width / len(self.amplitudes)

        for i, amp in enumerate(self.amplitudes):
            x = i * bar_width
            bar_height = amp * 5
            y = height / 2 - bar_height / 2
            color = QColor(255, 182, 193)  # Kawaii pink
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(x, y, bar_width * 0.6, bar_height)

class MicControlApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kawaii Mic Assistant")
        self.resize(400, 350)
        self.current_state = "ready"
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.continuous_mode = True  # Default to continuous mode
        
        # Timer for delay after AI speech in continuous mode
        self.continuous_timer = QTimer(self)
        self.continuous_timer.setSingleShot(True)
        self.continuous_timer.timeout.connect(self.auto_start_listening)

        # UI Components
        self.status_label = QLabel("Status: Ready (Continuous) 🌸", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        
        self.talk_button = QPushButton("🎤 Start Talking", self)
        self.talk_button.clicked.connect(self.start_talking)

        self.wave_widget = KawaiiWaveWidget()

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.wave_widget, stretch=1)
        layout.addWidget(self.talk_button)
        self.setLayout(layout)

        # Connect signals for thread-safe updates
        bridge.update_status.connect(self.update_status, Qt.QueuedConnection)
        bridge.update_button.connect(self.update_button, Qt.QueuedConnection)
        bridge.start_animation.connect(self.start_wave_animation, Qt.QueuedConnection)
        bridge.stop_animation.connect(self.stop_wave_animation, Qt.QueuedConnection)
        bridge.start_auto_listening.connect(self.start_auto_listening_delayed, Qt.QueuedConnection)

    def start_auto_listening_delayed(self):
        """Start auto-listening with delay - called from main thread via signal"""
        print("[GUI] 🎯 Auto-restart signal received in main thread")
        self.continuous_timer.start(2000)

    def check_processing_timeout(self):
        """Check if we're still stuck in processing state and reset if needed"""
        if self.current_state == "processing":
            print("[GUI] ⏰ Processing timeout - resetting to ready (likely no transcript)")
            self.current_state = "ready"
            bridge.update_status.emit("Status: Ready (No speech detected) 🌸")
            bridge.update_button.emit("🎤 Start Talking", True)
            bridge.stop_animation.emit()

    def auto_start_listening(self):
        """Automatically start listening in continuous mode"""
        if self.continuous_mode and self.current_state == "ready":
            print("[GUI] Auto-starting listening in continuous mode")
            bridge.update_status.emit("Status: Auto-listening... 🔄")
            self.start_talking()

    def start_talking(self):
        """Trigger the STT process through Redis state"""
        print(f"[GUI] 🎙️ start_talking() called - State: {self.current_state}")
        
        if self.current_state == "ready":
            self.current_state = "requesting"
            print("[GUI] 📢 Starting listening")
            bridge.update_status.emit("Status: Listening... ⚡")
            bridge.update_button.emit("🔄 Starting...", False)
            bridge.start_animation.emit()
            
            # Use RedisState to trigger STT with proper source and priority
            # Run in executor to avoid blocking the UI
            self.executor.submit(self._trigger_stt)
        else:
            print(f"[GUI] ❌ Cannot start talking - wrong state: {self.current_state}")

    def _trigger_stt(self):
        """Helper method to trigger STT asynchronously"""
        try:
            print("[GUI] 🚀 _trigger_stt called")
            print("[GUI] 🔍 Checking current Redis state before trigger...")
            
            # Check current state
            current_user_wants = state.get_value("user_wants_to_talk")
            current_ai_speaking = state.get_value("ai_speaking")
            current_human_speaking = state.get_value("human_speaking")
            
            print(f"[GUI]    user_wants_to_talk: {current_user_wants}")
            print(f"[GUI]    ai_speaking: {current_ai_speaking}")
            print(f"[GUI]    human_speaking: {current_human_speaking}")
            
            # Use higher priority than STT component (which uses 20)
            print("[GUI] 🚀 Setting user_wants_to_talk = True with source=gui, priority=25")
            result = state.set_value("user_wants_to_talk", "True", source="gui", priority=25)
            print(f"[GUI] 📊 State update result: {result}")
            
            if result:
                print("[GUI] ✅ Successfully triggered user_wants_to_talk")
            else:
                print("[GUI] ❌ Failed to set user_wants_to_talk - check rules")
                
        except Exception as e:
            print(f"[GUI] ❌ Error triggering STT: {e}")
            import traceback
            traceback.print_exc()
            # Reset to ready state on error
            bridge.update_status.emit("Status: Error - Ready 🌸")
            bridge.update_button.emit("🎤 Start Talking", True)
            bridge.stop_animation.emit()

    def update_status(self, text):
        """Update status label"""
        self.status_label.setText(text)

    def update_button(self, text, enabled):
        """Update button text and state"""
        self.talk_button.setText(text)
        self.talk_button.setEnabled(enabled)
        
    def start_wave_animation(self):
        """Start wave animation (thread-safe)"""
        self.wave_widget.start_animation()
        
    def stop_wave_animation(self):
        """Stop wave animation (thread-safe)"""
        self.wave_widget.stop_animation()

    def handle_state_change(self, key, value):
        """Handle different state changes from Redis"""
        print(f"[GUI] State change: {key} = {value}")
        
        if key == "human_speaking":
            if value == "True":
                self.current_state = "speaking"
                bridge.update_status.emit("Status: Speaking... 🗣️")
                bridge.update_button.emit("🔄 Speaking...", False)
                bridge.start_animation.emit()
            else:
                # Check if we should go to processing or back to ready
                if self.current_state == "speaking":
                    # Just finished speaking - check if STT will trigger LLM
                    self.current_state = "processing"
                    bridge.update_status.emit("Status: Processing... ⚡")
                    bridge.update_button.emit("🔄 Processing...", False)
                
        elif key == "ai_thinking":
            if value == "True":
                self.current_state = "thinking"
                bridge.update_status.emit("Status: Thinking... 🧠")
                bridge.update_button.emit("🔄 Thinking...", False)
                bridge.start_animation.emit()
                
        elif key == "ai_speaking":
            if value == "True":
                self.current_state = "ai_speaking"
                bridge.update_status.emit("Status: AI Speaking 🤖")
                bridge.update_button.emit("🔄 AI Speaking...", False)
                bridge.start_animation.emit()
            else:
                # AI finished speaking - auto-restart listening in continuous mode
                print(f"[GUI] 🎤 AI finished speaking. Emitting auto-restart signal")
                self.current_state = "ready"
                bridge.update_status.emit("Status: AI Done - Auto-listening soon... 🔄")
                bridge.update_button.emit("🔄 Auto-listening...", False)
                bridge.stop_animation.emit()
                
                # Use signal to safely trigger timer from main thread
                bridge.start_auto_listening.emit()
                
        elif key == "stt_ready":
            if value == "True":
                self.current_state = "stt_complete"
                bridge.update_status.emit("Status: Speech Recognized ✅")
                # Keep button disabled, waiting for LLM
            elif value == "False" and self.current_state == "processing":
                # STT explicitly saying no speech detected
                print("[GUI] 🚫 STT reports no speech detected - auto-restarting in continuous mode")
                self.current_state = "ready"
                bridge.update_status.emit("Status: No speech - Auto-listening soon... 🔄")
                bridge.update_button.emit("🔄 Auto-listening...", False)
                bridge.stop_animation.emit()
                
                # Auto-restart listening in continuous mode after brief delay
                bridge.start_auto_listening.emit()
                
        elif key == "tts_ready":
            if value == "True":
                self.current_state = "preparing_speech"
                bridge.update_status.emit("Status: Preparing Speech... 🔄")

def redis_listener():
    """Listen for Redis pub/sub messages and update GUI accordingly"""
    pubsub = r.pubsub()
    pubsub.subscribe(CHANNEL)
    print("[GUI] Listening to Redis state changes...")
    
    try:
        for message in pubsub.listen():
            if message["type"] != "message":
                continue
                
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode()
            
            if isinstance(data, str) and "=" in data:
                key, value = data.split("=", 1)
                
                # Get the main window reference safely
                app = QApplication.instance()
                if app and hasattr(app, 'main_window'):
                    app.main_window.handle_state_change(key, value)
    except Exception as e:
        print(f"[GUI] Error in Redis listener: {e}")

def main():
    # Create db file and collection
    create_db()

    # Start the Redis listener in a separate thread
    redis_thread = threading.Thread(target=redis_listener, daemon=True)
    redis_thread.start()

    # Create and run the Qt application
    app = QApplication(sys.argv)
    window = MicControlApp()
    
    # Store reference to window for the Redis listener
    app.main_window = window
    
    window.show()
    
    print("[GUI] Application started. Ready to interact!")
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("[GUI] Application interrupted by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
