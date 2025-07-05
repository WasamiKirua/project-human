"""
Services Router - API endpoints for service control (start/stop)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.service_manager import ServiceManager

router = APIRouter()
service_manager = ServiceManager()

class ServiceActionRequest(BaseModel):
    action: str  # "start" or "stop"

class ServiceActionResponse(BaseModel):
    success: bool
    message: str
    service: str
    action: str

@router.post("/services/{service_name}/action")
async def control_service(service_name: str, request: ServiceActionRequest) -> ServiceActionResponse:
    """Start or stop a service"""
    try:
        if request.action not in ["start", "stop"]:
            raise HTTPException(status_code=400, detail="Action must be 'start' or 'stop'")
        
        if request.action == "start":
            success, message = service_manager.start_service(service_name)
        else:
            success, message = service_manager.stop_service(service_name)
        
        return ServiceActionResponse(
            success=success,
            message=message,
            service=service_name,
            action=request.action
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to {request.action} {service_name}: {str(e)}")

@router.post("/services/{service_name}/start")
async def start_service(service_name: str) -> ServiceActionResponse:
    """Start a service (convenience endpoint)"""
    try:
        success, message = service_manager.start_service(service_name)
        return ServiceActionResponse(
            success=success,
            message=message,
            service=service_name,
            action="start"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start {service_name}: {str(e)}")

@router.post("/services/{service_name}/stop")
async def stop_service(service_name: str) -> ServiceActionResponse:
    """Stop a service (convenience endpoint)"""
    try:
        success, message = service_manager.stop_service(service_name)
        return ServiceActionResponse(
            success=success,
            message=message,
            service=service_name,
            action="stop"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop {service_name}: {str(e)}")

@router.post("/services/infrastructure/start-all")
async def start_all_infrastructure() -> Dict:
    """Start all infrastructure services (Redis, Weaviate, Whisper)"""
    results = {}
    services = ["redis", "weaviate", "whisper"]
    
    for service in services:
        try:
            success, message = service_manager.start_service(service)
            results[service] = {"success": success, "message": message}
        except Exception as e:
            results[service] = {"success": False, "message": str(e)}
    
    return {"action": "start_all_infrastructure", "results": results}

@router.post("/services/components/start-all")
async def start_all_components() -> Dict:
    """Start all Python components (STT, TTS, LLM, GUI)"""
    results = {}
    components = ["stt", "tts", "llm", "gui"]
    
    for component in components:
        try:
            # Add a timeout wrapper to prevent hanging
            import asyncio
            import concurrent.futures
            
            # Run the blocking operation in a thread with timeout
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(service_manager.start_service, component)
                try:
                    success, message = await asyncio.wrap_future(
                        asyncio.wait_for(asyncio.wrap_future(future), timeout=15.0)
                    )
                    results[component] = {"success": success, "message": message}
                except asyncio.TimeoutError:
                    results[component] = {"success": False, "message": f"Timeout starting {component} (>15s)"}
                except Exception as e:
                    results[component] = {"success": False, "message": f"Error: {str(e)}"}
        except Exception as e:
            results[component] = {"success": False, "message": str(e)}
    
    return {"action": "start_all_components", "results": results}

@router.post("/services/infrastructure/stop-all")
async def stop_all_infrastructure() -> Dict:
    """Stop all infrastructure services"""
    results = {}
    services = ["whisper", "weaviate", "redis"]  # Stop in reverse order
    
    for service in services:
        try:
            success, message = service_manager.stop_service(service)
            results[service] = {"success": success, "message": message}
        except Exception as e:
            results[service] = {"success": False, "message": str(e)}
    
    return {"action": "stop_all_infrastructure", "results": results}

@router.post("/services/components/stop-all")
async def stop_all_components() -> Dict:
    """Stop all Python components"""
    results = {}
    components = ["gui", "llm", "tts", "stt"]  # Stop in reverse order
    
    for component in components:
        try:
            success, message = service_manager.stop_service(component)
            results[component] = {"success": success, "message": message}
        except Exception as e:
            results[component] = {"success": False, "message": str(e)}
    
    return {"action": "stop_all_components", "results": results}

@router.post("/services/restart-all")
async def restart_all_services() -> Dict:
    """Restart all services and components"""
    # Stop all first
    stop_components_result = await stop_all_components()
    stop_infrastructure_result = await stop_all_infrastructure()
    
    # Small delay
    import asyncio
    await asyncio.sleep(2)
    
    # Start all
    start_infrastructure_result = await start_all_infrastructure()
    start_components_result = await start_all_components()
    
    return {
        "action": "restart_all",
        "stop_results": {
            "components": stop_components_result["results"],
            "infrastructure": stop_infrastructure_result["results"]
        },
        "start_results": {
            "infrastructure": start_infrastructure_result["results"],
            "components": start_components_result["results"]
        }
    }
