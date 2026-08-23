# Sakura

A reproducible benchmark for **local coding models** on consumer hardware.

Run it against any [Ollama](https://ollama.com) model, measure accuracy + latency + throughput across 23 tasks, and submit scores to the live leaderboard at [sakura.vaansh.dev/leaderboard](https://sakura.vaansh.dev/leaderboard).

## Quick start

```bash
git clone https://github.com/vansh-visariya/benchmark-sakura.git
cd benchmark-sakura
pip install -e .

# Build the Docker sandbox (one time)
./docker/build.sh        # Linux/macOS
.\docker\build.ps1       # Windows

# List tasks or filter by category / difficulty
sakura list
sakura list -c systems
sakura list -d hard

# Run benchmark
sakura run --model qwen2.5-coder:7b
# Enable reasoning for models that support Ollama thinking
sakura run --model qwen3.5:9b --think
```

Results are written to `.results/` as JSON.

## Submit to the leaderboard

```bash
sakura run --model qwen2.5-coder:7b --submit
# or upload a saved run:
sakura submit .results/20260822T155055Z_qwen2.5-coder_7b.json
```

Submissions POST to `https://sakura.vaansh.dev/api/v1/submissions`. The website polls `/api/v1/leaderboard` and updates live.

## Compare & Report Tools

```bash
# Compare two benchmark runs side-by-side in the terminal
sakura compare .results/run_qwen.json .results/run_deepseek.json

# Generate a formatted Markdown summary report
sakura report .results/run_qwen.json -o report.md
```

## Commands

| Command | Description |
|---------|-------------|
| `sakura list` | List all tasks |
| `sakura list -c CAT` | List tasks filtered by category (`codegen`, `bugfix`, `sql`, `refactor`, `systems`, `protocol`) |
| `sakura list -d DIFF` | List tasks filtered by difficulty (`easy`, `medium`, `hard`) |
| `sakura detect` | Print probed hardware (GPU, CPU, RAM, OS) |
| `sakura run -m MODEL` | Run the full benchmark |
| `sakura run -m MODEL -c CAT` | Run tasks in a specific category |
| `sakura run -m MODEL --think` | Enable model reasoning before code output |
| `sakura run -m MODEL --submit` | Run and submit to leaderboard |
| `sakura submit FILE.json` | Submit a saved `.results/` file |
| `sakura compare RUN1 RUN2` | Compare two runs side-by-side |
| `sakura report RUN.json` | Generate Markdown report |

## Task categories (23 curated tasks)

- **codegen (6)** — algorithms and utilities (Fibonacci, Two Sum, Palindrome, Linked Lists, Max Subarray, JSON-to-CSV)
- **bugfix (4)** — common defect patterns (Off-by-One, Divide-by-Zero, Null Handling, Regex Catastrophic Backtracking)
- **sql (6)** — queries against in-memory SQLite (Joins, Aggregates, Top-N Per Group, Recursive Hierarchy, Sessionization, Gaps & Islands)
- **refactor (3)** — structure and readability (Extract Method, Flatten Nested Logic, Replace Conditionals)
- **systems (2)** — stateful systems problems (O(1) LRU Cache, Token Bucket Rate Limiter)
- **protocol (2)** — serialization and network specifications (Redis RESP2 Protocol, SemVer 2.0.0 Comparator)

Add more tasks by dropping a JSON file in `benchmark/tasks/` and updating `manifest.json`.

Use `--think` for reasoning-capable models when solving complex tasks. Reasoning is kept separate from the final code response, and its token and latency cost is included in the run metrics. Without `--think`, the benchmark uses a faster code-only request.

## Website & API

[sakura.vaansh.dev](https://sakura.vaansh.dev) is served by a Cloudflare Worker that hosts:

- Static site (`website/`) — landing page (`index.html`), full interactive leaderboard (`leaderboard.html`) with category filtering, search, task drill-downs, and side-by-side model comparisons.
- REST API (`workers/`) — D1-backed submissions with sorting, pagination, and search endpoints.

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
| `SAKURA_SANDBOX_IMAGE` | `sakura-executor:0.2.0` | Docker image tag for sandbox |
| `SAKURA_SANDBOX_TIMEOUT`| `30` | Wall-clock execution timeout in seconds |
| `SAKURA_SANDBOX_MEM_MB` | `512` | Memory limit in MB |
| `SAKURA_SANDBOX_CPUS`   | `0.5` | CPU quota allocation |
| `SAKURA_SANDBOX_PIDS`   | `128` | Max process limit |

## License

MIT — Copyright 2026 vansh visariya
