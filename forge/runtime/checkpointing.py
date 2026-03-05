"""State checkpointing — save and restore agent/agency state for resumability."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CheckpointStore:
    """
    SQLite-backed checkpoint storage.

    Saves serialized state snapshots that can be restored later,
    enabling fault tolerance, session resumption, and time travel.
    """

    def __init__(self, db_path: str = "checkpoints.db", max_per_entity: int = 50) -> None:
        self.db_path = db_path
        self.max_per_entity = max_per_entity
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                state_json TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cp_entity ON checkpoints(entity_type, entity_name);
            CREATE INDEX IF NOT EXISTS idx_cp_created ON checkpoints(created_at);
        """)
        self._conn.commit()

    def save(
        self,
        entity_type: str,
        entity_name: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
    ) -> str:
        """Save a state checkpoint. Returns the checkpoint ID."""
        cp_id = checkpoint_id or f"cp-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO checkpoints (id, entity_type, entity_name, state_json, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cp_id, entity_type, entity_name, json.dumps(state, default=str), json.dumps(metadata or {}), now),
        )
        self._conn.commit()
        logger.info(f"Checkpoint saved: {cp_id} ({entity_type}/{entity_name})")
        self.rotate(entity_type, entity_name)
        return cp_id

    def load(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load a checkpoint by ID."""
        row = self._conn.execute("SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_name": row["entity_name"],
            "state": json.loads(row["state_json"]),
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def load_latest(self, entity_type: str, entity_name: str) -> dict[str, Any] | None:
        """Load the most recent checkpoint for an entity."""
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE entity_type = ? AND entity_name = ? ORDER BY rowid DESC LIMIT 1",
            (entity_type, entity_name),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_name": row["entity_name"],
            "state": json.loads(row["state_json"]),
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def list_checkpoints(self, entity_type: str | None = None, entity_name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List checkpoints, optionally filtered."""
        query = "SELECT id, entity_type, entity_name, created_at FROM checkpoints WHERE 1=1"
        params: list[Any] = []
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if entity_name:
            query += " AND entity_name = ?"
            params.append(entity_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def rotate(self, entity_type: str, entity_name: str) -> int:
        """Remove old checkpoints beyond the retention limit. Returns count removed."""
        # Get all checkpoint IDs for this entity, oldest first
        rows = self._conn.execute(
            "SELECT id FROM checkpoints WHERE entity_type = ? AND entity_name = ? ORDER BY created_at ASC",
            (entity_type, entity_name),
        ).fetchall()
        
        to_delete = len(rows) - self.max_per_entity
        if to_delete <= 0:
            return 0
        
        delete_ids = [r["id"] for r in rows[:to_delete]]
        placeholders = ",".join("?" * len(delete_ids))
        self._conn.execute(f"DELETE FROM checkpoints WHERE id IN ({placeholders})", delete_ids)
        self._conn.commit()
        logger.debug(f"Rotated {to_delete} old checkpoints for {entity_type}/{entity_name}")
        return to_delete

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        cursor = self._conn.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __repr__(self) -> str:
        count = self._conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        return f"CheckpointStore(db={self.db_path!r}, checkpoints={count})"
