"""
Physician — pure Python logic agent (no LLM calls).
Tracks survival mechanics: hunger, thirst, fatigue, exhaustion.
Runs concurrently with StateExtractor after every stream_end.

Driven entirely by config.yaml tunables — no hardcoded values.
"""

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage

# Hunger level thresholds (morality_score style: 0=full, 100=starving)
_HUNGER_LABELS = [
    (0,  25,  "Sated"),
    (25, 55,  "Peckish"),
    (55, 80,  "Hungry"),
    (80, 101, "Starving"),
]

# D&D 5e Exhaustion consequences for reference (applied narratively by DM)
EXHAUSTION_EFFECTS = {
    1: "Disadvantage on ability checks",
    2: "Speed halved",
    3: "Disadvantage on attack rolls and saving throws",
    4: "HP maximum halved",
    5: "Speed reduced to 0",
    6: "Death",
}


def _hunger_label(score: int) -> str:
    for lo, hi, label in _HUNGER_LABELS:
        if lo <= score < hi:
            return label
    return "Starving"


class Physician(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="Physician")

    async def process(self, context: dict, message: SocketMessage) -> dict:
        """
        Advance survival mechanics by one turn.
        Returns a changed_fields dict (may be empty if nothing crossed a threshold).
        """
        char = context.setdefault("character", {})
        changed: dict = {}

        # ── Hunger ─────────────────────────────────────────────────────────
        hunger_score: int = char.get("hunger_score", 0)
        hunger_score = min(100, hunger_score + settings.HUNGER_INCREMENT)
        char["hunger_score"] = hunger_score

        new_label = _hunger_label(hunger_score)
        old_label = char.get("hunger_level", "Sated")

        if new_label != old_label:
            char["hunger_level"] = new_label
            changed["hunger_level"] = new_label

        # ── Exhaustion from starvation ─────────────────────────────────────
        if hunger_score >= settings.EXHAUSTION_THRESHOLD:
            effects: list = char.setdefault("status_effects", [])
            if "Exhaustion" not in effects:
                effects.append("Exhaustion")
                changed["status_effects"] = effects[:]
                changed["_physician_note"] = (
                    "Starvation has set in. The character gains one level of Exhaustion."
                )

        # ── Days survived counter ──────────────────────────────────────────
        days = char.get("days_survived", 0) + 1
        char["days_survived"] = days
        # Only push days_survived every 10 turns to avoid noise
        if days % 10 == 0:
            changed["days_survived"] = days

        return changed

    def apply_rest(self, context: dict, rest_type: str) -> dict:
        """
        Call this when the DM narrates a rest event.
        rest_type: "short" or "long"
        Returns changed_fields dict.
        """
        char = context.setdefault("character", {})
        changed: dict = {}

        if rest_type == "long":
            # Long rest: full HP restore, hunger relief, clear exhaustion
            hp_max = char.get("hp_max", 10)
            char["hp_current"] = hp_max
            char["hunger_score"] = max(0, char.get("hunger_score", 0) - 40)
            char["hunger_level"] = _hunger_label(char["hunger_score"])

            effects: list = char.get("status_effects", [])
            if "Exhaustion" in effects:
                effects.remove("Exhaustion")
            char["status_effects"] = effects

            changed = {
                "hp_current": hp_max,
                "hunger_level": char["hunger_level"],
                "status_effects": effects[:],
                "_physician_note": "Long rest taken. HP fully restored.",
            }

        elif rest_type == "short":
            char["hunger_score"] = max(0, char.get("hunger_score", 0) - 15)
            char["hunger_level"] = _hunger_label(char["hunger_score"])
            changed = {
                "hunger_level": char["hunger_level"],
                "_physician_note": "Short rest taken.",
            }

        return changed