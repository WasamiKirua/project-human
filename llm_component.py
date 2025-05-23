import asyncio
import redis
from redis_state import RedisState
from memory_component import store_memory_entry, build_context

# Initialize Redis and state manager
r = redis.Redis(decode_responses=True, host='localhost', port=6379, password='rhost21')
state = RedisState(r)

# Simulated LLM API call
async def call_llm(transcript: str, context: str) -> str:
    await asyncio.sleep(2)  # Simulated delay
    return f"This is an LLM reply to: '{transcript}' with context: '{context}'"

# Async listener triggered when STT is ready
async def on_stt_ready(key, value, old):
    print(f"[LLM] Received: {key} = {value} (type: {type(value)})")
    if value == "True":
        try:
            print("[LLM] Triggered by STT readiness signal.")

            # Reset flag and notify system AI is thinking
            print("[LLM] Setting ai_thinking = True")
            await state.set("stt_ready", False, source="llm", priority=15)
            await state.set("ai_thinking", True, source="llm", priority=10)

            transcript = r.get("last_transcription") or "Hello"
            context = build_context()
            print(f"[LLM] Got transcript: '{transcript}'")
            print(f"[LLM] Got context: '{context[:100]}...'")

            # Optional: Save user input to memory
            store_memory_entry("user", transcript)
            print("[LLM] Saved user input to memory")

            # Generate AI reply
            print("[LLM] Calling LLM...")
            reply = await call_llm(transcript, context)
            print(f"[LLM] Got reply: '{reply[:100]}...'")

            # Save reply to Redis for TTS
            r.set("last_llm_reply", reply)
            print("[LLM] Saved reply to Redis")

            # Optional: Save AI reply to memory
            store_memory_entry("assistant", reply)
            print("[LLM] Saved assistant reply to memory")

            # Clear thinking flag, signal TTS readiness
            print("[LLM] Setting ai_thinking = False, tts_ready = True")
            await state.set("ai_thinking", False, source="llm", priority=10)
            await state.set("tts_ready", True, source="llm", priority=8)
            print("[LLM] LLM processing complete!")

        except Exception as e:
            print(f"[LLM] ERROR in LLM processing: {e}")
            # Reset states on error
            await state.set("ai_thinking", False, source="llm", priority=10)
            import traceback
            traceback.print_exc()

# Main listener loop
async def llm_loop():
    state.subscribe("stt_ready", on_stt_ready)
    print("[LLM] Listening for 'stt_ready' state changes...")
    
    # Start the state listener
    await state.listen()

if __name__ == "__main__":
    asyncio.run(llm_loop())
