# CLAUDE.md

Guidance for working in the benchmark-sakura repository.

## Architecture

```
cli.py          → CLI (sakura run | list | detect | submit | compare | report)
runner.py       → Orchestrates model calls, executor, scoring
compare.py      → Side-by-side run comparisons
report.py       → Markdown benchmark report generator
models.py       → Ollama streaming client
executor/       → Python (Docker sandbox) + SQL (SQLite) execution
sandbox.py      → Docker-isolated code runner
scoring.py      → Pass/fail aggregation and category scoring
detect.py       → Hardware probing (anti-cheat)
task.py         → Task JSON loader + manifest
submit.py       → Leaderboard submission
benchmark/tasks → 23 Task definitions (JSON) across 6 categories
docker/         → Sandbox image + driver
website/        → Static assets (index.html, leaderboard.html, etc.)
workers/        → Cloudflare Worker + D1 API + asset hosting
```

Production: `sakura.vaansh.dev` — one Worker serves the website (`/` and `/leaderboard`) and `/api/v1/*`.

## Commands

```bash
pip install -e .
./docker/build.sh          # or docker\build.ps1 on Windows
pytest -v                  # Run test suite (24 tests)
sakura list                # List all 23 tasks
sakura list -c systems     # Filter by category
sakura list -d hard        # Filter by difficulty
sakura run --model MODEL
sakura run --model MODEL --think
sakura run --model MODEL --category sql
sakura run --model MODEL --submit
sakura submit .results/run.json
sakura compare .results/run1.json .results/run2.json
sakura report .results/run.json -o report.md
sakura detect
```

Deploy API + website:

```bash
cd workers && npm install && npm run db:migrate && npm run deploy
```

## Adding a task

1. Add `benchmark/tasks/my_task.json` with `id`, `category`, `prompt`, `reference`, `tests`, and `tags`. SQL tasks also need `sql_schema`, `sql_setup`, and `expected` result rows.
2. Register the filename in `benchmark/tasks/manifest.json`.
3. Run `pytest tests/test_tasks_reference.py` to ensure reference solution passes 100% of tests.
4. Run `sakura list` to verify it loads.

Use `--think` when evaluating a model's reasoning mode. The default run disables Ollama thinking for faster, more comparable code-only results; only the model's final response is executed.

## License

MIT (Copyright 2026 vansh visariya). Preserve LICENSE in distributions.
