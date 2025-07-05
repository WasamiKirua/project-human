import json
import apsw
import sqlite_vec
import os
import re
import asyncio
from redis_state import RedisState
from datetime import datetime
from groq import AsyncGroq
from typing import List, Dict
import weaviate
from weaviate.classes.config import Configure, DataType, Property
from utils.prompts import MEMORY_ANALYSIS_PROMPT
from redis_client import create_redis_client

# Redis config & state
r = create_redis_client()
state = RedisState(r)

class MemoryComponent:
    def __init__(self):
        # Load configuration
        self.config = self.load_config()
        print(f"[Memory] Loaded config: {self.config}")
        
        # Validate and extract config values with defaults
        memory_config, api_keys, lorebook = self.config  # Unpack tuple properly
        
        self.db_file = memory_config.get('db_store', 'default_memory.db')
        self.weaviate_collection_name = memory_config.get('collection_name', 'ConversationMemory')
        self.groq_key = api_keys.get('groq_api_key', None)
        self.lorebook_elements = lorebook
        
        # Verify API key is loaded (don't print the full key for security)
        if self.groq_key:
            print(f"[Memory] ✅ Groq API key loaded (length: {len(self.groq_key)})")
        else:
            print(f"[Memory] ❌ Groq API key not found in config!")
        
        print(f"[Memory] Database file: {self.db_file}")
        print(f"[Memory] Collection name: {self.weaviate_collection_name}")

        # Initialize Weaviate connection (set to None initially, will be set by init_weaviate)
        self.init_weaviate()
        self.create_db()
        self.inject_lorebook()
        self.cleanup_contaminated_memories()

    def load_config(self):
        config_path = 'config.json'
        memory_config = {} # Default
        api_keys = {} # Default
        lorebook = {} # Default
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    memory_config = config.get("memory", {})
                    api_keys = config.get("api_keys", {})
                    lorebook = config.get("lorebook", {})
            except Exception as e:
                print(f"[Memory] ❌ Error loading config: {e}")
                # Use defaults if config loading fails
        else:
            # Try looking in parent directory (for when running from src/)
            parent_config_path = '../config.json'
            if os.path.exists(parent_config_path):
                try:
                    with open(parent_config_path, 'r') as f:
                        config = json.load(f)
                        memory_config = config.get("memory", {})
                        api_keys = config.get("api_keys", {})
                        lorebook = config.get("lorebook", {})
                except Exception as e:
                    print(f"[Memory] ❌ Error loading config from parent dir: {e}")
            else:
                print(f"[Memory] ⚠️ Config file not found in current or parent directory")
            
        return memory_config, api_keys, lorebook

    def init_weaviate(self):
        """Initialize Weaviate connection using your existing pattern"""
        try:
            print("[Memory] 🔗 Connecting to Weaviate...")
            self.weaviate_client = weaviate.connect_to_local(
                host="127.0.0.1",
                port=8080,
                grpc_port=50051,
            )
            
            # Check if collection exists
            if self.weaviate_client.collections.exists(self.weaviate_collection_name):
                print(f"[Memory] ✅ Collection exists")
                self.weaviate_collection = self.weaviate_client.collections.get(self.weaviate_collection_name)
            else:
                print(f"[Memory] 🔨 Creating collection '{self.weaviate_collection_name}'...")
                self.weaviate_collection = self.weaviate_client.collections.create(
                    name=self.weaviate_collection_name,
                    vectorizer_config=Configure.Vectorizer.text2vec_contextionary(
                        vectorize_collection_name=False
                    ),
                    properties=[
                        Property(
                            name="content", 
                            data_type=DataType.TEXT,
                            description="Main memory content for semantic search"
                        ),
                        Property(
                            name="memoryType", 
                            data_type=DataType.TEXT,
                            description="Type of memory: fact, preference, experience, general",
                            skip_vectorization=True
                        ),
                        Property(
                            name="timestamp", 
                            data_type=DataType.TEXT,
                            description="When the memory was created",
                            skip_vectorization=True
                        ),
                        Property(
                            name="importanceScore", 
                            data_type=DataType.NUMBER,
                            description="Importance score from 0.0 to 1.0",
                            skip_vectorization=True
                        ),
                        Property(
                            name="originalUserInput", 
                            data_type=DataType.TEXT,
                            description="Original user input that created this memory",
                            skip_vectorization=True
                        ),
                        Property(
                            name="originalAiResponse", 
                            data_type=DataType.TEXT,
                            description="AI response to the original input",
                            skip_vectorization=True
                        ),
                        Property(
                            name="position", 
                            data_type=DataType.INT,
                            description="Sequential position/ID of the memory",
                            skip_vectorization=True
                        )
                    ]
                )
                print(f"[Memory] ✅ Created collection")
            
            # Verify the collection is accessible
            print(f"[Memory] 🔍 Collection object type: {type(self.weaviate_collection)}")
            if self.weaviate_collection is not None:
                try:
                    # Test basic access to the collection
                    stats = self.weaviate_collection.aggregate.over_all(total_count=True)
                    print(f"[Memory] ✅ Successfully connected to collection")
                    print(f"[Memory] ✅ Collection verified - contains {stats.total_count} items")
                except Exception as verify_error:
                    print(f"[Memory] ⚠️ Collection exists but verification failed: {verify_error}")
                    # Try to get the collection again
                    try:
                        self.weaviate_collection = self.weaviate_client.collections.get(self.weaviate_collection_name)
                        print(f"[Memory] 🔄 Re-obtained collection reference")
                    except Exception as reget_error:
                        print(f"[Memory] ❌ Failed to re-obtain collection: {reget_error}")
                        self.weaviate_collection = None
            else:
                print(f"[Memory] ❌ Collection object is None after initialization")
                
        except Exception as e:
            print(f"[Memory] ❌ Failed to initialize Weaviate: {e}")
            # Ensure client is properly closed if initialization fails
            if hasattr(self, 'weaviate_client') and self.weaviate_client:
                try:
                    self.weaviate_client.close()
                except:
                    pass
            self.weaviate_client = None
            self.weaviate_collection = None

    def create_db(self):
        # Check if database file exists
        db_exists = os.path.exists(self.db_file)

        try:
            print(f"[GUI] --> [SQLite] 🔄 {'Opening' if db_exists else 'Creating'} SQLite database '{self.db_file}'")
            db = apsw.Connection(self.db_file)
            db.enable_load_extension(True)
            sqlite_vec.load(db)
            db.enable_load_extension(False)

            if not db_exists:
                # Create a simple messages table with just id and message
                db.execute(
                    """
                    CREATE TABLE messages(
                      id INTEGER PRIMARY KEY,
                      message TEXT
                    );
                    """
                )

                print(f"[GUI] --> [SQLite] ✅ Created SQLite database tables for storage")
            else:
                # Verify tables exist
                cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
                if not cursor.fetchone():
                    db.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, message TEXT);")
                    print("[GUI] --> [SQLite] ✅ Created missing messages table")

            return db
        except Exception as create_error:
            print(f"[GUI] --> [SQLite] ❌ Error with SQLite database: {str(create_error)}")
            return None

    def inject_lorebook(self):
        # Load Static Lorebook items abd store them to weaviate
        lock_file = 'logs/lorebook.lock'
        if os.path.exists(lock_file):
            print(f"[Memory Lorebook] ✅ Lorebook has already being imported into Weaviate!")
        else:
            print("[Memory Lorebook] 💭 Proceeding with Lorebook Injection ...")
            try:        
                for k, v in self.lorebook_elements.items():
                    if not self.is_weaviate_available():
                        print("[Memory Lorebook] ❌ Weaviate collection not available for semantic search")
                        return []
                    try:
                        results = self.weaviate_collection.aggregate.over_all(total_count=True)
                        position = results.total_count
                    except Exception as e:
                        print(f"[Memory Lorebook] Warning: Could not get count, using position 0: {e}")
                        position = 0

                    memory_type = self.classify_memory_type(v)

                    # Create memory object following your schema
                    memory_object = {
                        "content": v,
                        "memoryType": memory_type,
                        "timestamp": datetime.now().isoformat(),
                        "importanceScore": 1.0,
                        "originalUserInput": "",
                        "originalAiResponse": "",
                        "position": position
                    }
                    # Insert using your existing pattern
                    self.weaviate_collection.data.insert(properties=memory_object)

                    print(f"[Memory Lorebook] ✅ Stored in Weaviate: '{v}' (type: {memory_type}, position: {position})")
                with open('logs/lorebook.lock', 'w') as lock_file:
                    lock_file.write('')
                    print(f"[Memory Lorebook] ✅ Lorebook imported and Lock file created!")
            except Exception as e:
                print(f"[Memory Lorebook] ❌ Failed to store in Weaviate: {e}")
                return False

    def store_conversations(self, user_input, ai_response):
        """Store conversation in SQLite and evaluate for Weaviate storage"""
        # Store in SQLite (data warehouse) - synchronous
        self._store_in_sqlite(user_input, ai_response)
        
        # Run in background to avoid blocking the conversation flow
        try:
            # Try to get the current event loop, or create a new task if we're in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, create a task
                loop.create_task(self.evaluate_and_store_semantic_memory(user_input, ai_response))
                print("[Memory] 🚀 Started async semantic memory evaluation")
            except RuntimeError:
                # No running loop, we're in a sync context - run the evaluation synchronously
                print("[Memory] 🔄 Running semantic memory evaluation synchronously")
                asyncio.run(self.evaluate_and_store_semantic_memory(user_input, ai_response))
        except Exception as e:
            print(f"[Memory] ⚠️ Could not start semantic memory evaluation: {e}")

    async def evaluate_and_store_semantic_memory(self, user_input, ai_response):
        """Asynchronously evaluate and store important memories"""
        try:
            print("[Memory] 🤔 Evaluating conversation for semantic storage...")
            
            # Use Groq to evaluate if this conversation contains important memory
            formatted_memory = await self.eval_short_mem_groq(user_input)
            
            # Store in Weaviate if important
            if formatted_memory:
                success = await self.store_memory_if_important(user_input, ai_response, formatted_memory)
                if success:
                    print(f"[Memory] ✅ Stored semantic memory: '{formatted_memory[:50]}...'")
                else:
                    print("[Memory] ❌ Failed to store semantic memory")
            else:
                print("[Memory] 💭 Memory not flagged as important - not storing in Weaviate")
                
        except Exception as e:
            print(f"[Memory] ❌ Error in semantic memory evaluation: {e}")
            import traceback
            traceback.print_exc()

    def _store_in_sqlite(self, user_input, ai_response):
        """Internal method to store in SQLite"""
        # Connect to existing database
        db = apsw.Connection(self.db_file)
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)

        # Get the next ID
        cursor = db.execute("SELECT MAX(id) FROM messages")
        max_id_row = cursor.fetchone()
        max_id = max_id_row[0] if max_id_row[0] is not None else 0
        next_id = max_id + 1

        entries = []
        entries.append({
            "User": user_input,
            "Assistant": ai_response
        })

        try:
            # Convert the entries list to a JSON string
            entries_json = json.dumps(entries, ensure_ascii=False)

            db.execute(
                "INSERT INTO messages(id, message) VALUES(?, ?)",
                [next_id, entries_json] # Insert the JSON string
            )
            print(f"[Memory] 📝 Stored conversation in SQLite (ID: {next_id})")
        except Exception as insert_error:
            print(f"[Memory] ❌ Error inserting message: {str(insert_error)}")

    async def eval_short_mem_groq(self, query):
        print(f"[Memory] 🚀 Starting Groq evaluation for query: '{query}'")
        
        # ENHANCED BLOCKING: Block obvious patterns that shouldn't be stored as memories
        query_lower = query.lower().strip()
        
        # Block questions
        question_indicators = ["do you remember", "can you remember", "what is", "what's", "how are", "tell me about", "?"]
        if any(indicator in query_lower for indicator in question_indicators):
            print(f"[Memory] 🚫 BLOCKING question from memory storage: '{query}'")
            return None
            
        # Block corrections and clarifications
        correction_indicators = ["i mean", "i meant", "sorry, i meant", "actually i meant", "correction:", "let me correct"]
        if any(indicator in query_lower for indicator in correction_indicators):
            print(f"[Memory] 🚫 BLOCKING correction from memory storage: '{query}'")
            return None
            
        # Block music/entertainment requests (unless personal preferences)
        entertainment_indicators = ["play some", "search for", "find music", "play music", "do you know the anime", "do you know the manga", "tell me about the anime"]
        if any(indicator in query_lower for indicator in entertainment_indicators):
            print(f"[Memory] 🚫 BLOCKING entertainment request from memory storage: '{query}'")
            return None
            
        # Block very short inputs (likely incomplete)
        if len(query.strip()) < 5:
            print(f"[Memory] 🚫 BLOCKING too short input from memory storage: '{query}'")
            return None
        
        if not self.groq_key:
            print("[Memory] ❌ No Groq API key available!")
            return "Error: No Groq API key configured"
        
        # Use async context manager for automatic cleanup
        async with AsyncGroq(api_key=self.groq_key) as client:
            try:
                prompt = MEMORY_ANALYSIS_PROMPT.replace('{replacement}', f'{query}')
                print(f"[Memory] 📤 Sending request to Groq API...")
                
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[
                        {"role": "user", "content": f"{prompt}"}
                    ]
                )

                result = response.choices[0].message.content
                print(f"[Memory] 🔍 GROQ ANALYSIS DEBUG:")
                print(f"[Memory] 📤 Input: '{query}'")
                print(f"[Memory] 📥 Groq response: '{result}'")
                
                # Enhanced JSON parsing to handle markdown and double braces
                def clean_groq_response(response_text):
                    """Clean Groq response of markdown formatting and double braces"""
                    # Remove markdown code fences if present
                    cleaned = re.sub(r'^```json\s*', '', response_text.strip())
                    cleaned = re.sub(r'\s*```$', '', cleaned)
                    
                    # Fix double curly braces
                    cleaned = re.sub(r'^\{\{', '{', cleaned)
                    cleaned = re.sub(r'\}\}$', '}', cleaned)
                    
                    # Remove extra whitespace and newlines
                    cleaned = cleaned.strip()
                    return cleaned

                try:
                    # Clean the response first
                    cleaned_result = clean_groq_response(result)
                    
                    # Try to parse as complete JSON
                    import json
                    parsed_result = json.loads(cleaned_result)
                    
                    if parsed_result.get("is_important") == True:
                        formatted_memory = parsed_result.get("formatted_memory")
                        if formatted_memory:
                            print(f"[Memory] ✅ Extracted formatted memory: '{formatted_memory}'")
                            return formatted_memory
                        else:
                            print(f"[Memory] ⚠️ Important but no formatted memory found")
                            return None
                    else:
                        print(f"[Memory] ✅ Correctly identified as not important")
                        return None
                        
                except json.JSONDecodeError as e:
                    # Fallback to regex extraction if JSON parsing fails
                    print(f"[Memory] ⚠️ JSON parsing failed after cleaning: {e}")
                    print(f"[Memory] 📝 Original response: {repr(result)}")
                    print(f"[Memory] 📝 Cleaned response: {repr(cleaned_result)}")
                    
                    if '"is_important": true' in result:
                        memory_match = re.search(r'"formatted_memory":\s*"([^"]+)"', result)
                        if memory_match:
                            formatted_memory = memory_match.group(1)
                            print(f"[Memory] ✅ Regex extracted memory: '{formatted_memory}'")
                            return formatted_memory
                        else:
                            print(f"[Memory] ❌ Could not extract memory from malformed response")
                            return None
                    else:
                        print(f"[Memory] ✅ Correctly identified as not important (regex)")
                        return None
                
                print(f"[Memory] 🔒 Groq client automatically closed")
                
            except Exception as e:
                print(f"[Memory] ❌ Error in Groq API call: {e}")
                import traceback
                traceback.print_exc()
                return None  # Return None instead of error string to prevent storing errors as memories
            # No finally needed - context manager handles cleanup automatically

    async def store_memory_if_important(self, user_input, ai_response, formatted_memory):
        """Store memory in Weaviate if evaluation returned content"""
        if formatted_memory is None:
            print("[Memory] 💭 Memory not flagged as important")
            return False
            
        # Store in Weaviate directly since we already have the formatted content
        return await self.store_in_weaviate(user_input, ai_response, formatted_memory, "important")

    async def store_in_weaviate(self, user_input: str, ai_response: str, memory_content: str, eval_result: str) -> bool:
        """Store important memory in Weaviate using your existing patterns"""
        print(f"[Memory] 🔍 Debug: weaviate_client={self.weaviate_client is not None}, weaviate_collection={self.weaviate_collection is not None}")
        
        # Check if collection object exists (not None)
        if self.weaviate_collection is None:
            print(f"[Memory] ❌ Weaviate collection is None")
            return False
        
        # Try to test the collection with a simple operation (this is the real test)
        try:
            # Test if collection is actually working
            test_count = self.weaviate_collection.aggregate.over_all(total_count=True)
            print(f"[Memory] ✅ Collection test successful - {test_count.total_count} items")
        except Exception as test_error:
            print(f"[Memory] ❌ Collection test failed: {test_error}")
            print("[Memory] 🔄 Attempting to reinitialize Weaviate connection...")
            
            # Close old connection properly before reinitializing
            try:
                if hasattr(self, 'weaviate_client') and self.weaviate_client:
                    self.weaviate_client.close()
                    print("[Memory] 🔒 Closed old Weaviate connection")
            except:
                pass
            
            # Reinitialize
            try:
                self.init_weaviate()
                if self.weaviate_collection:
                    print("[Memory] ✅ Weaviate reinitialized successfully")
                    # Test again
                    test_count = self.weaviate_collection.aggregate.over_all(total_count=True)
                    print(f"[Memory] ✅ Reinitialized collection test successful - {test_count.total_count} items")
                else:
                    print("[Memory] ❌ Weaviate reinitialization failed")
                    return False
            except Exception as e:
                print(f"[Memory] ❌ Failed to reinitialize Weaviate: {e}")
                return False
            
        try:
            # Get current count for position (following your pattern)
            try:
                results = self.weaviate_collection.aggregate.over_all(total_count=True)
                position = results.total_count
            except Exception as e:
                print(f"[Memory] Warning: Could not get count, using position 0: {e}")
                position = 0

            # Determine memory type
            memory_type = self.classify_memory_type(memory_content)
            
            # Create memory object following your schema
            memory_object = {
                "content": memory_content,
                "memoryType": memory_type,  # Fixed: camelCase
                "timestamp": datetime.now().isoformat(),
                "importanceScore": 1.0,  # Fixed: camelCase
                "originalUserInput": user_input,  # Fixed: camelCase
                "originalAiResponse": ai_response,  # Fixed: camelCase
                "position": position
            }
            
            # Insert using your existing pattern
            self.weaviate_collection.data.insert(properties=memory_object)
            
            print(f"[Memory] ✅ Stored in Weaviate: '{memory_content}' (type: {memory_type}, position: {position})")
            return True
            
        except Exception as e:
            print(f"[Memory] ❌ Failed to store in Weaviate: {e}")
            return False

    def classify_memory_type(self, content: str) -> str:
        """Classify memory type based on content - generic classification without personal identifiers"""
        content_lower = content.lower()
        
        # Check if this is creator/developer information (generic patterns)
        creator_indicators = ["creator", "developer", "made me", "built me", "my maker"]
        if any(indicator in content_lower for indicator in creator_indicators):
            if any(word in content_lower for word in ["likes", "loves", "prefers", "favorite", "enjoys"]):
                return "creator_preference"
            else:
                return "creator_info"
        
        # Check for general creator-related content by looking for possessive references to non-user
        # This catches phrases like "John likes..." where John isn't the current user
        if any(pattern in content_lower for pattern in ["'s name is", " is a ", " years old", " old man", " old woman", " man who", " woman who"]):
            return "creator_fact"
            
        # User memory classification (about the person talking to the AI)
        elif any(word in content_lower for word in ["likes", "loved", "loves", "prefers", "preferred", "favorite", "favourite", "hates", "enjoys", "enjoyed"]):
            return "user_preference"
        elif any(word in content_lower for word in ["lives", "from", "age", "name", "job", "works", "years old"]):
            return "user_fact"
        elif any(word in content_lower for word in ["did", "went", "happened", "experienced", "visited"]):
            return "user_experience"
        else:
            return "general"

    def cleanup_contaminated_memories(self):
        """Clean up obviously contaminated or invalid memories from Weaviate"""
        if not self.is_weaviate_available():
            print("[Memory] ❌ Weaviate not available for cleanup")
            return
            
        try:
            print("[Memory] 🧹 Starting memory cleanup...")
            
            # Get all memories to examine
            all_memories = self.weaviate_collection.query.fetch_objects(
                return_properties=["content", "memoryType", "originalUserInput", "originalAiResponse"],
                limit=1000
            )
            
            deleted_count = 0
            contaminated_patterns = [
                # Content contamination patterns
                lambda content: len(content.strip()) < 3,  # Too short
                lambda content: content.endswith('\"') or content.endswith('\\"'),  # Truncated at quote
                lambda content: content.startswith('Means'),  # The specific bug we saw
                lambda content: content in ["None", "null", "undefined", ""],  # Invalid content
                
                # User input patterns that shouldn't be memories
                lambda user_input: user_input.lower().startswith("i mean"),
                lambda user_input: "do you know the anime" in user_input.lower(),
                lambda user_input: "do you know the manga" in user_input.lower(),
                lambda user_input: "search for" in user_input.lower(),
                lambda user_input: "play some" in user_input.lower(),
            ]
            
            for memory_obj in all_memories.objects:
                should_delete = False
                delete_reason = ""
                
                content = memory_obj.properties.get("content", "")
                user_input = memory_obj.properties.get("originalUserInput", "")
                
                # Check content contamination
                for i, pattern in enumerate(contaminated_patterns[:4]):  # Content patterns
                    if pattern(content):
                        should_delete = True
                        delete_reason = f"contaminated content (pattern {i+1})"
                        break
                
                # Check user input patterns
                if not should_delete and user_input:
                    for i, pattern in enumerate(contaminated_patterns[4:], 5):  # User input patterns
                        if pattern(user_input):
                            should_delete = True
                            delete_reason = f"invalid user input (pattern {i})"
                            break
                
                if should_delete:
                    try:
                        self.weaviate_collection.data.delete_by_id(memory_obj.uuid)
                        deleted_count += 1
                        print(f"[Memory] 🗑️ Deleted contaminated memory: '{content[:30]}...' ({delete_reason})")
                    except Exception as e:
                        print(f"[Memory] ❌ Failed to delete memory {memory_obj.uuid}: {e}")
            
            print(f"[Memory] ✅ Cleanup complete! Deleted {deleted_count} contaminated memories")
            
        except Exception as e:
            print(f"[Memory] ❌ Error during cleanup: {e}")
            import traceback
            traceback.print_exc()

    def is_weaviate_available(self) -> bool:
        """Check if Weaviate collection is available and log status"""
        available = self.weaviate_collection is not None
        print(f"[Memory] 🔍 Weaviate availability check: {available}")
        if not available:
            print(f"[Memory] 🔍 Client: {self.weaviate_client is not None}")
            print(f"[Memory] 🔍 Collection: {self.weaviate_collection}")
        return available

    async def get_semantic_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """Retrieve relevant memories from Weaviate with smart context filtering"""
        if not self.is_weaviate_available():
            print("[Memory] ❌ Weaviate collection not available for semantic search")
            return []
            
        try:
            print(f"[Memory] 🔍 Searching semantic memories for: '{query[:50]}...'")
            
            # Improve search query for better semantic matching
            search_query = query
            
            # Enhanced query preprocessing for specific topics
            query_lower = query.lower()
            if "manga artist" in query_lower:
                search_query = "favorite manga artists preferences"
                print(f"[Memory] 🎯 Enhanced search query: '{search_query}'")
            elif "manga" in query_lower and ("favorite" in query_lower or "like" in query_lower):
                search_query = "favorite manga preferences"
                print(f"[Memory] 🎯 Enhanced search query: '{search_query}'")
            
            # Import Filter class
            from weaviate.classes.query import Filter
            
            # Determine query context to filter appropriate memories
            query_lower = query.lower()
            
            # If asking about creator/developer specifically (generic patterns)
            creator_keywords = ["creator", "developer", "made you", "built you", "your maker", "tell me about your creator", "about your creator"]
            if any(keyword in query_lower for keyword in creator_keywords):
                print("[Memory] 🎯 Filtering for creator information")
                response = self.weaviate_collection.query.near_text(
                    query=search_query,
                    limit=limit,
                    filters=Filter.by_property("memoryType").like("creator*"),
                    return_properties=["content", "memoryType", "timestamp", "importanceScore", "position"]
                )
                           
            # If asking about user specifically - IMPROVED DETECTION
            elif any(phrase in query_lower for phrase in [
                "do you remember", "what do i", "my preference", "about me", 
                "what type of food do i", "what do i like", "my favorite",
                "remember what i", "what i told you", "i like", "i love"
            ]):
                print("[Memory] 🎯 Filtering for user information")
                response = self.weaviate_collection.query.near_text(
                    query=search_query,
                    limit=limit,
                    filters=Filter.by_property("memoryType").like("user*"),
                    return_properties=["content", "memoryType", "timestamp", "importanceScore", "position"]
                )
            else:
                # No filtering - search all memories
                response = self.weaviate_collection.query.near_text(
                    query=search_query,
                    limit=limit,
                    return_properties=["content", "memoryType", "timestamp", "importanceScore", "position"]
                )
            
            if not response.objects:
                print("[Memory] 💭 No semantic memories found")
                return []
                
            memories = []
            for obj in response.objects:
                memory = {
                    "content": obj.properties.get("content", ""),
                    "memory_type": obj.properties.get("memoryType", "unknown"),
                    "timestamp": obj.properties.get("timestamp", ""),
                    "importance_score": obj.properties.get("importanceScore", 0),
                    "position": obj.properties.get("position", 0)
                }
                memories.append(memory)
                
            print(f"[Memory] ✅ Found {len(memories)} relevant semantic memories")
            for memory in memories:
                print(f"[Memory] 📝 Memory type: {memory['memory_type']}, Content: {memory['content'][:50]}...")
            return memories
            
        except Exception as e:
            print(f"[Memory] ❌ Error in semantic search: {e}")
            print(f"[Memory] 🔄 Falling back to unfiltered search...")
            
            # Fallback: Try simple search without filtering
            try:
                response = self.weaviate_collection.query.near_text(
                    query=query,
                    limit=limit,
                    return_properties=["content", "memoryType", "timestamp", "importanceScore", "position"]
                )
                
                memories = []
                for obj in response.objects:
                    memory = {
                        "content": obj.properties.get("content", ""),
                        "memory_type": obj.properties.get("memoryType", "unknown"),
                        "timestamp": obj.properties.get("timestamp", ""),
                        "importance_score": obj.properties.get("importanceScore", 0),
                        "position": obj.properties.get("position", 0)
                    }
                    memories.append(memory)
                    
                print(f"[Memory] ✅ Fallback search found {len(memories)} memories")
                for memory in memories:
                    print(f"[Memory] 📝 Fallback - type: {memory['memory_type']}, Content: {memory['content'][:50]}...")
                return memories
                
            except Exception as fallback_error:
                print(f"[Memory] ❌ Fallback search also failed: {fallback_error}")
                return []

    def close_weaviate(self):
        """Close Weaviate connection"""
        if hasattr(self, 'weaviate_client') and self.weaviate_client:
            try:
                self.weaviate_client.close()
                print("[Memory] 🔒 Closed Weaviate connection")
            except Exception as e:
                print(f"[Memory] ❌ Error closing Weaviate: {e}")
            finally:
                self.weaviate_client = None
                self.weaviate_collection = None

    def __del__(self):
        """Destructor to ensure connections are closed"""
        try:
            self.close_weaviate()
        except AttributeError:
            # Handle case where object wasn't fully initialized
            pass
