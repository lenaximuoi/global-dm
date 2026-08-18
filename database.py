"""SQLite persistence for the Global Life narrative.

The database deliberately stores only durable, player-relevant facts.  The
complete transcript is available for recent conversational texture, while
inventory and flags are the compact source of truth for game state.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class GameDatabase:
    """Small repository around a SQLite game save."""

    def __init__(self, path: str | Path = "game.db") -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    item_name TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS quest_flags (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turn_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL
                );
                """
            )

    def add_item(self, item_name: str) -> bool:
        """Add a unique item and report whether the inventory changed."""
        with self.connection:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO inventory (item_name) VALUES (?)", (item_name,)
            )
        return cursor.rowcount == 1

    def remove_item(self, item_name: str) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM inventory WHERE item_name = ?", (item_name,)
            )
        return cursor.rowcount == 1

    def inventory(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT item_name FROM inventory ORDER BY item_name COLLATE NOCASE"
        )
        return [row["item_name"] for row in rows]

    def set_flag(self, key: str, value: Any) -> None:
        serialized_value = json.dumps(value)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO quest_flags (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, serialized_value),
            )

    def get_flag(self, key: str, default: Any = None) -> Any:
        row = self.connection.execute(
            "SELECT value FROM quest_flags WHERE key = ?", (key,)
        ).fetchone()
        return default if row is None else json.loads(row["value"])

    def flags(self) -> dict[str, Any]:
        rows = self.connection.execute("SELECT key, value FROM quest_flags ORDER BY key")
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def add_turn(self, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        with self.connection:
            self.connection.execute(
                "INSERT INTO turn_history (role, content) VALUES (?, ?)", (role, content)
            )

    def history(self, limit: int = 12) -> list[dict[str, str]]:
        """Return the most recent turns in chronological order."""
        rows = self.connection.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content FROM turn_history ORDER BY id DESC LIMIT ?
            ) ORDER BY id
            """,
            (limit,),
        )
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def state(self, history_limit: int = 12) -> dict[str, Any]:
        return {
            "inventory": self.inventory(),
            "quest_flags": self.flags(),
            "recent_history": self.history(history_limit),
        }

    def initialize_life(self, start_city: str, attributes: dict[str, int]) -> None:
        """Initialize a save once; never overwrite an existing life."""
        if self.get_flag("current_city") is None:
            self.set_flag("current_city", start_city)
            self.set_flag("visited_cities", [start_city])
            self.set_flag("attributes", attributes)

    def player_state(self) -> dict[str, Any]:
        return {
            "current_city": self.get_flag("current_city"),
            "visited_cities": self.get_flag("visited_cities", []),
            "attributes": self.get_flag("attributes", {}),
        }

    def move_to_city(self, city_id: str) -> bool:
        state = self.player_state()
        if state["current_city"] == city_id:
            return False
        visited = state["visited_cities"]
        if city_id not in visited:
            visited.append(city_id)
        self.set_flag("current_city", city_id)
        self.set_flag("visited_cities", visited)
        return True

    def adjust_attributes(self, changes: dict[str, int]) -> dict[str, int]:
        attributes = self.get_flag("attributes", {})
        applied: dict[str, int] = {}
        for attribute, delta in changes.items():
            if not delta:
                continue
            attributes[attribute] = max(0, min(100, attributes.get(attribute, 0) + delta))
            applied[attribute] = delta
        self.set_flag("attributes", attributes)
        return applied
