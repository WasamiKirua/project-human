import asyncio
import json
import os
import traceback
import aiohttp
from datetime import datetime
from redis_state import RedisState
from aiohttp import web
from openai import AsyncOpenAI
from memory_component import MemoryComponent
from utils.prompts import CHARACTER_CARD_PROMPT
from redis_client import create_redis_client

# Redis config & state
r = create_redis_client()
state = RedisState(r)

class LLMComponent:
    def __init__(self):
        global llm_component  # Set global reference immediately
        
        # Load configuration
        self.config = self.load_config()
        print(f"[LLM] Loaded config: {self.config}")
        
        # In-memory conversation context for current session
        self.conversation_history = []
        self.session_start = datetime.now()
        
        # Fake memory stores (will be replaced with SQLite/Weaviate later)
        self.short_term_memory = []  # Recent conversations
        self.long_term_memory = []   # Important/frequent topics
        self.memory_component = MemoryComponent()
        
        print("[LLM] LLM Component initialized with in-memory context")
    
    def load_config(self):
        """Load configuration from config.json"""
        config_path = 'config.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config.get("llm", {})
            except Exception as e:
                print(f"[LLM] Error loading config: {e}")
                return {}
        return {}
    
    async def process_transcript(self, transcript):
        """Process transcript directly from STT - main entry point"""
        print(f"[LLM] 📥 Received transcript directly: '{transcript}'")
        
        try:
            # Set thinking state
            await state.set("ai_thinking", "True", source="llm", priority=10)
            
            # Build context from memory systems
            context = await self.build_context(transcript)
            print(f"[LLM] Built context with {len(context['relevant_memories'])} semantic memories")
            
            # Generate response
            response = await self.generate_response(transcript, context)
            print(f"[LLM] Generated response: '{response[:100]}...'")
            
            # Update memory systems
            await self.store_conversation(transcript, response)
            
            # Pass response directly to TTS
            await self.trigger_tts_processing(response)
            
            # Clear thinking state and signal TTS readiness
            await state.set("ai_thinking", "False", source="llm", priority=10)
            await state.set("tts_ready", "True", source="llm", priority=8)
            
            print("[LLM] Processing complete!")
            
        except Exception as e:
            print(f"[LLM] ❌ Error in LLM processing: {e}")
            # Reset states on error
            await state.set("ai_thinking", "False", source="llm", priority=10)
            traceback.print_exc()
    
    async def build_context(self, current_transcript):
        """Build context from multiple memory sources"""
        print("[LLM] 🧠 Building context from memory systems...")
        
        # Get semantic memories (intelligent)
        relevant_memories = await self.get_fake_relevant_memories(current_transcript)
        
        # Current session context (recent)
        current_session = self.conversation_history[-10:]  # Last 10 exchanges
        
        context = {
            "relevant_memories": relevant_memories,
            "current_session": current_session
        }
        
        return context
    
    async def get_fake_relevant_memories(self, query):
        """Get relevant memories from Weaviate semantic search"""
        try:
            # Use real memory component instead of fake data
            memories = await self.memory_component.get_semantic_memories(query, limit=3)

            # Convert to the expected format for backward compatibility
            formatted_memories = []
            for memory in memories:
                formatted_memories.append({
                    "content": memory["content"],
                    "position": memory["position"],
                    "type": memory.get("memory_type", "general"),
                    "timestamp": memory.get("timestamp", "")
                })

            print(f"[LLM] 🧠 Retrieved {len(formatted_memories)} semantic memories")
            return formatted_memories

        except Exception as e:
            print(f"[LLM] ⚠️ Semantic memory retrieval failed: {e}")
            # Fallback to empty list if memory system fails
            return []
    
    async def generate_response(self, transcript, context):
        """Generate AI response using OpenAI API with full context"""
        print("[LLM] 🤖 Generating response...")

        # Retrieve LLM Config from JSON
        port = None
        api_key = None
        model = None
        
        for llm, config in self.config.items():
            if config.get('enabled') == 'true':
                port = config.get('port')
                api_key = config.get('api_key')
                model = config.get('model')
                break
        
        if not port:
            raise ValueError("No enabled LLM configuration found")
        
        # Build system prompt with context
        system_prompt = self.build_system_prompt(context)
        
        # Build conversation messages with context
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add current session
        for item in context["current_session"]:
            messages.append(item)
        
        # Add current user input
        messages.append({"role": "user", "content": transcript})

        client = AsyncOpenAI(base_url=f'http://localhost:{port}/v1', api_key=api_key)
        
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2048,
            temperature=0.7
        )
        return response.choices[0].message.content
    
    def build_system_prompt(self, context):
        """Build system prompt with context information"""
        base_prompt = CHARACTER_CARD_PROMPT
        
        # Add relevant memories to prompt
        if context["relevant_memories"]:
            memory_text = " Based on what I know about you: "
            memory_text += ", ".join([mem["content"] for mem in context["relevant_memories"]])
            base_prompt += memory_text
        
        return base_prompt
    
    async def store_conversation(self, user_input, ai_response):
        """Store conversation in memory systems"""
        print("[LLM] 💾 Storing conversation in memory systems...")
        
        timestamp = datetime.now()
        
        # Update in-memory session context
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": ai_response})
        
        # Keep only last 20 exchanges in memory
        if len(self.conversation_history) > 40:  # 20 exchanges * 2 messages each
            self.conversation_history = self.conversation_history[-40:]
        
        # SQLite storage
        await self.store_in_sqlite(user_input, ai_response)
        
        print("[LLM] ✅ Conversation stored in all memory systems")
    
    async def store_in_sqlite(self, user_input, ai_response):
        """Store conversation using memory component's public interface"""
        self.memory_component.store_conversations(user_input, ai_response)
        
        print(f"[LLM] 📝 Stored conversation in memory systems")
    
    async def store_in_fake_weaviate(self, user_input, ai_response, timestamp):
        """Fake Weaviate storage for semantic search"""
        # Simulate creating embeddings and storing in vector database
        # Extract potential long-term memories
        
        # Simple keyword-based "semantic" analysis for demo
        keywords = user_input.lower().split()
        
        if any(word in keywords for word in ["like", "prefer", "favorite", "love", "hate"]):
            # This seems like a preference
            preference_entry = {
                "type": "preference",
                "content": f"User expressed: {user_input}",
                "context": ai_response,
                "timestamp": timestamp.isoformat(),
                "relevance_keywords": keywords
            }
            self.long_term_memory.append(preference_entry)
        
        if any(word in keywords for word in ["live", "from", "location", "city"]):
            # This seems like location info
            location_entry = {
                "type": "location",
                "content": f"Location context: {user_input}",
                "context": ai_response,
                "timestamp": timestamp.isoformat(),
                "relevance_keywords": keywords
            }
            self.long_term_memory.append(location_entry)
        
        # Keep only last 500 long-term memories
        if len(self.long_term_memory) > 500:
            self.long_term_memory = self.long_term_memory[-500:]
        
        print(f"[LLM] 🧠 Stored in fake Weaviate: {len(self.long_term_memory)} total memories")
    
    async def trigger_tts_processing(self, response):
        """Direct communication with TTS component via HTTP API"""
        print(f"[LLM] 📞 Sending response to TTS via HTTP: '{response[:50]}...'")
        
        try:
            # Send response directly to TTS component via HTTP  
            async with aiohttp.ClientSession() as session:
                payload = {"text": response}
                async with session.post(
                    "http://localhost:8083/speak_text", 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as tts_response:
                    if tts_response.status == 200:
                        result = await tts_response.json()
                        print(f"[LLM] ✅ TTS processed response successfully")
                        return result
                    else:
                        print(f"[LLM] ❌ TTS HTTP error: {tts_response.status}")
                        
        except Exception as e:
            print(f"[LLM] ❌ Could not reach TTS component: {e}")
            print(f"[LLM] 📡 Using Redis state trigger as fallback")
            
            # Fallback: use Redis state management for TTS
            await state.set("tts_ready", "True", source="llm", priority=8)

async def http_process_transcript(request):
    """HTTP endpoint for receiving transcripts from STT"""
    try:
        data = await request.json()
        transcript = data.get("transcript", "")
        
        print(f"[LLM] 📥 Received transcript via HTTP: '{transcript}'")
        
        # Get the LLM component instance from the app context
        llm_comp = request.app['llm_component']
        
        if llm_comp and transcript:
            # Process transcript directly
            await llm_comp.process_transcript(transcript)
            return web.json_response({"status": "success", "message": "Transcript processed"})
        else:
            return web.json_response({"status": "error", "message": "No LLM component or empty transcript"}, status=400)
            
    except Exception as e:
        print(f"[LLM] ❌ Error in HTTP endpoint: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def start_http_server(llm_component):
    """Start HTTP server for receiving transcripts"""
    app = web.Application()
    app['llm_component'] = llm_component  # Store component in app context
    app.router.add_post('/process_transcript', http_process_transcript)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8082)
    await site.start()
    print("[LLM] HTTP server started on http://localhost:8082")

async def llm_loop():
    """Main LLM loop - HTTP server only"""
    # Create LLM component instance
    llm_component = LLMComponent()
    
    # Start HTTP server with component reference
    await start_http_server(llm_component)
    
    print("[LLM] LLM Component with HTTP API Started")
    print("[LLM] HTTP API: http://localhost:8082/process_transcript")
    print("[LLM] Memory Systems:")
    print("[LLM]   - In-Memory: Session context")
    print("[LLM]   - Fake SQLite: Recent conversation history")
    print("[LLM]   - Fake Weaviate: Semantic long-term memory")
    print("[LLM] Ready to receive transcripts via HTTP API")
    
    # Keep the server running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(llm_loop())
