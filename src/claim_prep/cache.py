"""Brief cache, keyed on everything a brief depends on.

A brief is reused only while its key matches: the deal's fingerprint (any
new activity or edited field changes it), the evidence stores' version, the
prompt version and the model. So there is no expiry time to tune, and a
cached brief is never stale.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS call_briefs (
    deal_id    INTEGER PRIMARY KEY,
    cache_key  TEXT    NOT NULL,
    brief_json TEXT    NOT NULL,
    created_at TEXT    NOT NULL
)
"""


class BriefCache:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.execute(_SCHEMA)

    def get(self, deal_id: int, key: str) -> tuple[dict, str] | None:
        """(brief, created_at) if a brief with this exact key is stored."""
        with closing(sqlite3.connect(self._path)) as conn:
            row = conn.execute("SELECT brief_json, created_at FROM call_briefs WHERE deal_id = ? AND cache_key = ?",
                               (deal_id, key)).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def put(self, deal_id: int, key: str, brief: dict) -> str:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO call_briefs VALUES (?, ?, ?, ?)",
                         (deal_id, key, json.dumps(brief), created_at))
        return created_at
