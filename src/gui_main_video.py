import sys
import random
import threading
import time
import json
import requests
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PySide6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QLabel, QSizePolicy)
from PySide6.QtCore import QTimer, Qt, Signal, QObject, QUrl, QSize
from PySide6.QtGui import QPainter, QColor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from redis_state import RedisState
from redis_client import create_redis_client
from listening_controller import ListeningController

# Redis config & state
r = create_redis_client()
state = RedisState(r)

CHANNEL = "channel:state"

# Signal bridge for thread-safe Qt updates
class SignalBridge(QObject):
    update_status = Signal(str)
    update_button = Signal(str, bool)  # text, enabled
    start_animation = Signal()
    stop_animation = Signal()
    start_auto_listening = Signal()  # New signal for auto-restart
    switch_to_idle_video = Signal()  # Signal for switching to idle video
    switch_to_speaking_video = Signal()  # Signal for switching to speaking video
    update_listening_status = Signal(str)  # NEW: "listening" or "paused"

bridge = SignalBridge()

class ServiceHealthChecker:
    def __init__(self):
        self.config = self.load_config()
        self.last_check = None
    
    def load_config(self):
        """Load configuration for health checks"""
        try:
            with open('config.json', 'r') as f:
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
        print(f"[Health] 🎤 Checking STT prerequisites...")
        
        redis_status = self.check_redis()
        whisper_status = self.check_whisper_server()
        
        redis_ok = redis_status["status"] == "healthy"
        whisper_ok = whisper_status["status"] == "healthy"
        
        print(f"[Health] {'✅' if redis_ok else '❌'} Redis: {redis_status['message']}")
        print(f"[Health] {'✅' if whisper_ok else '❌'} Whisper: {whisper_status['message']}")
        
        if redis_ok and whisper_ok:
            print(f"[Health] 🎉 STT ready to go!")
            return True, "STT Ready"
        else:
            missing = []
            if not redis_ok: missing.append("Redis")
            if not whisper_ok: missing.append("Whisper")
            error_msg = f"STT unavailable: {', '.join(missing)} down"
            print(f"[Health] ❌ {error_msg}")
            return False, error_msg
    
    def check_all_services(self):
        """Full system health check"""
        print(f"\n[Health] 🏥 Full system health check...")
        
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
            icon = "✅" if status["status"] == "healthy" else "❌"
            print(f"[Health] {icon} {name}: {status['message']}")
            if status["status"] != "healthy":
                all_healthy = False
        
        if all_healthy:
            print(f"[Health] 🎉 All services healthy!")
            return True, "All Systems Healthy"
        else:
            unhealthy = [name for name, status in services if status["status"] != "healthy"]
            error_msg = f"Issues: {', '.join(unhealthy)}"
            print(f"[Health] ⚠️ {error_msg}")
            return False, error_msg

class KawaiiWaveWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.amplitudes = [0] * 15  # Reduced number for smaller widget
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_wave)
        self.is_active = False
        
        # Set smaller fixed size for wave widget
        self.setFixedSize(200, 60)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def start_animation(self):
        self.is_active = True
        self.timer.start(100)

    def stop_animation(self):
        self.is_active = False
        self.timer.stop()
        self.amplitudes = [0] * 15
        self.update()

    def update_wave(self):
        if self.is_active:
            self.amplitudes = [random.randint(2, 8) for _ in self.amplitudes]
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
            bar_height = amp * 4  # Reduced height multiplier
            y = height / 2 - bar_height / 2
            color = QColor(255, 182, 193)  # Kawaii pink
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(x, y, bar_width * 0.6, bar_height)

class VideoManager(QObject):
    """Manages video playback and smooth transitions"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Video file paths
        self.idle_video_path = os.path.join("src", "utils", "animation", "1_blink.mp4")
        self.speaking_video_path = os.path.join("src", "utils", "animation", "1_no_audio.mp4")
        
        # Check if video files exist
        self.videos_available = self._check_video_files()
        
        # Media players for smooth switching
        self.current_player = None
        self.idle_player = None
        self.speaking_player = None
        
        # Video widget
        self.video_widget = QVideoWidget()
        
        if self.videos_available:
            self._setup_players()
        
        print(f"[Video] Video Manager initialized, files available: {self.videos_available}")
    
    def _check_video_files(self):
        """Check if both video files exist"""
        idle_exists = os.path.exists(self.idle_video_path)
        speaking_exists = os.path.exists(self.speaking_video_path)
        
        print(f"[Video] Idle video ({self.idle_video_path}): {'✅' if idle_exists else '❌'}")
        print(f"[Video] Speaking video ({self.speaking_video_path}): {'✅' if speaking_exists else '❌'}")
        
        return idle_exists and speaking_exists
    
    def _setup_players(self):
        """Setup media players for both videos"""
        # Idle video player
        self.idle_player = QMediaPlayer()
        self.idle_audio_output = QAudioOutput()
        self.idle_player.setAudioOutput(self.idle_audio_output)
        self.idle_player.setVideoOutput(self.video_widget)
        self.idle_player.setSource(QUrl.fromLocalFile(os.path.abspath(self.idle_video_path)))
        
        # Speaking video player  
        self.speaking_player = QMediaPlayer()
        self.speaking_audio_output = QAudioOutput()
        self.speaking_player.setAudioOutput(self.speaking_audio_output)
        self.speaking_player.setVideoOutput(self.video_widget)
        self.speaking_player.setSource(QUrl.fromLocalFile(os.path.abspath(self.speaking_video_path)))
        
        # Connect signals for looping
        self.idle_player.mediaStatusChanged.connect(self._on_idle_media_status_changed)
        self.speaking_player.mediaStatusChanged.connect(self._on_speaking_media_status_changed)
        
        # Mute audio outputs (since we only want video)
        self.idle_audio_output.setMuted(True)
        self.speaking_audio_output.setMuted(True)
        
        print("[Video] Media players setup complete")
    
    def _on_idle_media_status_changed(self, status):
        """Handle idle video status changes for looping"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.current_player == self.idle_player:
                self.idle_player.setPosition(0)
                self.idle_player.play()
    
    def _on_speaking_media_status_changed(self, status):
        """Handle speaking video status changes for looping"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.current_player == self.speaking_player:
                self.speaking_player.setPosition(0)
                self.speaking_player.play()
    
    def start_idle_video(self):
        """Start playing idle video (1_blink.mp4)"""
        if not self.videos_available:
            print("[Video] ❌ Videos not available")
            return
            
        print("[Video] 🎬 Switching to idle video")
        
        # Stop current player
        if self.current_player:
            self.current_player.stop()
        
        # Switch to idle player
        self.current_player = self.idle_player
        self.idle_player.setVideoOutput(self.video_widget)
        self.idle_player.setPosition(0)
        self.idle_player.play()
    
    def start_speaking_video(self):
        """Start playing speaking video (1_no_audio.mp4)"""
        if not self.videos_available:
            print("[Video] ❌ Videos not available")
            return
            
        print("[Video] 🎬 Switching to speaking video")
        
        # Stop current player
        if self.current_player:
            self.current_player.stop()
        
        # Switch to speaking player
        self.current_player = self.speaking_player
        self.speaking_player.setVideoOutput(self.video_widget)
        self.speaking_player.setPosition(0)
        self.speaking_player.play()
    
    def get_video_widget(self):
        """Get the video widget for layout"""
        return self.video_widget
    
    def stop_all(self):
        """Stop all video playback"""
        if self.idle_player:
            self.idle_player.stop()
        if self.speaking_player:
            self.speaking_player.stop()
        self.current_player = None
        print("[Video] 🛑 All video playback stopped")

class MicControlApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kawaii AI Assistant")
        
        # Initialize video manager
        self.video_manager = VideoManager(self)
        
        # Calculate window size based on video availability
        if self.video_manager.videos_available:
            # Set window size optimized for 9:16 video with UI elements
            self.resize(320, 580)  # More compact size for 9:16 content + minimal UI
        else:
            # Fallback to original size if no videos
            self.resize(400, 400)
        
        self.current_state = "ready"
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.continuous_mode = True  # Default to continuous mode
        
        # Add health checker
        self.health_checker = ServiceHealthChecker()
        
        # Timer for delay after AI speech in continuous mode
        self.continuous_timer = QTimer(self)
        self.continuous_timer.setSingleShot(True)
        self.continuous_timer.timeout.connect(self.auto_start_listening)

        self._setup_ui()
        self._connect_signals()
        
        # Start idle video immediately
        if self.video_manager.videos_available:
            QTimer.singleShot(500, self.video_manager.start_idle_video)
            
        # Auto health check on startup (after 3 seconds) - terminal logging only
        QTimer.singleShot(3000, self.startup_health_check)
            
        # Initialize listening status
        QTimer.singleShot(1000, self.initialize_listening_status)

    def startup_health_check(self):
        """Health check when GUI starts - terminal logging only"""
        def run_startup_check():
            print(f"\n[Health] 🚀 Startup health check...")
            healthy, message = self.health_checker.check_all_services()
            
            if healthy:
                print("[Health] 🎉 All systems ready!")
            else:
                print(f"[Health] ⚠️ {message}")
        
        self.executor.submit(run_startup_check)
    
    def manual_health_check(self):
        """Manual health check triggered by button - terminal logging only"""
        def run_manual_check():
            healthy, message = self.health_checker.check_all_services()
            print(f"[Health] Manual check: {message}")
        
        self.executor.submit(run_manual_check)

    def _setup_ui(self):
        """Setup the user interface"""
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Status label at top
        self.status_label = QLabel("Status: Starting up... 🚀", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px;")
        main_layout.addWidget(self.status_label)
        
        # NEW: Kawaii listening status indicator
        self.listening_status_label = QLabel("✨ Listening~", self)
        self.listening_status_label.setAlignment(Qt.AlignCenter)
        self.listening_status_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                padding: 3px 8px;
                border-radius: 12px;
                background-color: #E8F5E8;
                color: #4CAF50;
                margin: 2px;
            }
        """)
        main_layout.addWidget(self.listening_status_label)
        
        # Video widget (main content area)
        if self.video_manager.videos_available:
            video_widget = self.video_manager.get_video_widget()
            video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            main_layout.addWidget(video_widget, stretch=1)
            
            # Wave widget positioned at bottom of video area
            wave_container = QHBoxLayout()
            wave_container.addStretch()
            self.wave_widget = KawaiiWaveWidget()
            wave_container.addWidget(self.wave_widget)
            wave_container.addStretch()
            main_layout.addLayout(wave_container)
        else:
            # Fallback layout without video
            self.wave_widget = KawaiiWaveWidget()
            main_layout.addWidget(self.wave_widget, stretch=1)
        
        # Button area - talk button and health button
        self.talk_button = QPushButton("🎤 Start Talking", self)
        self.talk_button.clicked.connect(self.manual_start_talking)
        self.talk_button.setMinimumHeight(45)
        self.talk_button.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                background-color: #FFB6C1;
                border: 2px solid #FF69B4;
            }
            QPushButton:hover {
                background-color: #FF69B4;
            }
            QPushButton:pressed {
                background-color: #FF1493;
            }
            QPushButton:disabled {
                background-color: #D3D3D3;
                border-color: #A9A9A9;
                color: #808080;
            }
        """)
        
        # Add manual health check button
        self.health_button = QPushButton("🏥 Check System Health", self)
        self.health_button.clicked.connect(self.manual_health_check)
        
        main_layout.addWidget(self.talk_button)
        main_layout.addWidget(self.health_button)
        self.setLayout(main_layout)
    
    def _connect_signals(self):
        """Connect all signals for thread-safe updates"""
        bridge.update_status.connect(self.update_status, Qt.QueuedConnection)
        bridge.update_button.connect(self.update_button, Qt.QueuedConnection)
        bridge.start_animation.connect(self.start_wave_animation, Qt.QueuedConnection)
        bridge.stop_animation.connect(self.stop_wave_animation, Qt.QueuedConnection)
        bridge.start_auto_listening.connect(self.start_auto_listening_delayed, Qt.QueuedConnection)
        bridge.switch_to_idle_video.connect(self.switch_to_idle_video, Qt.QueuedConnection)
        bridge.switch_to_speaking_video.connect(self.switch_to_speaking_video, Qt.QueuedConnection)
        bridge.update_listening_status.connect(self.update_listening_status, Qt.QueuedConnection)  # NEW kawaii indicators

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
            # Check if listening is paused
            listening_paused = state.get_value("listening_paused")
            if listening_paused == "True":
                print("[GUI] ⏸️ PAUSED mode - no auto-restart, waiting for manual trigger or start command")
                bridge.update_status.emit("Status: Paused (listening for 'start listening') ⏸️")
                # DO NOT auto-restart when paused - wait for manual trigger or start command
                return
                
            else:
                print("[GUI] Auto-starting listening in continuous mode")
                bridge.update_status.emit("Status: Auto-listening... 🔄")
                self.start_talking()

    def manual_start_talking(self):
        """Manual start talking - can override paused state"""
        listening_paused = state.get_value("listening_paused")
        if listening_paused == "True":
            print("[GUI] 🔓 Manual override - unpausing listening")
            # Reset paused state and allow start
            state.set_value("listening_paused", "False", source="gui", priority=20)
            
        # Proceed with normal start
        self.start_talking()

    def start_talking(self):
        """Trigger the STT process through Redis state with health check"""
        print(f"[GUI] 🎙️ start_talking() called - State: {self.current_state}")
        
        # Check if listening is paused - but still allow STT for control commands
        listening_paused = state.get_value("listening_paused") 
        if listening_paused == "True":
            print("[GUI] 🎯 Starting STT in PAUSED mode - control commands only")
        
        if self.current_state == "ready":
            self.current_state = "requesting"
            print("[GUI] 📢 Starting listening with health check")
            bridge.update_button.emit("🔄 Checking...", False)
            
            # Run health check and STT trigger in executor
            self.executor.submit(self._check_and_start_stt)
        else:
            print(f"[GUI] ❌ Cannot start talking - wrong state: {self.current_state}")

    def _check_and_start_stt(self):
        """Check health and start STT if prerequisites are met"""
        try:
            # Check STT prerequisites (terminal logging only)
            stt_ready, stt_message = self.health_checker.check_services_for_stt()
            
            if not stt_ready:
                print(f"[Health] ❌ {stt_message}")
                bridge.update_button.emit("🎤 Start Talking", True)  # Re-enable button
                self.current_state = "ready"  # Reset state
                return
            
            # Prerequisites OK, proceed with STT
            print(f"[GUI] ✅ Health check passed, starting STT...")
            bridge.update_status.emit("Status: Listening... ⚡")
            bridge.update_button.emit("🔄 Starting...", False)
            bridge.start_animation.emit()
            
            # Check current Redis state
            current_user_wants = state.get_value("user_wants_to_talk")
            current_ai_speaking = state.get_value("ai_speaking")
            current_human_speaking = state.get_value("human_speaking")
            
            print(f"[GUI]    user_wants_to_talk: {current_user_wants}")
            print(f"[GUI]    ai_speaking: {current_ai_speaking}")
            print(f"[GUI]    human_speaking: {current_human_speaking}")
            
            # Use priority 38 - higher than STT control commands (37) to ensure GUI can always restart
            print("[GUI] 🚀 Setting user_wants_to_talk = True with source=gui, priority=38")
            result = state.set_value("user_wants_to_talk", "True", source="gui", priority=38)
            print(f"[GUI] 📊 State update result: {result}")
            
            if result:
                print("[GUI] ✅ Successfully triggered user_wants_to_talk")
            else:
                print("[GUI] ❌ Failed to set user_wants_to_talk - check rules")
                bridge.update_status.emit("Status: ❌ State management error")
                bridge.update_button.emit("🎤 Start Talking", True)
                bridge.stop_animation.emit()
                self.current_state = "ready"
                
        except Exception as e:
            print(f"[GUI] ❌ Error in health check/STT trigger: {e}")
            import traceback
            traceback.print_exc()
            # Reset to ready state on error
            bridge.update_status.emit("Status: ❌ Error - Ready 🌸")
            bridge.update_button.emit("🎤 Start Talking", True)
            bridge.stop_animation.emit()
            self.current_state = "ready"

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
        
    def switch_to_idle_video(self):
        """Switch to idle video (thread-safe)"""
        if self.video_manager.videos_available:
            self.video_manager.start_idle_video()
        
    def switch_to_speaking_video(self):
        """Switch to speaking video (thread-safe)"""
        if self.video_manager.videos_available:
            self.video_manager.start_speaking_video()

    def update_listening_status(self, status: str):
        """Update the kawaii listening status indicator"""
        print(f"[GUI] 🎀 Updating listening status to: {status}")
        
        if status == "listening":
            self.listening_status_label.setText("✨ Listening~")
            self.listening_status_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    font-weight: bold;
                    padding: 3px 8px;
                    border-radius: 12px;
                    background-color: #E8F5E8;
                    color: #4CAF50;
                    margin: 2px;
                }
            """)
        elif status == "paused":
            self.listening_status_label.setText("⏸️ Paused (say 'start listening')") 
            self.listening_status_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    font-weight: bold;
                    padding: 3px 8px;
                    border-radius: 12px;
                    background-color: #FFF3CD;
                    color: #856404;
                    margin: 2px;
                }
            """)

    def initialize_listening_status(self):
        """Initialize the listening status indicator based on current state"""
        try:
            listening_controller = ListeningController()
            current_status = listening_controller.get_listening_status()
            print(f"[GUI] 🎀 Initializing listening status: {current_status}")
            self.update_listening_status(current_status)
        except Exception as e:
            print(f"[GUI] ⚠️ Could not initialize listening status: {e}")
            # Default to listening state
            self.update_listening_status("listening")

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
                # Switch to speaking video
                bridge.switch_to_speaking_video.emit()
            else:
                # AI finished speaking - switch back to idle video and auto-restart listening
                print(f"[GUI] 🎤 AI finished speaking. Emitting auto-restart signal")
                self.current_state = "ready"
                bridge.update_status.emit("Status: AI Done - Auto-listening soon... 🔄")
                bridge.update_button.emit("🔄 Auto-listening...", False)
                bridge.stop_animation.emit()
                # Switch back to idle video
                bridge.switch_to_idle_video.emit()
                
                # Use signal to safely trigger timer from main thread
                bridge.start_auto_listening.emit()
                
        elif key == "gui_listening_status":
            # Handle listening status updates
            bridge.update_listening_status.emit(value)
            
        elif key == "listening_paused" and value == "True":
            # When listening is paused, TTS will handle triggering control command listening
            print("[GUI] 🎯 Listening paused detected - TTS will trigger control command listening after acknowledgment")
        
        elif key == "interrupt_ai_speech":
            if value == "true":
                # AI speech was interrupted - switch back to idle video immediately
                print("[GUI] 🛑 AI speech interrupted - switching to idle video")
                self.current_state = "ready"
                bridge.update_status.emit("Status: AI Interrupted - Ready 🔄")
                bridge.update_button.emit("🎤 Start Talking", True)
                bridge.stop_animation.emit()
                # Switch back to idle video immediately
                bridge.switch_to_idle_video.emit()
                
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

    def closeEvent(self, event):
        """Handle application close event"""
        print("[GUI] 👋 Closing application...")
        # Stop all video playback
        if hasattr(self, 'video_manager'):
            self.video_manager.stop_all()
        # Accept the close event
        event.accept()

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
    # Start the Redis listener in a separate thread
    redis_thread = threading.Thread(target=redis_listener, daemon=True)
    redis_thread.start()

    # Create and run the Qt application
    app = QApplication(sys.argv)
    window = MicControlApp()
    
    # Store reference to window for the Redis listener
    app.main_window = window
    
    window.show()
    
    print("[GUI] 🎬 Video-enhanced Kawaii AI Assistant started!")
    print("[GUI] 📺 Video files checked and players initialized")
    print("[GUI] Ready to interact!")
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("[GUI] Application interrupted by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
