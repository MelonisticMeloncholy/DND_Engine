"""
State Extractor — background agent (Ollama / Llama 3.2 3B).
Parses the DM's narrative prose into a structured JSON delta.
Runs AFTER stream_end as a fire-and-forget task — never blocks the player.

Extracts:
  - HP changes (damage taken, healing received)
  - Inventory changes (items gained, items lost)
  - Gold changes
  - New status effects / conditions cleared
"""

import asyncio
import json

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage

_SYSTEM_PROMPT = """
You are a precise D&D 5e game state parser. Read the Dungeon Master's narrative and extract concrete mechanical changes to the player character.

Return ONLY a valid JSON object with these keys (use null if nothing changed):
- "hp_change": integer or null (negative = damage, positive = healing)
- "hp_set": integer or null (only if HP is set to an exact value)
- "items_gained": list of strings or null
- "items_lost": list of strings or null
- "gold_change": float or null (negative = spent, positive = found)
- "status_added": list of strings or null
- "status_removed": list of strings or null
- "notes": string or null (brief mechanical note, otherwise null)

CRITICAL RULES:
- Only extract things EXPLICITLY stated. Never infer or guess.
- If the narrative describes an action but mentions no numbers or items, return all nulls.
- Return ONLY valid JSON. No markdown formatting, no conversational text.

=== EXAMPLES ===

Narrative: "The goblin's arrow strikes your shoulder. You take 6 piercing damage. You drop your Torch in the mud, losing it forever."
{"hp_change": -6, "hp_set": null, "items_gained": null, "items_lost": ["Torch"], "gold_change": null, "status_added": null, "status_removed": null, "notes": null}

Narrative: "You hand the merchant 15 gold pieces. He smiles and hands you a Healing Potion and a rope."
{"hp_change": null, "hp_set": null, "items_gained": ["Healing Potion", "Rope"], "items_lost": null, "gold_change": -15.0, "status_added": null, "status_removed": null, "notes": null}

Narrative: "The trap triggers, releasing a cloud of toxic gas. You are now Poisoned. The DM notes you feel weak."
{"hp_change": null, "hp_set": null, "items_gained": null, "items_lost": null, "gold_change": null, "status_added": ["Poisoned"], "status_removed": null, "notes": "Player triggered a gas trap."}

Narrative: "You stare out across the Ashen Wastes. The wind howls, carrying the scent of sulfur. You take a step forward."
{"hp_change": null, "hp_set": null, "items_gained": null, "items_lost": null, "gold_change": null, "status_added": null, "status_removed": null, "notes": null}

=== END EXAMPLES ===

Analyze the following narrative and output the JSON:
"""


class StateExtractor(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="StateExtractor")

    async def process(self, context: dict, message: SocketMessage) -> dict | None:
        """
        Parse the DM's full narrative text and return a state delta dict.
        Returns None if Ollama fails or nothing changed.
        """
        dm_text = message.content
        if not dm_text or len(dm_text) < 20:
            return None

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
            print(f"\n--- STATE EXTRACTOR RAW OUTPUT ---")
            print(raw_text)
            print(f"----------------------------------\n")
            delta = json.loads(raw)

            # Check if anything actually changed — skip empty deltas
            has_change = any(
                v is not None and v != [] and v != 0
                for v in delta.values()
            )
            return delta if has_change else None

        except Exception as exc:
            print(f"[StateExtractor] Ollama error: {exc}")
            return None

    def apply_delta(self, context: dict, delta: dict) -> dict:
        """
        Mutate session_context['character'] in-place with the extracted delta.
        Returns a 'changed_fields' dict containing only the keys that changed
        (used for the minimal WebSocket push to the frontend).
        """
        char = context.setdefault("character", {})
        changed: dict = {}

        # ── HP ─────────────────────────────────────────────────────────────
        if delta.get("hp_set") is not None:
            char["hp_current"] = max(0, int(delta["hp_set"]))
            changed["hp_current"] = char["hp_current"]

        elif delta.get("hp_change") is not None:
            old_hp = char.get("hp_current", char.get("hp_max", 10))
            hp_max = char.get("hp_max", old_hp)
            new_hp = max(0, min(old_hp + int(delta["hp_change"]), hp_max))
            char["hp_current"] = new_hp
            changed["hp_current"] = new_hp
            # Flag permadeath check for the ws_router to handle
            if new_hp == 0:
                changed["_zero_hp"] = True

        # ── Inventory ──────────────────────────────────────────────────────
        inventory: list = char.setdefault("inventory", [])

        if delta.get("items_gained"):
            for item in delta["items_gained"]:
                if item not in inventory:
                    inventory.append(item)
            changed["inventory"] = inventory[:]

        if delta.get("items_lost"):
            for item in delta["items_lost"]:
                if item in inventory:
                    inventory.remove(item)
            changed["inventory"] = inventory[:]

        # ── Gold ───────────────────────────────────────────────────────────
        if delta.get("gold_change") is not None:
            old_gold = char.get("gold_pieces", 0.0)
            new_gold = max(0.0, old_gold + float(delta["gold_change"]))
            char["gold_pieces"] = new_gold
            changed["gold_pieces"] = new_gold

        # ── Status effects ─────────────────────────────────────────────────
        effects: list = char.setdefault("status_effects", [])

        if delta.get("status_added"):
            for s in delta["status_added"]:
                if s not in effects:
                    effects.append(s)
            changed["status_effects"] = effects[:]

        if delta.get("status_removed"):
            for s in delta["status_removed"]:
                if s in effects:
                    effects.remove(s)
            changed["status_effects"] = effects[:]

        return changed