from .weather_tool import WeatherTool
from .news_tool import NewsTool

class ToolManager:
    def __init__(self):
        self.tools = {
            "news": NewsTool(),
            "weather": WeatherTool()
            #"spotify": SpotifyTool(), 
            #"search": SearchTool(),
        }
    
    async def execute_tool(self, tool_type, transcript, context=None):
        if tool_type in self.tools:
            return await self.tools[tool_type].execute(transcript, context)
        else:
            return f"Unknown tool: {tool_type}"