"""
Intent Router — local Ollama agent (Llama 3.2 3B).
Determines what kind of action the player is taking so the pipeline
can route correctly without wasting Gemini tokens.

IMPORTANT: ollama.chat() is SYNCHRONOUS. We wrap it in asyncio.to_thread()
to prevent it from blocking the FastAPI async event loop.
"""

import asyncio
import json

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage

# Intent types used by ws_router to decide the next step
INTENT_NARRATIVE = "NARRATIVE"   # pure story action → full critical path
INTENT_ACTION = "ACTION"         # attack/roll → needs rules check
INTENT_UI_QUERY = "UI_QUERY"     # "what's my AC?" → answer locally, skip Gemini

_SYSTEM_PROMPT = """
You are a D&D session traffic controller. 
Analyze the player's input and classify it.
Return ONLY a valid JSON object with exactly two keys:
- "intent": one of "NARRATIVE", "ACTION", "UI_QUERY"
- "requires_roll": true or false

Examples:
- "I carefully open the chest" → {"intent": "ACTION", "requires_roll": true}
- "I walk into the tavern" → {"intent": "NARRATIVE", "requires_roll": false}
- "What is my current HP?" → {"intent": "UI_QUERY", "requires_roll": false}
- "I attack the goblin with my sword" → {"intent": "ACTION", "requires_roll": true}

Return ONLY the JSON object. No explanation. No markdown.
"""


class IntentRouter(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="IntentRouter")

    async def process(self, context: dict, message: SocketMessage) -> dict:
        """
        Classify the player's intent using a local Llama 3B call.

        Returns:
            dict with keys "intent" and "requires_roll".
            Falls back to {"intent": "NARRATIVE", "requires_roll": False}
            on any Ollama error so the pipeline never hard-blocks.
        """
        try:
            # Wrap the synchronous ollama.chat() call so it doesn't block
            # the FastAPI async event loop
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": message.content},
                ],
                format="json",
                options={"temperature": 0.0},  # zero temp for consistent routing
            )
            raw = response["message"]["content"]
            result = json.loads(raw)

            # Validate expected keys exist
            intent = result.get("intent", INTENT_NARRATIVE).upper()
            if intent not in (INTENT_NARRATIVE, INTENT_ACTION, INTENT_UI_QUERY):
                intent = INTENT_NARRATIVE

            return {
                "intent": intent,
                "requires_roll": bool(result.get("requires_roll", False)),
            }

        except Exception as exc:
            print(f"[IntentRouter] Ollama error, defaulting to NARRATIVE: {exc}")
            # Safe default — never crash the pipeline over a routing failure
            return {"intent": INTENT_NARRATIVE, "requires_roll": False}