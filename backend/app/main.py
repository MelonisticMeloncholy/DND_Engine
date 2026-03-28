import app.core.env_patch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ws_router import router as websocket_router
from pydantic import BaseModel
from typing import Any

app = FastAPI(
    title="Chronicles of the Forgotten Realm Engine",
    version="0.1.0",
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


# In-memory session store (replaced by SQLite in a later step)
_pending_sessions: dict[str, dict] = {}


@app.post("/api/session/create")
async def create_session(req: SessionCreateRequest):
    """
    Called by SessionZero on Begin.
    Stores character + world so ws_router can seed session_context
    on the next WebSocket connection.
    """
    import uuid
    session_id = str(uuid.uuid4())
    _pending_sessions[session_id] = {
        "character": req.character,
        "world":     req.world,
    }
    return {"session_id": session_id, "status": "ready"}


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