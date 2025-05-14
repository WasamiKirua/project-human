from pocketflow import Node
from utils.vector_index import create_index, add_vector, search_vectors
from utils.call_llm import call_llm

class GetUserQuestionNode(Node):
    def prep(self, shared):
        """Initialize messages if first run"""
        if "messages" not in shared:
            shared["messages"] = []
            print("Welcome to the interactive chat! Type 'exit' to end the conversation.")
        
        return None
    
    def exec(self, _):
        """Get user input interactively"""
        # Get interactive input from user
        user_input = input("\nYou: ")
            
        # Check if user wants to exit
        if user_input.lower() == 'exit':
            return "exit"  # Changed to "exit" for proper flow termination
            
        return user_input
    
    def post(self, shared, prep_res, exec_res):
        # If exec_res is "exit", the user wants to exit
        if exec_res == "exit":
            print("\nGoodbye!")
            
            # Close Weaviate connection if it exists
            if "vector_index" in shared:
                client, _ = shared["vector_index"]
                if client:
                    try:
                        client.close()
                        print("✅ Weaviate connection closed successfully.")
                    except Exception as e:
                        print(f"⚠️ Error closing Weaviate connection: {e}")
            
            return "exit"  # We'll handle this in flow.py
            
        # Add user message to current messages
        shared["messages"].append({"role": "user", "content": exec_res})
        
        return "retrieve"

class AnswerNode(Node):
    def prep(self, shared):
        """Prepare context for the LLM"""
        print("🤖 AnswerNode.prep() called")
        
        if not shared.get("messages"):
            print("❌ No messages in shared state")
            return None
            
        # 1. Get the last 3 conversation pairs (or fewer if not available)
        recent_messages = shared["messages"][-6:] if len(shared["messages"]) > 6 else shared["messages"]
        
        # 2. Add the retrieved relevant conversation if available
        context = []
        
        # Add a system message to override any built-in persona
        context.append({
            "role": "system",
            "content": "You are Samantha an empathic and conscious companion. Respond to the user's questions based on the conversation history provided. Do not sign your messages or use a specific persona."
        })
        
        if shared.get("retrieved_conversation"):
            print("✅ Including retrieved conversation in context")
            # Add a system message to indicate this is a relevant past conversation
            context.append({
                "role": "system", 
                "content": "The following is a relevant past conversation that may help with the current query:"
            })
            context.extend(shared["retrieved_conversation"])
            context.append({
                "role": "system", 
                "content": "Now continue the current conversation:"
            })
        else:
            print("❌ No retrieved conversation to include")
        
        # 3. Add the recent messages
        context.extend(recent_messages)
        
        print(f"✅ Prepared context with {len(context)} messages")
        return context
    
    def exec(self, messages):
        """Generate a response using the LLM"""
        print("🤖 AnswerNode.exec() called")
        
        if messages is None:
            print("❌ No messages to send to LLM")
            return None
        
        print(f"✅ Sending {len(messages)} messages to LLM")
        
        # Call LLM with the context
        try:
            response = call_llm(messages)
            print(f"✅ Received response from LLM: {response[:50]}...")
            return response
        except Exception as e:
            print(f"❌ Error calling LLM: {str(e)}")
            return "I'm sorry, I encountered an error while processing your request."
    
    def post(self, shared, prep_res, exec_res):
        """Process the LLM response"""
        print("🤖 AnswerNode.post() called")
        
        if prep_res is None or exec_res is None:
            print("❌ No response from LLM")
            return None  # End the conversation
        
        # Print the assistant's response
        print(f"\nAssistant: {exec_res}")
        
        # Add assistant message to history
        shared["messages"].append({"role": "assistant", "content": exec_res})
        
        # If we have more than 6 messages (3 conversation pairs), archive the oldest pair
        if len(shared["messages"]) > 6:
            print("📦 We have enough messages to archive the oldest pair")
            return "embed"
        
        print(f"👂 Ready for next question (message count: {len(shared['messages'])})")
        # We only end if the user explicitly typed 'exit'
        # Even if last_question is set, we continue in interactive mode
        return "question"

class EmbedNodeWeaviate(Node):
    def prep(self, shared):
        """Extract the oldest conversation pair for embedding"""
        print("📋 EmbedNode.prep() called")
        
        if len(shared["messages"]) <= 6:
            print("❌ Not enough messages to embed yet (need > 6, have", len(shared["messages"]), ")")
            return None
            
        # Extract the oldest user-assistant pair
        oldest_pair = shared["messages"][:2]
        # Remove them from current messages
        shared["messages"] = shared["messages"][2:]
        
        print(f"✅ Extracted oldest conversation pair for embedding")
        return oldest_pair
    
    def exec(self, conversation):
        """Prepare conversation for storage"""
        print("📋 EmbedNode.exec() called")
        
        if not conversation:
            print("❌ No conversation to embed")
            return None
            
        # Combine user and assistant messages into a single text for Weaviate to vectorize
        user_msg = next((msg for msg in conversation if msg["role"] == "user"), {"content": ""})
        assistant_msg = next((msg for msg in conversation if msg["role"] == "assistant"), {"content": ""})
        combined = f"User: {user_msg['content']} Assistant: {assistant_msg['content']}"
        
        print(f"✅ Prepared conversation text for embedding: {combined[:50]}...")
        
        # With Weaviate's built-in vectorizer, we don't need to generate an embedding
        # We just pass the text content directly
        return {
            "conversation": conversation,
            "content": combined
        }
    
    def post(self, shared, prep_res, exec_res):
        """Store the text content and add to index"""
        print("📋 EmbedNode.post() called")
        
        if not exec_res:
            print("❌ Nothing to embed")
            # If there's nothing to embed, just continue with the next question
            return "question"
            
        # Initialize vector index if not exist
        if "vector_index" not in shared:
            print("🔧 Creating new vector index")
            try:
                # Try to connect to existing vector store first, create new only if needed
                shared["vector_index"] = create_index(create_new=True)
                shared["vector_items"] = []  # Track items separately
                print("✅ Vector index created successfully")
            except Exception as e:
                print(f"❌ Error creating vector index: {str(e)}")
                return "question"
        else:
            print("✅ Using existing vector index")
            
        try:
            # Add the content to the index and store the conversation
            position = add_vector(shared["vector_index"], content=exec_res["content"])
            
            # Check for sentinel value
            if position == -1:
                print("❌ Failed to add vector to index")
                return "question"
                
            shared["vector_items"].append(exec_res["conversation"])
            
            print(f"✅ Added conversation to index at position {position}")
            print(f"✅ Index now contains {len(shared['vector_items'])} conversations")
        except Exception as e:
            print(f"❌ Error adding vector: {str(e)}")
            
        # Continue with the next question
        return "question"

class EmbedNodeSql(Node):
    def prep(self, shared):
        """Extract all conversations for archiving to SQLite"""
        print("📋 EmbedNodeLite.prep() called")
        
        if len(shared["messages"]) <= 6:
            print("❌ Not enough messages to embed yet (need > 6, have", len(shared["messages"]), ")")
            return None
        
        # Take a snapshot of all messages for storage
        all_messages = shared["messages"].copy()
        
        # Clear all current messages from in-memory storage
        # But keep the last pair active for the current conversation
        last_pair = shared["messages"][-2:] if len(shared["messages"]) >= 2 else shared["messages"]
        shared["messages"] = last_pair
        
        print(f"✅ Extracted {len(all_messages)} messages for archiving to SQLite")
        print(f"✅ Kept {len(last_pair)} messages in active memory")
        
        return all_messages
    
    def exec(self, messages):
        """Prepare all messages for storage"""
        print("📋 EmbedNodeLite.exec() called")
        
        if not messages or not isinstance(messages, list):
            print("❌ No messages to embed")
            return None
        
        print(f"⏳ Processing {len(messages)} messages for SQLite storage")
        
        # Transform all messages into individual entries for storage
        entries = []
        
        for i, msg in enumerate(messages):
            if "role" in msg and "content" in msg:
                # Format each message for storage
                formatted = f"{msg['role'].capitalize()}: {msg['content']}"
                entries.append({
                    "position": i,
                    "role": msg["role"],
                    "content": msg["content"],
                    "formatted": formatted
                })
        
        print(f"✅ Prepared {len(entries)} messages for SQLite storage")
        
        return {
            "messages": messages,
            "entries": entries
        }

    def post(self, shared, prep_res, exec_res):
        """Store all conversations in SQLite as short-term memory"""
        print("📋 EmbedNodeLite.post() called")
        
        if not exec_res or "entries" not in exec_res or not exec_res["entries"]:
            print("❌ Nothing to embed")
            # If there's nothing to embed, just continue with the next question
            return "question"
            
        try:
            # Connect to the SQLite database
            import apsw
            import sqlite_vec
            import os
            import time
            from utils.vector_index import SHORT_MEM_DB
            
            # Check if database file exists
            if not os.path.exists(SHORT_MEM_DB):
                print(f"❌ SQLite database file '{SHORT_MEM_DB}' not found")
                # Try to create it
                try:
                    print(f"🔄 Creating SQLite database '{SHORT_MEM_DB}'")
                    db = apsw.Connection(SHORT_MEM_DB)
                    db.enable_load_extension(True)
                    sqlite_vec.load(db)
                    db.enable_load_extension(False)
                    
                    # Create a simple messages table with just id and message
                    db.execute(
                        """
                        CREATE TABLE messages(
                          id INTEGER PRIMARY KEY,
                          message TEXT
                        );
                        """
                    )
                    print(f"✅ Created SQLite database and messages table")
                except Exception as create_error:
                    print(f"❌ Error creating SQLite database: {str(create_error)}")
                    return "question"
            else:
                # Connect to existing database
                db = apsw.Connection(SHORT_MEM_DB)
                db.enable_load_extension(True)
                sqlite_vec.load(db)
                db.enable_load_extension(False)
            
            # Get the next ID
            cursor = db.execute("SELECT MAX(id) FROM messages")
            max_id_row = cursor.fetchone()
            max_id = max_id_row[0] if max_id_row[0] is not None else 0
            next_id = max_id + 1
            
            # Track the batch info for debugging
            batch_time = int(time.time())
            batch_id = f"batch_{batch_time}"
            entries_stored = 0
            
            # Store each message with a unique ID
            for entry in exec_res["entries"]:
                # Format the message with role info
                message_text = entry["formatted"]
                
                # Simple insert with just id and message
                db.execute(
                    "INSERT INTO messages(id, message) VALUES(?, ?)", 
                    [next_id, message_text]
                )
                
                print(f"📝 Added message {next_id}: {message_text[:50]}...")
                next_id += 1
                entries_stored += 1
            
            # Verify insertion
            cursor = db.execute("SELECT COUNT(*) FROM messages")
            count = cursor.fetchone()[0]
            
            print(f"✅ Stored {entries_stored} messages in SQLite database")
            print(f"✅ SQLite database now contains {count} total messages")
            
            # Initialize short-term memory items if needed
            if "short_term_items" not in shared:
                shared["short_term_items"] = []
            
            # Add minimal info about this batch
            shared["short_term_items"].append({
                "batch_id": batch_id,
                "timestamp": batch_time,
                "message_count": entries_stored
            })
            
            print(f"✅ Short-term memory tracking {len(shared['short_term_items'])} batches")
            
        except Exception as e:
            print(f"❌ Error storing conversations in SQLite: {str(e)}")
            import traceback
            traceback.print_exc()
            
        # Continue with the next question
        return "question"

class RetrieveNode(Node):
    def prep(self, shared):
        """Get the current query for retrieval"""
        print("🔍 RetrieveNode.prep() called")
        
        if not shared.get("messages"):
            print("❌ No messages in shared state")
            return None
            
        # Get the latest user message for searching
        latest_user_msg = next((msg for msg in reversed(shared["messages"]) 
                                if msg["role"] == "user"), {"content": ""})
        print(f"📝 Latest user message: {latest_user_msg['content'][:30]}...")
        
        # Check if we have a vector index with items
        if "vector_index" not in shared:
            print("❌ No vector_index in shared state")
            # Try to connect to existing vector store but don't create a new one
            try:
                print("🔄 Attempting to connect to existing vector store...")
                from utils.vector_index import create_index, get_all_items
                vector_index = create_index(create_new=False)
                if vector_index[1] is not None:  # Check if collection is valid
                    shared["vector_index"] = vector_index
                    
                    # Load existing conversation items
                    vector_items = get_all_items(vector_index)
                    shared["vector_items"] = vector_items
                    
                    print(f"✅ Successfully connected to vector store with {len(vector_items)} stored conversations")
                else:
                    print("❌ Couldn't connect to existing vector store")
                    return None
            except Exception as e:
                print(f"❌ Error connecting to vector store: {str(e)}")
                return None
            
        if "vector_items" not in shared:
            print("❌ No vector_items in shared state")
            return None
            
        if len(shared["vector_items"]) == 0:
            print("❌ vector_items is empty - no past conversations to retrieve")
            return None
            
        print(f"✅ Found {len(shared['vector_items'])} past conversations to search through")
        
        return {
            "query": latest_user_msg["content"],
            "vector_index": shared["vector_index"],
            "vector_items": shared["vector_items"]
        }
    
    def exec(self, inputs):
        """Find the most relevant past conversation"""
        if not inputs:
            print("❌ RetrieveNode.exec() - No inputs provided")
            return None
            
        query = inputs["query"]
        vector_index = inputs["vector_index"]
        vector_items = inputs["vector_items"]
        
        print(f"🔍 Finding relevant conversation for: {query[:30]}...")
        
        try:
            # Use the query text directly with Weaviate's text2vec-contextionary
            indices, distances = search_vectors(vector_index, query_text=query, k=1)
            
            if not indices:
                print("❌ No similar conversations found")
                return None
                
            # Get the corresponding conversation
            conversation = vector_items[indices[0]]
            
            print(f"✅ Found relevant conversation at index {indices[0]}")
            return {
                "conversation": conversation,
                "distance": distances[0]
            }
        except Exception as e:
            print(f"❌ Error in search_vectors: {str(e)}")
            return None
    
    def post(self, shared, prep_res, exec_res):
        """Store the retrieved conversation"""
        print("🔍 RetrieveNode.post() called")
        
        if exec_res is not None:
            shared["retrieved_conversation"] = exec_res["conversation"]
            print(f"📄 Retrieved conversation (distance: {exec_res['distance']:.4f})")
        else:
            shared["retrieved_conversation"] = None
            print("❌ No conversation retrieved")
        
        return "answer"
    