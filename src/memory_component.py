import redis
import json
import apsw
import sqlite_vec
import os
import re
import asyncio
from redis_state import RedisState
from datetime import datetime
from groq import AsyncGroq
from typing import List, Dict, Optional, Tuple
import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter
from utils.prompts import MEMORY_ANALYSIS_PROMPT

# Initialize Redis and state manager
r = redis.Redis(decode_responses=True, host='localhost', port=6379, password='rhost21')
state = RedisState(r)

class MemoryComponent:
    def __init__(self):
        # Load configuration
        self.config = self.load_config()
        print(f"[Memory] Loaded config: {self.config}")
        
        # Validate and extract config values with defaults
        memory_config, api_keys = self.config  # Unpack tuple properly
        
        self.db_file = memory_config.get('db_store', 'default_memory.db')
        self.weaviate_collection_name = memory_config.get('collection_name', 'ConversationMemory')
        self.groq_key = api_keys.get('groq_api_key', None)
        
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

    def load_config(self):
        config_path = 'config.json'
        memory_config = {}  # Initialize with default
        api_keys = {}       # Initialize with default
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    memory_config = config.get("memory", {})
                    api_keys = config.get("api_keys", {})
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
                except Exception as e:
                    print(f"[Memory] ❌ Error loading config from parent dir: {e}")
            else:
                print(f"[Memory] ⚠️ Config file not found in current or parent directory")
            
        return memory_config, api_keys

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
        
    def store_conversations(self, user_input, ai_response):
        """Store conversation in SQLite and evaluate for Weaviate storage"""
        # Store in SQLite (data warehouse) - synchronous
        self._store_in_sqlite(user_input, ai_response)
        
        # Evaluate and potentially store in Weaviate (semantic memory) - asynchronous
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
            entries_json = json.dumps(entries)

            db.execute(
                "INSERT INTO messages(id, message) VALUES(?, ?)",
                [next_id, entries_json] # Insert the JSON string
            )
            print(f"[Memory] 📝 Stored conversation in SQLite (ID: {next_id})")
        except Exception as insert_error:
            print(f"[Memory] ❌ Error inserting message: {str(insert_error)}")

    async def eval_short_mem_groq(self, query):
        print(f"[Memory] 🚀 Starting Groq evaluation for query: '{query}'")
        
        if not self.groq_key:
            print("[Memory] ❌ No Groq API key available!")
            return "Error: No Groq API key configured"
        
        client = AsyncGroq(api_key=self.groq_key)
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
            # Direct extraction of formatted_memory when is_important is true
            if '"is_important": true' in result:
                memory_match = re.search(r'"formatted_memory":\s*"([^"]+)"', result)
                if memory_match:
                    formatted_memory = memory_match.group(1)
                    print(f"[Memory] Extracted memory: {formatted_memory}")
                else:
                    formatted_memory = None
            else:
                formatted_memory = None
            
            return formatted_memory
            
        except Exception as e:
            print(f"[Memory] ❌ Error in Groq API call: {e}")
            import traceback
            traceback.print_exc()
            return f"Error: {str(e)}"
        finally:
            # Properly close the client to avoid resource warnings
            try:
                await client.close()  # Use close() instead of aclose()
                print(f"[Memory] 🔒 Closed Groq client")
            except Exception as close_error:
                print(f"[Memory] ⚠️ Error closing Groq client: {close_error}")

    async def store_memory_if_important(self, user_input, ai_response, formatted_memory):
        """Store memory in Weaviate if evaluation returned content"""
        if formatted_memory is None:
            print("[Memory] 💭 Memory not flagged as important")
            return False
            
        # Store in Weaviate directly since we already have the formatted content
        return await self.store_in_weaviate(user_input, ai_response, formatted_memory, "important")

    async def store_in_weaviate(self, user_input: str, ai_response: str, memory_content: str, eval_result: str) -> bool:
        """Store important memory in Weaviate using your existing patterns"""
        if not self.weaviate_collection:
            print("[Memory] ❌ Weaviate collection not available for storage")
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
        """Classify memory type based on content"""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ["likes", "loves", "prefers", "favorite", "hates", "enjoys"]):
            return "preference"
        elif any(word in content_lower for word in ["lives", "from", "age", "name", "job", "works", "years old"]):
            return "fact"
        elif any(word in content_lower for word in ["did", "went", "happened", "experienced", "visited"]):
            return "experience"
        else:
            return "general"

    def is_weaviate_available(self) -> bool:
        """Check if Weaviate collection is available and log status"""
        available = self.weaviate_collection is not None
        print(f"[Memory] 🔍 Weaviate availability check: {available}")
        if not available:
            print(f"[Memory] 🔍 Client: {self.weaviate_client is not None}")
            print(f"[Memory] 🔍 Collection: {self.weaviate_collection}")
        return available

    async def get_semantic_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """Retrieve relevant memories from Weaviate using your existing search pattern"""
        if not self.is_weaviate_available():
            print("[Memory] ❌ Weaviate collection not available for semantic search")
            return []
            
        try:
            print(f"[Memory] 🔍 Searching semantic memories for: '{query[:50]}...'")
            
            # Use your existing search pattern - sync call in async function
            response = self.weaviate_collection.query.near_text(
                query=query,
                limit=limit,
                return_properties=["content", "memoryType", "timestamp", "importanceScore", "position"]  # Fixed: camelCase
            )
            
            if not response.objects:
                print("[Memory] 💭 No semantic memories found")
                return []
                
            memories = []
            for obj in response.objects:
                memory = {
                    "content": obj.properties.get("content", ""),
                    "memory_type": obj.properties.get("memoryType", "unknown"),  # Fixed: map from camelCase
                    "timestamp": obj.properties.get("timestamp", ""),
                    "importance_score": obj.properties.get("importanceScore", 0),  # Fixed: map from camelCase
                    "position": obj.properties.get("position", 0)
                }
                memories.append(memory)
                
            print(f"[Memory] ✅ Found {len(memories)} relevant semantic memories")
            return memories
            
        except Exception as e:
            print(f"[Memory] ❌ Error in semantic search: {e}")
            return []

    async def get_user_facts(self, query: Optional[str] = None) -> List[Dict]:
        """Get user facts specifically, optionally filtered by query - OPTIMIZED for Weaviate v4.14.4+"""
        if not self.weaviate_collection:
            return []
            
        try:
            if query:
                # Use semantic search with filtering - v4.14.4+ correct syntax
                response = self.weaviate_collection.query.near_text(
                    query=query,
                    limit=10,
                    return_properties=["content", "timestamp", "position"],
                    filters=Filter.by_property("memoryType").equal("fact")
                )
            else:
                # Get all facts using native Weaviate filtering - v4.14.4+ correct syntax
                response = self.weaviate_collection.query.fetch_objects(
                    limit=20,
                    return_properties=["content", "timestamp", "position"],
                    filters=Filter.by_property("memoryType").equal("fact")
                )
                
            facts = []
            if response.objects:
                for obj in response.objects:
                    fact = {
                        "content": obj.properties.get("content", ""),
                        "timestamp": obj.properties.get("timestamp", ""),
                        "position": obj.properties.get("position", 0)
                    }
                    facts.append(fact)
                    
            print(f"[Memory] 📋 Retrieved {len(facts)} user facts (v4.14.4+ optimized)")
            return facts
            
        except Exception as e:
            print(f"[Memory] ❌ Error retrieving user facts: {e}")
            # Fallback: get all semantic memories and filter in Python
            try:
                all_memories = await self.get_semantic_memories(query or "user facts", limit=20)
                facts = [mem for mem in all_memories if mem.get("memory_type") == "fact"]
                print(f"[Memory] 📋 Fallback: Retrieved {len(facts)} user facts")
                return facts
            except:
                return []

    def get_weaviate_stats(self) -> Dict:
        """Get statistics about stored memories - OPTIMIZED for Weaviate v4.14.4+"""
        if not self.weaviate_collection:
            return {"error": "Weaviate not available"}
            
        try:
            # Get total count using v4.14.4+ optimized approach
            total_result = self.weaviate_collection.aggregate.over_all(total_count=True)
            total_count = total_result.total_count
            
            # Get count by memory type using native Weaviate aggregation - v4.14.4+ correct syntax
            type_counts = {}
            for memory_type in ["fact", "preference", "experience", "general"]:
                try:
                    type_result = self.weaviate_collection.aggregate.over_all(
                        total_count=True,
                        filters=Filter.by_property("memoryType").equal(memory_type)
                    )
                    type_counts[memory_type] = type_result.total_count
                except Exception as e:
                    print(f"[Memory] ⚠️ Could not get count for {memory_type}: {e}")
                    type_counts[memory_type] = 0
                    
            return {
                "total_memories": total_count,
                "by_type": type_counts,
                "status": "connected (v4.14.4+ optimized)"
            }
            
        except Exception as e:
            print(f"[Memory] ❌ Native aggregation failed, using fallback: {e}")
            # Fallback: fetch and count in Python if aggregation fails
            try:
                response = self.weaviate_collection.query.fetch_objects(
                    limit=1000,
                    return_properties=["memoryType"]
                )
                
                type_counts = {"fact": 0, "preference": 0, "experience": 0, "general": 0}
                total_count = 0
                
                if response.objects:
                    for obj in response.objects:
                        total_count += 1
                        memory_type = obj.properties.get("memoryType", "general")
                        if memory_type in type_counts:
                            type_counts[memory_type] += 1
                        else:
                            type_counts["general"] += 1
                            
                return {
                    "total_memories": total_count,
                    "by_type": type_counts,
                    "status": "connected (fallback mode)"
                }
            except Exception as fallback_error:
                return {"error": f"Could not get stats: {fallback_error}"}

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
