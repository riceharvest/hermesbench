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
