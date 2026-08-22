# CLAUDE.md

Guidance for working in the benchmark-sakura repository.

## Architecture

```
cli.py          → CLI entry point (sakura run | list | detect)
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
website/        → Static site for sakura.vaansh.dev
```

## Commands

```bash
pip install -e .
./docker/build.sh          # or docker/build.ps1 on Windows
sakura list
sakura run --model MODEL
sakura detect
python -m cli run --model MODEL   # without install
```

## Adding a task

1. Add `benchmark/tasks/my_task.json` with `id`, `category`, `prompt`, `reference`, `tests`, `tags`.
2. Register the filename in `benchmark/tasks/manifest.json`.
3. Run `sakura list` to verify it loads.

## License

MIT (Copyright 2026 vansh visariya). Preserve LICENSE in distributions.
