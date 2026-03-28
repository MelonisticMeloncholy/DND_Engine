"""
Tactician — combat rules enforcement agent.
Runs during combat turns to validate actions and advance initiative.
Pure Python — no LLM calls. Fast and deterministic.

D&D 5e action economy per turn:
  - 1 Action      (Attack, Cast, Dash, Disengage, Dodge, Help, Hide, Ready, Search, Use)
  - 1 Bonus Action (class features, certain spells)
  - 1 Reaction    (opportunity attack, Shield spell, Counterspell)
  - Movement      (speed in feet, default 30ft)
"""

from app.agents.base_agent import BaseAgent
from app.schemas.contracts import SocketMessage

# D&D 5e action economy rules
ACTION_ECONOMY = {
    "action":      "One per turn. Used for Attack, Cast a Spell, Dash, Dodge, Help, Hide, Ready, Search.",
    "bonus_action":"One per turn. Used for off-hand attack, certain spells, class features like Cunning Action.",
    "reaction":    "One per round. Used for Opportunity Attacks, Shield spell, Counterspell, Uncanny Dodge.",
    "movement":    "Up to your Speed (default 30ft) per turn. Can split before/after actions.",
}

AVAILABLE_ACTIONS = [
    {"id": "attack",     "name": "Attack",      "type": "action",      "desc": "Make one melee or ranged weapon attack."},
    {"id": "cast",       "name": "Cast Spell",  "type": "action",      "desc": "Cast a spell with a casting time of 1 action."},
    {"id": "dash",       "name": "Dash",        "type": "action",      "desc": "Double your movement speed this turn."},
    {"id": "disengage",  "name": "Disengage",   "type": "action",      "desc": "Your movement doesn't provoke opportunity attacks."},
    {"id": "dodge",      "name": "Dodge",       "type": "action",      "desc": "Attackers have disadvantage, you have advantage on DEX saves."},
    {"id": "help",       "name": "Help",        "type": "action",      "desc": "Give an ally advantage on their next ability check or attack."},
    {"id": "hide",       "name": "Hide",        "type": "action",      "desc": "Make a Stealth check to become hidden."},
    {"id": "ready",      "name": "Ready",       "type": "action",      "desc": "Prepare an action to trigger on a specific condition."},
    {"id": "search",     "name": "Search",      "type": "action",      "desc": "Devote attention to finding something (Perception or Investigation)."},
    {"id": "use_object", "name": "Use Object",  "type": "action",      "desc": "Interact with a second object or use a special object."},
    {"id": "offhand",    "name": "Off-hand Attack", "type": "bonus",   "desc": "Attack with your light off-hand weapon (no modifier to damage)."},
    {"id": "bonus_cast", "name": "Bonus Spell", "type": "bonus",       "desc": "Cast a spell with casting time of 1 bonus action."},
    {"id": "move",       "name": "Move",        "type": "movement",    "desc": "Move up to your speed. Can split before, during, after actions."},
    {"id": "opportunity","name": "Opportunity Attack", "type": "reaction", "desc": "When an enemy leaves your reach without Disengaging."},
]


class Tactician(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="Tactician")

    async def process(self, context: dict, message: SocketMessage) -> dict:
        """
        Called by ws_router when combat is active.
        Returns updated combat state after advancing the turn.
        """
        combat = context.get("combat", {})
        if not combat.get("active"):
            return {}

        return self.get_combat_state(context)

    def get_combat_state(self, context: dict) -> dict:
        """Return the full combat state dict for the frontend."""
        combat = context.get("combat", {})
        if not combat.get("active"):
            return {"active": False}

        combatants   = combat.get("combatants", [])
        turn_index   = combat.get("turn_index", 0)
        current      = combatants[turn_index] if combatants else None

        return {
            "active":        True,
            "round":         combat.get("round", 1),
            "combatants":    combatants,
            "current_turn":  current,
            "turn_index":    turn_index,
            "action_used":   combat.get("action_used", False),
            "bonus_used":    combat.get("bonus_used", False),
            "reaction_used": combat.get("reaction_used", False),
            "movement_used": combat.get("movement_used", 0),
            "available_actions": self._get_available_actions(combat),
        }

    def advance_turn(self, context: dict) -> dict:
        """
        Move to the next combatant in initiative order.
        Skips defeated enemies (hp_current <= 0).
        Increments round counter when initiative loops back to top.
        Returns updated combat state.
        """
        combat     = context.setdefault("combat", {})
        combatants = combat.get("combatants", [])
        if not combatants:
            return {}

        current_idx = combat.get("turn_index", 0)

        # Mark current combatant as no longer active
        combatants[current_idx]["is_active"] = False

        # Find next living combatant
        next_idx    = (current_idx + 1) % len(combatants)
        loops       = 0
        new_round   = False

        while loops < len(combatants):
            if next_idx < current_idx:
                new_round = True
            candidate = combatants[next_idx]
            if candidate.get("hp_current", 1) > 0:
                break
            next_idx = (next_idx + 1) % len(combatants)
            loops += 1

        combatants[next_idx]["is_active"] = True
        combat["turn_index"]   = next_idx
        combat["action_used"]  = False
        combat["bonus_used"]   = False
        combat["reaction_used"]= False
        combat["movement_used"]= 0

        if new_round:
            combat["round"] = combat.get("round", 1) + 1

        context["combat"] = combat
        return self.get_combat_state(context)

    def apply_enemy_damage(self, context: dict, enemy_id: str, damage: int) -> dict:
        """Apply damage to an enemy. Called by StateExtractor integration."""
        combat     = context.get("combat", {})
        combatants = combat.get("combatants", [])
        for c in combatants:
            if c["id"] == enemy_id:
                c["hp_current"] = max(0, c["hp_current"] - damage)
                break
        context["combat"] = combat
        return self.get_combat_state(context)

    def end_combat(self, context: dict) -> dict:
        """Called when StateExtractor detects combat_ended."""
        combat = context.get("combat", {})
        combat["active"] = False
        context["combat"] = combat
        return {"active": False}

    def _get_available_actions(self, combat: dict) -> list:
        """Return which actions are still available this turn."""
        action_used   = combat.get("action_used", False)
        bonus_used    = combat.get("bonus_used", False)
        reaction_used = combat.get("reaction_used", False)
        movement_used = combat.get("movement_used", 0)

        available = []
        for action in AVAILABLE_ACTIONS:
            t = action["type"]
            if t == "action"   and action_used:   continue
            if t == "bonus"    and bonus_used:     continue
            if t == "reaction" and reaction_used:  continue
            if t == "movement" and movement_used >= 30: continue
            available.append(action)

        return available