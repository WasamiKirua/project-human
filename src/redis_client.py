# In a new file: src/redis_client.py
import redis
import json
import os

def load_redis_config():
    """Load Redis configuration from config.json"""
    config_path = 'config.json'
    if not os.path.exists(config_path):
        config_path = '../config.json'  # For when running from src/
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    return config.get("redis", {
        "host": "localhost",
        "port": 6379,
        "password": "rhost21",
        "decode_responses": True
    })

def create_redis_client():
    """Create Redis client with loaded configuration"""
    redis_config = load_redis_config()
    return redis.Redis(**redis_config)

# Usage in any component:
# from redis_client import create_redis_client
# r = create_redis_client()