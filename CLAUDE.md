# CLAUDE.md

Guidance for working in the benchmark-sakura repository.

## Architecture

```
cli.py          → CLI (sakura run | list | detect | submit | compare | report)
runner.py       → Orchestrates model calls, executor, scoring; dispatch by task kind (codegen/sql/terminal)
compare.py      → Side-by-side run comparisons
report.py       → Markdown benchmark report generator
models.py       → Ollama streaming client (one-shot complete() + multi-turn tool-calling chat())
agent.py        → Terminal-agent episode loop (bash tool, step budget, trajectory, hidden-test scoring)
executor/       → Python (Docker sandbox) + SQL (SQLite) execution for one-shot tasks
sandbox.py      → Docker-isolated runner: payload exec for codegen, shell exec for terminal (read-only rootfs + /workspace tmpfs, tests installed only at scoring)
scoring.py      → Pass/fail aggregation and category scoring (TaskResult carries agent metrics)
detect.py       → Hardware probing (anti-cheat, env-safe parsing)
task.py         → Task JSON loader + manifest (codegen/sql/terminal kinds, per-kind validation)
submit.py       → Leaderboard submission
benchmark/tasks → 27 Task definitions (JSON): 23 one-shot + 4 terminal-agent episodes
docker/         → Sandbox image (v0.3.0) + driver
website/        → Static assets (index.html, leaderboard.html, etc.)
workers/        → Cloudflare Worker + D1 API + asset hosting
```

Production: `sakura.vaansh.dev` — one Worker serves the website (`/` and `/leaderboard`) and `/api/v1/*`.

Terminal-agent flow: `task.py` parses a `kind: "terminal"` task → `runner.py` starts the shared sandbox, installs `environment_files` into `/workspace`, runs `setup_cmd`, then `agent.py` drives a `bash` tool loop via `models.OllamaClient.chat()` (tools API) up to `agent_max_steps` → finally `sandbox.install_files(test_files, "/opt/tests")` + `exec_shell(tests_cmd)` decides solved/not-solved. Hidden tests enter the container only at scoring, so the model cannot read them mid-episode.

## Commands

```bash
pip install -e .
./docker/build.sh          # or docker\build.ps1 on Windows
pytest -v                  # Run test suite (45 tests)
sakura list                # List all 27 tasks
sakura list -c systems     # Filter by category
sakura list -c terminal    # Terminal-agent episodes
sakura list -d hard        # Filter by difficulty
sakura run --model MODEL
sakura run --model MODEL --think
sakura run --model MODEL -c terminal --steps N
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
2. Terminal tasks use `kind: "terminal"` and require `tests_cmd` instead; they take `environment_files`, an optional `setup_cmd`, optional hidden `test_files` (installed only at scoring time), and an optional `max_steps`. See README for a template.
3. Register the filename in `benchmark/tasks/manifest.json`.
4. Run `pytest tests/test_tasks_reference.py` to ensure reference solution passes 100% of tests.
5. Run `sakura list` to verify it loads.

Use `--think` when evaluating a model's reasoning mode. The default run disables Ollama thinking for faster, more comparable code-only results; only the model's final response is executed. For terminal tasks, `--think` is also passed through so reasoning-capable models can think before each tool call. The runner is fault-tolerant: a failed model call or broken task is recorded as an error result without aborting the rest of the run.

## Sandbox image

The terminal-agent sandbox image is `sakura-executor:0.3.0` (built via `docker/build.sh` / `docker/build.psl` on Windows, or `docker build -t sakura-executor:0.3.0 docker`). It ships Python 3.13 + pytest plus shell tooling (git, grep, sed, etc.) on a read-only rootfs with a writable `/workspace` tmpfs. Rebuild after any image change or before submitting scores.

## License

MIT (Copyright 2026 vansh visariya). Preserve LICENSE in distributions.
