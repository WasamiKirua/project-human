import time
import asyncio
import threading
import tempfile
import os
import wave
import requests
import json
import aiohttp
import concurrent.futures
from redis_state import RedisState
from redis_client import create_redis_client

# Redis config & state
r = create_redis_client()
state = RedisState(r)

# Audio recording dependencies
try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
    print("[STT] sounddevice available")
except ImportError:
    print("[STT] Warning: sounddevice not installed. Install with: pip install sounddevice numpy")
    AUDIO_AVAILABLE = False

# Silero VAD dependencies
try:
    from silero_vad import load_silero_vad, VADIterator
    import torch
    torch.set_num_threads(1)  # Optimize for real-time processing
    SILERO_AVAILABLE = True
    print("[STT] Silero VAD available")
except ImportError:
    print("[STT] Warning: silero-vad not installed. Install with: pip install silero-vad onnxruntime")
    SILERO_AVAILABLE = False


# Global Silero VAD model
silero_model = None
vad_iterator = None

class ContinuousAudioMonitor:
    """Continuous audio monitoring for interruption detection"""
    
    def __init__(self):
        self.sampling_rate = json_config['sampling_rate']
        self.vad_threshold = json_config['vad_threshold']
        self.channels = json_config['channels']
        self.chunk_size = json_config['chunk_size']
        self.is_monitoring = False
        self.stream = None
        self.chunk_buffer = np.array([], dtype=np.float32)
        self.last_interruption_time = 0  # Add debouncing timestamp
        
    def process_vad_chunk(self, audio_chunk):
        """Process audio chunk with Silero VAD using direct model call (VADIterator not working properly)"""
        if not SILERO_AVAILABLE or silero_model is None:
            # Fallback to amplitude detection
            return np.max(np.abs(audio_chunk)) > 0.02  # Lower threshold for interruption
        
        try:
            if len(audio_chunk) == self.chunk_size:
                # VADIterator returns None, so use direct model call which works reliably
                speech_prob = silero_model(torch.from_numpy(audio_chunk), self.sampling_rate).item()
                return speech_prob > self.vad_threshold
            return False
        except Exception as e:
            print(f"[STT Monitor] VAD processing error: {e}")
            return np.max(np.abs(audio_chunk)) > 0.02
    
    def audio_callback(self, indata, frames, time_info, status):
        """Continuous audio monitoring callback for interruption detection"""
        if status:
            print(f"[STT Monitor] Audio callback status: {status}")
        
        audio_data = indata.flatten() if self.channels == 1 else indata[:, 0]
        self.chunk_buffer = np.concatenate([self.chunk_buffer, audio_data])
        
        while len(self.chunk_buffer) >= self.chunk_size:
            chunk = self.chunk_buffer[:self.chunk_size]
            self.chunk_buffer = self.chunk_buffer[self.chunk_size:]
            
            is_speech = self.process_vad_chunk(chunk)
            
            if is_speech:
                # Check if AI is currently speaking
                ai_currently_speaking = state.get_value("ai_speaking")
                if ai_currently_speaking == "True":
                    # Debouncing: only send interruption if 1.5 seconds have passed since last one
                    current_time = time.time()
                    if current_time - self.last_interruption_time >= 1.5:
                        print("[STT Monitor] 🗣️ User speech detected during AI speaking - triggering interruption")
                        # Use direct Redis call instead of state.set_value to avoid asyncio issues
                        try:
                            full_key = "state:interrupt_ai_speech"
                            ts = int(current_time)
                            state.r.hset(full_key, mapping={
                                "value": "true",
                                "source": "stt",
                                "priority": 10,
                                "timestamp": ts
                            })
                            # Publish the message directly
                            state.r.publish(state.pub_channel, "interrupt_ai_speech=true")
                            print("[STT Monitor] ✅ Interruption signal sent via direct Redis")
                            self.last_interruption_time = current_time  # Update debounce timestamp
                        except Exception as e:
                            print(f"[STT Monitor] ❌ Error setting interruption state: {e}")
                    else:
                        # Skip rapid-fire interruptions (too soon since last one)
                        pass
    
    def start_monitoring(self):
        """Start continuous audio monitoring"""
        if not AUDIO_AVAILABLE or self.is_monitoring:
            return False
        
        try:
            print("[STT Monitor] 🎧 Starting continuous audio monitoring for interruptions...")
            
            self.stream = sd.InputStream(
                samplerate=self.sampling_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=self.chunk_size,
                callback=self.audio_callback
            )
            self.stream.start()
            self.is_monitoring = True
            print("[STT Monitor] ✅ Continuous monitoring active")
            return True
        except Exception as e:
            print(f"[STT Monitor] ❌ Error starting monitoring: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop continuous audio monitoring"""
        if self.stream and self.is_monitoring:
            try:
                self.stream.stop()
                self.stream.close()
                self.is_monitoring = False
                print("[STT Monitor] 🛑 Continuous monitoring stopped")
            except Exception as e:
                print(f"[STT Monitor] Error stopping monitoring: {e}")

# Global continuous monitor
continuous_monitor = None

def load_config():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            stt_config = config.get("stt", {})
    return stt_config

def initialize_silero_vad():
    """Initialize Silero VAD ONNX model following the official documentation pattern"""
    sampling_rate = json_config['sampling_rate']
    global silero_model, vad_iterator
    
    if not SILERO_AVAILABLE:
        print("[STT] Silero VAD not available")
        return False
    
    try:
        print("[STT] Loading Silero VAD ONNX model...")
        
        try:
            silero_model = load_silero_vad(onnx=True)
            print("[STT] Silero VAD ONNX model loaded successfully (pip package)")
        except Exception as e:
            print(f"[STT] ONNX loading failed: {e}")
            print("[STT] Falling back to PyTorch JIT model...")
            silero_model = load_silero_vad(onnx=False)
            print("[STT] Silero VAD PyTorch model loaded successfully")
        
        vad_iterator = VADIterator(silero_model, sampling_rate=sampling_rate)
        print("[STT] Silero VAD initialized successfully")
        return True
        
    except Exception as e:
        print(f"[STT] Error loading Silero VAD: {e}")
        print("[STT] Falling back to amplitude-based detection")
        return False

class SileroVADAudioRecorder:
    """Audio recorder with real-time Silero VAD processing"""
    
    def __init__(self):
        self.amplitude_threshold = json_config['amplitude_threshold']
        self.chunk_size = json_config['chunk_size']
        self.sampling_rate = json_config['sampling_rate']
        self.vad_threshold = json_config['vad_threshold']
        self.channels = json_config['channels']
        self.silence_duration = json_config['silence_duration']
        self.min_audio_length = json_config['min_audio_length']
        self.is_recording = False
        self.speech_detected = False
        self.audio_buffer = []
        self.speech_chunks = []
        self.recording_start_time = None
        self.last_speech_time = None
        self.stream = None
        self.chunk_buffer = np.array([], dtype=np.float32)
        
        # Threading communication
        self.recording_complete = threading.Event()
        self.completed_audio = None
        self.audio_lock = threading.Lock()
        
        # Temporal smoothing configuration from config.json
        temporal_config = json_config.get('temporal_smoothing', {})
        self.enable_temporal_smoothing = temporal_config.get('enabled', False)
        self.confidence_buffer_size = temporal_config.get('confidence_buffer_size', 5)
        
        # Calculate thresholds from ratios (no hardcoded values)
        start_ratio = temporal_config.get('start_threshold_ratio', 0.7)
        continue_ratio = temporal_config.get('continue_threshold_ratio', 0.9)
        self.speech_start_threshold = self.vad_threshold * start_ratio
        self.speech_continue_threshold = self.vad_threshold * continue_ratio
        
        # Temporal smoothing variables
        self.confidence_buffer = []
        self.smoothed_confidence = 0.0
        
    def process_vad_chunk(self, audio_chunk):
        """Process audio chunk with Silero VAD using direct model call (VADIterator not working properly)"""
        if not SILERO_AVAILABLE or silero_model is None:
            return np.max(np.abs(audio_chunk)) > self.amplitude_threshold
        
        try:
            if len(audio_chunk) == self.chunk_size:
                # VADIterator returns None, so use direct model call which works reliably
                speech_prob = silero_model(torch.from_numpy(audio_chunk), self.sampling_rate).item()
                return speech_prob > self.vad_threshold
            return False
        except Exception as e:
            print(f"[STT] VAD processing error: {e}")
            return np.max(np.abs(audio_chunk)) > self.amplitude_threshold
    
    def process_vad_chunk_with_smoothing(self, audio_chunk):
        """Process audio chunk with temporal smoothing and hysteresis"""
        if not self.enable_temporal_smoothing:
            # Fallback to original method if smoothing disabled
            return self.process_vad_chunk(audio_chunk)
        
        if not SILERO_AVAILABLE or silero_model is None:
            return np.max(np.abs(audio_chunk)) > self.amplitude_threshold
        
        try:
            if len(audio_chunk) == self.chunk_size:
                # Get raw speech probability
                speech_prob = silero_model(torch.from_numpy(audio_chunk), self.sampling_rate).item()
                
                # Add to confidence buffer
                self.confidence_buffer.append(speech_prob)
                if len(self.confidence_buffer) > self.confidence_buffer_size:
                    self.confidence_buffer.pop(0)
                
                # Calculate smoothed confidence (running average)
                self.smoothed_confidence = sum(self.confidence_buffer) / len(self.confidence_buffer)
                
                # Apply hysteresis: different thresholds for starting vs continuing speech
                if not self.is_recording:
                    # Not currently recording - use lower threshold to start
                    is_speech = self.smoothed_confidence > self.speech_start_threshold
                else:
                    # Currently recording - use higher threshold to continue (prevents premature stops)
                    is_speech = self.smoothed_confidence > self.speech_continue_threshold
                
                return is_speech
            return False
        except Exception as e:
            print(f"[STT] VAD smoothing error: {e}")
            # Fallback to original method
            return self.process_vad_chunk(audio_chunk)
    
    def audio_callback(self, indata, frames, time_info, status):
        """Real-time audio callback with Silero VAD processing"""
        if status:
            print(f"[STT] Audio callback status: {status}")
        
        audio_data = indata.flatten() if self.channels == 1 else indata[:, 0]
        self.chunk_buffer = np.concatenate([self.chunk_buffer, audio_data])
        current_time = time.time()
        
        while len(self.chunk_buffer) >= self.chunk_size:
            chunk = self.chunk_buffer[:self.chunk_size]
            self.chunk_buffer = self.chunk_buffer[self.chunk_size:]
            
            is_speech = self.process_vad_chunk_with_smoothing(chunk)
            
            if is_speech:
                self.last_speech_time = current_time
                
                if not self.is_recording:
                    self.is_recording = True
                    self.recording_start_time = current_time
                    with self.audio_lock:
                        self.audio_buffer = []
                    print("[STT] 🎤 Speech detected by Silero VAD with temporal smoothing, recording...")
                
                with self.audio_lock:
                    self.audio_buffer.extend((chunk * 32767).astype(np.int16))
                
            elif self.is_recording:
                with self.audio_lock:
                    self.audio_buffer.extend((chunk * 32767).astype(np.int16))
                
                if current_time - self.last_speech_time > self.silence_duration:
                    recording_duration = current_time - self.recording_start_time
                    
                    if recording_duration >= self.min_audio_length:
                        print("[STT] 🔇 End of speech detected by Silero VAD")
                        self._finish_recording()
                        return
                    else:
                        print("[STT] ⏳ Recording too short, continuing...")
                        self.is_recording = False
                        with self.audio_lock:
                            self.audio_buffer = []

    def _finish_recording(self):
        """Finish recording and signal completion via threading Event"""
        with self.audio_lock:
            if len(self.audio_buffer) > 0:
                self.completed_audio = self.audio_buffer.copy()
                print(f"[STT] Recording finished, {len(self.completed_audio)} samples captured")
            else:
                self.completed_audio = None
                print("[STT] Recording finished but no audio captured")
            
            self.audio_buffer = []
            self.is_recording = False
        
        if vad_iterator:
            vad_iterator.reset_states()
        
        self.recording_complete.set()
    
    def start_recording(self):
        """Start audio recording stream"""
        if not AUDIO_AVAILABLE:
            print("[STT] Audio recording not available")
            return False
        
        try:
            print(f"[STT] Starting Silero VAD audio stream (rate={self.sampling_rate}, chunk={self.chunk_size})")
            
            self.recording_complete.clear()
            self.completed_audio = None
            
            if vad_iterator:
                vad_iterator.reset_states()
            
            self.stream = sd.InputStream(
                samplerate=self.sampling_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=self.chunk_size,
                callback=self.audio_callback
            )
            self.stream.start()
            return True
        except Exception as e:
            print(f"[STT] Error starting recording: {e}")
            return False
        
    def wait_for_recording_completion(self, timeout=60):
        """Wait for recording to complete and return audio data"""
        print(f"[STT] Waiting for recording completion (timeout: {timeout}s)...")
        
        if self.recording_complete.wait(timeout=timeout):
            print("[STT] Recording completed successfully")
            with self.audio_lock:
                return self.completed_audio
        else:
            print(f"[STT] Recording wait timed out after {timeout}s")
            # Don't return None immediately - let caller check for captured audio
            return None
    
    def stop_recording(self):
        """Stop audio recording stream"""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        if vad_iterator:
            vad_iterator.reset_states()
        
        if self.is_recording:
            self._finish_recording()
        
        with self.audio_lock:
            return self.completed_audio

def save_audio_to_file(audio_data, filename):
    """Save recorded audio to WAV file"""
    channels = json_config['channels']
    sampling_rate = json_config['sampling_rate']
    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sampling_rate)
            wf.writeframes(np.array(audio_data).tobytes())
        return True
    except Exception as e:
        print(f"[STT] Error saving audio file: {e}")
        return False

def check_whisper_server():
    """Check if Whisper.cpp server is available"""
    whisper_health_url = json_config['whisper_health_url']
    try:
        response = requests.get(whisper_health_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("status") == "ok"
    except Exception as e:
        print(f"[STT] Whisper server health check failed: {e}")
    return False

def transcribe_with_whisper_server(audio_file_path):
    """Transcribe audio file using Whisper.cpp server"""
    whisper_api_url = json_config['whisper_api_url']
    try:
        print(f"[STT] Sending audio to Whisper server: {whisper_api_url}")
        
        with open(audio_file_path, 'rb') as f:
            files = {'file': (os.path.basename(audio_file_path), f, 'audio/wav')}
            headers = {'accept': 'application/json'}
            
            response = requests.post(
                whisper_api_url,
                files=files,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                transcript = result.get('text', '').strip()
                print(f"[STT] Whisper transcribed: '{transcript}'")
                return transcript
            else:
                print(f"[STT] Whisper server error: {response.status_code}, {response.text}")
                return ""
                
    except Exception as e:
        print(f"[STT] Error in Whisper transcription: {e}")

def record_audio_with_silero_vad():
    """Record audio using Silero VAD for real-time speech detection"""
    sampling_rate = json_config['sampling_rate']
    max_duration = json_config.get('max_recording_duration', 120)  # Default 2 minutes
    
    if not AUDIO_AVAILABLE:
        return None
    
    print("[STT] Starting Silero VAD recording...")
    print(f"[STT] Maximum recording duration: {max_duration} seconds")
    recorder = SileroVADAudioRecorder()
    
    if not recorder.start_recording():
        return None
    
    print("[STT] Listening with Silero VAD... speak now!")
    
    try:
        # Wait for recording completion with configurable timeout
        audio_data = recorder.wait_for_recording_completion(timeout=max_duration)
        
        if audio_data:
            duration_seconds = len(audio_data) / sampling_rate
            print(f"[STT] Successfully captured {duration_seconds:.2f} seconds of audio")
            return audio_data
        else:
            print("[STT] Wait timed out, checking for captured audio...")
            # Even if wait timed out, check if audio was captured
            final_audio = recorder.stop_recording()
            if final_audio and len(final_audio) > 0:
                duration_seconds = len(final_audio) / sampling_rate
                print(f"[STT] ✅ Recovered {duration_seconds:.2f} seconds of audio after timeout")
                return final_audio
            else:
                print("[STT] No audio data captured")
                return None
            
    except KeyboardInterrupt:
        print("[STT] Recording interrupted by user")
        # Still try to recover any captured audio
        final_audio = recorder.stop_recording()
        if final_audio and len(final_audio) > 0:
            print("[STT] Recovered audio after interruption")
            return final_audio
        return None
    except Exception as e:
        print(f"[STT] Error during recording: {e}")
        # Still try to recover any captured audio
        final_audio = recorder.stop_recording()
        if final_audio and len(final_audio) > 0:
            print("[STT] Recovered audio after error")
            return final_audio
        return None
    finally:
        # Ensure recording is stopped
        try:
            recorder.stop_recording()
        except:
            pass

def real_transcription():
    """Real speech-to-text using Silero VAD and Whisper.cpp server"""
    print("[STT] Starting real speech recognition with Silero VAD...")
    
    sampling_rate = json_config['sampling_rate']
    
    audio_data = record_audio_with_silero_vad()
    
    if not audio_data:
        print("[STT] No audio recorded")
        return ""
    
    duration_seconds = len(audio_data) / sampling_rate
    print(f"[STT] Recorded {duration_seconds:.2f} seconds of speech")
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        temp_filename = temp_audio.name
    
    if not save_audio_to_file(audio_data, temp_filename):
        return ""
    
    try:
        transcript = transcribe_with_whisper_server(temp_filename)
        return transcript
    finally:
        try:
            os.unlink(temp_filename)
        except:
            pass

async def trigger_llm_processing(transcript):
    """Direct communication with LLM component via HTTP API with retry"""
    print(f"[STT] 📞 Sending transcript to LLM via HTTP: '{transcript}'")
    
    max_retries = 3
    retry_delay = 1.0  # seconds
    
    for attempt in range(max_retries):
        try:
            # Send transcript directly to LLM component via HTTP
            async with aiohttp.ClientSession() as session:
                payload = {"transcript": transcript}
                async with session.post(
                    "http://localhost:8082/process_transcript", 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"[STT] ✅ LLM processed transcript successfully")
                        return result
                    else:
                        print(f"[STT] ❌ LLM HTTP error: {response.status}")
                        
        except Exception as e:
            print(f"[STT] ❌ HTTP attempt {attempt + 1}/{max_retries} failed: {e}")
            
            if attempt < max_retries - 1:  # Not the last attempt
                print(f"[STT] 🔄 Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"[STT] ❌ All HTTP attempts failed. LLM component may not be running.")
                return None

async def on_user_wants_to_talk(key, value, old):
    """Handle GUI trigger for starting speech recognition"""
    if value == "True":
        print(f"[STT] 🎯 USER_WANTS_TO_TALK triggered: {key} = {value}")
        
        # Reset the trigger with higher priority to overcome GUI's trigger priority
        print(f"[STT] 🔄 Resetting user_wants_to_talk with priority 30...")
        await state.set("user_wants_to_talk", "False", source="stt", priority=30)
        
        # Check if AI is currently speaking
        ai_speaking = state.get_value("ai_speaking")
        if ai_speaking == "True":
            print("[STT] AI is speaking, waiting...")
            return
            
        # Start the speech recognition process
        print("[STT] ✅ Starting speech recognition...")
        await state.set("human_speaking", "True", source="stt", priority=10)
        
        # Use real transcription in a separate thread to avoid blocking
        def transcribe_async():
            return real_transcription()
        
        # Run transcription in thread pool to avoid blocking async loop
        with concurrent.futures.ThreadPoolExecutor() as executor:
            transcript = await asyncio.get_event_loop().run_in_executor(
                executor, transcribe_async
            )
        
        # Process the result and only proceed if we have a transcript
        if transcript and transcript.strip():
            print(f"[STT] Final transcript: '{transcript}'")
            
            # Pass transcript directly to LLM (not Redis)
            await trigger_llm_processing(transcript)
            
            print("[STT] Setting stt_ready = True")
            await state.set("stt_ready", "True", source="stt", priority=20)
            print("[STT] Setting human_speaking = False") 
            await state.set("human_speaking", "False", source="stt", priority=10)
            print("[STT] Speech recognition complete")
            
            print("[STT] 🔄 Ready for next user_wants_to_talk trigger")
            # Reset to normal priority - GUI priority 40 can override this
            await state.set("user_wants_to_talk", "False", source="stt", priority=30)
            print("[STT] 🔄 Reset to normal priority for GUI compatibility")
        else:
            print("[STT] No transcript generated - not triggering LLM")
            print("[STT] Setting human_speaking = False") 
            await state.set("human_speaking", "False", source="stt", priority=10)
            
            print("[STT] 🔄 Ready for next user_wants_to_talk trigger")
            # Reset to normal priority - GUI priority 40 can override this
            await state.set("user_wants_to_talk", "False", source="stt", priority=30)
            print("[STT] 🔄 Reset to normal priority for GUI compatibility")
            
            # Signal GUI that no speech was detected
            await state.set("stt_ready", "False", source="stt", priority=20)
            
            print("[STT] Speech recognition aborted (no audio/transcript)")
            
            # Reset the user_wants_to_talk to allow new attempts
            await state.set("user_wants_to_talk", "False", source="stt", priority=10)
        
async def stt_listener():
    """Listen for user_wants_to_talk events"""
    global continuous_monitor
    
    # STT component initialization - removed ai_speaking and ai_thinking 
    # since those states are managed by TTS and LLM components respectively
    print("[STT] ✅ STT component initialized")
    
    whisper_server_url = json_config['whisper_server_url']
    sampling_rate = json_config['sampling_rate']
    amplitude_threshold = json_config['amplitude_threshold']
    chunk_size = json_config['chunk_size']
    vad_threshold = json_config['vad_threshold']
    silence_duration = json_config['silence_duration']
    min_audio_length = json_config['min_audio_length']
    max_recording_duration = json_config.get('max_recording_duration', 120)

    state.subscribe("user_wants_to_talk", on_user_wants_to_talk)
    
    # Initialize Silero VAD
    silero_initialized = initialize_silero_vad()
    
    # Initialize and start continuous audio monitor for interruptions
    if AUDIO_AVAILABLE and silero_initialized:
        continuous_monitor = ContinuousAudioMonitor()
        monitor_started = continuous_monitor.start_monitoring()
        print(f"[STT] Continuous Interruption Monitor: {'✅ Active' if monitor_started else '❌ Failed'}")
    else:
        print("[STT] ⚠️ Continuous monitoring disabled (audio or VAD unavailable)")
    
    # Print startup status
    print("[STT] Speech-to-Text Component with Direct LLM Communication Started")
    print(f"[STT] Audio Available: {AUDIO_AVAILABLE}")
    print(f"[STT] Silero VAD Available: {SILERO_AVAILABLE}")
    print(f"[STT] Silero VAD Initialized: {silero_initialized}")
    print(f"[STT] Whisper Server: {whisper_server_url}")
    
    # Check Whisper server availability
    server_available = check_whisper_server()
    print(f"[STT] Whisper Server Available: {server_available}")
    
    if silero_initialized:
        print(f"[STT] VAD Configuration:")
        print(f"[STT]   - Sampling Rate: {sampling_rate} Hz")
        print(f"[STT]   - Chunk Size: {chunk_size} samples ({chunk_size/sampling_rate*1000:.0f}ms)")
        print(f"[STT]   - Base VAD Threshold: {vad_threshold}")
        print(f"[STT]   - Fallback Amplitude Threshold: {amplitude_threshold}")
        print(f"[STT]   - Silence Duration: {silence_duration}s")
        print(f"[STT]   - Min Audio Length: {min_audio_length}s")
        print(f"[STT]   - Max Recording Duration: {max_recording_duration}s")
        
        # Show temporal smoothing configuration
        temporal_config = json_config.get('temporal_smoothing', {})
        if temporal_config.get('enabled', False):
            print(f"[STT]   - Temporal Smoothing: ENABLED")
            print(f"[STT]     * Confidence Buffer Size: {temporal_config.get('confidence_buffer_size', 5)} chunks")
            print(f"[STT]     * Start Threshold Ratio: {temporal_config.get('start_threshold_ratio', 0.7)} (={vad_threshold * temporal_config.get('start_threshold_ratio', 0.7):.3f})")
            print(f"[STT]     * Continue Threshold Ratio: {temporal_config.get('continue_threshold_ratio', 0.9)} (={vad_threshold * temporal_config.get('continue_threshold_ratio', 0.9):.3f})")
        else:
            print(f"[STT]   - Temporal Smoothing: DISABLED (using base threshold {vad_threshold})")
    
    print("[STT] Listening for GUI triggers and state changes...")
    print("[STT] Using HTTP API to communicate with LLM component...")
    
    # Start the state listener in the background
    try:
        await state.listen()
    except KeyboardInterrupt:
        print("[STT] 👋 STT component stopped by user")
    finally:
        # Cleanup continuous monitor
        if continuous_monitor:
            continuous_monitor.stop_monitoring()

if __name__ == "__main__":
    json_config = load_config()
    try:
        asyncio.run(stt_listener())
    except KeyboardInterrupt:
        print("[STT] 👋 STT component stopped by user")
        # Cleanup continuous monitor
        if continuous_monitor:
            continuous_monitor.stop_monitoring()