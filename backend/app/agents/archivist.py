"""
Archivist — background agent (Ollama / Llama 1B).
Every ARCHIVIST_INTERVAL turns, compresses the raw narrative history
into a dense paragraph and saves it to ChromaDB.

This is the solution to context rot — instead of sending 50 raw turns
to Gemini, we send 4 recent turns + the compressed archive paragraph.
The DM gets full narrative continuity without token explosion.
"""

import asyncio
import json

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage
from app.db.chroma_client import chroma_service
from app.db import sqlite_session

_COMPRESS_SYSTEM = """
You are a narrative archivist for a D&D campaign.
Given a series of recent turns, compress them into ONE dense paragraph
of 3-5 sentences that captures:
- Key events and outcomes
- Important NPCs encountered
- Items gained or lost
- Any moral decisions or consequences
- Current location and situation

Write in past tense, third person. Be specific — names, places, outcomes.
No filler phrases. Every sentence must contain information.
Output ONLY the paragraph. No preamble, no labels, no markdown.
"""


class Archivist(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="Archivist")

    async def process(self, context: dict, message: SocketMessage) -> dict:
        """
        Check if it's time to archive. If so, compress and store.
        Returns empty dict — Archivist never pushes to the frontend.
        """
        session_id = context.get("session_id", "")
        turn_count = context.get("turn_count", 0)

        if not session_id:
            return {}

        # Only run every ARCHIVIST_INTERVAL turns
        if turn_count % settings.ARCHIVIST_INTERVAL != 0:
            return {}

        await self._compress_and_store(session_id, turn_count, context)
        return {}

    async def _compress_and_store(
        self,
        session_id: str,
        turn_count: int,
        context: dict,
    ) -> None:
        try:
            # Fetch the last N turns from SQLite
            recent_turns = await sqlite_service.get_recent_turns(
                session_id,
                limit=settings.ARCHIVIST_INTERVAL,
            )
            if not recent_turns:
                return

            # Build the raw text to compress
            raw_log = "\n\n".join(
                f"Player: {t['player_input']}\nDM: {t['dm_response']}"
                for t in recent_turns
            )

            # Compress via Ollama
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _COMPRESS_SYSTEM},
                    {"role": "user",   "content": raw_log[:3000]},  # cap input
                ],
                options={"temperature": 0.3},
            )
            compressed = response["message"]["content"].strip()

            if not compressed:
                return

            # Store in ChromaDB for long-term recall
            chroma_service.store_memory(
                session_id=session_id,
                turn_number=turn_count,
                compressed_text=compressed,
            )

            # Also prepend to narrative_history so DM gets it next turn
            history: list = context.setdefault("narrative_history", [])
            archive_entry = f"[ARCHIVED — Turns {turn_count - settings.ARCHIVIST_INTERVAL + 1}-{turn_count}]: {compressed}"

            # Keep only recent raw beats, replacing old ones with archive entry
            recent_raw = history[-(settings.DM_HISTORY_WINDOW):]
            context["narrative_history"] = [archive_entry] + recent_raw

            print(f"[Archivist] Compressed turns {turn_count - settings.ARCHIVIST_INTERVAL + 1}-{turn_count} for session {session_id[:8]}")

        except Exception as exc:
            print(f"[Archivist] Error: {exc}")