"""
Service Manager - Utilities for controlling system components
"""

import os
import subprocess
import psutil
import time
import json
from pathlib import Path
from typing import Tuple, Dict, List
from redis_client import create_redis_client
from redis_state import RedisState

class ServiceManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent.parent
        self.logs_dir = self.project_root / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # Initialize Redis connection
        try:
            self.redis_client = create_redis_client()
            # Use absolute path to config.json - go up 4 levels from utils/service_manager.py
            config_path = self.project_root / "config.json"
            if config_path.exists():
                self.state = RedisState(self.redis_client, str(config_path))
                print(f"[ServiceManager] ✅ Connected to Redis with config: {config_path}")
            else:
                print(f"[ServiceManager] ⚠️ Config file not found at {config_path}, using Redis without state rules")
                self.state = None
        except Exception as e:
            print(f"[ServiceManager] ❌ Redis connection failed: {e}")
            self.redis_client = None
            self.state = None

    def get_all_status(self) -> Dict:
        """Get status of all services and components"""
        status = {
            "infrastructure": {
                "redis": self._check_redis_status(),
                "weaviate": self._check_weaviate_status(),
                "whisper": self._check_whisper_status()
            },
            "components": {
                "stt": self._check_component_status("stt"),
                "tts": self._check_component_status("tts"),
                "llm": self._check_component_status("llm"),
                "gui": self._check_component_status("gui"),
                "webinterface": self._check_component_status("webinterface")
            }
        }
        return status

    def _check_redis_status(self) -> Dict:
        """Check Redis Docker container status"""
        try:
            result = subprocess.run(
                ["docker-compose", "ps", "redis"], 
                cwd=self.project_root,
                capture_output=True, 
                text=True
            )
            if result.returncode == 0 and "Up" in result.stdout:
                # Test actual connection
                if self.redis_client:
                    try:
                        self.redis_client.ping()
                        return {"status": "running", "message": "Connected and responsive"}
                    except:
                        return {"status": "error", "message": "Container up but not responsive"}
                return {"status": "running", "message": "Container running"}
            return {"status": "stopped", "message": "Container not running"}
        except Exception as e:
            return {"status": "error", "message": f"Check failed: {str(e)}"}

    def _check_weaviate_status(self) -> Dict:
        """Check Weaviate Docker container status"""
        try:
            result = subprocess.run(
                ["docker-compose", "ps", "weaviate"], 
                cwd=self.project_root,
                capture_output=True, 
                text=True
            )
            if result.returncode == 0 and "Up" in result.stdout:
                # Test actual connection
                try:
                    import requests
                    response = requests.get("http://localhost:8080/v1/meta", timeout=5)
                    if response.status_code == 200:
                        return {"status": "running", "message": "Connected and responsive"}
                    return {"status": "error", "message": "Container up but endpoint not accessible"}
                except:
                    return {"status": "error", "message": "Container up but endpoint not accessible"}
            return {"status": "stopped", "message": "Container not running"}
        except Exception as e:
            return {"status": "error", "message": f"Check failed: {str(e)}"}

    def _check_whisper_status(self) -> Dict:
        """Check Whisper server status"""
        try:
            pid_file = self.logs_dir / "whisper.pid"
            if pid_file.exists():
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    return {"status": "running", "message": f"Running (PID: {pid})"}
                else:
                    pid_file.unlink()
                    return {"status": "stopped", "message": "Process not running (cleaned stale PID)"}
            return {"status": "stopped", "message": "Not running"}
        except Exception as e:
            return {"status": "error", "message": f"Check failed: {str(e)}"}

    def _check_component_status(self, component: str) -> Dict:
        """Check Python component status"""
        try:
            pid_file = self.logs_dir / f"{component}.pid"
            if pid_file.exists():
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    return {"status": "running", "message": f"Running (PID: {pid})"}
                else:
                    # Clean up stale PID file
                    pid_file.unlink()
                    return {"status": "stopped", "message": "Process not running (cleaned stale PID)"}
            
            # Check if process is running without PID file
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline_list = proc.info['cmdline']
                    if not cmdline_list:  # Handle None or empty list
                        continue
                    cmdline = ' '.join(cmdline_list)
                    if (f"{component}_component.py" in cmdline or 
                        f"gui_main.py" in cmdline or
                        (component == "webinterface" and "src/webinterface/app.py" in cmdline)):
                        return {"status": "running", "message": f"Running (PID: {proc.info['pid']}, no PID file)"}
                except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
                    continue
            
            return {"status": "stopped", "message": "Not running"}
        except Exception as e:
            return {"status": "error", "message": f"Check failed: {str(e)}"}

    def start_service(self, service_name: str) -> Tuple[bool, str]:
        """Start a service or component"""
        try:
            if service_name == "redis":
                return self._start_docker_service("redis")
            elif service_name == "weaviate":
                # Weaviate requires contextionary, so start both
                return self._start_weaviate_with_dependencies()
            elif service_name == "whisper":
                return self._start_whisper()
            elif service_name in ["stt", "tts", "llm", "gui", "webinterface"]:
                return self._start_component(service_name)
            else:
                return False, f"Unknown service: {service_name}"
        except Exception as e:
            return False, f"Failed to start {service_name}: {str(e)}"

    def stop_service(self, service_name: str) -> Tuple[bool, str]:
        """Stop a service or component"""
        try:
            if service_name == "redis":
                return self._stop_docker_service("redis")
            elif service_name == "weaviate":
                # Weaviate should stop contextionary too
                return self._stop_weaviate_with_dependencies()
            elif service_name == "whisper":
                return self._stop_whisper()
            elif service_name in ["stt", "tts", "llm", "gui", "webinterface"]:
                return self._stop_component(service_name)
            else:
                return False, f"Unknown service: {service_name}"
        except Exception as e:
            return False, f"Failed to stop {service_name}: {str(e)}"

    def _start_docker_service(self, service: str) -> Tuple[bool, str]:
        """Start Docker service"""
        result = subprocess.run(
            ["docker-compose", "up", "-d", service],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, f"{service} started successfully"
        return False, f"Failed to start {service}: {result.stderr}"

    def _start_weaviate_with_dependencies(self) -> Tuple[bool, str]:
        """Start Weaviate with required contextionary dependency"""
        result = subprocess.run(
            ["docker-compose", "up", "-d", "contextionary", "weaviate"],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, "Weaviate (with contextionary) started successfully"
        return False, f"Failed to start Weaviate: {result.stderr}"

    def _stop_docker_service(self, service: str) -> Tuple[bool, str]:
        """Stop Docker service"""
        result = subprocess.run(
            ["docker-compose", "stop", service],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, f"{service} stopped successfully"
        return False, f"Failed to stop {service}: {result.stderr}"

    def _stop_weaviate_with_dependencies(self) -> Tuple[bool, str]:
        """Stop Weaviate and its contextionary dependency"""
        result = subprocess.run(
            ["docker-compose", "stop", "weaviate", "contextionary"],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True, "Weaviate (with contextionary) stopped successfully"
        return False, f"Failed to stop Weaviate: {result.stderr}"

    def _start_whisper(self) -> Tuple[bool, str]:
        """Start Whisper server"""
        whisper_binary = "./whisper.cpp/build/bin/whisper-server"
        whisper_model = "./whisper.cpp/models/ggml-medium.en.bin"
        
        # Check if files exist using absolute paths for verification
        abs_binary = self.project_root / "whisper.cpp" / "build" / "bin" / "whisper-server"
        abs_model = self.project_root / "whisper.cpp" / "models" / "ggml-medium.en.bin"
        
        if not abs_binary.exists():
            return False, "Whisper binary not found"
        if not abs_model.exists():
            return False, "Whisper model not found"
        
        # Check if already running
        status = self._check_whisper_status()
        if status["status"] == "running":
            return True, "Whisper already running"
        
        try:
            log_file = self.logs_dir / "whisper.log"
            pid_file = self.logs_dir / "whisper.pid"
            
            # Use the exact same command as Makefile with nohup and relative paths
            cmd = [
                "nohup", whisper_binary,
                "--model", whisper_model,
                "--host", "0.0.0.0",
                "--port", "8081"
            ]
            
            with open(log_file, 'w') as log:
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=self.project_root,  # Run from project root for relative paths
                    preexec_fn=os.setsid  # Create new process group for nohup-like behavior
                )
            
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))
            
            # Give it a moment to start
            time.sleep(2)
            
            # Verify it started
            if psutil.pid_exists(process.pid):
                return True, f"Whisper started successfully (PID: {process.pid})"
            return False, "Whisper failed to start"
            
        except Exception as e:
            return False, f"Failed to start Whisper: {str(e)}"

    def _stop_whisper(self) -> Tuple[bool, str]:
        """Stop Whisper server"""
        try:
            pid_file = self.logs_dir / "whisper.pid"
            
            if pid_file.exists():
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    process.terminate()
                    process.wait(timeout=5)
                
                # Clean up PID file only
                pid_file.unlink()
                
                return True, "Whisper stopped successfully"
            return True, "Whisper was not running"
        except Exception as e:
            return False, f"Failed to stop Whisper: {str(e)}"

    def _start_component(self, component: str) -> Tuple[bool, str]:
        """Start Python component - Fixed to not hang"""
        # Check if already running
        status = self._check_component_status(component)
        if status["status"] == "running":
            return True, f"{component} already running"
        
        try:
            # Create log and PID files
            log_file = self.logs_dir / f"{component}.log"
            pid_file = self.logs_dir / f"{component}.pid"
            
            # Determine script path - use paths relative to project root like Makefile
            if component == "gui":
                script = "src/gui_main.py"
            elif component == "webinterface":
                script = "src/webinterface/app.py"
            else:
                script = f"src/{component}_component.py"
            
            # Use virtual environment python
            venv_python = self.project_root / ".venv" / "bin" / "python"
            script_path = self.project_root / script
            
            if not script_path.exists():
                return False, f"Script not found: {script_path}"
            if not venv_python.exists():
                return False, "Virtual environment not found"
            
            # Start process from project root (so config.json is accessible)
            with open(log_file, 'w') as log:
                process = subprocess.Popen(
                    [str(venv_python), "-u", script],  # Add -u for unbuffered output
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=self.project_root,  # Run from project root, not src
                    preexec_fn=os.setsid  # Create new process group
                )
            
            # Write PID to file immediately
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))
            
            # Give it a moment to start
            time.sleep(0.5)
            
            # Verify it started
            if psutil.pid_exists(process.pid):
                return True, f"{component} started successfully (PID: {process.pid})"
            else:
                return False, f"{component} failed to start (process not found)"
            
        except Exception as e:
            return False, f"Failed to start {component}: {str(e)}"

    def _stop_component(self, component: str) -> Tuple[bool, str]:
        """Stop Python component"""
        try:
            pid_file = self.logs_dir / f"{component}.pid"
            
            if pid_file.exists():
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    
                    # For TTS component, be more aggressive
                    if component == "tts":
                        try:
                            # First try gentle termination
                            process.terminate()
                            process.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            # If it doesn't respond, force kill
                            process.kill()
                            process.wait(timeout=2)
                    else:
                        # Standard termination for other components
                        process.terminate()
                        process.wait(timeout=5)
                
                # Clean up PID file only
                pid_file.unlink()
                
                return True, f"{component} stopped successfully"
            
            # Try to find and kill process by cmdline
            killed = False
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline_list = proc.info['cmdline']
                    if not cmdline_list:  # Handle None or empty list
                        continue
                    cmdline = ' '.join(cmdline_list)
                    if (f"{component}_component.py" in cmdline or 
                        (component == "gui" and "gui_main.py" in cmdline) or
                        (component == "webinterface" and "src/webinterface/app.py" in cmdline)):
                        
                        # For TTS, use kill immediately if found without PID file
                        if component == "tts":
                            proc.kill()
                        else:
                            proc.terminate()
                        proc.wait(timeout=5)
                        killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
                    continue
            
            if killed:
                return True, f"{component} stopped successfully"
            
            return True, f"{component} was not running"
            
        except Exception as e:
            return False, f"Failed to stop {component}: {str(e)}"

    def get_logs(self, component: str, lines: int = 50) -> List[str]:
        """Get recent log lines for a component"""
        try:
            log_file = self.logs_dir / f"{component}.log"
            if not log_file.exists():
                return [f"No log file found for {component}"]
            
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                return [line.rstrip() for line in all_lines[-lines:]]
        except Exception as e:
            return [f"Error reading logs: {str(e)}"]
