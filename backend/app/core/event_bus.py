"""
Event Bus — orchestrates all background agents after each DM turn.
Now includes Archivist for turn compression and SQLite archival.
"""

import asyncio

from app.agents.archivist import Archivist
from app.agents.confessor import Confessor
from app.agents.physician import Physician
from app.agents.state_extractor import StateExtractor
from app.agents.tactician import Tactician
from app.schemas.contracts import SocketMessage
from app.db import sqlite_session

_state_extractor = StateExtractor()
_physician       = Physician()
_confessor       = Confessor()
_tactician       = Tactician()
_archivist       = Archivist()


async def dispatch(
    dm_full_text: str,
    context: dict,
    send_fn,
    player_input: str = "",
) -> None:
    dm_message = SocketMessage(
        sender="DM",
        message_type="narrative",
        content=dm_full_text,
    )

    # Increment turn counter
    context["turn_count"] = context.get("turn_count", 0) + 1

    # Run state agents concurrently
    results = await asyncio.gather(
        _run_state_extractor(dm_message, context),
        _physician.process(context, dm_message),
        _confessor.process(context, dm_message),
        return_exceptions=True,
    )

    merged_delta: dict = {}
    agent_names = ["StateExtractor", "Physician", "Confessor"]

    for agent_name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            print(f"[EventBus] {agent_name} raised: {result}")
            continue
        if isinstance(result, dict) and result:
            public = {k: v for k, v in result.items() if not k.startswith("_")}
            notes  = {k: v for k, v in result.items() if k.startswith("_")}
            merged_delta.update(public)
            for key, note in notes.items():
                print(f"[EventBus] {agent_name} note — {key}: {note}")

    # Combat handling
    state_result = results[0] if not isinstance(results[0], Exception) else {}

    if state_result.get("_combat_started"):
        combat_state = _tactician.get_combat_state(context)
        merged_delta["combat"] = combat_state
        print(f"[EventBus] Combat started — {len(context.get('combat',{}).get('combatants',[]))} combatants")

    if state_result.get("_combat_ended"):
        combat_state = _tactician.end_combat(context)
        merged_delta["combat"] = combat_state
        print(f"[EventBus] Combat ended")

    elif context.get("combat", {}).get("active"):
        combat_state = _tactician.get_combat_state(context)
        merged_delta["combat"] = combat_state

    print(f"[EventBus] merged_delta = {merged_delta}")

    # Push state update to frontend
    if merged_delta:
        try:
            await send_fn(SocketMessage(
                sender="System",
                message_type="state_update",
                content="Character state updated.",
                metadata={
                    "delta":  merged_delta,
                    "source": "event_bus",
                },
            ))
        except Exception as exc:
            print(f"[EventBus] WebSocket push failed: {exc}")

    # SQLite archival (fire and forget — never blocks)
    session_id = context.get("session_id", "")
    if session_id:
        asyncio.create_task(_archive_turn(context, player_input, dm_full_text, merged_delta))

    # Archivist compression (runs every N turns)
    asyncio.create_task(_archivist.process(context, dm_message))


async def _archive_turn(
    context: dict,
    player_input: str,
    dm_response: str,
    delta: dict,
) -> None:
    """Write turn to SQLite and save snapshot. Non-blocking."""
    session_id  = context.get("session_id", "")
    turn_number = context.get("turn_count", 0)
    try:
        await sqlite_service.archive_turn(
            session_id=session_id,
            turn_number=turn_number,
            player_input=player_input,
            dm_response=dm_response,
            state_delta=delta,
        )
        await sqlite_service.save_snapshot(session_id, context)
    except Exception as exc:
        print(f"[EventBus] SQLite archive error: {exc}")


async def _run_state_extractor(message: SocketMessage, context: dict) -> dict:
    delta = await _state_extractor.process(context, message)
    if delta is None:
        return {}
    return _state_extractor.apply_delta(context, delta)