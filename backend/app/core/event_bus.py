"""
Event Bus — orchestrates all background agents after each DM turn.
Triggered by ws_router via asyncio.create_task (fire-and-forget).

Flow per turn:
  1. StateExtractor parses HP/inventory/gold/status from DM prose
  2. Physician advances hunger/survival timers
  3. Confessor detects morality shifts and NPC relationship changes
  4. All three run CONCURRENTLY (asyncio.gather)
  5. All changes merged into session_context
  6. Single WebSocket push with the full merged state_update delta
"""

import asyncio

from app.agents.confessor import Confessor
from app.agents.physician import Physician
from app.agents.state_extractor import StateExtractor
from app.schemas.contracts import SocketMessage

# Agent singletons
_state_extractor = StateExtractor()
_physician = Physician()
_confessor = Confessor()


async def dispatch(
    dm_full_text: str,
    context: dict,
    send_fn,          # async callable: (SocketMessage) -> None
) -> None:
    """
    Fire all background agents concurrently.
    Merges their outputs and pushes a single state_update to the frontend.

    Args:
        dm_full_text: The complete DM narrative from this turn.
        context:      The live session_context dict (mutated in-place).
        send_fn:      Bound coroutine that sends a SocketMessage over WebSocket.
    """
    # Wrap the full DM text as a SocketMessage for agents that expect one
    dm_message = SocketMessage(
        sender="DM",
        message_type="narrative",
        content=dm_full_text,
    )

    # ── Run all three agents concurrently ──────────────────────────────────
    results = await asyncio.gather(
        _run_state_extractor(dm_message, context),
        _physician.process(context, dm_message),
        _confessor.process(context, dm_message),
        return_exceptions=True,  # one agent failing must not crash the others
    )

    # ── Merge all changed_fields into a single delta ───────────────────────
    merged_delta: dict = {}
    agent_names = ["StateExtractor", "Physician", "Confessor"]

    for agent_name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            print(f"[EventBus] {agent_name} raised: {result}")
            continue
        if isinstance(result, dict) and result:
            # Private keys (prefixed with _) are notes/flags, not UI fields
            public = {k: v for k, v in result.items() if not k.startswith("_")}
            notes  = {k: v for k, v in result.items() if k.startswith("_")}
            merged_delta.update(public)

            # Log internal notes for debugging
            for key, note in notes.items():
                print(f"[EventBus] {agent_name} note — {key}: {note}")
    #TEMPORARY, REMOVE LATER              
    print(f"[EventBus] merged_delta = {merged_delta}")

    # ── Push to frontend if anything changed ──────────────────────────────
    if merged_delta:
        try:
            await send_fn(SocketMessage(
                sender="System",
                message_type="state_update",
                content="Character state updated.",
                metadata={
                    "delta": merged_delta,
                    "source": "event_bus",
                },
            ))
        except Exception as exc:
            print(f"[EventBus] WebSocket push failed: {exc}")


async def _run_state_extractor(message: SocketMessage, context: dict) -> dict:
    """
    StateExtractor has a two-phase call: parse then apply.
    Wraps both phases so event_bus.dispatch gets a clean changed_fields dict.
    """
    delta = await _state_extractor.process(context, message)
    if delta is None:
        return {}
    return _state_extractor.apply_delta(context, delta)