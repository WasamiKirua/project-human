import redis
import time
import json
import os
import asyncio
from typing import Any, Callable, Dict

class RedisState:
    def __init__(self, redis_client: redis.Redis, config_path="config.json"):
        self.r = redis_client
        self.pub_channel = "channel:state"
        self.subscribers: Dict[str, Callable] = {}
        self._load_rules(config_path)

    def _load_rules(self, path):
        self.rules = {}
        if os.path.exists(path):
            with open(path, "r") as f:
                config = json.load(f)
                self.rules = config.get("rules", {})
        print(f"[State] Loaded rules for: {list(self.rules.keys())}")

    def _rule_for(self, key: str) -> Dict[str, Any]:
        return self.rules.get(key, {})

    def _is_allowed(self, key: str, new_value: Any, source: str, priority: int) -> bool:
        rule = self._rule_for(key)

        # Rule: allow_if condition
        if "allow_if" in rule:
            expected = rule["allow_if"]
            if str(new_value).lower() != str(expected).lower():
                return False

        # Rule: min_priority
        if "min_priority" in rule and priority < rule["min_priority"]:
            return False

        # Rule: allowed_sources
        if "allowed_sources" in rule and source not in rule["allowed_sources"]:
            return False

        return True

    async def set(self, key: str, value: Any, source: str = "unknown", priority: int = 0) -> bool:
        full_key = f"state:{key}"
        ts = int(time.time())

        existing = self.r.hgetall(full_key)
        if existing:
            existing_priority = int(existing.get("priority", 0))
            if priority < existing_priority:
                print(f"[State] Skipped {key}: lower priority")
                return False

        if not self._is_allowed(key, value, source, priority):
            print(f"[State] Denied update for {key} from {source} due to rule")
            return False

        self.r.hset(full_key, mapping={
            "value": str(value),
            "source": source,
            "priority": priority,
            "timestamp": ts
        })
        self.r.publish(self.pub_channel, f"{key}={value}")
        return True

    def get_value(self, key: str) -> Any:
        full_key = f"state:{key}"
        return self.r.hget(full_key, "value")

    def set_value(self, key: str, value: Any, source: str = "system", priority: int = 1):
        # Synchronous version of set (for non-async components)
        asyncio.run(self.set(key, value, source, priority))

    def subscribe(self, key: str, callback: Callable[[str, Any, Any], Any]):
        self.subscribers[key] = callback

    async def listen(self):
        pubsub = self.r.pubsub()
        pubsub.subscribe(self.pub_channel)
        print("[State] Listening to state pub/sub channel...")

        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode()

            if "=" in data:
                key, val = data.split("=", 1)
                if key in self.subscribers:
                    old = self.get_value(key)
                    await self.subscribers[key](key, val, old)
