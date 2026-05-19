from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, projects, segments


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

    return app


app = create_app()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
