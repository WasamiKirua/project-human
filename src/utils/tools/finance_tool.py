import json
import os
from tavily import AsyncTavilyClient
from typing import Dict, Any, Optional
from groq import AsyncGroq
from ..prompts import FINANCE_TOOL

class FinanceTool:
    def __init__(self):
        """Initialize finance tool with config"""
        self.config = self._load_config()
        self.api_keys = self._load_api_keys()
        self.api_key = self.api_keys.get("tavily_api_key")
        self.groq_key = self.api_keys.get("groq_api_key")
        
        # Initialize Tavily client if API key exists
        self.tavily_client = None
        if self.api_key:
            self.tavily_client = AsyncTavilyClient(api_key=self.api_key)

    def _load_config(self) -> Dict[str, Any]:
        """Load finance tool configuration from config.json"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                config_path = '../config.json'
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("tools", {}).get("finance", {})
        except Exception as e:
            print(f"[FinanceTool] ❌ Error loading config: {e}")
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
            print(f"[FinanceTool] ❌ Error loading API keys: {e}")
            return {}
        
    async def execute(self, transcript: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Execute finance tool request
        
        Args:
            transcript: User's original request
            context: Additional context (optional)
            
        Returns:
            Dict with success/error status and data
        """
        print(f"[FinanceTool] 💰 Processing request: {transcript}")

        try:
            # Extract finance query using LLM
            finance_query = await self._extract_finance_query(transcript)
            
            # Validate API key
            if not self.api_key:
                return self._error_response("Tavily API key not configured")
            
            # Fetch finance data
            finance_data = await self._fetch_finance_data(finance_query)
            
            if finance_data and finance_data.get("answer"):
                # Format for Samantha (using only the answer field)
                formatted_data = self._format_finance_data(finance_data, finance_query)
                
                return {
                    "success": True,
                    "tool_type": "finance",
                    "data": formatted_data,
                    "raw_data": finance_data  # Keep raw data for debugging
                }
            else:
                return self._error_response("Could not fetch financial info or no answer found")
                
        except Exception as e:
            print(f"[FinanceTool] ❌ Error: {e}")
            return self._error_response(f"Technical error: {str(e)}")
        
    async def _extract_finance_query(self, transcript: str) -> str:
        """Extract finance query using LLM (Groq)"""
        
        prompt = FINANCE_TOOL.replace('{replacement}', transcript)

        try:
            if not self.groq_key:
                print(f"[FinanceTool] ❌ No Groq API key configured")
                return self.config.get("default_search", "Latest European market status")

            print(f"[FinanceTool] 🤖 Using LLM to extract finance query from: '{transcript}'")

            async with AsyncGroq(api_key=self.groq_key) as client:
                response = await client.chat.completions.create(
                    model="gemma2-9b-it",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.1
                )
                
                # Extract finance query from response
                finance_query = response.choices[0].message.content.strip().strip('"\'')
                
                print(f"[FinanceTool] 💰 LLM extracted: '{finance_query}'")

                # Handle unknown/empty responses
                if finance_query.upper() == "UNKNOWN" or not finance_query or len(finance_query.strip()) < 2:
                    default_query = self.config.get("default_search", "Latest European market status")
                    print(f"[FinanceTool] 💰 No specific query, using default: {default_query}")
                    return default_query

                return finance_query
        except Exception as e:
            print(f"[FinanceTool] ❌ LLM extraction failed: {e}")
            default_query = self.config.get("default_search", "Latest European market status")
            print(f"[FinanceTool] 💰 Fallback to default: {default_query}")
            return default_query
        
    async def _fetch_finance_data(self, finance_query: str) -> Optional[Dict]:
        """Fetch finance data from Tavily API"""
        try:
            print(f"[FinanceTool] 🌐 Fetching financial data for: {finance_query}")
            
            if not self.tavily_client:
                print(f"[FinanceTool] ❌ Tavily client not initialized")
                return None

            # Configure search parameters for financial content
            search_params = {
                "query": finance_query,
                "search_depth": "basic",
                "max_results": 3,  # We only need the answer, but get some results for context
                "include_domains": ["finance.yahoo.com", "bloomberg.com", "marketwatch.com", "reuters.com"],
                "include_answer": True,  # Enable AI answer - this is what we primarily need
                "include_raw_content": False
            }

            # Execute search
            response = await self.tavily_client.search(**search_params)
            
            print(f"[FinanceTool] ✅ Finance data retrieved successfully")
            print(f"[FinanceTool] 📊 Answer: {response.get('answer', 'No answer provided')[:100]}...")
            
            return response
                        
        except Exception as e:
            print(f"[FinanceTool] ❌ Fetch error: {e}")
            return None
        
    def _format_finance_data(self, raw_data: Dict, finance_query: str) -> Dict[str, Any]:
        """Format Tavily finance data for Samantha to process (TTS-friendly)"""
        try:
            # Extract the answer field (primary content we need)
            answer = raw_data.get("answer", "").strip()
            
            if not answer:
                summary = f"I couldn't find financial information for: {finance_query}"
            else:
                # Clean the answer for TTS (remove special chars, keep only text)
                clean_answer = answer.replace("·", ".").replace("•", ".").replace("$", "dollars").strip()
                summary = clean_answer

            # Keep some metadata for debugging if needed
            results = raw_data.get("results", [])
            
            formatted_data = {
                "query": finance_query,
                "summary": summary,  # This is what will be spoken by TTS
                "answer": answer,    # Raw answer from Tavily
                "total_results": len(results),
                "response_time": raw_data.get("response_time", 0)
            }
            
            print(f"[FinanceTool] 📊 Formatted finance answer for TTS: {summary[:100]}...")
            return formatted_data
            
        except Exception as e:
            print(f"[FinanceTool] ❌ Format error: {e}")
            return {
                "query": finance_query,
                "summary": f"Error formatting financial information for {finance_query}",
                "answer": "",
                "total_results": 0,
                "response_time": 0
            }
        
    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        print(f"[FinanceTool] ❌ Error response: {error_message}")
        return {
            "success": False,
            "tool_type": "finance",
            "error": error_message
        }
