import json
import os
import requests
import re
from typing import Dict, Any, Optional
from groq import AsyncGroq
from ..prompts import OTAKU_TOOL, OTAKU_RECAP_PROMPT

class OtakuTool:
    def __init__(self):
        """Initialize otaku tool with config"""
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self.groq_key = self.api_keys.get("groq_api_key")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load otaku tool configuration from config.json"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("tools", {}).get("otaku", {})
        except Exception as e:
            print(f"[OtakuTool] ❌ Error loading config: {e}")
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
            print(f"[OtakuTool] ❌ Error loading API keys: {e}")
            return {}
        
    async def execute(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute otaku tool request
        
        Args:
            transcript: User's original request
            context: Additional context (optional)
            
        Returns:
            Dict with success/error status and data
        """
        print(f"[OtakuTool] ⛩️🌸🍥☯🍜 Processing request: {transcript}")

        try:
            # Extract otaku query using LLM
            otaku_query = await self._extract_otaku_query(transcript)
            
            # Validate groq response
            if not otaku_query or otaku_query.upper() in ["UNKNOWN", "NOT_OTAKU", "NONE"]:
                return self._error_response("This request is not about anime or manga content. Try asking about music with the music tool instead!")
            
            # Fetch otaku data
            otaku_data = await self._fetch_otaku_data(otaku_query)
            
            if otaku_data:
                # Format for Samantha (with recap generation)
                formatted_data = await self._format_otaku_data(otaku_data, otaku_query)
                
                return {
                    "success": True,
                    "tool_type": "otaku",
                    "data": formatted_data,
                    "raw_data": otaku_data  # Keep raw data for debugging
                }
            else:
                return self._error_response("Could not fetch anime/manga info or no results found")
                
        except Exception as e:
            print(f"[OtakuTool] ❌ Error: {e}")
            return self._error_response(f"Technical error: {str(e)}")
        
    async def _extract_otaku_query(self, transcript: str) -> str:
        """Extract otaku query using LLM (Groq)"""
        
        prompt = OTAKU_TOOL.replace('{replacement}', transcript)

        try:
            if not self.groq_key:
                print(f"[OtakuTool] ❌ No Groq API key configured")
                return "UNKNOWN"

            print(f"[OtakuTool] 🤖 Using LLM to extract otaku query from: '{transcript}'")

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.1
                )
                
                # Extract otaku query from response
                otaku_query = response.choices[0].message.content.strip().strip('"\'')
                
                print(f"[OtakuTool] ⛩️🌸🍥☯🍜 LLM extracted: '{otaku_query}'")

                # Handle unknown/empty responses
                if otaku_query.upper() in ["UNKNOWN", "NOT_OTAKU", "NONE"] or not otaku_query or len(otaku_query.strip()) < 2:
                    print(f"[OtakuTool] ⛩️🌸🍥☯🍜 Request is not about anime/manga content")
                    return "NOT_OTAKU"

                return otaku_query
            
        except Exception as e:
            print(f"[OtakuTool] ❌ LLM extraction failed: {e}")
            print(f"[OtakuTool] ⛩️🌸🍥☯🍜 Fallback to not otaku")
            return "NOT_OTAKU"
    
    def _extract_title_from_brackets(self, query: str) -> str:
        """Extract anime/manga title from brackets like [grave of the fireflies]"""
        try:
            # Use regex to find content within brackets
            match = re.search(r'\[(.*?)\]', query)
            if match:
                title = match.group(1).strip()
                print(f"[OtakuTool] 📖 Extracted title from brackets: '{title}'")
                return title
            else:
                # If no brackets found, return the query as-is (fallback)
                print(f"[OtakuTool] ⚠️ No brackets found, using full query: '{query}'")
                return query
        except Exception as e:
            print(f"[OtakuTool] ❌ Error extracting title from brackets: {e}")
            return query
        
    async def _fetch_otaku_data(self, otaku_query: str) -> Optional[Dict]:
        """Fetch otaku data from Jikan API"""
        try:
            print(f"[OtakuTool] 🌐 Fetching otaku data for: {otaku_query}")
            
            # Extract title from brackets
            title = self._extract_title_from_brackets(otaku_query)
            
            # Determine if it's anime or manga request
            if 'MANGA' in otaku_query.upper():
                print(f"[OtakuTool] 📚 Searching for MANGA: {title}")
                response = requests.get(f'https://api.jikan.moe/v4/manga?q={title}')
                json_resp = response.json()
                
                if json_resp.get('data') and len(json_resp['data']) > 0:
                    manga_data = json_resp['data'][0]
                    return {
                        "type": "manga",
                        "title": manga_data.get('title_english') or manga_data.get('title', 'Unknown Title'),
                        "synopsis": manga_data.get('synopsis', 'No synopsis available'),
                        "background": manga_data.get('background', 'No background available'),
                        "author": manga_data.get('authors', [{}])[0].get('name', 'Unknown Author') if manga_data.get('authors') else 'Unknown Author'
                    }
                    
            elif 'ANIME' in otaku_query.upper():
                print(f"[OtakuTool] 📺 Searching for ANIME: {title}")
                response = requests.get(f'https://api.jikan.moe/v4/anime?q={title}')
                json_resp = response.json()
                
                if json_resp.get('data') and len(json_resp['data']) > 0:
                    anime_data = json_resp['data'][0]
                    return {
                        "type": "anime",
                        "title": anime_data.get('title_english') or anime_data.get('title', 'Unknown Title'),
                        "synopsis": anime_data.get('synopsis', 'No synopsis available'),
                        "background": anime_data.get('background', 'No background available'),
                        "studio": anime_data.get('studios', [{}])[0].get('name', 'Unknown Studio') if anime_data.get('studios') else 'Unknown Studio'
                    }
            
            print(f"[OtakuTool] ❌ No data found for query: {otaku_query}")
            return None
                        
        except Exception as e:
            print(f"[OtakuTool] ❌ Fetch error: {e}")
            return None
    
    async def _generate_recap(self, formatted_info: str) -> str:
        """Generate a conversational recap using Groq for TTS"""
        try:
            if not self.groq_key:
                print(f"[OtakuTool] ❌ No Groq API key for recap generation")
                return formatted_info[:150] + "..." if len(formatted_info) > 150 else formatted_info

            print(f"[OtakuTool] 🤖 Generating conversational recap...")

            # Create prompt with the formatted information
            prompt = OTAKU_RECAP_PROMPT.replace('{replacement}', formatted_info)

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,  # Keep recap short for TTS
                    temperature=0.7  # Slightly more creative for conversational tone
                )
                
                recap = response.choices[0].message.content.strip()
                
                print(f"[OtakuTool] ✨ Generated recap: '{recap[:100]}...'")
                return recap
                
        except Exception as e:
            print(f"[OtakuTool] ❌ Recap generation failed: {e}")
            # Fallback to truncated original info
            return formatted_info[:150] + "..." if len(formatted_info) > 150 else formatted_info
    
    async def _format_otaku_data(self, raw_data: Dict, otaku_query: str) -> Dict[str, Any]:
        """Format otaku data for Samantha to process (TTS-friendly)"""
        try:
            if raw_data.get("type") == "manga":
                # Format manga information for recap generation
                title = raw_data.get("title", "Unknown Manga")
                author = raw_data.get("author", "Unknown Author")
                synopsis = raw_data.get("synopsis", "No synopsis available")
                
                detailed_info = f"""Title: {title}
                                Type: Manga
                                Author: {author}
                                Synopsis: {synopsis}
                                """
                
            elif raw_data.get("type") == "anime":
                # Format anime information for recap generation
                title = raw_data.get("title", "Unknown Anime")
                studio = raw_data.get("studio", "Unknown Studio")
                synopsis = raw_data.get("synopsis", "No synopsis available")

                detailed_info = f"""Title: {title}
                                Type: Anime
                                Studio: {studio}
                                Synopsis: {synopsis}
                                """
            else:
                detailed_info = f"Title: {raw_data.get('title', 'Unknown')}, Type: Unknown"

            # Generate conversational recap using Groq
            recap = await self._generate_recap(detailed_info)

            formatted_data = {
                "query": otaku_query,
                "summary": recap,  # Short conversational recap for TTS
                "detailed_info": detailed_info,  # Full info for reference
                "raw_info": raw_data,  # Keep raw API data
                "type": raw_data.get("type", "unknown")
            }
            
            print(f"[OtakuTool] 📊 Generated recap for {raw_data.get('type', 'otaku')} data")
            return formatted_data
            
        except Exception as e:
            print(f"[OtakuTool] ❌ Format error: {e}")
            return {
                "query": otaku_query,
                "summary": f"Sorry, I had trouble getting information about {otaku_query}",
                "detailed_info": "",
                "raw_info": raw_data,
                "type": "error"
            }
    
    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        print(f"[OtakuTool] ❌ Error response: {error_message}")
        return {
            "success": False,
            "tool_type": "otaku",
            "error": error_message
        }
