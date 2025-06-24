"""
WebSocket Router - Real-time updates for status monitoring
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
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

    async def send_to_all(self, message: dict):
        """Send message to all connected clients"""
        if not self.active_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                print(f"[WebSocket] Error sending to client: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast_status_updates(self):
        """Continuously broadcast status updates to all clients"""
        while True:
            try:
                if self.active_connections:
                    # Get current status
                    status = self.service_manager.get_service_status()
                    system_info = self.service_manager.get_system_info()
                    
                    # Send status update
                    await self.send_to_all({
                        "type": "status_update",
                        "data": {
                            "services": status,
                            "system": system_info,
                            "timestamp": asyncio.get_event_loop().time()
                        }
                    })
                
                # Wait before next update
                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                print(f"[WebSocket] Error in broadcast loop: {e}")
                await asyncio.sleep(5)

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
                elif message.get("type") == "request_logs":
                    component = message.get("component", "")
                    lines = message.get("lines", 50)
                    if component:
                        logs = manager.service_manager.get_logs(component, lines)
                        await websocket.send_text(json.dumps({
                            "type": "logs_update",
                            "data": {
                                "component": component,
                                "logs": logs
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

# Start the background task for broadcasting status updates
@router.on_event("startup")
async def startup_event():
    # Start background task for status broadcasting
    asyncio.create_task(manager.broadcast_status_updates())
    print("[WebSocket] Started background status broadcasting")
