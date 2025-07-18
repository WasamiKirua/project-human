"""
WebSocket Router - Real-time updates for status monitoring
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import sys
from pathlib import Path
from typing import Set

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.service_manager import ServiceManager

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.service_manager = ServiceManager()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"[WebSocket] Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WebSocket] Client disconnected. Total connections: {len(self.active_connections)}")

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        # Send initial status
        initial_status = manager.service_manager.get_all_status()
        system_info = {"cpu": 0, "memory": 0, "disk": 0}  # Simplified since we removed system overview
        
        await websocket.send_text(json.dumps({
            "type": "initial_status",
            "data": {
                "services": initial_status,
                "system": system_info
            }
        }))
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif message.get("type") == "request_status":
                    status = manager.service_manager.get_all_status()
                    system_info = {"cpu": 0, "memory": 0, "disk": 0}
                    await websocket.send_text(json.dumps({
                        "type": "status_update",
                        "data": {
                            "services": status,
                            "system": system_info
                        }
                    }))
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"[WebSocket] Error handling message: {e}")
                break
    
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
