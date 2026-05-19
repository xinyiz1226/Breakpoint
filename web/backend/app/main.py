from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, projects, segments, export
from app.ws.progress import progress_websocket


def create_app() -> FastAPI:
    app = FastAPI(title="Breakpoint API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(segments.router)
    app.include_router(export.router)

    @app.websocket("/api/ws/progress/{task_id}")
    async def ws_progress(websocket: WebSocket, task_id: str):
        await progress_websocket(websocket, task_id)

    return app


app = create_app()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
