"""Explicit user placements; visual observations never write to this store."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import os


def default_database():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pharos/placements.sqlite3"


class Store:
    def __init__(self, path=None):
        path = Path(path) if path else default_database()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create with private permissions, before SQLite writes any user data.
        path.touch(mode=0o600, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA secure_delete=ON")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS placements "
            "(item TEXT PRIMARY KEY, location TEXT NOT NULL, confirmed_at TEXT NOT NULL)"
        )
        self.connection.commit()

    def remember(self, item, location):
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "INSERT INTO placements VALUES (?, ?, ?) ON CONFLICT(item) DO UPDATE SET "
                "location=excluded.location, confirmed_at=excluded.confirmed_at",
                (item, location, timestamp),
            )
        return self.recall(item)

    def recall(self, item):
        row = self.connection.execute(
            "SELECT * FROM placements WHERE item = ?", (item,)
        ).fetchone()
        return dict(row) if row else None

    def forget(self, item):
        with self.connection:
            return self.connection.execute("DELETE FROM placements WHERE item = ?", (item,)).rowcount > 0

    def close(self):
        self.connection.close()
