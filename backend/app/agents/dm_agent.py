"""
DM Agent — the only agent that uses Gemini.
Responsibilities:
  - Compose a compressed system prompt from CharacterSheet + WorldState
  - Window the narrative history to DM_HISTORY_WINDOW turns
  - Stream tokens via GeminiClient
  - Yield SocketMessage envelopes for the WebSocket router

This agent is ALWAYS called LAST in the critical path, after:
  Bouncer → IntentRouter → RulesLawyer → DMAgent
"""

import time
from typing import AsyncGenerator

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage
from app.services.gemini_client import gemini_client


# ── System Prompt Template ────────────────────────────────────────────────────
# Keep this SHORT — it gets compressed to GEMINI_SYSTEM_PROMPT_TOKEN_BUDGET.
# Every word here costs tokens on every single turn.

_SYSTEM_TEMPLATE = """\
You are Aldrathas, a merciless but fair D&D 5e Dungeon Master.
Campaign: Chronicles of the Forgotten Realm.
Tone: grimdark, second-person present tense, highly atmospheric.
Rules: enforce 5e mechanics strictly. Never break the fourth wall.
Never roll dice yourself — describe outcomes narratively only.
Never make decisions for the player.
Always end your response with an implicit or explicit prompt for the player's next action.
Keep responses to 2-4 paragraphs max.

CRITICAL RULE: When dealing damage or changing gold, NEVER output dice formulas (e.g., do not say 'You take 1d4 damage').
You must resolve the roll yourself behind the screen and output the final concrete integer (e.g., 'You take 3 fire damage').
The automated state-tracker cannot process dice notation.

Current state:
- Location: {location}
- Time: {time_of_day}
- Tension: {tension}/10
- Character: {char_name}, Level {level}, {hp_current}/{hp_max} HP
- Status effects: {status_effects}
- Hunger: {hunger}
"""


class DMAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="DM")

    def _build_system_prompt(self, context: dict) -> str:
        """
        Build the system prompt from context dict.
        Falls back gracefully if character/world data isn't present yet.
        """
        char = context.get("character", {})
        world = context.get("world", {})

        return _SYSTEM_TEMPLATE.format(
            location=world.get("current_location", "Unknown"),
            time_of_day=world.get("time_of_day", "Unknown"),
            tension=world.get("tension_level", 1),
            char_name=char.get("name", "Adventurer"),
            level=char.get("level", 1),
            hp_current=char.get("hp_current", "?"),
            hp_max=char.get("hp_max", "?"),
            status_effects=", ".join(char.get("status_effects", [])) or "none",
            hunger=char.get("hunger_level", "Sated"),
        )

    def _build_user_prompt(self, message: SocketMessage, rules_context: str) -> str:
        """
        Combine the player's action with injected rules context.
        Rules context comes from RulesLawyer — already a short JSON snippet.
        """
        if rules_context:
            return (
                f"[RELEVANT 5E MECHANICS]\n{rules_context}\n\n"
                f"[PLAYER ACTION]\n{message.content}\n\n"
                "Respond as the DM."
            )
        return f"[PLAYER ACTION]\n{message.content}\n\nRespond as the DM."

    def _get_history_window(self, context: dict) -> list[str]:
        """
        Return only the last N narrative beats.
        DM_HISTORY_WINDOW (default 4) prevents history from bloating token usage.
        """
        history: list[str] = context.get("narrative_history", [])
        window = settings.DM_HISTORY_WINDOW
        return history[-window:] if history else []

    async def process(
        self, context: dict, message: SocketMessage
    ) -> AsyncGenerator[SocketMessage, None]:
        """
        Stream DM narrative as a sequence of SocketMessage chunks.

        Yields:
            - One "system_alert" → stream is starting
            - Many "narrative" chunks → each streamed token
            - One final "narrative" with message_type="stream_end" → done
        """
        # Signal to the frontend that the DM is responding
        yield SocketMessage(
            sender="System",
            message_type="system_alert",
            content="stream_start",
            metadata={"turn_id": message.metadata.get("turn_id", "")},
        )

        system_prompt = self._build_system_prompt(context)
        rules_context = context.get("rules_context", "")
        user_prompt = self._build_user_prompt(message, rules_context)
        history = self._get_history_window(context)
        turn_id = message.metadata.get("turn_id", str(time.time()))

        full_text_parts: list[str] = []

        try:
            async for token in gemini_client.stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                history=history,
                turn_id=turn_id,
            ):
                full_text_parts.append(token)
                yield SocketMessage(
                    sender="DM",
                    message_type="narrative",
                    content=token,
                    metadata={"turn_id": turn_id, "chunk": True},
                )

        except Exception as exc:
            yield SocketMessage(
                sender="System",
                message_type="error",
                content=f"The DM's vision fractured: {exc}",
                metadata={"code": "GEMINI_ERROR", "fatal": False},
            )
            return

        # Signal stream complete — frontend uses this to stop the loading state
        yield SocketMessage(
            sender="System",
            message_type="system_alert",
            content="stream_end",
            metadata={
                "turn_id": turn_id,
                "full_text": "".join(full_text_parts),
            },
        )