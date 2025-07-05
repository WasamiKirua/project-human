"""
Project Human Redis - Web Interface
Main FastAPI application for system monitoring and control
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn

# Add parent directory to path to import Redis modules
sys.path.append(str(Path(__file__).parent.parent))

from routers import status, services, websocket_router
from utils.service_manager import ServiceManager

# Initialize FastAPI app
app = FastAPI(
    title="Project Human Redis - Web Interface",
    description="Web interface for monitoring and controlling AI assistant components",
    version="1.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Setup templates
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Include routers
app.include_router(status.router, prefix="/api", tags=["status"])
app.include_router(services.router, prefix="/api", tags=["services"])
app.include_router(websocket_router.router, tags=["websocket"])

# Initialize service manager
service_manager = ServiceManager()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse(
        "dashboard.html", 
        {"request": request, "title": "Project Human Redis Dashboard"}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "web-interface"}

if __name__ == "__main__":
    print("🚀 Starting Project Human Redis Web Interface...")
    print("📊 Dashboard available at: http://0.0.0.0:5001")
    print("📖 API docs available at: http://0.0.0.0:5001/docs")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5001,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],
        log_level="info"
    )
