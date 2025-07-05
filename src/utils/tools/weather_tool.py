import json
import os
import aiohttp
from typing import Dict, Any, Optional
from groq import AsyncGroq
from ..prompts import WEATHER_TOOL

class WeatherTool:
    def __init__(self):
        """Initialize weather tool with config"""
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self.base_url = self.config.get("base_url", "https://api.weatherstack.com")
        self.api_key = self.api_keys.get("tavily_api_key")
        self.groq_key = self.api_keys.get("groq_api_key")
        
    def _load_config(self) -> Dict[str, Any]:
        """Load weather tool configuration from config.json"""
        try:
            # Look for config.json in project root
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'  # Try parent directory
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("tools", {}).get("weather", {})
        except Exception as e:
            print(f"[WeatherTool] ❌ Error loading config: {e}")
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
            print(f"[WeatherTool] ❌ Error loading API keys: {e}")
            return {}

    async def execute(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute weather tool request
        
        Args:
            transcript: User's original request
            context: Additional context (optional)
            
        Returns:
            Dict with success/error status and data
        """
        print(f"[WeatherTool] 🌤️ Processing request: {transcript}")
        
        try:
            # Extract location using LLM
            location = await self._extract_location(transcript)
            
            # Validate API key
            if not self.api_key:
                return self._error_response("Weather API key not configured")
            
            # Get weather data
            weather_data = await self._fetch_weather_data(location)
            
            if weather_data and not weather_data.get("error"):
                # Format for Samantha
                formatted_data = self._format_weather_data(weather_data, location)
                
                return {
                    "success": True,
                    "tool_type": "weather",
                    "data": formatted_data,
                    "raw_data": weather_data  # Keep raw data for debugging
                }
            else:
                error_msg = weather_data.get("error", {}).get("info", "Could not fetch weather data") if weather_data else "Could not fetch weather data"
                return self._error_response(error_msg)
                
        except Exception as e:
            print(f"[WeatherTool] ❌ Error: {e}")
            return self._error_response(f"Technical error: {str(e)}")

    async def _extract_location(self, transcript: str) -> str:
        """Extract location using LLM (Groq)"""

        prompt = WEATHER_TOOL.replace('replacement', transcript)

        try:
            if not self.groq_key:
                print(f"[WeatherTool] ❌ No Groq API key configured")
                return self.config.get("default_location", "Munich, Germany")

            print(f"[WeatherTool] 🤖 Using LLM to extract location from: '{transcript}'")

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=30,
                    temperature=0.1  # Low temperature for consistent extraction
                )
                
                # Extract location from response
                location = response.choices[0].message.content.strip().strip('"\'')
                
                print(f"[WeatherTool] 📍 LLM extracted: '{location}'")

                # Handle unknown/empty responses
                if location.upper() == "UNKNOWN" or not location or len(location.strip()) < 2:
                    default_location = self.config.get("default_location", "Munich, Germany")
                    print(f"[WeatherTool] 📍 No location found, using default: {default_location}")
                    return default_location

                return location
                
        except Exception as e:
            print(f"[WeatherTool] ❌ LLM extraction failed: {e}")
            default_location = self.config.get("default_location", "Munich, Germany")
            print(f"[WeatherTool] 📍 Fallback to default: {default_location}")
            return default_location
    
    async def _fetch_weather_data(self, location: str) -> Optional[Dict]:
        """Fetch weather data from WeatherStack API"""
        try:
            url = f"{self.base_url}/current"
            params = {
                "access_key": self.api_key,
                "query": location
            }
            
            print(f"[WeatherTool] 🌐 Fetching weather for: {location}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check for API errors in response
                        if data.get("error"):
                            print(f"[WeatherTool] ❌ WeatherStack API Error: {data['error']}")
                            return data  # Return with error for proper handling
                        
                        print(f"[WeatherTool] ✅ Weather data retrieved successfully")
                        return data
                    else:
                        print(f"[WeatherTool] ❌ HTTP Error: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"[WeatherTool] ❌ Fetch error: {e}")
            return None
    
    def _format_weather_data(self, raw_data: Dict, location: str) -> Dict[str, Any]:
        """Format WeatherStack data for Samantha to process"""
        try:
            # WeatherStack API structure (exact format from API response)
            current = raw_data.get("current", {})
            location_data = raw_data.get("location", {})
            astro = current.get("astro", {})
            air_quality = current.get("air_quality", {})
            
            # Extract core weather information
            temperature = current.get("temperature", 0)
            feels_like = current.get("feelslike", 0)  # Note: WeatherStack uses "feelslike"
            humidity = current.get("humidity", 0)
            wind_speed = current.get("wind_speed", 0)
            wind_dir = current.get("wind_dir", "")
            wind_degree = current.get("wind_degree", 0)
            pressure = current.get("pressure", 0)
            uv_index = current.get("uv_index", 0)
            visibility = current.get("visibility", 0)
            cloudcover = current.get("cloudcover", 0)
            precipitation = current.get("precip", 0)
            weather_code = current.get("weather_code", 0)
            
            # Weather descriptions and icons
            descriptions = current.get("weather_descriptions", ["unknown"])
            description = descriptions[0] if descriptions else "unknown"
            weather_icons = current.get("weather_icons", [])
            weather_icon = weather_icons[0] if weather_icons else ""
            
            # Location information
            city = location_data.get("name", "")
            country = location_data.get("country", "")
            region = location_data.get("region", "")
            timezone = location_data.get("timezone_id", "")
            localtime = location_data.get("localtime", "")
            
            # Build comprehensive location name
            if city and country:
                location_name = f"{city}, {country}"
            elif city:
                location_name = city
            else:
                location_name = location
                
            # Astronomical data
            sunrise = astro.get("sunrise", "")
            sunset = astro.get("sunset", "")
            moon_phase = astro.get("moon_phase", "")
            
            # Create intelligent summary for Samantha
            summary = f"It's {temperature}°C with {description.lower()} in {location_name}"
            
            # Add feels-like if different
            if feels_like != temperature:
                summary += f", feels like {feels_like}°C"
            
            # Add wind information if significant
            if wind_speed > 5:
                summary += f", wind {wind_speed} km/h from the {wind_dir}"
            
            # Add precipitation info if any
            if precipitation > 0:
                summary += f", {precipitation}mm precipitation"
            
            # Add humidity if high/low
            if humidity > 80:
                summary += f", quite humid at {humidity}%"
            elif humidity < 30:
                summary += f", dry at {humidity}% humidity"
            
            # Comprehensive formatted data for Samantha
            formatted_data = {
                "location": location_name,
                "temperature": temperature,
                "feels_like": feels_like,
                "humidity": humidity,
                "description": description.lower(),
                "weather_code": weather_code,
                "weather_icon": weather_icon,
                "wind_speed": wind_speed,
                "wind_direction": wind_dir,
                "wind_degree": wind_degree,
                "pressure": pressure,
                "uv_index": uv_index,
                "visibility": visibility,
                "cloudcover": cloudcover,
                "precipitation": precipitation,
                "timezone": timezone,
                "localtime": localtime,
                "sunrise": sunrise,
                "sunset": sunset,
                "moon_phase": moon_phase,
                "air_quality": air_quality,
                "summary": summary
            }
            
            print(f"[WeatherTool] 📊 Formatted weather data: {formatted_data['summary']}")
            return formatted_data
            
        except Exception as e:
            print(f"[WeatherTool] ❌ Format error: {e}")
            return {
                "location": location,
                "temperature": 0,
                "summary": f"Weather formatting error for {location}"
            }
    
    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        print(f"[WeatherTool] ❌ Error response: {error_message}")
        return {
            "success": False,
            "tool_type": "weather",
            "error": error_message
        }