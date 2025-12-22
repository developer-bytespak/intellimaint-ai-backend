import redis
import os

print("🔥 redis_client.py LOADED")


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

try:
    redis_client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True
    )
    redis_client.ping()
    print("[redis] connected")
except Exception as e:
    print("[redis] connection failed", e)
    redis_client = None
