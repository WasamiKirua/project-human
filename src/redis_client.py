# In a new file: src/redis_client.py
import redis
import json
import os

def load_redis_config():
    """Load Redis configuration from config.json"""
    # config.json is always in the project root
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get("redis", {
            "host": "localhost",
            "port": 6379,
            "password": "rhost21",
            "decode_responses": True
        })
    except Exception as e:
        print(f"[Redis] ❌ Error loading config from {config_path}: {e}")
        return {
            "host": "localhost",
            "port": 6379,
            "password": "rhost21",
            "decode_responses": True
        }

def create_redis_client():
    """Create Redis client with loaded configuration"""
    redis_config = load_redis_config()
    return redis.Redis(**redis_config)

# Usage in any component:
# from redis_client import create_redis_client
# r = create_redis_client()