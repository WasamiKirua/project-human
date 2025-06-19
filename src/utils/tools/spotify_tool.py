import json
import os
import requests
from typing import Dict, Any, Optional, List
from groq import AsyncGroq
from ..prompts import SPOTIFY_TOOL, SPOTIFY_RECAP_PROMPT

class SpotifyTool:
    def __init__(self):
        """Initialize Spotify tool with config"""
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self.spotify_client_id = self.api_keys.get("spotify_client_id")
        self.spotify_client_secret = self.api_keys.get("spotify_client_secret")
        self.groq_key = self.api_keys.get("groq_api_key")
        self.access_token = None
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Spotify tool configuration"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("tools", {}).get("spotify", {})
        except Exception as e:
            print(f"[SpotifyTool] ❌ Error loading config: {e}")
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
            print(f"[SpotifyTool] ❌ Error loading API keys: {e}")
            return {}

    async def execute(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute Spotify tool request
        
        Args:
            transcript: User's original request
            context: Additional context (optional)
            
        Returns:
            Dict with success/error status and data
        """
        print(f"[SpotifyTool] 🎵 Processing request: {transcript}")

        try:
            # Extract Spotify action using LLM
            spotify_action = await self._extract_spotify_action(transcript)
            
            if not spotify_action or spotify_action.upper() == "UNKNOWN":
                return self._error_response("Could not understand music request")
            
            # Route to appropriate handler
            if "SEARCH" in spotify_action:
                result = await self._handle_search(spotify_action)
            elif "RECOMMEND" in spotify_action:
                result = await self._handle_recommend(spotify_action)
            else:
                return self._error_response("Unsupported Spotify action. Try searching or asking for recommendations!")
            
            if result:
                # Generate conversational recap
                recap = await self._generate_recap(result)
                
                return {
                    "success": True,
                    "tool_type": "spotify",
                    "data": {
                        "summary": recap,
                        "detailed_info": result,
                        "action": spotify_action
                    }
                }
            else:
                return self._error_response("Could not process music request")
                
        except Exception as e:
            print(f"[SpotifyTool] ❌ Error: {e}")
            return self._error_response(f"Technical error: {str(e)}")

    async def _extract_spotify_action(self, transcript: str) -> str:
        """Extract Spotify action using LLM (Groq)"""
        prompt = SPOTIFY_TOOL.replace('{replacement}', transcript)

        try:
            if not self.groq_key:
                print(f"[SpotifyTool] ❌ No Groq API key configured")
                return "UNKNOWN"

            print(f"[SpotifyTool] 🤖 Extracting Spotify action from: '{transcript}'")

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.1
                )
                
                action = response.choices[0].message.content.strip().strip('"\'')
                print(f"[SpotifyTool] 🎵 LLM extracted: '{action}'")
                return action
            
        except Exception as e:
            print(f"[SpotifyTool] ❌ LLM extraction failed: {e}")
            return "UNKNOWN"

    async def _get_access_token(self) -> Optional[str]:
        """Get Spotify access token using Client Credentials flow"""
        try:
            if not self.spotify_client_id or not self.spotify_client_secret:
                print(f"[SpotifyTool] ❌ Missing Spotify credentials")
                return None

            auth_url = "https://accounts.spotify.com/api/token"
            auth_data = {
                "grant_type": "client_credentials",
                "client_id": self.spotify_client_id,
                "client_secret": self.spotify_client_secret
            }
            
            response = requests.post(auth_url, data=auth_data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get("access_token")
                print(f"[SpotifyTool] ✅ Access token obtained")
                return self.access_token
            else:
                print(f"[SpotifyTool] ❌ Token request failed: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"[SpotifyTool] ❌ Token error: {e}")
            return None

    async def _handle_search(self, action: str) -> Optional[Dict]:
        """Handle search requests"""
        try:
            # Extract search query from action like "SEARCH [daft punk]"
            import re
            match = re.search(r'\[(.*?)\]', action)
            if not match:
                return None
                
            query = match.group(1).strip()
            print(f"[SpotifyTool] 🔍 Searching for: {query}")
            
            # Get access token
            token = await self._get_access_token()
            if not token:
                return None
            
            # Search Spotify
            search_url = f"https://api.spotify.com/v1/search"
            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "q": query,
                "type": "track",
                "limit": 5
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                tracks = data.get("tracks", {}).get("items", [])
                
                if tracks:
                    top_track = tracks[0]
                    return {
                        "action_type": "search",
                        "query": query,
                        "track_name": top_track.get("name"),
                        "artist": top_track.get("artists", [{}])[0].get("name"),
                        "album": top_track.get("album", {}).get("name"),
                        "spotify_url": top_track.get("external_urls", {}).get("spotify"),
                        "preview_url": top_track.get("preview_url"),
                        "all_results": tracks[:3]  # Top 3 results
                    }
                    
            return None
            
        except Exception as e:
            print(f"[SpotifyTool] ❌ Search error: {e}")
            return None

    async def _handle_recommend(self, action: str) -> Optional[Dict]:
        """Handle recommendation requests"""
        try:
            # Extract recommendation query from action like "RECOMMEND [jazz]"
            import re
            match = re.search(r'\[(.*?)\]', action)
            if not match:
                return None
                
            mood_genre = match.group(1).strip()
            print(f"[SpotifyTool] 🎯 Recommending: {mood_genre}")
            
            # Map common moods/genres to Spotify search terms
            recommendation_queries = {
                "energetic": "high energy workout",
                "chill": "chill vibes ambient",
                "jazz": "jazz classics",
                "study": "focus study instrumental",
                "workout": "workout pump up",
                "relaxing": "relaxing ambient",
                "sad": "sad emotional ballads",
                "happy": "happy upbeat pop",
                "classical": "classical piano",
                "electronic": "electronic dance",
                "rock": "classic rock hits",
                "pop": "top pop hits",
                "general": "popular trending"
            }
            
            # Get the search query for the mood/genre
            search_query = recommendation_queries.get(mood_genre.lower(), mood_genre)
            
            # Get access token
            token = await self._get_access_token()
            if not token:
                return None
            
            # Search Spotify for recommendations
            search_url = f"https://api.spotify.com/v1/search"
            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "q": search_query,
                "type": "track",
                "limit": 10
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                tracks = data.get("tracks", {}).get("items", [])
                
                if tracks:
                    # Return multiple recommendations
                    recommendations = []
                    for track in tracks[:5]:  # Top 5 recommendations
                        recommendations.append({
                            "name": track.get("name"),
                            "artist": track.get("artists", [{}])[0].get("name"),
                            "album": track.get("album", {}).get("name"),
                            "spotify_url": track.get("external_urls", {}).get("spotify")
                        })
                    
                    return {
                        "action_type": "recommend",
                        "mood_genre": mood_genre,
                        "search_query": search_query,
                        "recommendations": recommendations,
                        "top_pick": recommendations[0] if recommendations else None
                    }
                    
            return None
            
        except Exception as e:
            print(f"[SpotifyTool] ❌ Recommendation error: {e}")
            return None

    async def _generate_recap(self, result_data: Dict) -> str:
        """Generate conversational recap for TTS"""
        try:
            if not self.groq_key:
                return self._fallback_recap(result_data)

            # Format result data for recap generation
            formatted_info = self._format_for_recap(result_data)
            prompt = SPOTIFY_RECAP_PROMPT.replace('{replacement}', formatted_info)

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=120,
                    temperature=0.7
                )
                
                recap = response.choices[0].message.content.strip()
                print(f"[SpotifyTool] ✨ Generated recap")
                return recap
                
        except Exception as e:
            print(f"[SpotifyTool] ❌ Recap generation failed: {e}")
            return self._fallback_recap(result_data)

    def _format_for_recap(self, result_data: Dict) -> str:
        """Format result data for recap generation"""
        action_type = result_data.get("action_type", "unknown")
        
        if action_type == "search":
            return f"""Action: Found music
                       Track: {result_data.get('track_name', 'Unknown')}
                       Artist: {result_data.get('artist', 'Unknown')}
                       Album: {result_data.get('album', 'Unknown')}
                       Query: {result_data.get('query', '')}"""
        
        elif action_type == "recommend":
            top_pick = result_data.get('top_pick', {})
            mood = result_data.get('mood_genre', 'music')
            return f"""Action: Music recommendations
                       Mood/Genre: {mood}
                       Top pick: {top_pick.get('name', 'Unknown')} by {top_pick.get('artist', 'Unknown')}
                       Total recommendations: {len(result_data.get('recommendations', []))}"""
        
        else:
            return f"Action: {action_type}\nResult: {str(result_data)}"

    def _fallback_recap(self, result_data: Dict) -> str:
        """Fallback recap when Groq is unavailable"""
        action_type = result_data.get("action_type", "unknown")
        
        if action_type == "search":
            track = result_data.get('track_name', 'a track')
            artist = result_data.get('artist', 'an artist')
            return f"I found '{track}' by {artist}! Great choice!"
        
        elif action_type == "recommend":
            mood = result_data.get('mood_genre', 'music')
            recommendations = result_data.get('recommendations', [])
            if recommendations:
                top_pick = recommendations[0]
                return f"Perfect! For {mood} vibes, I recommend '{top_pick.get('name')}' by {top_pick.get('artist')}!"
            else:
                return f"I found some great {mood} recommendations for you!"
        
        else:
            return "Music action completed!"

    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        print(f"[SpotifyTool] ❌ Error response: {error_message}")
        return {
            "success": False,
            "tool_type": "spotify",
            "error": error_message
        }