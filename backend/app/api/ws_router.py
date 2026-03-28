"""
WebSocket Router — full critical path with session initialisation.

Message flow per turn:
  [session_init] → seeds session_context, triggers Gemini opening scene
  0. Bouncer       — hard-limit safety filter (Layer 1: instant, Layer 2: Ollama)
  1. IntentRouter  — classify action type (Ollama)
  2. Short-circuit if UI_QUERY
  3. RulesLawyer   — inject 5e mechanics (Ollama)
  4. DMAgent       — stream narrative (Gemini)

After stream_end (fire-and-forget):
  5. EventBus — StateExtractor + Physician + Confessor concurrently
"""

import asyncio
import uuid
import app.core.env_patch
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.bouncer import Bouncer
from app.agents.dm_agent import DMAgent
from app.agents.intent_router import IntentRouter, INTENT_UI_QUERY
from app.agents.rules_lawyer import RulesLawyer
from app.core.event_bus import dispatch as bus_dispatch
from app.schemas.contracts import SocketMessage

router = APIRouter()

_bouncer       = Bouncer()
_dm            = DMAgent()
_intent_router = IntentRouter()
_rules_lawyer  = RulesLawyer()


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] Client connected. Active: {len(self.active)}")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        print(f"[WS] Client disconnected. Active: {len(self.active)}")

    async def send(self, msg: SocketMessage, ws: WebSocket) -> None:
        try:
            await ws.send_text(msg.model_dump_json())
        except Exception as exc:
            print(f"[WS] Send failed: {exc}")


manager = ConnectionManager()


@router.websocket("/ws/game")
async def game_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)

    session_context: dict = {
        "character":         {},
        "world":             {},
        "narrative_history": [],
        "rules_context":     "",
    }

    async def send_to_client(msg: SocketMessage) -> None:
        await manager.send(msg, websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            # ── Parse ─────────────────────────────────────────────────────
            try:
                user_msg = SocketMessage.model_validate_json(raw)
            except Exception as parse_err:
                await manager.send(SocketMessage(
                    sender="System",
                    message_type="error",
                    content=f"Invalid message format: {parse_err}",
                ), websocket)
                continue

            turn_id = str(uuid.uuid4())[:8]
            if user_msg.metadata is None:
                user_msg.metadata = {}
            user_msg.metadata["turn_id"] = turn_id

            # ── Session init ──────────────────────────────────────────────
            # Sent once by useGameSocket.initSession() right after
            # SessionZero completes. Seeds character + world into context,
            # then triggers the Gemini opening scene.
            # Must run BEFORE the Bouncer — it is never a player action.
            if user_msg.message_type == "session_init":
                char  = user_msg.metadata.get("character", {})
                world = user_msg.metadata.get("world", {})

                session_context["character"].update(char)
                session_context["world"].update(world)

                print(
                    f"[WS] Session init — "
                    f"{char.get('name','?')} the "
                    f"{char.get('race','?')} {char.get('char_class','?')}"
                )

                # Build the opening scene prompt from backstory + world bible
                anchors     = world.get("backstory_anchors", [])
                anchor_text = "; ".join(anchors) if anchors else "no backstory provided"
                world_name  = world.get("world_bible_name", "the Forgotten Realm")
                world_desc  = world.get("world_description", "")

                opening_prompt = (
                    f"Begin the campaign. "
                    f"The player character is {char.get('name')} — "
                    f"a {char.get('race')} {char.get('char_class')} "
                    f"({char.get('background')}, {char.get('alignment')}). "
                    f"Backstory: {anchor_text}. "
                    f"Setting: {world_name}. {world_desc} "
                    f"Write a cinematic opening scene (3-4 paragraphs) that "
                    f"immediately draws on the backstory anchors. "
                    f"End with the character arriving somewhere and a clear "
                    f"implicit prompt for their first action. "
                    f"Do NOT ask what they do explicitly — show, don't tell."
                )

                opening_msg = SocketMessage(
                    sender="User",
                    message_type="narrative",
                    content=opening_prompt,
                    metadata={"turn_id": turn_id, "is_opening": True},
                )

                try:
                    async for msg_chunk in _dm.process(session_context, opening_msg):
                        await manager.send(msg_chunk, websocket)

                        # Archive the opening scene in history
                        if (
                            msg_chunk.message_type == "system_alert"
                            and msg_chunk.content == "stream_end"
                            and msg_chunk.metadata
                        ):
                            full_text = msg_chunk.metadata.get("full_text", "")
                            if full_text:
                                _update_history(
                                    session_context,
                                    "[OPENING SCENE]",
                                    full_text,
                                )
                except Exception as opening_err:
                    print(f"[WS] Opening scene error: {opening_err}")
                    await manager.send(SocketMessage(
                        sender="System",
                        message_type="error",
                        content="The realm failed to materialise. Refresh and try again.",
                        metadata={"code": "OPENING_ERROR", "fatal": False},
                    ), websocket)

                continue  # opening scene done — wait for first player action

            # ── Step 0: Bouncer ───────────────────────────────────────────
            verdict = await _bouncer.process(session_context, user_msg)

            if not verdict.allowed:
                await manager.send(SocketMessage(
                    sender="Bouncer",
                    message_type="error",
                    content=(
                        "The ancient wards reject your words. "
                        "Speak differently, traveller."
                    ),
                    metadata={
                        "turn_id": turn_id,
                        "reason":  verdict.reason,
                        "layer":   verdict.layer,
                    },
                ), websocket)
                continue

            print(f"[Bouncer] Passed layer={verdict.layer} turn={turn_id}")

            # ── Step 1+2: Intent + Rules concurrently ─────────────────────
            intent_task = asyncio.create_task(
                _intent_router.process(session_context, user_msg)
            )
            rules_task = asyncio.create_task(
                _rules_lawyer.process(session_context, user_msg)
            )

            intent_result = await intent_task

            # ── UI_QUERY short-circuit ────────────────────────────────────
            if intent_result["intent"] == INTENT_UI_QUERY:
                rules_task.cancel()
                await manager.send(SocketMessage(
                    sender="System",
                    message_type="system_alert",
                    content=_answer_ui_query(user_msg.content, session_context),
                    metadata={"turn_id": turn_id, "intent": "UI_QUERY"},
                ), websocket)
                continue

            rules_context = await rules_task
            session_context["rules_context"] = rules_context

            # ── Step 3: Stream DM narrative ───────────────────────────────
            try:
                async for msg_chunk in _dm.process(session_context, user_msg):
                    await manager.send(msg_chunk, websocket)

                    if (
                        msg_chunk.message_type == "system_alert"
                        and msg_chunk.content == "stream_end"
                        and msg_chunk.metadata
                    ):
                        full_text = msg_chunk.metadata.get("full_text", "")
                        if full_text:
                            _update_history(
                                session_context,
                                user_msg.content,
                                full_text,
                            )
                            asyncio.create_task(
                                bus_dispatch(
                                    dm_full_text=full_text,
                                    context=session_context,
                                    send_fn=send_to_client,
                                )
                            )

            except Exception as dm_err:
                await manager.send(SocketMessage(
                    sender="System",
                    message_type="error",
                    content=f"Engine error: {dm_err}",
                    metadata={"code": "PIPELINE_ERROR", "fatal": False},
                ), websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _answer_ui_query(content: str, context: dict) -> str:
    char  = context.get("character", {})
    lower = content.lower()

    if "hp" in lower or "health" in lower or "hit point" in lower:
        return f"HP: {char.get('hp_current','?')} / {char.get('hp_max','?')}"
    if "ac" in lower or "armor" in lower:
        return f"AC: {char.get('armor_class','?')}"
    if "level" in lower:
        return f"Level {char.get('level', 1)}"
    if "inventory" in lower or "items" in lower:
        items = char.get("inventory", [])
        return f"Inventory: {', '.join(items) if items else 'Empty'}"
    if "gold" in lower or "gp" in lower:
        return f"Gold: {char.get('gold_pieces', 0)} GP"
    if "hunger" in lower or "food" in lower:
        return f"Hunger: {char.get('hunger_level','Sated')}"
    if "moralit" in lower or "alignment" in lower:
        score = char.get('morality_score', 50)
        label = "Good" if score > 65 else "Evil" if score < 35 else "Neutral"
        return f"Morality: {score}/100 ({label})"
    return "Check your character sheet for that information."


def _update_history(context: dict, player_action: str, dm_response: str) -> None:
    MAX_STORED = 50
    history: list = context["narrative_history"]
    history.append(f"Player: {player_action[:200]}")
    history.append(f"DM: {dm_response[:500]}")
    if len(history) > MAX_STORED:
        context["narrative_history"] = history[-MAX_STORED:]