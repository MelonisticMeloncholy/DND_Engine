import app.core.env_patch  # noqa: F401 — must be first

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ws_router import router as websocket_router
from app.db import sqlite_session
from pydantic import BaseModel
from typing import Any


@asynccontextmanager
async def lifespan(app: FastAPI):
    await sqlite_session.init_db()
    print("[DB] SQLite initialised.")
    yield


app = FastAPI(
    title="Chronicles of the Forgotten Realm Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)


class SessionCreateRequest(BaseModel):
    character: dict[str, Any]
    world:     dict[str, Any]


@app.post("/api/session/create")
async def create_session(req: SessionCreateRequest):
    import uuid
    session_id = str(uuid.uuid4())
    await sqlite_session.create_session(session_id, req.character, req.world)
    return {"session_id": session_id, "status": "ready"}


@app.get("/api/sessions")
async def get_sessions():
    """Save slot list for the start menu."""
    sessions = await sqlite_session.list_sessions()
    return {"sessions": sessions}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    await sqlite_session.delete_session(session_id)
    return {"status": "deleted"}


@app.get("/health")
async def health():
    return {"status": "The Forgotten Realm is online."}


@app.get("/health/rag")
async def rag_health():
    from app.services.chroma_service import chroma_service
    stats = chroma_service.collection_stats()
    return {
        "status": "ready" if sum(stats.values()) > 100 else "empty",
        "collections": stats,
    }