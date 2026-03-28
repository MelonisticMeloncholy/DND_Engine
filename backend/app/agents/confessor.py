"""
Confessor — background agent (Ollama / Llama 3.2 3B).
Tracks morality shifts and NPC relationship changes from DM narrative.
Runs concurrently with StateExtractor after every stream_end.

Morality score: 0 = absolute evil, 100 = absolute good (starts at 50).
Relationship scores: -100 (hostile) to +100 (allied) per NPC/faction.
"""

import asyncio
import json

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage

_SYSTEM_PROMPT = """
You are a D&D moral alignment and relationship tracker.
Read the Dungeon Master's narrative and extract any shifts in player morality
or changes in NPC/faction relationships.

Return ONLY a valid JSON object with these keys (use null if nothing changed):
- "morality_change": integer or null
    Positive = good act (helped someone: +5, saved a life: +15, major sacrifice: +25)
    Negative = evil act (stole: -5, killed innocent: -20, atrocity: -40)
- "morality_reason": string or null (one sentence explaining the shift)
- "relationship_changes": list of objects or null
    Each object: {"npc_name": string, "change": integer, "reason": string}
    change range: -30 to +30 per event
- "notable_act": string or null
    A short memorable description of a morally significant action for the log.

Rules:
- Only extract EXPLICIT moral actions, not ambiguous ones.
- Routine combat against monsters = no morality change.
- Killing a surrendered enemy = -15. Sparing them = +5.
- Return ONLY the JSON object. No markdown. No explanation.

Example:
{"morality_change": -15, "morality_reason": "Executed a surrendered bandit in cold blood.",
 "relationship_changes": [{"npc_name": "Guard Captain Maren", "change": -20,
 "reason": "Witnessed the execution"}],
 "notable_act": "Executed surrendered bandit at the crossroads."}
"""


class Confessor(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="Confessor")

    async def process(self, context: dict, message: SocketMessage) -> dict:
        """
        Detect morality/relationship shifts in the DM's narrative.
        Returns a changed_fields dict (may be empty).
        """
        dm_text = message.content
        if not dm_text or len(dm_text) < 30:
            return {}

        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"DM Narrative:\n{dm_text}"},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            raw = response["message"]["content"]
            result = json.loads(raw)
        except Exception as exc:
            print(f"[Confessor] Ollama error: {exc}")
            return {}

        changed: dict = {}
        char = context.setdefault("character", {})
        world = context.setdefault("world", {})

        # ── Morality score ─────────────────────────────────────────────────
        if result.get("morality_change") is not None:
            old = char.get("morality_score", 50)
            new = max(0, min(100, old + int(result["morality_change"])))
            char["morality_score"] = new
            changed["morality_score"] = new

            if result.get("morality_reason"):
                changed["_morality_reason"] = result["morality_reason"]

        # ── Notable acts log (capped at 20 entries) ────────────────────────
        if result.get("notable_act"):
            acts: list = char.setdefault("notable_acts", [])
            acts.append(result["notable_act"])
            if len(acts) > 20:
                char["notable_acts"] = acts[-20:]
            changed["notable_acts"] = char["notable_acts"]

        # ── NPC/Faction relationships ──────────────────────────────────────
        if result.get("relationship_changes"):
            relationships: dict = world.setdefault("relationships", {})
            updated_rels: dict = {}

            for rel in result["relationship_changes"]:
                name = rel.get("npc_name", "Unknown")
                delta = int(rel.get("change", 0))
                current = relationships.get(name, 0)
                relationships[name] = max(-100, min(100, current + delta))
                updated_rels[name] = relationships[name]

            if updated_rels:
                changed["relationships"] = updated_rels

        return changed