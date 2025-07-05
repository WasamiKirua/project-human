from .weather_tool import WeatherTool
from .news_tool import NewsTool
from .movies_tool import MoviesTool
from .finance_tool import FinanceTool
from .otaku_tool import OtakuTool

class ToolManager:
    def __init__(self):
        self.tools = {
            "news": NewsTool(),
            "weather": WeatherTool(),
            "movies": MoviesTool(),
            "finance": FinanceTool(),
            "otaku": OtakuTool(),
        }
    
    async def execute_tool(self, tool_type, transcript, context=None):
        if tool_type in self.tools:
            return await self.tools[tool_type].execute(transcript, context)
        else:
            return {
                "success": False,
                "tool_type": tool_type,
                "error": f"Unknown tool: {tool_type}"
            }