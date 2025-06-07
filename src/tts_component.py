import time
import os
import json
import asyncio
import requests
import base64
import re
from resemble import Resemble
from redis_state import RedisState
from redis_client import create_redis_client

# Redis config & state
r = create_redis_client()
state = RedisState(r)

# Audio playback dependencies
try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
    print("[TTS] pygame available for audio playback")
except ImportError:
    try:
        import subprocess
        SUBPROCESS_AVAILABLE = True
        PYGAME_AVAILABLE = False
        print("[TTS] Using system audio playback")
    except ImportError:
        print("[TTS] Warning: No audio playback method available")
        PYGAME_AVAILABLE = False
        SUBPROCESS_AVAILABLE = False

class TtsComponent:
    def __init__(self):
    
        global tts_component

        # Load configuration
        self.config = self.load_config()
        print(f"[TTS] Loaded config: {self.config}")

        # Validate and extract config values with defaults
        api_keys = self.config

        self.resemble_key = api_keys.get("resemble_api_key", None)

        # Verify API key is loaded (don't print the full key for security)
        if self.resemble_key:
            print(f"[TTS] ✅ Resemble API key loaded (length: {len(self.resemble_key)})")
        else:
            print(f"[TTS] ❌ Resemble API key not found in config!")
        
        # Initialize component
        tts_component = self

    def load_config(self):
        config_path = 'config.json'
        api_keys = {} # Default
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    api_keys = config.get("api_keys", {})
            except Exception as e:
                print(f"[TTS] ❌ Error loading config: {e}")
                # Use defaults if config loading fails
        else:
            # Try looking in parent directory (for when running from src/)
            parent_config_path = '../config.json'
            if os.path.exists(parent_config_path):
                try:
                    with open(parent_config_path, 'r') as f:
                        config = json.load(f)
                        api_keys = config.get("api_keys", {})
                except Exception as e:
                    print(f"[TTS] ❌ Error loading config from parent dir: {e}")
            else:
                print(f"[TTS] ⚠️ Config file not found in current or parent directory")
            
        return api_keys

    def sanitize_text_for_tts(self, text: str) -> str:
        """Sanitize text to prevent SSML validation errors"""
        import re
        
        # Remove or replace problematic characters that could be interpreted as SSML
        sanitized = text
        
        # Replace common emoticons that use < > characters
        sanitized = re.sub(r'<3', '♥', sanitized)  # Heart emoticon
        sanitized = re.sub(r'<\/3', '💔', sanitized)  # Broken heart
        
        # Remove any remaining standalone < or > that aren't part of valid SSML
        # This is a simple approach - for more complex SSML support, we'd need proper parsing
        sanitized = re.sub(r'<(?![a-zA-Z/])', '&lt;', sanitized)  # < not followed by letter or /
        sanitized = re.sub(r'(?<![a-zA-Z/])>', '&gt;', sanitized)  # > not preceded by letter or /
        
        # Remove any other problematic characters that could cause SSML issues
        sanitized = re.sub(r'[^\w\s\.,!?;:\'"()\-–—♥💔]', '', sanitized)
        
        # Clean up extra whitespace
        sanitized = ' '.join(sanitized.split())
        
        if sanitized != text:
            print(f"[TTS] 🧹 Sanitized text: '{text}' → '{sanitized}'")
            
        return sanitized

    def generate_audio(self, text: str):
        """Generate audio using Resemble AI API with retry logic and cleanup"""
        # Sanitize text before processing
        sanitized_text = self.sanitize_text_for_tts(text)
        
        print(f"[TTS] 🎤 Generating audio from text: {sanitized_text[:60]}...")

        if not self.resemble_key:
            print("[TTS] ❌ No Resemble API key available")
            return None

        data = {
            "voice_uuid": "e28236ee",
            "data": sanitized_text,  # Use sanitized text
            "sample_rate": 48000,
            "output_format": "wav"
        }
        headers = {
            "Authorization": f"Bearer {self.resemble_key}",
            "Content-Type": "application/json"
        }

        max_attempts = 15
        wait_time = 1
        
        # Add small delay to prevent rapid API calls after interruption
        time.sleep(0.5)

        for attempt in range(1, max_attempts + 1):
            try:
                print(f"[TTS] 🚀 Attempt {attempt}/{max_attempts} - Calling Resemble API...")

                response = requests.post("https://f.cluster.resemble.ai/synthesize", 
                                       headers=headers, json=data, timeout=30)

                if response.status_code == 200:
                    try:
                        result = response.json()
                        print(f"[TTS] ✅ Success on attempt {attempt}")

                        if result.get("success"):
                            # Clean up existing files FIRST when we get a successful API response
                            self.cleanup_existing_audio_files()

                            audio_base64 = result.get("audio_content")
                            if audio_base64:
                                audio_bytes = base64.b64decode(audio_base64.strip())

                                # Option 1: Simple filename (since we cleanup)
                                audio_filename = "output.wav"

                                # Option 2: Unique filename (comment out line above and use this)
                                # timestamp = int(time.time() * 1000)
                                # audio_filename = f"tts_audio_{timestamp}.wav"

                                with open(audio_filename, "wb") as f:
                                    f.write(audio_bytes)
                                print(f"[TTS] ✅ Audio saved to {audio_filename} (Duration: {result.get('duration', 'Unknown')}s)")
                                return audio_filename
                            else:
                                print(f"[TTS] ❌ No audio data in response (attempt {attempt})")
                        else:
                            print(f"[TTS] ❌ API reported failure on attempt {attempt}:")
                            print(f"[TTS] Issues: {result.get('issues', [])}")

                    except requests.exceptions.JSONDecodeError as e:
                        print(f"[TTS] ❌ JSON parsing error on attempt {attempt}: {e}")

                elif response.status_code == 400:
                    # 400 errors are usually validation issues that won't be fixed by retrying
                    print(f"[TTS] ❌ Validation error (400) - not retrying")
                    try:
                        error_details = response.json()
                        error_name = error_details.get("error_name", "Unknown")
                        error_message = error_details.get("message", "No message")
                        print(f"[TTS] Error details: {error_name} - {error_message}")
                        
                        # If it's an SSML error, we could try to sanitize further or fall back
                        if "SSML" in error_name or "SSML" in error_message:
                            print("[TTS] ⚠️ SSML validation failed despite sanitization")
                            
                    except:
                        print(f"[TTS] Response: {response.text}")
                    
                    return None  # Don't retry 400 errors

                elif response.status_code in [500, 502, 503, 504]:
                    print(f"[TTS] ⚠️ Server error {response.status_code} on attempt {attempt}/{max_attempts}")
                    if attempt < max_attempts:
                        # Exponential backoff for server errors after interruption
                        backoff_time = wait_time * (2 ** min(attempt - 1, 3))  # Cap at 8 seconds
                        print(f"[TTS] 🔄 Waiting {backoff_time}s before retry...")
                        time.sleep(backoff_time)
                        continue
                    else:
                        print(f"[TTS] ❌ Max attempts reached, giving up")
                        return None

                else:
                    print(f"[TTS] ❌ API Error {response.status_code} on attempt {attempt}")
                    print(f"[TTS] Response: {response.text}")
                    if attempt < max_attempts:
                        print(f"[TTS] 🔄 Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[TTS] ❌ Max attempts reached")
                        return None

            except requests.exceptions.Timeout:
                print(f"[TTS] ⏰ Timeout on attempt {attempt}")
                if attempt < max_attempts:
                    print(f"[TTS] 🔄 Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[TTS] ❌ Max attempts reached due to timeouts")
                    return None

            except Exception as e:
                print(f"[TTS] ❌ Error on attempt {attempt}: {e}")
                if attempt < max_attempts:
                    print(f"[TTS] 🔄 Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[TTS] ❌ Max attempts reached due to errors")
                    return None

        print(f"[TTS] ❌ All {max_attempts} attempts failed")
        return None

    def cleanup_existing_audio_files(self):
        """Clean up any existing TTS audio files before generating new ones"""
        try:
            import glob
            import os
            
            # Stop any ongoing pygame playback before cleanup
            try:
                if hasattr(pygame.mixer, 'music') and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                    time.sleep(0.1)  # Small delay to ensure cleanup
            except:
                pass
            
            # Clean both patterns: simple and unique filenames
            patterns = ["output.wav", "tts_audio_*.wav"]
            
            cleaned_count = 0
            for pattern in patterns:
                audio_files = glob.glob(pattern)
                for file_path in audio_files:
                    try:
                        # Ensure file is not in use before deletion
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            cleaned_count += 1
                    except Exception as e:
                        print(f"[TTS] ⚠️ Could not delete {file_path}: {e}")
                        
            if cleaned_count > 0:
                print(f"[TTS] 🧹 Cleaned up {cleaned_count} existing audio files")
                
        except Exception as e:
            print(f"[TTS] ⚠️ Error during cleanup: {e}")

    async def play_audio_pygame_async(self, filename):
        """Async version of play audio using pygame with interruption detection"""
        try:
            # Clear any interruption state before starting
            await state.set("interrupt_ai_speech", "false", source="tts", priority=10)
            
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            
            # Wait for playback to complete or interruption
            while pygame.mixer.music.get_busy():
                # Check for interruption signal
                interrupt_value = state.get_value("interrupt_ai_speech")
                if interrupt_value == "true":
                    pygame.mixer.music.stop()
                    print("[TTS] 🛑 Audio interrupted by user speech")
                    return "interrupted"
                    
                # Legacy check for human_speaking (keeping for compatibility)
                human_speaking = state.get_value("human_speaking")
                if human_speaking == "True":
                    pygame.mixer.music.stop()
                    print("[TTS] 🛑 Playback interrupted by human")
                    return "interrupted"
                    
                # Use asyncio.sleep instead of time.sleep for async compatibility
                await asyncio.sleep(0.1)  # 100ms polling interval
                
            print("[TTS] ✅ Playback finished successfully")
            return "completed"
            
        except Exception as e:
            print(f"[TTS] ❌ Pygame playback error: {e}")
            return "error"

    def play_audio_pygame(self, filename):
        """Play audio using pygame with interruption detection"""
        try:
            # Clear any interruption state before starting - use direct Redis to avoid asyncio issues
            try:
                full_key = "state:interrupt_ai_speech"
                ts = int(time.time())
                state.r.hset(full_key, mapping={
                    "value": "false",
                    "source": "tts", 
                    "priority": 10,
                    "timestamp": ts
                })
                state.r.publish(state.pub_channel, "interrupt_ai_speech=false")
            except Exception as e:
                print(f"[TTS] ⚠️ Error clearing interruption state: {e}")
            
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            
            # Wait for playback to complete or interruption
            while pygame.mixer.music.get_busy():
                # Check for interruption signal
                interrupt_value = state.get_value("interrupt_ai_speech")
                if interrupt_value == "true":
                    pygame.mixer.music.stop()
                    print("[TTS] 🛑 Audio interrupted by user speech")
                    return "interrupted"
                    
                # Legacy check for human_speaking (keeping for compatibility)
                human_speaking = state.get_value("human_speaking")
                if human_speaking == "True":
                    pygame.mixer.music.stop()
                    print("[TTS] 🛑 Playback interrupted by human")
                    return "interrupted"
                    
                time.sleep(0.1)  # 100ms polling interval
                
            print("[TTS] ✅ Playback finished successfully")
            return "completed"
            
        except Exception as e:
            print(f"[TTS] ❌ Pygame playback error: {e}")
            return "error"
        
    def play_audio_system(self, filename):
        """Play audio using system command with interruption detection"""
        try:
            if os.name == 'posix':  # macOS/Linux
                import subprocess
                process = subprocess.Popen(['afplay', filename])
                
                # Monitor for interruption
                while process.poll() is None:
                    # Check for interruption signal
                    if state.get_value("interrupt_ai_speech") == "true":
                        process.terminate()
                        print("[TTS] 🛑 Audio interrupted by user speech")
                        return "interrupted"
                        
                    # Legacy check for human_speaking (keeping for compatibility)
                    if state.get_value("human_speaking") == "True":
                        process.terminate()
                        print("[TTS] 🛑 Playback interrupted by human")
                        return "interrupted"
                        
                    time.sleep(0.1)  # 100ms polling interval
                    
                print("[TTS] ✅ Playback finished successfully")
                return "completed"
            else:
                print("[TTS] ❌ System audio playback not implemented for this OS")
                return "error"
                
        except Exception as e:
            print(f"[TTS] ❌ System playback error: {e}")
            return "error"
        
    def play_audio(self, filename):
        """Play audio with interruption detection"""
        if not filename or not os.path.exists(filename):
            print("[TTS] ❌ Audio file not found")
            return "error"
            
        print(f"[TTS] 🔊 Starting playback: {filename}")
        
        # Try different playback methods
        if PYGAME_AVAILABLE:
            return self.play_audio_pygame(filename)
        else:
            return self.play_audio_system(filename)

# Global component instance
tts_component = None

# Async listener for TTS readiness signal
async def on_tts_ready(key, value, old):
    """Handle TTS readiness signal from LLM"""
    global tts_component
    
    if value == "True":
        try:
            print("[TTS] 🎯 Detected 'tts_ready' = True")
            
            # Get the text to speak from Redis state
            text_to_speak = state.get_value("tts_text")
            if not text_to_speak:
                print("[TTS] ❌ No text found in 'tts_text' state")
                # Use priority >= 8 to clear LLM-set states
                await state.set("tts_ready", "False", source="tts", priority=10)
                return
                
            print(f"[TTS] 📝 Text to speak: '{text_to_speak[:100]}...'")
            
            # Set ai_speaking state - use higher priority
            await state.set("ai_speaking", "True", source="tts", priority=10)
            print("[TTS] 🎤 AI is now 'speaking'")
            
            # Generate audio using Resemble API
            audio_file = tts_component.generate_audio(text_to_speak)
            
            if audio_file:
                # Play the generated audio
                playback_result = tts_component.play_audio(audio_file)
                
                if playback_result == "completed":
                    print("[TTS] ✅ TTS processing completed successfully")
                elif playback_result == "interrupted":
                    print("[TTS] ⚠️ Playback was interrupted by user")
                else:
                    print("[TTS] ❌ Playback failed or encountered an error")
            else:
                print("[TTS] ❌ Audio generation failed")
            
            # Reset ai_speaking flag - keep high priority for immediate effect
            await state.set("ai_speaking", "False", source="tts", priority=10)
            
            # Reset interrupt flag to clear any pending interruptions
            await state.set("interrupt_ai_speech", "false", source="tts", priority=10)
            
            # Clear tts_ready signal - use priority LOWER than LLM (8) so LLM can set it again
            await state.set("tts_ready", "False", source="tts", priority=5)
            
            # Clear the text - use priority LOWER than LLM (8) so LLM can set it again  
            await state.set("tts_text", "", source="tts", priority=5)
            
            print("[TTS] 🏁 TTS cycle completed - ready for next interaction")
            
        except Exception as e:
            print(f"[TTS] ❌ Error in TTS processing: {e}")
            import traceback
            traceback.print_exc()
            
            # Ensure states are cleaned up on error - use higher priorities
            await state.set("ai_speaking", "False", source="tts", priority=10)
            await state.set("interrupt_ai_speech", "false", source="tts", priority=10)
            await state.set("tts_ready", "False", source="tts", priority=10)

# Main TTS listener loop
async def tts_loop():
    """Main loop that listens for tts_ready state changes"""
    global tts_component
    
    # Initialize TTS component
    tts_component = TtsComponent()
    print("[TTS] 🎧 TTS component initialized")
    
    # Subscribe to TTS ready signal with correct callback signature
    state.subscribe("tts_ready", on_tts_ready)
    print("[TTS] 📡 Subscribed to 'tts_ready' state changes")
    
    # Start the state listener
    print("[TTS] 🔄 Starting state listener...")
    await state.listen()

if __name__ == "__main__":
    print("[TTS] 🚀 Starting TTS component...")
    try:
        asyncio.run(tts_loop())
    except KeyboardInterrupt:
        print("[TTS] 👋 TTS component stopped by user")
    except Exception as e:
        print(f"[TTS] ❌ TTS component error: {e}")
        import traceback
        traceback.print_exc()
