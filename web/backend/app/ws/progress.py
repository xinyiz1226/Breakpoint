import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.config import settings


async def progress_websocket(websocket: WebSocket, task_id: str):
    await websocket.accept()
    redis = Redis.from_url(settings.redis_url)

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"progress:{task_id}")

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"].decode())

            task_status = await redis.get(f"task_status:{task_id}")
            if task_status and task_status.decode() in ("complete", "failed"):
                await websocket.send_text(json.dumps({"type": "done", "status": task_status.decode()}))
                break

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"progress:{task_id}")
        await redis.close()
