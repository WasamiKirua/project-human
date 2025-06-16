import json
import os
from tavily import AsyncTavilyClient
from typing import Dict, Any, Optional
from groq import AsyncGroq
from ..prompts import NEWS_TOOL

class NewsTool:
    def __init__(self):
            """Initialize news tool with config"""
            self.config = self._load_config()
            self.api_keys = self._load_api_keys()
            self.api_key = self.api_keys.get("tavily_api_key")
            self.groq_key = self.api_keys.get("groq_api_key")
            
            # Initialize Tavily client if API key exists
            self.tavily_client = None
            if self.api_key:
                self.tavily_client = AsyncTavilyClient(api_key=self.api_key)

    def _load_config(self) -> Dict[str, Any]:
        """Load news tool configuration from config.json"""
        try:
            # Look for config.json in project root
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'  # Try parent directory
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("tools", {}).get("news", {})
        except Exception as e:
            print(f"[NewsTool] ❌ Error loading config: {e}")
            return {}
    
    def _load_api_keys(self) -> Dict[str, Any]:
        """Load API keys from config.json"""
        try:
            # Look for config.json in project root
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'  # Try parent directory
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("api_keys", {})
        except Exception as e:
            print(f"[NewsTool] ❌ Error loading API keys: {e}")
            return {}
    
    async def execute(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute news tool request
        
        Args:
            transcript: User's original request
            context: Additional context (optional)
            
        Returns:
            Dict with success/error status and data
        """
        print(f"[NewsTool] 🗞️ Processing request: {transcript}")

        try:
            # Extract news query using LLM
            news_query = await self._extract_news_query(transcript)
            
            # Validate API key
            if not self.api_key:
                return self._error_response("Tavily API key not configured")
            
            # Fetch news data
            news_data = await self._fetch_news_data(news_query)
            
            if news_data and news_data.get("results"):
                # Format for Samantha
                formatted_data = self._format_news_data(news_data, news_query)
                
                return {
                    "success": True,
                    "tool_type": "news",
                    "data": formatted_data,
                    "raw_data": news_data  # Keep raw data for debugging
                }
            else:
                return self._error_response("Could not fetch news data or no results found")
                
        except Exception as e:
            print(f"[NewsTool] ❌ Error: {e}")
            return self._error_response(f"Technical error: {str(e)}")
        
    async def _extract_news_query(self, transcript: str) -> str:
        """Extract news query using LLM (Groq)"""
        
        prompt = NEWS_TOOL.replace('{replacement}', transcript)

        try:
            if not self.groq_key:
                print(f"[NewsTool] ❌ No Groq API key configured")
                return self.config.get("default_news", "Latest World News")

            print(f"[NewsTool] 🤖 Using LLM to extract news query from: '{transcript}'")

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.1
                )
                
                # Extract news query from response
                news_query = response.choices[0].message.content.strip().strip('"\'')
                
                print(f"[NewsTool] 📰 LLM extracted: '{news_query}'")

                # Handle unknown/empty responses
                if news_query.upper() == "UNKNOWN" or not news_query or len(news_query.strip()) < 2:
                    default_query = self.config.get("default_news", "Latest World News")
                    print(f"[NewsTool] 📰 No specific query, using default: {default_query}")
                    return default_query

                return news_query
                
        except Exception as e:
            print(f"[NewsTool] ❌ LLM extraction failed: {e}")
            default_query = self.config.get("default_news", "Latest World News")
            print(f"[NewsTool] 📰 Fallback to default: {default_query}")
            return default_query
    
    async def _fetch_news_data(self, news_query: str) -> Optional[Dict]:
        """Fetch news data from Tavily API"""
        try:
            print(f"[NewsTool] 🌐 Fetching news for: {news_query}")
            
            if not self.tavily_client:
                print(f"[NewsTool] ❌ Tavily client not initialized")
                return None

            # Configure search parameters
            search_params = {
                "query": news_query,
                "search_depth": "basic",  # or "advanced" for more comprehensive results
                "max_results": self.config.get("max_results", 3),
                "include_domains": [],  # Can specify trusted news sources
                "exclude_domains": [],  # Can exclude specific domains
                "include_answer": False,  # Disable AI answer for clean TTS output
                "include_raw_content": False  # Set to True if you want full article content
            }

            # Execute search
            response = await self.tavily_client.search(**search_params)
            
            print(f"[NewsTool] ✅ News data retrieved successfully")
            print(f"[NewsTool] 📊 Found {len(response.get('results', []))} articles")
            
            return response
                        
        except Exception as e:
            print(f"[NewsTool] ❌ Fetch error: {e}")
            return None
        
    def _format_news_data(self, raw_data: Dict, news_query: str) -> Dict[str, Any]:
        """Format Tavily news data for Samantha to process (TTS-friendly)"""
        try:
            results = raw_data.get("results", [])
            
            # Extract content from each article for clean TTS output
            content_pieces = []
            articles = []
            
            for i, result in enumerate(results):
                content = result.get("content", "").strip()
                if content:
                    # Clean content for TTS (remove special chars, keep only text)
                    clean_content = content.replace("·", ".").replace("•", ".").strip()
                    content_pieces.append(clean_content)
                
                # Keep article metadata for debugging/logging
                article = {
                    "title": result.get("title", "Unknown Title"),
                    "url": result.get("url", ""),
                    "content": content,
                    "source": result.get("url", "").split('/')[2] if result.get("url") else "Unknown Source",
                    "score": result.get("score", 0)
                }
                articles.append(article)

            # Create clean summary by joining all content pieces
            if content_pieces:
                # Simple, clean summary for TTS - just the content values
                summary = f"Latest news about {news_query}: " + " ".join(content_pieces)
            else:
                summary = f"I couldn't find recent news about {news_query}"

            formatted_data = {
                "query": news_query,
                "summary": summary,
                "content_pieces": content_pieces,  # Individual content values
                "articles": articles,  # Full article data for debugging
                "total_results": len(results)
            }
            
            print(f"[NewsTool] 📊 Formatted {len(content_pieces)} content pieces for TTS")
            return formatted_data
            
        except Exception as e:
            print(f"[NewsTool] ❌ Format error: {e}")
            return {
                "query": news_query,
                "summary": f"Error formatting news data for {news_query}",
                "content_pieces": [],
                "articles": [],
                "total_results": 0
            }

    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        print(f"[NewsTool] ❌ Error response: {error_message}")
        return {
            "success": False,
            "tool_type": "news",
            "error": error_message
        }
        