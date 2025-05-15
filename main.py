from flow import chat_flow
from utils.vector_index import create_index, get_all_items
import warnings
import asyncio


# Suppress specific Pydantic deprecation warning from Weaviate
warnings.filterwarnings("ignore", message="Accessing the 'model_fields' attribute on the instance is deprecated")

async def run_chat_memory_demo_async():
    """
    Run an interactive chat interface with memory retrieval.
    
    Features:
    1. Maintains a window of the 3 most recent conversation pairs
    2. Archives older conversations with embeddings
    3. Retrieves 1 relevant past conversation when needed
    4. Total context to LLM: 3 recent pairs + 1 retrieved pair
    5. Processes memory evaluations asynchronously
    """
    
    print("=" * 50)
    print("PocketFlow Chat with Memory (Async Version)")
    print("=" * 50)
    print("This chat keeps your 3 most recent conversations")
    print("and brings back relevant past conversations when helpful")
    print("Type 'exit' to end the conversation")
    print("=" * 50)
    
    # Initialize shared state with vector index
    shared = {}
    
    # Initialize vector store at startup
    print("🔄 Connecting to existing vector store...")

    try:
        # Connect to existing vector store or create a new one if needed
        vector_index = create_index(create_new=True)
        shared["vector_index"] = vector_index
        
        # Load existing conversation items 
        vector_items = get_all_items(vector_index)
        shared["vector_items"] = vector_items
        
        print(f"✅ Successfully connected to vector store with {len(vector_items)} stored conversations")
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize vector store: {str(e)}")
        print("⚠️ Will create a new vector store when needed")
    
    # Run the chat flow asynchronously
    await chat_flow.run_async(shared)

def run_chat_memory_demo():
    """Wrapper to run the async demo"""
    asyncio.run(run_chat_memory_demo_async())

if __name__ == "__main__":
    run_chat_memory_demo()