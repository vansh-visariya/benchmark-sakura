CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  version TEXT NOT NULL,
  pass_rate REAL NOT NULL,
  solved_count INTEGER NOT NULL,
  task_count INTEGER NOT NULL,
  throughput REAL,
  avg_ttft_ms REAL,
  total_time_s REAL,
  gpu_name TEXT,
  gpu_vram_gb REAL,
  cpu_cores INTEGER,
  ram_gb REAL,
  platform TEXT,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_submissions_pass_rate ON submissions (pass_rate DESC, throughput DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_model ON submissions (model);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions (created_at DESC);
