import redis
import json
from redis_state import RedisState
from datetime import datetime

# Initialize Redis and state manager
r = redis.Redis(decode_responses=True, host='localhost', port=6379, password='rhost21')
state = RedisState(r)

MEMORY_KEY = "memory:conversation"
MAX_MEMORY_ENTRIES = 20  # Circular memory buffer

def _get_now():
    return datetime.utcnow().isoformat()

def store_memory_entry(role: str, content: str):
    """Save one interaction to memory."""
    entry = {
        "timestamp": _get_now(),
        "role": role,
        "content": content
    }

    memory = load_memory()
    memory.append(entry)

    # Keep last N entries
    if len(memory) > MAX_MEMORY_ENTRIES:
        memory = memory[-MAX_MEMORY_ENTRIES:]

    r.set(MEMORY_KEY, json.dumps(memory))
    print(f"[Memory] Stored new entry: {role} → {content[:50]}")

def load_memory() -> list:
    """Fetch the current memory list."""
    raw = r.get(MEMORY_KEY)
    if raw:
        try:
            return json.loads(raw)
        except Exception as e:
            print("[Memory] Corrupted memory format:", e)
            return []
    return []

def build_context() -> str:
    """Generate a string context for the LLM."""
    memory = load_memory()
    if not memory:
        return "<no memory yet>"
    
    context_lines = [f"{entry['role'].capitalize()}: {entry['content']}" for entry in memory]
    return "\n".join(context_lines[-6:])  # last 6 lines max

# Optional: Reset memory
def clear_memory():
    r.delete(MEMORY_KEY)
    print("[Memory] Memory cleared.")
