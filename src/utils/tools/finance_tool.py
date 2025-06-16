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
        self.api_key = self.config.get("tavily_api_key")
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
                return config.get("tools", {}).get("finance", {})
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