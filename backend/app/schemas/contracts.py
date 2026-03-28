"""
Core data contracts — Pydantic schemas shared across the entire backend.
The frontend's useGameSocket.js reads these shapes directly.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CharacterSheet(BaseModel):
    name: str = Field(default="Valren")
    level: int = Field(default=1, ge=1, le=20)
    hp_current: int = Field(default=10)
    hp_max: int = Field(default=10)
    armor_class: int = Field(default=10)
    gold_pieces: float = Field(default=0.0)
    inventory: List[str] = Field(default_factory=list)
    status_effects: List[str] = Field(default_factory=list)
    hunger_level: Literal["Sated", "Peckish", "Hungry", "Starving"] = "Sated"
    morality_score: int = Field(default=50, ge=0, le=100)


class WorldState(BaseModel):
    current_location: str = Field(default="The Forgotten Realm")
    time_of_day: Literal["Dawn", "Noon", "Dusk", "Midnight"] = "Dawn"
    tension_level: int = Field(default=1, ge=1, le=10)
    active_npcs: List[str] = Field(default_factory=list)
    local_bounties: List[Dict[str, str]] = Field(default_factory=list)


class SocketMessage(BaseModel):
    """
    The single envelope for ALL WebSocket traffic (both directions).

    message_type values:
      "narrative"     — DM story text (may be a streaming chunk)
      "system_alert"  — pipeline signals: "stream_start", "stream_end"
      "state_update"  — character/world state delta
      "dice_roll_request" — DM wants a player roll
      "error"         — something went wrong (non-fatal unless metadata.fatal=True)

    metadata.chunk = True means this is a partial streaming token.
    The frontend assembles chunks into the full narrative bubble.
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sender: Literal["User", "Bouncer", "IntentRouter", "RulesLawyer", "DM", "System"]
    message_type: Literal[
        "narrative",
        "system_alert",
        "state_update",
        "dice_roll_request",
        "session_init",
        "error",
    ]
    content: str = Field(..., description="Text payload or signal keyword")
    metadata: Optional[Dict] = Field(default=None)