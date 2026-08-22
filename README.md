# Sakura

A reproducible benchmark for **local coding models** on consumer hardware.

Run it against any [Ollama](https://ollama.com) model, measure accuracy + latency + throughput, and submit scores to the live leaderboard at [sakura.vaansh.dev](https://sakura.vaansh.dev).

## Quick start

```bash
git clone https://github.com/vansh-visariya/benchmark-sakura.git
cd benchmark-sakura
pip install -e .

# Build the Docker sandbox (one time)
./docker/build.sh        # Linux/macOS
.\docker\build.ps1       # Windows

# Run
sakura list
sakura run --model qwen2.5-coder:7b
```

Results are written to `.results/` as JSON.

## Submit to the leaderboard

```bash
sakura run --model qwen2.5-coder:7b --submit
# or upload a saved run:
sakura submit .results/20260822T155055Z_qwen2.5-coder_7b.json
```

Submissions POST to `https://sakura.vaansh.dev/api/v1/submissions`. The website polls `/api/v1/leaderboard` every minute.

## Commands

| Command | Description |
|---------|-------------|
| `sakura list` | List tasks for the configured tags |
| `sakura detect` | Print probed hardware (GPU, CPU, RAM) |
| `sakura run -m MODEL` | Run the benchmark |
| `sakura run -m MODEL --tags sql` | Run tasks matching tags |
| `sakura run -m MODEL --submit` | Run and submit to leaderboard |
| `sakura submit FILE.json` | Submit a saved `.results/` file |

## Task categories

- **codegen** — algorithms and utilities
- **bugfix** — common defect patterns
- **sql** — queries against in-memory SQLite
- **refactor** — structure and readability

17 tasks ship in the starter set. Add more by dropping a JSON file in `benchmark/tasks/` and updating `manifest.json`.

## Website & API

[sakura.vaansh.dev](https://sakura.vaansh.dev) is served by a Cloudflare Worker that hosts:

- Static site (`website/`) — landing page + live leaderboard
- REST API (`workers/`) — D1-backed submissions

Deploy:

```bash
cd workers
npm install
npm run db:migrate    # once, creates D1 tables
npm run deploy
```

See [workers/README.md](workers/README.md) for full setup.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `SAKURA_DATABASE_URL` | `https://sakura.vaansh.dev` | Leaderboard API base |
| `SAKURA_TASK_TAGS` | `all` | Default task filter |
| `SAKURA_DOCKER_NETWORK` | `none` | Docker network mode for sandbox |

## License

MIT — Copyright 2026 vansh visariya
