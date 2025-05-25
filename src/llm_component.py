import asyncio
import redis
import openai
import json
import os
import traceback
import aiohttp
from datetime import datetime
from redis_state import RedisState
from aiohttp import web
from openai import AsyncOpenAI
from utils.prompts import CHARACTER_CARD_PROMPT


# Set your OpenAI API key
# openai.api_key = os.getenv("OPENAI_API_KEY")  # Uncomment when you have API key

# Initialize Redis and state manager
r = redis.Redis(decode_responses=True, host='localhost', port=6379, password='rhost21')
state = RedisState(r)

class LLMComponent:
    def __init__(self):
        global llm_component  # Set global reference immediately
        
        # Load configuration
        self.config = self.load_config()
        
        # In-memory conversation context for current session
        self.conversation_history = []
        self.session_start = datetime.now()
        
        # Fake memory stores (will be replaced with SQLite/Weaviate later)
        self.short_term_memory = []  # Recent conversations
        self.long_term_memory = []   # Important/frequent topics
        self.user_preferences = {}   # User-specific data
        
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
            print(f"[LLM] Built context with {len(context['recent'])} recent items")
            
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
        
        # Fake SQLite recent history simulation
        recent_history = await self.get_fake_recent_history()
        
        # Fake Weaviate semantic search simulation
        relevant_memories = await self.get_fake_relevant_memories(current_transcript)
        
        # Current session context
        current_session = self.conversation_history[-10:]  # Last 10 exchanges
        
        context = {
            "recent": recent_history,
            "relevant_memories": relevant_memories,
            "current_session": current_session,
            "user_preferences": self.user_preferences
        }
        
        return context
    
    async def get_fake_recent_history(self):
        """Fake SQLite database - recent conversations"""
        # Simulate recent conversation history
        fake_recent = [
            {"role": "user", "content": "What's the weather like?"},
            {"role": "assistant", "content": "I'd need your location to check the weather."},
            {"role": "user", "content": "I'm in Munich"},
            {"role": "assistant", "content": "Munich typically has mild weather this time of year."}
        ]
        
        # Return only last 3 for context (simulate LIMIT 3)
        return fake_recent[-3:]
    
    async def get_fake_relevant_memories(self, query):
        """Fake Weaviate semantic search"""
        # Simulate semantic search based on keywords
        all_memories = [
            {"content": "User prefers detailed explanations", "position": 0},
            {"content": "User is interested in technology topics", "position": 1},
            {"content": "User lives in Munich, Germany", "position": 2},
            {"content": "User asks about weather frequently", "position": 3},
            {"content": "User prefers casual conversation style", "position": 4}
        ]
        
        # Fake long term memory based on simple keyword matching
        relevant = []
        query_lower = query.lower()
        
        for memory in all_memories:
            # Simple scoring based on keyword overlap
            if any(word in query_lower for word in ["weather", "munich", "location"]):
                if "munich" in memory["content"].lower() or "weather" in memory["content"].lower():
                    relevant.append(memory)
            elif any(word in query_lower for word in ["how", "what", "explain"]):
                if "detailed" in memory["content"].lower():
                    relevant.append(memory)
        
        # Return top 3 most relevant
        return sorted(relevant, key=lambda x: x["position"], reverse=True)[:3]
    
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
        
        # Add recent history
        for item in context["recent"]:
            messages.append({"role": item["role"], "content": item["content"]})
        
        # Add current session
        for item in context["current_session"]:
            messages.append(item)
        
        # Add current user input
        messages.append({"role": "user", "content": transcript})
        
        # For now, simulate OpenAI API call (replace with real call when you have API key)
        # response = await self.simulate_openai_call(messages)

        client = AsyncOpenAI(base_url=f'http://localhost:{port}/v1', api_key=api_key)
        
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2048,
            temperature=0.7
        )
        return response.choices[0].message.content
        
        #return response
    
    def build_system_prompt(self, context):
        """Build system prompt with context information"""
        base_prompt = CHARACTER_CARD_PROMPT
        
        # Add relevant memories to prompt
        if context["relevant_memories"]:
            memory_text = " Based on what I know about you: "
            memory_text += ", ".join([mem["content"] for mem in context["relevant_memories"]])
            base_prompt += memory_text
        
        # Add user preferences
        if context["user_preferences"]:
            pref_text = " Your preferences: "
            pref_text += ", ".join([f"{k}: {v}" for k, v in context["user_preferences"].items()])
            base_prompt += pref_text
        
        return base_prompt
    
    async def simulate_openai_call(self, messages):
        """Simulate OpenAI API call for testing"""
        # Simulate API delay
        await asyncio.sleep(1)
        
        # Get the user's message
        user_message = messages[-1]["content"]
        
        # Simple response generation based on keywords
        if any(word in user_message.lower() for word in ["hello", "hi", "hey"]):
            return f"Hello! Nice to hear from you. How can I help you today?"
        elif any(word in user_message.lower() for word in ["weather", "temperature"]):
            return f"I'd be happy to help with weather information. Since you're in Munich, I can tell you that the weather there is typically quite pleasant this time of year!"
        elif any(word in user_message.lower() for word in ["how", "are", "you"]):
            return f"I'm doing great, thank you for asking! I'm here and ready to help with whatever you need."
        elif any(word in user_message.lower() for word in ["time", "what time"]):
            return f"I don't have access to real-time information, but I can help you with time-related questions if you'd like!"
        else:
            return f"Thanks for sharing that with me! I heard you say: '{user_message}'. How can I help you with that?"
    
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
        
        #TODO: Memory implementation
        # Fake SQLite storage simulation
        # await self.store_in_fake_sqlite(user_input, ai_response, timestamp)
        
        # Fake Weaviate storage simulation
        # await self.store_in_fake_weaviate(user_input, ai_response, timestamp)
        
        print("[LLM] ✅ Conversation stored in all memory systems")
    
    async def store_in_fake_sqlite(self, user_input, ai_response, timestamp):
        """Fake SQLite storage for recent history"""
        # Simulate storing in SQLite database
        conversation_entry = {
            "id": len(self.short_term_memory) + 1,
            "user_input": user_input,
            "ai_response": ai_response,
            "timestamp": timestamp.isoformat(),
            "session_id": self.session_start.isoformat()
        }
        
        self.short_term_memory.append(conversation_entry)
        
        # Keep only last 100 entries (simulate database cleanup)
        if len(self.short_term_memory) > 100:
            self.short_term_memory = self.short_term_memory[-100:]
        
        print(f"[LLM] 📝 Stored in fake SQLite: {len(self.short_term_memory)} total entries")
    
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
