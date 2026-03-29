"""
SQLite service — persistent campaign storage.
Handles:
  - Session creation and loading
  - Turn-by-turn archival (immutable log)
  - Character/world state snapshots (latest wins)
  - Save slot management (list, delete)

All writes are async via aiosqlite.
Schema is created on first run automatically.
"""

import json
import time
from pathlib import Path

import aiosqlite

from app.core.config import settings

DB_PATH = settings.SQLITE_DB_PATH


async def init_db() -> None:
    """Create tables if they don't exist. Called once at app startup."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                char_name    TEXT NOT NULL,
                char_class   TEXT NOT NULL,
                char_race    TEXT NOT NULL,
                world_bible  TEXT NOT NULL,
                created_at   REAL NOT NULL,
                last_played  REAL NOT NULL,
                turn_count   INTEGER DEFAULT 0,
                is_dead      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS turns (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                turn_number  INTEGER NOT NULL,
                player_input TEXT NOT NULL,
                dm_response  TEXT NOT NULL,
                state_delta  TEXT,
                timestamp    REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                session_id   TEXT PRIMARY KEY,
                character    TEXT NOT NULL,
                world        TEXT NOT NULL,
                combat       TEXT,
                narrative_history TEXT NOT NULL,
                updated_at   REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session
                ON turns(session_id, turn_number);
        """)
        await db.commit()


# ── Session management ────────────────────────────────────────────────────────

async def create_session(session_id: str, character: dict, world: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO sessions
               (session_id, char_name, char_class, char_race, world_bible,
                created_at, last_played, turn_count, is_dead)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)""",
            (
                session_id,
                character.get("name", "Unknown"),
                character.get("char_class", "Unknown"),
                character.get("race", "Unknown"),
                world.get("world_bible_name", "Unknown"),
                time.time(),
                time.time(),
            ),
        )
        # Create initial snapshot
        await db.execute(
            """INSERT OR REPLACE INTO snapshots
               (session_id, character, world, combat, narrative_history, updated_at)
               VALUES (?, ?, ?, NULL, ?, ?)""",
            (
                session_id,
                json.dumps(character),
                json.dumps(world),
                json.dumps([]),
                time.time(),
            ),
        )
        await db.commit()


async def list_sessions() -> list[dict]:
    """Return all sessions ordered by last_played desc — for the save slot UI."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT session_id, char_name, char_class, char_race,
                      world_bible, created_at, last_played, turn_count, is_dead
               FROM sessions ORDER BY last_played DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def delete_session(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM snapshots WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await db.commit()


async def mark_dead(session_id: str) -> None:
    """Permadeath — locks the session."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET is_dead = 1 WHERE session_id = ?",
            (session_id,),
        )
        await db.commit()


# ── Turn archival ─────────────────────────────────────────────────────────────

async def archive_turn(
    session_id: str,
    turn_number: int,
    player_input: str,
    dm_response: str,
    state_delta: dict | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO turns
               (session_id, turn_number, player_input, dm_response,
                state_delta, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                turn_number,
                player_input,
                dm_response,
                json.dumps(state_delta) if state_delta else None,
                time.time(),
            ),
        )
        await db.execute(
            """UPDATE sessions
               SET last_played = ?, turn_count = turn_count + 1
               WHERE session_id = ?""",
            (time.time(), session_id),
        )
        await db.commit()


# ── Snapshot (live state) ─────────────────────────────────────────────────────

async def save_snapshot(session_id: str, context: dict) -> None:
    """Overwrite the latest game state. Called after every turn."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO snapshots
               (session_id, character, world, combat, narrative_history, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                json.dumps(context.get("character", {})),
                json.dumps(context.get("world", {})),
                json.dumps(context.get("combat")) if context.get("combat") else None,
                json.dumps(context.get("narrative_history", [])),
                time.time(),
            ),
        )
        await db.commit()


async def load_snapshot(session_id: str) -> dict | None:
    """Load the full session_context for a returning player."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM snapshots WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "character":         json.loads(row["character"]),
                "world":             json.loads(row["world"]),
                "combat":            json.loads(row["combat"]) if row["combat"] else None,
                "narrative_history": json.loads(row["narrative_history"]),
                "rules_context":     "",
            }


async def get_recent_turns(session_id: str, limit: int = 20) -> list[dict]:
    """Fetch the last N turns for the Archivist."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT turn_number, player_input, dm_response, timestamp
               FROM turns WHERE session_id = ?
               ORDER BY turn_number DESC LIMIT ?""",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in reversed(rows)]