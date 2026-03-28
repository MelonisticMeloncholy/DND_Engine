"""
State Extractor — background agent (Ollama / Llama 3.2 1B).
Now also detects combat start/end and enemy stat extraction.
"""

import asyncio
import json

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage

_SYSTEM_PROMPT = """
You are a precise D&D 5e game state parser. Read the Dungeon Master's narrative and extract concrete mechanical changes.

Return ONLY a valid JSON object with these keys (use null if nothing changed):
- "hp_change": integer or null (negative = damage, positive = healing)
- "hp_set": integer or null (only if HP is set to an exact value)
- "items_gained": list of strings or null
- "items_lost": list of strings or null
- "gold_change": float or null (negative = spent, positive = found)
- "status_added": list of strings or null
- "status_removed": list of strings or null
- "combat_started": boolean (true ONLY if combat explicitly begins this turn)
- "combat_ended": boolean (true ONLY if combat explicitly ends this turn)
- "enemies": list of objects or null (ONLY when combat_started is true)
  Each enemy object: {"name": string, "hp": integer, "max_hp": integer, "ac": integer}
- "notes": string or null

CRITICAL RULES:
- Only extract things EXPLICITLY stated. Never infer or guess.
- combat_started = true only when the narrative describes initiative being rolled,
  a creature attacking, or combat explicitly beginning.
- combat_ended = true only when enemies are defeated, flee, or surrender.
- For enemies, estimate HP from CR if not stated (goblin=7, bandit=11, orc=15, troll=84).
- Return ONLY valid JSON. No markdown. No explanation.

=== EXAMPLES ===

Narrative: "The goblin lunges at you, rusty blade gleaming. Roll for initiative!"
{"hp_change": null, "hp_set": null, "items_gained": null, "items_lost": null,
 "gold_change": null, "status_added": null, "status_removed": null,
 "combat_started": true, "combat_ended": false,
 "enemies": [{"name": "Goblin", "hp": 7, "max_hp": 7, "ac": 15}],
 "notes": null}

Narrative: "The bandit falls to the ground, clutching his chest. The threat is over."
{"hp_change": null, "hp_set": null, "items_gained": null, "items_lost": null,
 "gold_change": null, "status_added": null, "status_removed": null,
 "combat_started": false, "combat_ended": true, "enemies": null, "notes": null}

Narrative: "You press the torch against your arm. You take 1 fire damage."
{"hp_change": -1, "hp_set": null, "items_gained": null, "items_lost": null,
 "gold_change": null, "status_added": null, "status_removed": null,
 "combat_started": false, "combat_ended": false, "enemies": null, "notes": null}

=== END EXAMPLES ===

Analyze the following narrative and output the JSON:
"""


class StateExtractor(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="StateExtractor")

    async def process(self, context: dict, message: SocketMessage) -> dict | None:
        dm_text = message.content
        if not dm_text or len(dm_text) < 20:
            return None

        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": f"DM Narrative:\n{dm_text}"},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            raw = response["message"]["content"]
            print(f"\n--- STATE EXTRACTOR RAW OUTPUT ---")
            print(raw)
            print(f"----------------------------------\n")
            delta = json.loads(raw)

            has_change = any(
                v is not None and v != [] and v != 0 and v is not False
                for v in delta.values()
            )
            return delta if has_change else None

        except Exception as exc:
            print(f"[StateExtractor] Ollama error: {exc}")
            return None

    def apply_delta(self, context: dict, delta: dict) -> dict:
        char    = context.setdefault("character", {})
        combat  = context.setdefault("combat", {})
        changed: dict = {}

        # ── HP ────────────────────────────────────────────────────────────
        if delta.get("hp_set") is not None:
            char["hp_current"] = max(0, int(delta["hp_set"]))
            changed["hp_current"] = char["hp_current"]

        elif delta.get("hp_change") is not None:
            old_hp = char.get("hp_current", char.get("hp_max", 10))
            hp_max = char.get("hp_max", old_hp)
            new_hp = max(0, min(old_hp + int(delta["hp_change"]), hp_max))
            char["hp_current"] = new_hp
            changed["hp_current"] = new_hp
            if new_hp == 0:
                changed["_zero_hp"] = True

        # ── Inventory ─────────────────────────────────────────────────────
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

        # ── Gold ──────────────────────────────────────────────────────────
        if delta.get("gold_change") is not None:
            old_gold = char.get("gold_pieces", 0.0)
            new_gold = max(0.0, old_gold + float(delta["gold_change"]))
            char["gold_pieces"] = new_gold
            changed["gold_pieces"] = new_gold

        # ── Status effects ────────────────────────────────────────────────
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

        # ── Combat state ──────────────────────────────────────────────────
        if delta.get("combat_started"):
            enemies = delta.get("enemies") or []
            player_initiative = _roll_initiative(
                char.get("ability_scores", {}).get("dex", 10)
            )
            # Build combatant list — player first, then enemies with rolled initiatives
            combatants = [{
                "id":         "player",
                "name":       char.get("name", "You"),
                "initiative": player_initiative,
                "hp_current": char.get("hp_current", 10),
                "hp_max":     char.get("hp_max", 10),
                "ac":         char.get("armor_class", 10),
                "is_player":  True,
                "is_active":  False,
            }]
            for enemy in enemies:
                combatants.append({
                    "id":         enemy["name"].lower().replace(" ", "_"),
                    "name":       enemy["name"],
                    "initiative": _roll_initiative(10),  # average DEX
                    "hp_current": enemy.get("hp", 10),
                    "hp_max":     enemy.get("max_hp", enemy.get("hp", 10)),
                    "ac":         enemy.get("ac", 12),
                    "is_player":  False,
                    "is_active":  False,
                })

            # Sort by initiative descending, mark first as active
            combatants.sort(key=lambda c: c["initiative"], reverse=True)
            if combatants:
                combatants[0]["is_active"] = True

            combat.update({
                "active":      True,
                "round":       1,
                "combatants":  combatants,
                "turn_index":  0,
                "action_used":    False,
                "bonus_used":     False,
                "reaction_used":  False,
                "movement_used":  0,   # feet used this turn
            })
            context["combat"] = combat
            changed["combat"] = combat
            changed["_combat_started"] = True

        if delta.get("combat_ended"):
            combat["active"] = False
            context["combat"] = combat
            changed["combat"] = combat
            changed["_combat_ended"] = True

        return changed


def _roll_initiative(dex_score: int) -> int:
    import random
    dex_mod = (dex_score - 10) // 2
    return random.randint(1, 20) + dex_mod  