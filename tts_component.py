import time
import redis
import asyncio
from redis_state import RedisState

# Initialize Redis and RedisState
r = redis.Redis(decode_responses=True, host='localhost', port=6379, password='rhost21')
state = RedisState(r)

# Constants
TTS_RESPONSE_KEY = "last_llm_reply"

# Simulated audio generation
def generate_audio(text: str):
    print(f"[TTS] Generating audio from text: {text[:60]}...")
    time.sleep(2)  # Simulated TTS latency
    print("[TTS] Audio generation complete.")

# Simulated playback with interruption logic
def play_audio():
    print("[TTS] Starting playback...")
    for _ in range(10):
        if state.get_value("human_speaking") == "True":
            print("[TTS] Playback interrupted by human.")
            return False
        time.sleep(0.3)
    print("[TTS] Playback finished successfully.")
    return True

# Async listener for TTS readiness signal
async def on_tts_ready(key, value, old):
    """Handle TTS readiness signal from LLM"""
    if value == "True":
        try:
            print("[TTS] Detected 'tts_ready' = True")

            text = r.get(TTS_RESPONSE_KEY)
            if not text:
                print("[TTS] No LLM reply available. Skipping TTS.")
                # Clear the tts_ready flag anyway
                await state.set("tts_ready", "False", source="tts", priority=3)
                return

            # Set ai_speaking state
            await state.set("ai_speaking", "True", source="tts", priority=3)

            # Generate and play audio
            generate_audio(text)
            success = play_audio()

            # Reset ai_speaking flag
            await state.set("ai_speaking", "False", source="tts", priority=3)

            # Clear tts_ready signal
            await state.set("tts_ready", "False", source="tts", priority=3)

            # Clear LLM reply to avoid reuse
            if success:
                r.delete(TTS_RESPONSE_KEY)
                print("[TTS] Audio playback completed successfully.")

        except Exception as e:
            print(f"[TTS] Error occurred: {e}")
            await state.set("ai_speaking", "False", source="tts", priority=3)
            await state.set("tts_ready", "False", source="tts", priority=2)

# Main TTS listener loop
async def tts_loop():
    """Main loop that listens for tts_ready state changes"""
    state.subscribe("tts_ready", on_tts_ready)
    print("[TTS] Listening for 'tts_ready' state changes...")
    
    # Start the state listener
    await state.listen()

if __name__ == "__main__":
    print("[TTS] Starting TTS component...")
    asyncio.run(tts_loop())
