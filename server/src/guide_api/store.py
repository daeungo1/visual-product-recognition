"""Transactional SQLite storage for one local machine, not managed cloud persistence."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from guide_api.catalog import get_guide
from guide_api.models import AdvanceEvent, SessionState

MAX_SESSIONS = 2000


class Store:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    guide_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL DEFAULT 0 CHECK(step_index BETWEEN 0 AND 3),
                    last_source TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    event_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    response TEXT NOT NULL,
                    PRIMARY KEY(session_id, event_id)
                );
            """)

    def ready(self) -> bool:
        try:
            with self.connection() as connection:
                connection.execute("SELECT id FROM sessions LIMIT 1").fetchone()
                connection.execute("SELECT event_id FROM events LIMIT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    @staticmethod
    def state(row: sqlite3.Row) -> SessionState:
        guide = get_guide(row["guide_id"])
        index = row["step_index"]
        return SessionState(
            id=row["id"],
            guide_id=guide.id,
            step_index=index,
            current_step_id=guide.steps[index].id if index < len(guide.steps) else None,
            finished=index == len(guide.steps),
            last_source=row["last_source"],
        )

    @staticmethod
    def row(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Session not found.")
        return row

    def start(self, guide_id: str) -> SessionState:
        get_guide(guide_id)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= MAX_SESSIONS:
                raise HTTPException(
                    507, "Local demo session limit reached. Archive the local database."
                )
            session_id = str(uuid4())
            connection.execute(
                "INSERT INTO sessions(id, guide_id) VALUES (?,?)", (session_id, guide_id)
            )
            state = self.state(self.row(connection, session_id))
            connection.commit()
            return state

    def get(self, session_id: str) -> SessionState:
        with self.connection() as connection:
            return self.state(self.row(connection, session_id))

    def advance(self, session_id: str, event: AdvanceEvent) -> SessionState:
        payload = json.dumps(
            {"step_id": event.step_id, "source": event.source}, sort_keys=True
        )
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self.row(connection, session_id)
            duplicate = connection.execute(
                "SELECT payload, response FROM events WHERE session_id=? AND event_id=?",
                (session_id, event.event_id),
            ).fetchone()
            if duplicate is not None:
                if duplicate["payload"] != payload:
                    raise HTTPException(409, "Event ID reused for a different payload.")
                result = SessionState.model_validate_json(duplicate["response"])
                connection.commit()
                return result
            current = self.state(row)
            if current.finished or event.step_id != current.current_step_id:
                raise HTTPException(409, "Only the current unfinished step can advance.")
            connection.execute(
                "UPDATE sessions SET step_index=step_index+1, last_source=? WHERE id=?",
                (event.source, session_id),
            )
            result = self.state(self.row(connection, session_id))
            connection.execute(
                "INSERT INTO events(session_id,event_id,payload,response) VALUES (?,?,?,?)",
                (session_id, event.event_id, payload, result.model_dump_json()),
            )
            connection.commit()
            return result
