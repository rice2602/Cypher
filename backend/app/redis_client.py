from redis import asyncio as aioredis
from app.config import settings

redis_client = aioredis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=20,
    retry_on_timeout=True,
    socket_keepalive=True,
    socket_connect_timeout=5,
)
