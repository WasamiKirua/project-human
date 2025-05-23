import time
import redis
import asyncio
import threading
import tempfile
import os
import wave
import requests
import json
from redis_state import RedisState

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

r = redis.Redis(decode_responses=True, host='localhost', port=6379, password='rhost21')
state = RedisState(r)

TRANSCRIPT_KEY = "last_transcription"

# Global Silero VAD model
silero_model = None
vad_iterator = None

def load_config():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            stt_config = config.get("stt", {})
    return stt_config

def initialize_silero_vad():
    """Initialize Silero VAD ONNX model following the official documentation pattern"""
    sempling_rate = json_config['sampling_rate']
    global silero_model, vad_iterator
    
    if not SILERO_AVAILABLE:
        print("[STT] Silero VAD not available")
        return False
    
    try:
        print("[STT] Loading Silero VAD ONNX model...")
        
        # For pip package (silero-vad v5.1.2+), load_silero_vad() only accepts onnx parameter
        # The opset_version is handled internally and cannot be specified
        try:
            silero_model = load_silero_vad(onnx=True)
            print("[STT] Silero VAD ONNX model loaded successfully (pip package)")
        except Exception as e:
            # Fallback: try non-ONNX version
            print(f"[STT] ONNX loading failed: {e}")
            print("[STT] Falling back to PyTorch JIT model...")
            silero_model = load_silero_vad(onnx=False)
            print("[STT] Silero VAD PyTorch model loaded successfully")
        
        # Create VAD iterator for real-time processing
        vad_iterator = VADIterator(silero_model, sampling_rate=sempling_rate)
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
        
    def process_vad_chunk(self, audio_chunk):
        """Process audio chunk with Silero VAD"""
        if not SILERO_AVAILABLE or silero_model is None:
            # Fallback to simple amplitude detection using AMPLITUDE_THRESHOLD
            return np.max(np.abs(audio_chunk)) > self.amplitude_threshold
        
        try:
            # Silero VAD expects chunks of exactly 512 samples for 16kHz
            if len(audio_chunk) == self.chunk_size:
                # Get VAD prediction (returns probability 0.0-1.0)
                speech_prob = silero_model(torch.from_numpy(audio_chunk), self.sampling_rate).item()
                return speech_prob > self.vad_threshold
            return False
        except Exception as e:
            print(f"[STT] VAD processing error: {e}")
            # Fallback to amplitude detection using AMPLITUDE_THRESHOLD
            return np.max(np.abs(audio_chunk)) > self.amplitude_threshold
    
    def audio_callback(self, indata, frames, time_info, status):
        """Real-time audio callback with Silero VAD processing"""
        if status:
            print(f"[STT] Audio callback status: {status}")
        
        # Convert to mono and flatten
        audio_data = indata.flatten() if self.channels == 1 else indata[:, 0]
        
        # Add to chunk buffer
        self.chunk_buffer = np.concatenate([self.chunk_buffer, audio_data])
        
        current_time = time.time()
        
        # Process complete chunks of 512 samples
        while len(self.chunk_buffer) >= self.chunk_size:
            # Extract chunk
            chunk = self.chunk_buffer[:self.chunk_size]
            self.chunk_buffer = self.chunk_buffer[self.chunk_size:]
            
            # Process with Silero VAD
            is_speech = self.process_vad_chunk(chunk)
            
            if is_speech:
                self.last_speech_time = current_time
                
                if not self.is_recording:
                    self.is_recording = True
                    self.recording_start_time = current_time
                    with self.audio_lock:
                        self.audio_buffer = []
                    print("[STT] 🎤 Speech detected by Silero VAD, recording...")
                
                # Add chunk to buffer (convert to int16 for WAV)
                with self.audio_lock:
                    self.audio_buffer.extend((chunk * 32767).astype(np.int16))
                
            elif self.is_recording:
                # Continue recording during brief pauses
                with self.audio_lock:
                    self.audio_buffer.extend((chunk * 32767).astype(np.int16))
                
                # Check if silence duration exceeded
                if current_time - self.last_speech_time > self.silence_duration:
                    recording_duration = current_time - self.recording_start_time
                    
                    if recording_duration >= self.min_audio_length:
                        print("[STT] 🔇 End of speech detected by Silero VAD")
                        self._finish_recording()
                        return  # Important: stop processing more audio
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
        
        # Reset VAD iterator states for next recording
        if vad_iterator:
            vad_iterator.reset_states()
        
        # Signal that recording is complete
        self.recording_complete.set()
    
    def start_recording(self):
        """Start audio recording stream"""
        if not AUDIO_AVAILABLE:
            print("[STT] Audio recording not available")
            return False
        
        try:
            print(f"[STT] Starting Silero VAD audio stream (rate={self.sampling_rate}, chunk={self.chunk_size})")
            
            # Reset state
            self.recording_complete.clear()
            self.completed_audio = None
            
            # Reset VAD iterator
            if vad_iterator:
                vad_iterator.reset_states()
            
            self.stream = sd.InputStream(
                samplerate=self.sampling_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=self.chunk_size,  # Use Silero's preferred chunk size
                callback=self.audio_callback
            )
            self.stream.start()
            return True
        except Exception as e:
            print(f"[STT] Error starting recording: {e}")
            return False
        
    def wait_for_recording_completion(self, timeout=30):
        """Wait for recording to complete and return audio data"""
        print("[STT] Waiting for recording completion...")
        
        # Wait for the recording_complete event
        if self.recording_complete.wait(timeout=timeout):
            print("[STT] Recording completed successfully")
            with self.audio_lock:
                return self.completed_audio
        else:
            print("[STT] Recording timed out")
            return None
    
    def stop_recording(self):
        """Stop audio recording stream"""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        # Reset VAD states
        if vad_iterator:
            vad_iterator.reset_states()
        
        # If we're still recording, finish it
        if self.is_recording:
            self._finish_recording()
        
        # Return any remaining audio data
        with self.audio_lock:
            return self.completed_audio

def save_audio_to_file(audio_data, filename):
    """Save recorded audio to WAV file"""
    channels = json_config['channels']
    sampling_rate = json_config['sampling_rate']
    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 2 bytes for int16
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
    if not AUDIO_AVAILABLE:
        return None
    
    print("[STT] Starting Silero VAD recording...")
    recorder = SileroVADAudioRecorder()
    
    if not recorder.start_recording():
        return None
    
    print("[STT] Listening with Silero VAD... speak now!")
    
    try:
        # Wait for recording to complete (with timeout)
        audio_data = recorder.wait_for_recording_completion(timeout=30)
        
        if audio_data:
            duration_seconds = len(audio_data) / sampling_rate
            print(f"[STT] Successfully captured {duration_seconds:.2f} seconds of audio")
            return audio_data
        else:
            print("[STT] No audio data captured")
            return None
            
    except KeyboardInterrupt:
        print("[STT] Recording interrupted by user")
        return None
    except Exception as e:
        print(f"[STT] Error during recording: {e}")
        return None
    finally:
        # Always stop the recording stream
        recorder.stop_recording()

def real_transcription():
    """
    Real speech-to-text using Silero VAD and Whisper.cpp server
    """
    print("[STT] Starting real speech recognition with Silero VAD...")
    
    sampling_rate = json_config['sampling_rate']
    
    # Check server availability
    if not check_whisper_server():
        print("[STT] Whisper server not available, using simulation")
        return simulate_transcription()
    
    # Record audio with Silero VAD
    audio_data = record_audio_with_silero_vad()
    
    if not audio_data:
        print("[STT] No audio recorded")
        return ""
    
    duration_seconds = len(audio_data) / sampling_rate
    print(f"[STT] Recorded {duration_seconds:.2f} seconds of speech")
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        temp_filename = temp_audio.name
    
    if not save_audio_to_file(audio_data, temp_filename):
        return ""
    
    try:
        # Transcribe with Whisper server
        transcript = transcribe_with_whisper_server(temp_filename)
        return transcript
    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_filename)
        except:
            pass

def simulate_transcription():
    """
    Simulates receiving audio input and converting it to text.
    In a real app, this would call your STT backend.
    """
    print("[STT] Listening for user speech...")
    time.sleep(3)  # Simulate user talking
    transcript = "Hello, how are you?"
    print(f"[STT] Transcribed: '{transcript}'")
    return transcript

async def on_user_wants_to_talk(key, value, old):
    """Handle GUI trigger for starting speech recognition"""
    if value == "True":
        print("[STT] GUI triggered speech recognition")
        
        # Reset the trigger
        await state.set("user_wants_to_talk", "False", source="stt", priority=10)
        
        # Check if AI is currently speaking
        if state.get_value("ai_speaking") == "True":
            print("[STT] AI is speaking, waiting...")
            return
            
        # Start the speech recognition process
        print("[STT] Starting speech recognition...")
        await state.set("human_speaking", "True", source="stt", priority=10)
        
        # Use real transcription in a separate thread to avoid blocking
        def transcribe_async():
            return real_transcription()
        
        # Run transcription in thread pool to avoid blocking async loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            transcript = await asyncio.get_event_loop().run_in_executor(
                executor, transcribe_async
            )
        
        # Store the result
        if transcript:
            r.set(TRANSCRIPT_KEY, transcript)
            print(f"[STT] Final transcript: '{transcript}'")
        else:
            print("[STT] No transcript generated")
            transcript = ""
        
        # Set flags
        print("[STT] Setting stt_ready = True")
        await state.set("stt_ready", "True", source="stt", priority=20)  # Higher than LLM's 15
        print("[STT] Setting human_speaking = False") 
        await state.set("human_speaking", "False", source="stt", priority=10)
        print("[STT] Speech recognition complete")
        
async def stt_listener():
    """Listen for user_wants_to_talk events"""
    whisper_server_url = json_config['whisper_server_url']
    sampling_rate = json_config['sampling_rate']
    amplitude_threshold = json_config['amplitude_threshold']
    chunk_size = json_config['chunk_size']
    vad_threshold = json_config['vad_threshold']
    silence_duration = json_config['silence_duration']
    min_audio_length = json_config['min_audio_length']

    state.subscribe("user_wants_to_talk", on_user_wants_to_talk)
    
    # Initialize Silero VAD
    silero_initialized = initialize_silero_vad()
    
    # Print startup status
    print("[STT] Speech-to-Text Component with Silero VAD Started")
    print(f"[STT] Audio Available: {AUDIO_AVAILABLE}")
    print(f"[STT] Silero VAD Available: {SILERO_AVAILABLE}")
    print(f"[STT] Silero VAD Initialized: {silero_initialized}")
    print(f"[STT] Whisper Server: {whisper_server_url}")
    
    # Check Whisper server availability
    server_available = check_whisper_server()
    print(f"[STT] Whisper Server Available: {server_available}")
    
    if not AUDIO_AVAILABLE:
        print("[STT] Install sounddevice for real audio recording:")
        print("[STT]   pip install sounddevice numpy")
    
    if not SILERO_AVAILABLE:
        print("[STT] Install Silero VAD for better speech detection:")
        print("[STT]   pip install silero-vad onnxruntime")
    
    if not server_available:
        print("[STT] Start your Whisper.cpp server:")
        print(f"[STT]   whisper-server --host 127.0.0.1 --port 8081 --model <model_path>")
    
    if silero_initialized:
        print(f"[STT] VAD Configuration:")
        print(f"[STT]   - Sampling Rate: {sampling_rate} Hz")
        print(f"[STT]   - Chunk Size: {chunk_size} samples (32ms)")
        print(f"[STT]   - Silero VAD Threshold: {vad_threshold}")
        print(f"[STT]   - Fallback Amplitude Threshold: {amplitude_threshold}")
        print(f"[STT]   - Silence Duration: {silence_duration}s")
        print(f"[STT]   - Min Audio Length: {min_audio_length}s")
    
    print("[STT] Listening for GUI triggers and state changes...")
    
    # Start the state listener in the background
    await state.listen()

if __name__ == "__main__":
    json_config = load_config()
    asyncio.run(stt_listener())
