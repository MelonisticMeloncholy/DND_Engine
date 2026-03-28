"""
Central configuration — single source of truth for ALL tunables.
Loaded once via lru_cache. Never hardcode values anywhere else.

Usage:
    from app.core.config import settings
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root




class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    # ── ChromaDB ──────────────────────────────────────────────────────────────────
    # Native path for development. Docker volume mount path for production.
    CHROMA_PERSIST_PATH: str = "./data/chromadb"

    # How many chunks to retrieve per collection per query
    RAG_TOP_K: int = 3

    # How many turns between Archivist compressions
    ARCHIVIST_INTERVAL: int = 10

    # ── Gemini ────────────────────────────────────────────────────────────────
    # Add multiple comma-separated keys to multiply your effective RPM.
    # Free tier: 15 RPM per key. 3 keys → 45 RPM effective.
    # Get keys: https://aistudio.google.com/app/apikey
    GEMINI_API_KEYS: str
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Free tier hard limit is 15 RPM. We cap at 14 to leave a safety buffer.
    GEMINI_RPM_LIMIT: int = 14

    # Max tokens Gemini generates per response. DO NOT leave at default (8192).
    GEMINI_MAX_OUTPUT_TOKENS: int = 1024

    # Temperature: higher = more creative DM prose
    DM_TEMPERATURE: float = 0.85

    # How many recent narrative turns to send as chat history.
    # CRITICAL: sending full history is the #1 cause of token exhaustion.
    # 4 turns = enough narrative continuity, minimal token cost.
    DM_HISTORY_WINDOW: int = 4

    # Prompt compression budgets (in tokens; 1 token ≈ 4 chars)
    GEMINI_SYSTEM_PROMPT_TOKEN_BUDGET: int = 600   # ~2400 chars
    GEMINI_USER_PROMPT_TOKEN_BUDGET: int = 500     # ~2000 chars

    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:1b"
    OLLAMA_TIMEOUT_S: int = 30

    # ── Game Mechanics ────────────────────────────────────────────────────────
    # All difficulty/balance knobs live here. Change these, not the agent code.
    DIFFICULTY: Literal["easy", "normal", "hard", "nightmare"] = "normal"
    TENSION_INCREMENT: int = 5       # added per combat/danger turn
    TENSION_DECAY: int = 2           # removed per peaceful turn
    HUNGER_INCREMENT: int = 3        # per turn without eating
    EXHAUSTION_THRESHOLD: int = 80   # hunger level that triggers Exhaustion
    DAMAGE_SCALE: float = 1.0        # multiply all incoming enemy damage by this

    @field_validator("GEMINI_API_KEYS")
    @classmethod
    def at_least_one_key(cls, v: str) -> str:
        keys = [k.strip() for k in v.split(",") if k.strip()]
        if not keys:
            raise ValueError("GEMINI_API_KEYS must contain at least one API key.")
        return v

    def get_gemini_keys(self) -> list[str]:
        """Return the list of individual API keys."""
        return [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience singleton — import this everywhere
settings = get_settings()