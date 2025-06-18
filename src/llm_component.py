import asyncio
import json
import os
import traceback
from datetime import datetime
from redis_state import RedisState
from aiohttp import web
from openai import AsyncOpenAI
from memory_component import MemoryComponent
from utils.prompts import CHARACTER_CARD_PROMPT, ROUTING_PROMPT
from utils.tools import ToolManager
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

        # Add router configuration loading
        self.router_config = self.load_router_config()
        self.openrouter_client = self.init_openrouter_client()
        self.routing_tools = self.define_routing_tools()
        
        print("[LLM] LLM Component initialized with in-memory context")

    def load_router_config(self):
        """Load router configuration"""
        config_path = 'config.json'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config.get("router", {}), config.get("api_keys", {})
            except Exception as e:
                print(f"[LLM] Error loading router config: {e}")
                return {}, {}
        return {}, {}
    
    def load_config(self):
        """Load llm configuration"""
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
    
    def init_openrouter_client(self):
        """Initialize OpenRouter client"""

        api_keys = self.router_config
        openrouter_key = api_keys[1]['open_router']
        
        if not openrouter_key:
            print("[LLM] ❌ OpenRouter API key not found!")
            return None
            
        return AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key
        )

    def define_routing_tools(self):
        """Define tools for routing classification"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "handle_conversation",
                    "description": "Handle casual conversation, questions, and general chat",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "use_tool",
                    "description": "Use a specific tool or service for information/actions",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_type": {
                                "type": "string",
                                "enum": ["news", "weather", "movies", "finance"],
                                "description": "Type of tool to use"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Why this tool is needed"
                            }
                        },
                        "required": ["tool_type"]
                    }
                }
            }
        ]
    
    async def route_request(self, transcript):
        """Route request using OpenRouter"""
        if not self.openrouter_client:
            print("[LLM] ❌ OpenRouter client not available, defaulting to conversation")
            return {"type": "conversation"}
        
        try:
            router_config, _ = self.router_config
            models_string = router_config.get("models")

            # Parse comma-separated models
            models_list = [model.strip() for model in models_string.split(",")]
            primary_model = models_list[0]  # First model for 'model' parameter
            
            print(f"[LLM] 🔀 Routing request with model: {primary_model}, fallbacks: {models_list[1:]}")
            
            response = await self.openrouter_client.chat.completions.create(
                model=primary_model,
                extra_body={
                    "models": models_list
                },
                messages=[
                    {"role": "system", "content": ROUTING_PROMPT},
                    {"role": "user", "content": transcript}
                ],
                tools=self.routing_tools,
                tool_choice="auto"
            )
            
            # Parse the response
            message = response.choices[0].message
            
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                function_name = tool_call.function.name
                
                if function_name == "handle_conversation":
                    print("[LLM] 🗣️ Routed to: CONVERSATION")
                    return {"type": "conversation"}
                    
                elif function_name == "use_tool":
                    try:
                        args = json.loads(tool_call.function.arguments)
                        tool_type = args.get("tool_type")
                        reasoning = args.get("reasoning", "")
                        
                        print(f"[LLM] 🔧 Routed to: TOOL ({tool_type}) - {reasoning}")
                        return {
                            "type": "tool",
                            "tool_type": tool_type,
                            "reasoning": reasoning
                        }
                    except json.JSONDecodeError:
                        print("[LLM] ❌ Error parsing tool arguments, defaulting to conversation")
                        return {"type": "conversation"}
            
            # Default to conversation if no tool calls
            print("[LLM] 🗣️ No tool calls, defaulting to: CONVERSATION")
            return {"type": "conversation"}
            
        except Exception as e:
            print(f"[LLM] ❌ Error in routing: {e}")
            print("[LLM] 🗣️ Defaulting to: CONVERSATION")
            return {"type": "conversation"}
    
    async def process_transcript(self, transcript):
        """Process transcript directly from STT - main entry point"""
        print(f"[LLM] 📥 Received transcript directly: '{transcript}'")
        
        try:
            # Set thinking state
            await state.set("ai_thinking", "True", source="llm", priority=10)

            # Routing the transcription for tools triggering if any
            route_info = await self.route_request(transcript)

            if route_info["type"] == "conversation":
                # Handle as conversation (existing logic)
                response = await self.process_conversation(transcript)
            else:
                # Handle as tool request (new logic)
                response = await self.handle_tool_request(transcript, route_info)
        
            # Clear thinking state 
            await state.set("ai_thinking", "False", source="llm", priority=10)
        
            print("[LLM] ✅ Processing complete!")
            return response
        
        except Exception as e:
            print(f"[LLM] ❌ Error in LLM processing: {e}")
            traceback.print_exc()
            await state.set("ai_thinking", "False", source="llm", priority=10)
            raise

    async def process_conversation(self, transcript):
        """Handle conversational requests (extracted from original process_transcript)"""
        # Build context from memory systems
        context = await self.build_context(transcript)
        print(f"[LLM] Built context with {len(context['relevant_memories'])} semantic memories")

        # Generate response
        response = await self.generate_response(transcript, context)
        print(f"[LLM] Generated response: '{response[:100]}...'")

        # Update memory systems
        await self.store_conversation(transcript, response)

        # Trigger TTS processing via Redis state
        tts_success = await self.trigger_tts_processing(response)
        if tts_success:
            print("[LLM] ✅ TTS processing triggered successfully")
        else:
            print("[LLM] ❌ Failed to trigger TTS processing")

        return response
    
    async def handle_tool_request(self, transcript, route_info):
        """Handle tool requests with class-based tool execution"""
        tool_type = route_info.get("tool_type", "unknown")

        print(f"[LLM] 🔧 Handling tool request: {tool_type}")

        try:
            # Import and initialize tool manager
            tool_manager = ToolManager()

            # Execute the tool to get structured data
            print(f"[LLM] 🔧 Executing {tool_type} tool...")
            tool_result = await tool_manager.execute_tool(tool_type, transcript)

            if tool_result.get("success", False):
                # Build context with tool data for Samantha
                print(f"[LLM] 📊 Tool succeeded, building context with data...")
                tool_context = await self.build_context_with_tool_data(transcript, tool_result)

                # Generate Samantha's response incorporating tool data
                response = await self.generate_response(transcript, tool_context)
            else:
                # Tool failed - provide Samantha with failure context
                print(f"[LLM] ❌ Tool failed: {tool_result.get('error', 'Unknown error')}")

                # Build context with failure information
                failure_context = await self.build_context_with_tool_failure(transcript, tool_type, tool_result)

                response = await self.generate_response(transcript, failure_context)

        except Exception as e:
            print(f"[LLM] ❌ Error in tool execution: {e}")

            # Build context with exception failure info
            exception_context = await self.build_context_with_tool_failure(
                transcript, 
                tool_type, 
                {"error": f"Technical error: {str(e)}", "success": False}
            )

            response = await self.generate_response(transcript, exception_context)

        # Store in memory (so Samantha remembers tool interactions)
        await self.store_conversation(transcript, response)

        # Trigger TTS processing
        tts_success = await self.trigger_tts_processing(response)
        if tts_success:
            print("[LLM] ✅ TTS processing triggered successfully")
        else:
            print("[LLM] ❌ Failed to trigger TTS processing")

        return response
    
    async def build_context_with_tool_data(self, transcript, tool_result):
        """Build context including successful tool data for Samantha to process"""
        # Get regular context first
        base_context = await self.build_context(transcript)

        # Add tool-specific context
        tool_context = {
            **base_context,
            "tool_data": tool_result["data"],
            "tool_type": tool_result.get("tool_type"),
            "tool_context": f"User requested {tool_result.get('tool_type')} information. Use this data to respond naturally."
        }

        return tool_context
    
    async def build_context_with_tool_failure(self, transcript, tool_type, tool_result):
        """Build context including tool failure info for Samantha to respond gracefully"""
        # Get regular context first
        base_context = await self.build_context(transcript)

        # Add failure context
        failure_context = {
            **base_context,
            "tool_failure": {
                "requested_tool": tool_type,
                "user_intent": transcript,
                "error_reason": tool_result.get('error', 'Service temporarily unavailable'),
                "guidance": f"User wanted {tool_type} information but the service is unavailable. Acknowledge this and offer alternatives or ask how else you can help."
            }
        }

        return failure_context

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
            memories = await self.memory_component.get_semantic_memories(query, limit=5)

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
        """Generate AI response using configured LLM provider"""
        print("[LLM] 🤖 Generating response...")

        # Check for vLLM first (remote)
        vllm_config = self.config.get('vllm', {})
        if vllm_config.get('enabled') == 'true':
            return await self._generate_response_vllm(transcript, context, vllm_config)
        
        # Check for local LLM providers
        for llm_name, config in self.config.items():
            if config.get('enabled') == 'true':
                return await self._generate_response_local(transcript, context, config, llm_name)
        
        raise ValueError("No enabled LLM configuration found")
    
    async def _generate_response_vllm(self, transcript, context, config):
        """Generate AI response using vLLM via Vast.ai"""
        print("[LLM] 🚀 Using vLLM provider...")
        
        vast_ai_ip = config.get('vast_ai_ip')
        vast_ai_port = config.get('vast_ai_port')
        bearer_token = config.get('bearer')
        model = config.get('model')
        
        if not all([vast_ai_ip, vast_ai_port, bearer_token, model]):
            raise ValueError("Missing vLLM configuration: need vast_ai_ip, vast_ai_port, bearer, and model")
        
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

        print(f"[LLM] 🌐 Connecting to vLLM at {vast_ai_ip}:{vast_ai_port}")
        
        # Use AsyncOpenAI client to connect to vLLM endpoint
        base_url = f'http://{vast_ai_ip}:{vast_ai_port}/v1'
        
        async with AsyncOpenAI(base_url=base_url, api_key=bearer_token) as client:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                timeout=30.0
            )
            print("[LLM] ✅ vLLM response received successfully")
            print("[LLM] 🔒 AsyncOpenAI client automatically closed")
            return response.choices[0].message.content
    
    async def _generate_response_local(self, transcript, context, config, llm_name):
        """Generate AI response using local LLM providers"""
        print(f"[LLM] 🏠 Using local {llm_name} provider...")
        
        port = config.get('port')
        api_key = config.get('api_key', 'not-needed')
        model = config.get('model')
        
        if not all([port, model]):
            raise ValueError(f"Missing {llm_name} configuration: need port and model")
        
        # Build system prompt with context
        system_prompt = self.build_system_prompt(context)
        
        # DEBUG: Print the actual system prompt being sent to LLM
        print(f"[LLM] 🔍 LOCAL SYSTEM PROMPT DEBUG:")
        print(f"[LLM] 📝 Length: {len(system_prompt)} characters")
        if context.get("relevant_memories"):
            print(f"[LLM] 🧠 Memory section:")
            for i, mem in enumerate(context["relevant_memories"]):
                print(f"[LLM] 📝 Memory {i+1}: Type={mem.get('type')}, Content='{mem['content'][:100]}...'")
        print(f"[LLM] 📝 System prompt preview (last 500 chars):")
        print(f"[LLM] 📝 {system_prompt[-500:]}")
        
        # Build conversation messages with context
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add current session
        for item in context["current_session"]:
            messages.append(item)
        
        # Add current user input
        messages.append({"role": "user", "content": transcript})

        print(f"[LLM] 🏠 Connecting to {llm_name} at localhost:{port}")
        
        async with AsyncOpenAI(base_url=f'http://localhost:{port}/v1', api_key=api_key) as client:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                timeout=30.0
            )
            print(f"[LLM] ✅ {llm_name} response received successfully")
            print("[LLM] 🔒 AsyncOpenAI client automatically closed")
            return response.choices[0].message.content
    
    def build_system_prompt(self, context):
        """Build system prompt with context information"""
        base_prompt = CHARACTER_CARD_PROMPT
        
        # Add relevant memories to prompt with proper context
        if context.get("relevant_memories"):
            user_memories = []
            creator_memories = []
            general_memories = []
            
            # Categorize memories by type
            for mem in context["relevant_memories"]:
                memory_type = mem.get("type", "general")
                if memory_type.startswith("user_"):
                    user_memories.append(mem["content"])
                elif memory_type.startswith("creator_"):
                    creator_memories.append(mem["content"])
                else:
                    general_memories.append(mem["content"])
            
            # Add critical instructions to prevent memory/character confusion
            base_prompt += "\n\nCRITICAL MEMORY INSTRUCTIONS:"
            base_prompt += "\n- NEVER confuse memory information with your character background"
            base_prompt += "\n- NEVER claim to have met or have personal relationships with people from memories"
            base_prompt += "\n- NEVER mix creator information with your fictional backstory"
            base_prompt += "\n- Keep your character consistent but separate from memory data"
            
            # Add user memories with proper context
            if user_memories:
                memory_text = f"\n\nWhat I know about the user (the person I'm talking to): {', '.join(user_memories)}"
                memory_text += "\n\nIMPORTANT: These are facts about the USER, not about my creator or anyone else."
                base_prompt += memory_text
            
            # Add creator memories with proper context  
            if creator_memories:
                memory_text = f"\n\nAbout my creator (who built me): {', '.join(creator_memories)}"
                memory_text += "\n\nIMPORTANT: This is information about my creator/developer. I should NOT claim to have met them or have personal relationships with them. I am an AI assistant created by them."
                base_prompt += memory_text
                
            # Add general memories
            if general_memories:
                memory_text = f"\n\nGeneral context: {', '.join(general_memories)}"
                base_prompt += memory_text
        
        # Add tool data to prompt (THIS WAS MISSING!)
        if context.get("tool_data"):
            tool_type = context.get("tool_type", "unknown")
            tool_data = context["tool_data"]
            
            if tool_type == "weather":
                base_prompt += f"\n\nCURRENT WEATHER DATA: {tool_data['summary']} (Temperature: {tool_data['temperature']}°C, Humidity: {tool_data['humidity']}%, Wind: {tool_data['wind_speed']} km/h {tool_data['wind_direction']}, Conditions: {tool_data['description']}). Use this weather information to respond naturally to the user's request."
            elif tool_type == "news":
                base_prompt += f"\n\nLATEST NEWS: {tool_data['summary']} Use this news information to respond naturally to the user's request."
            elif tool_type == "movies":
                base_prompt += f"\n\nMOVIE RECOMMENDATIONS: {tool_data['summary']} Use this movie information to respond naturally to the user's request."
            else:
                base_prompt += f"\n\nTOOL DATA ({tool_type}): {tool_data}. Use this information to respond to the user's request."
        
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
        """Trigger TTS processing via Redis state management"""
        print(f"[LLM] 🎤 Triggering TTS for response: '{response[:50]}...'")

        try:
            # Set the text to be spoken in Redis state
            await state.set("tts_text", response, source="llm", priority=8)
            print(f"[LLM] 📝 Set tts_text state with response")

            # Signal TTS component that text is ready for processing
            await state.set("tts_ready", "True", source="llm", priority=8)
            print(f"[LLM] 🚀 Set tts_ready=True to trigger TTS processing")

            return True

        except Exception as e:
            print(f"[LLM] ❌ Error triggering TTS: {e}")
            traceback.print_exc()
            return False

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
