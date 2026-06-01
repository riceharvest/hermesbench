from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .api import _score_payload

MIGRATION_0001 = """
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL UNIQUE,
  agent TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  suite TEXT NOT NULL,
  benchmark_version TEXT,
  overall_score REAL NOT NULL,
  pass_at_1 REAL NOT NULL,
  false_done_rate REAL,
  timeout_rate REAL,
  median_wall_time_seconds REAL,
  tool_call_count INTEGER,
  cost_per_successful_task_usd REAL,
  official INTEGER NOT NULL DEFAULT 0,
  raw_result_json TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class SQLiteSubmissionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self):
        return sqlite3.connect(self.path)

    def migrate(self) -> None:
        with self.connect() as db:
            db.executescript(MIGRATION_0001)

    def append(self, payload: dict[str, Any]) -> None:
        stored = dict(payload)
        stored.pop('submission_token', None)
        score = _score_payload(stored)
        rows = stored.get('results', [])
        n = len(rows) or 1
        false_done_rate = sum(1 for r in rows if r.get('false_done')) / n
        timeout_rate = sum(1 for r in rows if r.get('timeout')) / n
        wall = sorted(r.get('wall_time_seconds', 0) for r in rows)
        median = wall[len(wall)//2] if wall else 0
        tool_calls = sum(r.get('tool_calls', 0) for r in rows)
        costs = [r.get('cost_usd') for r in rows if r.get('passed') and r.get('cost_usd') is not None]
        cost_success = sum(costs) / len(costs) if costs else None
        try:
            with self.connect() as db:
                db.execute(
                    """INSERT INTO submissions
                    (run_id, agent, provider, model, suite, benchmark_version, overall_score, pass_at_1,
                     false_done_rate, timeout_rate, median_wall_time_seconds, tool_call_count,
                     cost_per_successful_task_usd, official, raw_result_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (stored['run_id'], stored['agent'], stored.get('provider'), stored.get('model'), stored['suite'],
                     stored.get('benchmark_version') or stored.get('metadata', {}).get('benchmark_version'),
                     score['overall_score'], score['pass_at_1'], false_done_rate, timeout_rate, median, tool_calls,
                     cost_success, int(bool(stored.get('metadata', {}).get('official'))), json.dumps(stored, sort_keys=True)),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"duplicate run_id: {stored.get('run_id')}") from exc

    def read_all(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute('SELECT raw_result_json FROM submissions ORDER BY id').fetchall()
        return [json.loads(row[0]) for row in rows]

    def leaderboard(self, official: bool | None = None) -> list[dict[str, Any]]:
        where = '' if official is None else 'WHERE official = ?'
        params = () if official is None else (int(official),)
        with self.connect() as db:
            rows = db.execute(
                f'''SELECT run_id, agent, provider, model, suite, benchmark_version, overall_score, pass_at_1,
                          false_done_rate, timeout_rate, median_wall_time_seconds, tool_call_count,
                          cost_per_successful_task_usd, official, created_at
                   FROM submissions {where} ORDER BY overall_score DESC, pass_at_1 DESC, created_at ASC''',
                params,
            ).fetchall()
        keys = ['run_id','agent','provider','model','suite','benchmark_version','overall_score','pass_at_1','false_done_rate','timeout_rate','median_wall_time_seconds','tool_call_count','cost_per_successful_task_usd','official','submitted_at']
        return [{k: (bool(v) if k == 'official' else v) for k, v in zip(keys, row)} for row in rows]


def create_sqlite_store(path: str | Path = 'submissions/submissions.db') -> SQLiteSubmissionStore:
    return SQLiteSubmissionStore(path)
