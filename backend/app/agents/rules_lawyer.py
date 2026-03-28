"""
Rules Lawyer — local Ollama + ChromaDB RAG agent.
Now has a real D&D 5e knowledge base behind it instead of guessing.

Two-phase process per player action:
  Phase 1: ChromaDB semantic search across all 5 collections (no LLM, instant)
  Phase 2: Ollama distills the raw chunks into a clean structured summary
            for the DM prompt (keeps the injection concise)

If ChromaDB has no relevant results, falls back to Ollama-only mode.
If Ollama fails, returns the raw ChromaDB chunks directly (still useful).
"""

import asyncio
import json

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage
from app.db.chroma_client import chroma_service

_DISTILL_SYSTEM = """
You are a D&D 5e rules assistant. You have been given raw SRD excerpts
relevant to a player's action. Distill them into a clean, concise rules
summary for the Dungeon Master.

Format your response as JSON with these keys:
- "applicable_rules": string (2-3 sentences max — the most relevant rule)
- "skill_check": string or null (e.g. "Dexterity (Stealth) DC 14")
- "damage_dice": string or null (e.g. "8d6 fire" — only if relevant)
- "saving_throw": string or null (e.g. "Constitution DC 13")
- "special_notes": string or null (one short note if something unusual applies)

Rules:
- Be concise. The DM will read this mid-generation.
- Only include fields that are genuinely relevant to the action.
- If no check is needed, set skill_check to null.
- Return ONLY valid JSON. No markdown. No explanation.
"""


def _format_rules_for_dm(distilled: dict, raw_chunks: str) -> str:
    """
    Convert distilled JSON into a compact string for DM prompt injection.
    Falls back to raw chunks if distillation produced nothing useful.
    """
    parts: list[str] = []

    if distilled.get("applicable_rules"):
        parts.append(f"Rule: {distilled['applicable_rules']}")
    if distilled.get("skill_check"):
        parts.append(f"Check: {distilled['skill_check']}")
    if distilled.get("damage_dice"):
        parts.append(f"Damage: {distilled['damage_dice']}")
    if distilled.get("saving_throw"):
        parts.append(f"Save: {distilled['saving_throw']}")
    if distilled.get("special_notes"):
        parts.append(f"Note: {distilled['special_notes']}")

    if parts:
        return "\n".join(parts)

    # Fallback: trim raw chunks to first 800 chars to avoid token bloat
    return raw_chunks[:800] if raw_chunks else ""


class RulesLawyer(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="RulesLawyer")

    async def process(self, context: dict, message: SocketMessage) -> str:
        """
        Returns a compact rules string for injection into the DM prompt.
        Empty string if nothing relevant found and Ollama fails.
        """
        player_action = message.content

        # ── Phase 1: ChromaDB semantic search (no LLM, ~50ms) ────────────
        raw_chunks = await asyncio.to_thread(
            chroma_service.query_all_game_collections,
            player_action,
            2,  # top_k per collection
        )

        if not raw_chunks:
            # ChromaDB empty or not ingested yet — fall back to Ollama-only
            return await self._ollama_only_fallback(player_action)

        # ── Phase 2: Ollama distillation (makes chunks DM-prompt friendly) ─
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _DISTILL_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Player action: {player_action}\n\n"
                            f"Relevant SRD excerpts:\n{raw_chunks[:2000]}"
                        ),
                    },
                ],
                format="json",
                options={"temperature": 0.0},
            )
            distilled = json.loads(response["message"]["content"])
            return _format_rules_for_dm(distilled, raw_chunks)

        except Exception as exc:
            print(f"[RulesLawyer] Ollama distillation failed, using raw chunks: {exc}")
            return raw_chunks[:800]

    async def _ollama_only_fallback(self, player_action: str) -> str:
        """
        Used when ChromaDB has no content yet.
        Pure Ollama rules lookup — same as the old implementation.
        """
        _FALLBACK_SYSTEM = """
        You are a D&D 5e rules expert.
        Given a player action, identify the relevant mechanics.
        Return JSON: {"skill_check": string or null, "dc": integer or null,
        "relevant_rule": string, "damage_dice": string or null}
        Return ONLY JSON. No markdown.
        """
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _FALLBACK_SYSTEM},
                    {"role": "user",   "content": f"Player action: {player_action}"},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            result = json.loads(response["message"]["content"])
            parts  = []
            if result.get("relevant_rule"):
                parts.append(f"Rule: {result['relevant_rule']}")
            if result.get("skill_check") and result.get("dc"):
                parts.append(f"Check: {result['skill_check']} DC {result['dc']}")
            if result.get("damage_dice"):
                parts.append(f"Damage: {result['damage_dice']}")
            return "\n".join(parts)
        except Exception as exc:
            print(f"[RulesLawyer] Ollama fallback failed: {exc}")
            return ""