# Sakura

A reproducible benchmark for **local coding models** on consumer hardware.

Run it against any [Ollama](https://ollama.com) model, measure accuracy + latency + throughput, and optionally submit scores to the leaderboard at [sakura.vaansh.dev](https://sakura.vaansh.dev).

## Quick start

```bash
git clone https://github.com/vanshvisariya/benchmark-sakura.git
cd benchmark-sakura
pip install -e .

# Build the sandbox image (one time)
./docker/build.sh        # Linux/macOS
.\docker\build.ps1       # Windows

# Run
sakura list
sakura run --model qwen2.5-coder:7b
```

Results are written to `.results/` as JSON.

## Commands

| Command | Description |
|---------|-------------|
| `sakura list` | List tasks for the configured tags |
| `sakura detect` | Print probed hardware (GPU, CPU, RAM) |
| `sakura run -m MODEL` | Run the benchmark |
| `sakura run -m MODEL --tags codegen` | Run only tasks matching tags |
| `sakura run -m MODEL --submit` | Submit results to the leaderboard |

## Task categories

- **codegen** — algorithms and utilities
- **bugfix** — common defect patterns
- **sql** — queries against in-memory SQLite
- **refactor** — structure and readability

17 tasks ship in the starter set. Add more by dropping a JSON file in `benchmark/tasks/` and updating `manifest.json`.

## Website

Static site for [sakura.vaansh.dev](https://sakura.vaansh.dev) lives in `website/`. Deploy the folder to any static host (Cloudflare Pages, GitHub Pages, etc.).

## Configuration

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `SAKURA_DATABASE_URL` | `https://sakura.vaansh.dev` | Leaderboard API base |
| `SAKURA_TASK_TAGS` | `all` | Default task filter |
| `SAKURA_DOCKER_NETWORK` | `none` | Docker network mode for sandbox |

## License

MIT — Copyright 2026 vansh visariya
