"""
Status Router - API endpoints for service status monitoring
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.service_manager import ServiceManager

router = APIRouter()
service_manager = ServiceManager()

@router.get("/status/all")
async def get_all_status() -> Dict:
    """Get status of all services and components"""
    try:
        return service_manager.get_all_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@router.get("/status/{service_name}")
async def get_service_status(service_name: str) -> Dict:
    """Get status of a specific service"""
    try:
        all_status = service_manager.get_all_status()
        
        # Check in infrastructure
        if service_name in all_status["infrastructure"]:
            return {
                "service": service_name,
                "category": "infrastructure",
                **all_status["infrastructure"][service_name]
            }
        
        # Check in components
        if service_name in all_status["components"]:
            return {
                "service": service_name,
                "category": "components",
                **all_status["components"][service_name]
            }
        
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@router.get("/logs/{component}")
async def get_component_logs(component: str, lines: int = 50) -> Dict[str, List[str]]:
    """Get recent log lines for a component"""
    try:
        logs = service_manager.get_logs(component, lines)
        return {"component": component, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")

@router.get("/system")
async def get_system_info() -> Dict:
    """Get basic system information"""
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system info: {str(e)}")
