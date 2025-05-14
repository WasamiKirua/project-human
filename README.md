# PocketFlow Chat with Weaviate Memory

This project implements a conversational agent with memory using PocketFlow, backed by a locally hosted Weaviate vector database for storing and retrieving conversations.

## Features

- Interactive chat interface with memory
- Maintains a window of the 3 most recent conversation pairs
- Archives older conversations in Weaviate with auto-vectorization
- Retrieves relevant past conversations when needed
- No external API dependencies - everything runs locally

## Setup

1. **Start the Weaviate Docker container**

   Make sure your docker-compose.yml is properly configured:

   ```yaml
   services:
     weaviate:
       command:
       - --host
       - 0.0.0.0
       - --port
       - '8080'
       - --scheme
       - http
       image: cr.weaviate.io/semitechnologies/weaviate:1.30.0
       ports:
       - 8080:8080
       - 50051:50051
       volumes:
       - ./weaviate_data:/var/lib/weaviate
       restart: on-failure:0
       environment:
         CONTEXTIONARY_URL: contextionary:9999
         QUERY_DEFAULTS_LIMIT: 25
         AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
         PERSISTENCE_DATA_PATH: '/var/lib/weaviate'
         DEFAULT_VECTORIZER_MODULE: 'text2vec-contextionary'
         ENABLE_MODULES: 'text2vec-contextionary'
         CLUSTER_HOSTNAME: 'node1'
     contextionary:
       environment:
         OCCURRENCE_WEIGHT_LINEAR_FACTOR: 0.75
         EXTENSIONS_STORAGE_MODE: weaviate
         EXTENSIONS_STORAGE_ORIGIN: http://weaviate:8080
         NEIGHBOR_OCCURRENCE_IGNORE_PERCENTILE: 5
         ENABLE_COMPOUND_SPLITTING: 'false'
       image: cr.weaviate.io/semitechnologies/contextionary:en0.16.0-v1.2.1
       ports:
       - 9999:9999
   ```

   Start the container with:

   ```bash
   docker-compose up -d
   ```

2. **Install dependencies**

   ```bash
   pip install -e .
   ```

3. **Run the chat application**

   ```bash
   python main.py
   ```

## Implementation Details

- **Vector Storage**: Uses Weaviate with text2vec-contextionary for storing and retrieving conversations
- **Zero External Dependencies for Embeddings**: No need for external APIs - vectorization happens inside Weaviate
- **LLM Integration**: Uses Ollama local models via the OpenAI API format
- **Conversation History**: Keeps the 3 most recent conversation pairs in memory
- **Retrieval Mechanism**: Retrieves 1 relevant past conversation when needed

## How It Works

1. When a conversation exceeds 3 pairs, the oldest pair is archived
2. The text is stored in Weaviate, which automatically creates vector embeddings
3. When a new question is asked, Weaviate searches for semantically similar past conversations
4. Relevant past conversations are included in the context for the LLM to generate a response

## Usage

1. Start a conversation by running `python main.py`
2. Type your questions or messages
3. The system will remember recent conversations and fetch relevant past ones
4. Type 'exit' to end the conversation

## Benefits of This Approach

- **Privacy**: All data and processing stays local
- **No Embedding API Costs**: No external API calls for embeddings means no usage costs for vector generation
- **Simplicity**: Fewer dependencies and configurations
- **Persistence**: Conversations are stored persistently between sessions
