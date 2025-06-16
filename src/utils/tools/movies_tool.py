import json
import os
from tavily import AsyncTavilyClient
from typing import Dict, Any, Optional, List
from groq import AsyncGroq
from ..prompts import MOVIES_TOOL

class MoviesTool:
    def __init__(self):
        """Initialize movies tool with config"""
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self.api_key = self.api_keys.get("tavily_api_key")
        self.groq_key = self.api_keys.get("groq_api_key")
        
        # Initialize Tavily client if API key exists
        self.tavily_client = None
        if self.api_key:
            self.tavily_client = AsyncTavilyClient(api_key=self.api_key)

    def _load_config(self) -> Dict[str, Any]:
        """Load movies tool configuration from config.json"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("tools", {}).get("movies", {})
        except Exception as e:
            print(f"[MoviesTool] ❌ Error loading config: {e}")
            return {}
    
    def _load_api_keys(self) -> Dict[str, Any]:
        """Load API keys from config.json"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("api_keys", {})
        except Exception as e:
            print(f"[MoviesTool] ❌ Error loading API keys: {e}")
            return {}

    async def execute(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute movies tool request
        
        Args:
            transcript: User's original request
            context: Additional context (optional)
            
        Returns:
            Dict with success/error status and data
        """
        print(f"[MoviesTool] 🎬 Processing request: {transcript}")

        try:
            # Extract movie query using LLM
            movie_query = await self._extract_movie_query(transcript)
            
            # Validate API key
            if not self.api_key:
                return self._error_response("Tavily API key not configured")
            
            # Fetch movie recommendations data
            movie_data = await self._fetch_movie_data(movie_query)
            
            if movie_data and movie_data.get("results"):
                # Format for Samantha
                formatted_data = self._format_movie_data(movie_data, movie_query)
                
                return {
                    "success": True,
                    "tool_type": "movies",
                    "data": formatted_data,
                    "raw_data": movie_data  # Keep raw data for debugging
                }
            else:
                return self._error_response("Could not fetch movie recommendations or no results found")
                
        except Exception as e:
            print(f"[MoviesTool] ❌ Error: {e}")
            return self._error_response(f"Technical error: {str(e)}")

    async def _extract_movie_query(self, transcript: str) -> str:
        """Extract movie query using LLM (Groq)"""
        
        prompt = MOVIES_TOOL.replace('{replacement}', transcript)

        try:
            if not self.groq_key:
                print(f"[MoviesTool] ❌ No Groq API key configured")
                return self.config.get("default_movies", "Best movies of the year")

            print(f"[MoviesTool] 🤖 Using LLM to extract movie query from: '{transcript}'")

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.1
                )
                
                # Extract movie query from response
                movie_query = response.choices[0].message.content.strip().strip('"\'')
                
                print(f"[MoviesTool] 🎬 LLM extracted: '{movie_query}'")

                # Handle unknown/empty responses
                if movie_query.upper() == "UNKNOWN" or not movie_query or len(movie_query.strip()) < 2:
                    default_query = self.config.get("default_movies", "Best movies of the year")
                    print(f"[MoviesTool] 🎬 No specific query, using default: {default_query}")
                    return default_query

                return movie_query
                
        except Exception as e:
            print(f"[MoviesTool] ❌ LLM extraction failed: {e}")
            default_query = self.config.get("default_movies", "Best movies of the year")
            print(f"[MoviesTool] 🎬 Fallback to default: {default_query}")
            return default_query

    async def _fetch_movie_data(self, movie_query: str) -> Optional[Dict]:
        """Fetch movie data from Tavily API"""
        try:
            print(f"[MoviesTool] 🌐 Fetching movies for: {movie_query}")
            
            if not self.tavily_client:
                print(f"[MoviesTool] ❌ Tavily client not initialized")
                return None

            # Configure search parameters for movie content
            search_params = {
                "query": movie_query + " recommendations reviews",  # Enhanced query for better results
                "search_depth": "basic",
                "max_results": self.config.get("max_results", 3),
                "include_domains": ["imdb.com", "rottentomatoes.com", "metacritic.com", "collider.com", "variety.com"],  # Movie-focused domains
                "exclude_domains": [],
                "include_answer": False,  # Disable AI answer for clean TTS output
                "include_raw_content": False
            }

            # Execute search
            response = await self.tavily_client.search(**search_params)
            
            print(f"[MoviesTool] ✅ Movie data retrieved successfully")
            print(f"[MoviesTool] 📊 Found {len(response.get('results', []))} movie recommendations")
            
            return response
                        
        except Exception as e:
            print(f"[MoviesTool] ❌ Fetch error: {e}")
            return None

    def _format_movie_data(self, raw_data: Dict, movie_query: str) -> Dict[str, Any]:
        """Format Tavily movie data for Samantha to process (TTS-friendly)"""
        try:
            results = raw_data.get("results", [])
            
            # Extract content from each result for clean TTS output
            content_pieces = []
            movies = []
            
            for i, result in enumerate(results):
                content = result.get("content", "").strip()
                if content:
                    # Clean content for TTS (remove special chars, keep only text)
                    clean_content = content.replace("·", ".").replace("•", ".").replace("★", "star").replace("★★★★★", "5 stars").strip()
                    content_pieces.append(clean_content)
                
                # Keep movie metadata for debugging/logging
                movie = {
                    "title": result.get("title", "Unknown Title"),
                    "url": result.get("url", ""),
                    "content": content,
                    "source": result.get("url", "").split('/')[2] if result.get("url") else "Unknown Source",
                    "score": result.get("score", 0)
                }
                movies.append(movie)

            # Create clean summary by joining all content pieces
            if content_pieces:
                # Simple, clean summary for TTS - just the content values
                summary = f"Movie recommendations for {movie_query}: " + " ".join(content_pieces)
            else:
                summary = f"I couldn't find movie recommendations for {movie_query}"

            formatted_data = {
                "query": movie_query,
                "summary": summary,
                "content_pieces": content_pieces,  # Individual content values
                "movies": movies,  # Full movie data for debugging
                "total_results": len(results)
            }
            
            print(f"[MoviesTool] 📊 Formatted {len(content_pieces)} movie recommendations for TTS")
            return formatted_data
            
        except Exception as e:
            print(f"[MoviesTool] ❌ Format error: {e}")
            return {
                "query": movie_query,
                "summary": f"Error formatting movie recommendations for {movie_query}",
                "content_pieces": [],
                "movies": [],
                "total_results": 0
            }

    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        print(f"[MoviesTool] ❌ Error response: {error_message}")
        return {
            "success": False,
            "tool_type": "movies",
            "error": error_message
        }
