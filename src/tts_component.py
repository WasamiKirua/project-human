import time
import os
import json
import asyncio
import requests
import re
import replicate
import traceback
from openai import OpenAI
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
        api_keys, tts_config = self.config

        self.replicate_key = api_keys.get("replicate_api_key", None)
        self.openai_key = api_keys.get("openai_api_key", None)
        self.tts_elements = tts_config

        # Initialize Replicate client if API key is available
        if self.replicate_key:
            os.environ["REPLICATE_API_TOKEN"] = self.replicate_key
            print(f"[TTS] ✅ Replicate API key loaded (length: {len(self.replicate_key)})")
        else:
            print(f"[TTS] ❌ Replicate API key not found in config!")

        # Verify API keys are loaded (don't print the full key for security)
        if self.openai_key:
            os.environ["OPENAI_API_KEY"] = self.openai_key
            self.openai_tts_client = OpenAI()
            print(f"[TTS] ✅ OpenAI API key loaded (length: {len(self.openai_key)})")

        else:
            print(f"[TTS] ❌ OpenAI API key not found in config!")
        
        # Initialize component
        tts_component = self

    def load_config(self):
        config_path = 'config.json'
        api_keys = {} # Default
        tts_config = {}
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    api_keys = config.get("api_keys", {})
                    tts_config = config.get("tts", {})
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
                        tts_config = config.get("tts", {})
                except Exception as e:
                    print(f"[TTS] ❌ Error loading config from parent dir: {e}")
            else:
                print(f"[TTS] ⚠️ Config file not found in current or parent directory")
            
        return api_keys, tts_config

    def sanitize_text_for_tts(self, text: str) -> str:
        """Sanitize text to prevent SSML validation errors"""
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
        """Generate audio using configured TTS provider"""
        sanitized_text = self.sanitize_text_for_tts(text)
        print(f"[TTS] 🎤 Generating audio from text: {sanitized_text[:60]}...")

        # Get the active TTS provider from config
        tts_provider = self.tts_elements.get('tts_provider', None)
        
        if not tts_provider:
            print("[TTS] ❌ No tts_provider specified in configuration")
            return None

        print(f"[TTS] 🎯 Using TTS provider: {tts_provider}")
        
        if tts_provider == 'resemble':
            return self._generate_audio_resemble(sanitized_text)
        elif tts_provider == 'replicate':
            return self._generate_audio_replicate(sanitized_text)
        elif tts_provider == 'openai':
            return self._generate_audio_openai(sanitized_text)
        else:
            print(f"[TTS] ❌ Unknown TTS provider: {tts_provider}")
            print(f"[TTS] Available providers: resemble, replicate, openai")
            return None

    def _generate_audio_replicate(self, text: str):
        """Generate audio using Replicate Kokoro TTS"""
        if not self.replicate_key:
            print("[TTS] ❌ No Replicate API key available")
            return None

        try:
            # Get model from config or use default
            model_name = self.tts_elements.get('replicate_model')
            

            print(f"[TTS] 🤖 Using Replicate model: {model_name}")

            # Prepare input for the model
            model_input = {
                "text": text,
                "speed": 1,
                "voice": "af_sky"
            }

            print("[TTS] 🚀 Calling Replicate API...")
            
            # Run the model
            output = replicate.run(model_name, input=model_input)
            
            if output:
                print(f"[TTS] ✅ Replicate API returned audio URL: {output}")
                
                # Clean up existing files before downloading new one
                self.cleanup_existing_audio_files()
                
                # Download the audio file
                print("[TTS] 📥 Downloading audio file...")
                response = requests.get(output, timeout=30)
                response.raise_for_status()
                
                audio_filename = "output.wav"
                with open(audio_filename, "wb") as f:
                    f.write(response.content)
                
                print(f"[TTS] ✅ Audio downloaded and saved to {audio_filename}")
                return audio_filename
            else:
                print("[TTS] ❌ Replicate API returned no output")
                return None

        except replicate.exceptions.ReplicateError as e:
            print(f"[TTS] ❌ Replicate API error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[TTS] ❌ Error downloading audio file: {e}")
            return None
        except Exception as e:
            print(f"[TTS] ❌ Unexpected error in Replicate TTS: {e}")
            traceback.print_exc()
            return None

    def _generate_audio_openai(self, text: str):
        """Generate audio using OpenAI TTS API"""
        if not self.openai_key:
            print("[TTS] ❌ No OpenAI API key available")
            return None
        
        try:
            print("[TTS] 🚀 Calling OpenAI TTS API...")
            
            # Clean up existing files before generating new one
            self.cleanup_existing_audio_files()
            
            audio_filename = "output.wav"

            # Generate speech using OpenAI TTS
            with self.openai_tts_client.audio.speech.with_streaming_response.create(
                model='tts-1',
                voice='nova',
                input=text,
                response_format='wav'
            ) as response:
                response.stream_to_file(audio_filename)
            
            print(f"[TTS] ✅ OpenAI TTS audio saved to {audio_filename}")
            return audio_filename
            
        except Exception as e:
            print(f"[TTS] ❌ Error in OpenAI TTS: {e}")
            import traceback
            traceback.print_exc()
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
                    
            audio_file = tts_component.generate_audio(text_to_speak)
            
            if audio_file:
                # Set ai_speaking state RIGHT BEFORE playing - use higher priority
                await state.set("ai_speaking", "True", source="tts", priority=10)
                print("[TTS] 🎤 AI is now 'speaking' - starting playback")
                
                # Play the generated audio
                playback_result = tts_component.play_audio(audio_file)
                
                if playback_result == "completed":
                    print("[TTS] ✅ TTS processing completed successfully")
                elif playback_result == "interrupted":
                    print("[TTS] ⚠️ Playback was interrupted by user")
                else:
                    print("[TTS] ❌ Playback failed or encountered an error")
                
                # Reset ai_speaking flag after playback ends - keep high priority for immediate effect
                await state.set("ai_speaking", "False", source="tts", priority=10)
            else:
                print("[TTS] ❌ Audio generation failed - not setting ai_speaking")
            
            # Reset interrupt flag to clear any pending interruptions
            await state.set("interrupt_ai_speech", "false", source="tts", priority=10)
            
            # Clear tts_ready signal - use priority LOWER than LLM (8) so LLM can set it again
            await state.set("tts_ready", "False", source="tts", priority=5)
            
            # Clear the text - use priority LOWER than LLM (8) so LLM can set it again  
            await state.set("tts_text", "", source="tts", priority=5)
            
            print("[TTS] 🏁 TTS cycle completed - ready for next interaction")
            
        except Exception as e:
            print(f"[TTS] ❌ Error in TTS processing: {e}")
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
        traceback.print_exc()
