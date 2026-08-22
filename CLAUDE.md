# CLAUDE.md

Guidance for working in the benchmark-sakura repository.

## Architecture

```
cli.py          → CLI (sakura run | list | detect | submit)
runner.py       → Orchestrates model calls, executor, scoring
models.py       → Ollama streaming client
executor/       → Python (Docker sandbox) + SQL (SQLite) execution
sandbox.py      → Docker-isolated code runner
scoring.py      → Pass/fail aggregation
detect.py       → Hardware probing (anti-cheat)
task.py         → Task JSON loader + manifest
submit.py       → Leaderboard submission
benchmark/tasks → Task definitions (JSON)
docker/         → Sandbox image + driver
website/        → Static assets (served by the Worker)
workers/        → Cloudflare Worker + D1 API + asset hosting
```

Production: `sakura.vaansh.dev` — one Worker serves the website and `/api/v1/*`.

## Commands

```bash
pip install -e .
./docker/build.sh          # or docker/build.ps1 on Windows
sakura list
sakura run --model MODEL
sakura run --model MODEL --submit
sakura submit .results/run.json
sakura detect
```

Deploy API + website:

```bash
cd workers && npm install && npm run db:migrate && npm run deploy
```

## Adding a task

1. Add `benchmark/tasks/my_task.json` with `id`, `category`, `prompt`, `reference`, `tests`, `tags`.
2. Register the filename in `benchmark/tasks/manifest.json`.
3. Run `sakura list` to verify it loads.

## License

MIT (Copyright 2026 vansh visariya). Preserve LICENSE in distributions.
