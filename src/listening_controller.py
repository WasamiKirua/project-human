import json
import os
from typing import Optional
from redis_state import RedisState
from redis_client import create_redis_client

# Redis config & state
r = create_redis_client()
state = RedisState(r)

class ListeningController:
    _initialized = False  # Class variable to track if already initialized
    
    def __init__(self):
        """Initialize listening controller with config and Redis state"""
        self.config = self._load_config()
        self.state = state
        self.enabled = self.config.get("enabled", True)
        self.user_name = self.config.get("user_name", "friend")
        self.stop_phrases = self.config.get("stop_phrases", [])
        self.start_phrases = self.config.get("start_phrases", [])
        self.stop_acknowledgment = self.config.get("stop_acknowledgment", "Ok {user_name} I stop listening")
        self.start_acknowledgment = self.config.get("start_acknowledgment", "Ok {user_name} I'm listening again")
        
        print(f"[ListeningController] 🎧 Initialized with user: {self.user_name}")
        print(f"[ListeningController] 📝 Stop phrases: {self.stop_phrases}")
        print(f"[ListeningController] 📝 Start phrases: {self.start_phrases}")
        
        # Only initialize to listening state on FIRST instantiation (app startup)
        if not ListeningController._initialized:
            try:
                # Force synchronous state setting to avoid race conditions
                print(f"[ListeningController] 🔧 Force setting listening state to active...")
                
                # Use direct Redis write to ensure immediate persistence
                self.state.r.hset("state:listening_paused", "value", "False")
                self.state.r.hset("state:listening_paused", "source", "listening_controller")
                self.state.r.hset("state:listening_paused", "priority", "1")
                
                # Verify it was set
                verification = self.state.get_value("listening_paused")
                print(f"[ListeningController] ✅ Verified state - listening_paused: {verification}")
                print(f"[ListeningController] ✅ Listening is now: {'paused' if verification == 'True' else 'active'}")
                
                ListeningController._initialized = True  # Mark as initialized
                
            except Exception as e:
                print(f"[ListeningController] ⚠️ Could not force-set state: {e}")
                # Fallback to normal method
                try:
                    self.state.set_value("listening_paused", False)
                    print(f"[ListeningController] 🔄 Fallback: Used set_value method")
                    ListeningController._initialized = True
                except Exception as e2:
                    print(f"[ListeningController] ❌ Both methods failed: {e2}")
        else:
            print(f"[ListeningController] ♻️ Using existing state (not resetting)")
            # Still show current state for debugging
            current_state = self.state.get_value("listening_paused")
            print(f"[ListeningController] 📊 Current state - listening_paused: {current_state}")

    def _load_config(self) -> dict:
        """Load listening control configuration from config.json"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("listening_control", {})
        except Exception as e:
            print(f"[ListeningController] ❌ Error loading config: {e}")
            return {}

    def check_control_command(self, transcript: str) -> Optional[str]:
        """
        Check if transcript contains a listening control command
        
        Args:
            transcript: The transcribed text to check
            
        Returns:
            "stop" if stop command detected
            "start" if start command detected  
            None if no control command found
        """
        if not self.enabled:
            return None
            
        transcript_lower = transcript.lower().strip()
        
        # Remove common punctuation to improve phrase matching
        import re
        transcript_clean = re.sub(r'[,\.!?;:]', ' ', transcript_lower)
        transcript_clean = re.sub(r'\s+', ' ', transcript_clean).strip()  # Normalize whitespace
        
        print(f"[ListeningController] 🔍 Checking transcript: '{transcript}'")
        print(f"[ListeningController] 🧹 Cleaned transcript: '{transcript_clean}'")
        
        # Check for stop commands
        for stop_phrase in self.stop_phrases:
            stop_phrase_clean = re.sub(r'[,\.!?;:]', ' ', stop_phrase.lower())
            stop_phrase_clean = re.sub(r'\s+', ' ', stop_phrase_clean).strip()
            
            if stop_phrase_clean in transcript_clean:
                print(f"[ListeningController] 🛑 Stop command detected: '{transcript}'")
                print(f"[ListeningController] 🎯 Matched phrase: '{stop_phrase}' → '{stop_phrase_clean}'")
                return "stop"
        
        # Check for start commands
        for start_phrase in self.start_phrases:
            start_phrase_clean = re.sub(r'[,\.!?;:]', ' ', start_phrase.lower())
            start_phrase_clean = re.sub(r'\s+', ' ', start_phrase_clean).strip()
            
            if start_phrase_clean in transcript_clean:
                print(f"[ListeningController] ▶️ Start command detected: '{transcript}'")
                print(f"[ListeningController] 🎯 Matched phrase: '{start_phrase}' → '{start_phrase_clean}'")
                return "start"
        
        return None

    def handle_stop_listening(self) -> str:
        """
        Handle stop listening command
        
        Returns:
            Acknowledgment text for TTS
        """
        print(f"[ListeningController] 💤 Setting listening to paused state")
        self.state.set_value("listening_paused", "True", source="listening_controller", priority=10)
        print(f"[ListeningController] ✅ Listening paused state confirmed")
        
        # Format acknowledgment with user name
        acknowledgment = self.stop_acknowledgment.format(user_name=self.user_name)
        print(f"[ListeningController] 📢 Stop acknowledgment: '{acknowledgment}'")
        
        return acknowledgment

    def handle_start_listening(self) -> str:
        """
        Handle start listening command
        
        Returns:
            Acknowledgment text for TTS
        """
        print(f"[ListeningController] ✨ Setting listening to active state")
        
        # Clear control state with priority 38 then immediately allow GUI to take over
        self.state.set_value("user_wants_to_talk", "False", source="listening_controller", priority=38)
        print(f"[ListeningController] 🧹 Cleared control state with priority 38")
        print(f"[ListeningController] ✅ State cleared - GUI can now restart with same priority")
        
        self.state.set_value("listening_paused", "False", source="listening_controller", priority=10)
        
        # Format acknowledgment with user name
        acknowledgment = self.start_acknowledgment.format(user_name=self.user_name)
        print(f"[ListeningController] 📢 Start acknowledgment: '{acknowledgment}'")
        
        return acknowledgment

    def is_listening_paused(self) -> bool:
        """
        Check if listening is currently paused
        
        Returns:
            True if listening is paused, False if actively listening
        """
        if not self.enabled:
            return False
            
        try:
            paused = self.state.get_value("listening_paused")
            print(f"[ListeningController] 🔍 Raw state value: '{paused}' (type: {type(paused)})")
            
            # Handle Redis string values correctly
            if paused is None:
                print(f"[ListeningController] 📝 State is None - defaulting to listening (False)")
                return False
            elif isinstance(paused, str):
                result = paused.lower() == "true"
                print(f"[ListeningController] 📝 String value '{paused}' → paused: {result}")
                return result
            else:
                result = bool(paused)
                print(f"[ListeningController] 📝 Boolean value {paused} → paused: {result}")
                return result
                
        except Exception as e:
            print(f"[ListeningController] ⚠️ Error checking pause state (assuming listening): {e}")
            # Default to listening if we can't check the state
            return False

    def get_listening_status(self) -> str:
        """
        Get current listening status for GUI display
        
        Returns:
            "listening" or "paused"
        """
        return "paused" if self.is_listening_paused() else "listening"

    def force_resume_listening(self):
        """Force resume listening (for debugging/admin purposes)"""
        print(f"[ListeningController] 🔧 Force resuming listening")
        self.state.set_value("listening_paused", False)

    def get_config_info(self) -> dict:
        """Get current configuration for debugging"""
        return {
            "enabled": self.enabled,
            "user_name": self.user_name,
            "stop_phrases": self.stop_phrases,
            "start_phrases": self.start_phrases,
            "currently_paused": self.is_listening_paused()
        }
