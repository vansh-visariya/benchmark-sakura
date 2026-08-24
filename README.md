# Sakura

A reproducible benchmark for **local coding models** on consumer hardware.

Run it against any [Ollama](https://ollama.com) model, measure accuracy + latency + throughput across 27 tasks, and submit scores to the live leaderboard at [sakura.vaansh.dev/leaderboard](https://sakura.vaansh.dev/leaderboard).

Sakura supports two evaluation modes: **one-shot codegen** (the model emits code that is checked against hidden tests) and **terminal-agent episodes** (the model drives a shell inside the sandbox over multiple steps — like Terminal-Bench / SWE-bench).

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
sakura list -c terminal        # terminal-agent episodes
sakura list -d hard

# Run benchmark (one-shot codegen + sql)
sakura run --model qwen2.5-coder:7b
# Terminal-agent mode (filter to terminal tasks). Requires a model with Ollama
# tool-calling support; the model gets a shell and iterates up to --steps:
sakura run --model qwen2.5-coder:7b -c terminal
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
| `sakura list -c CAT` | List tasks filtered by category (`codegen`, `bugfix`, `sql`, `refactor`, `systems`, `protocol`, `terminal`) |
| `sakura list -d DIFF` | List tasks filtered by difficulty (`easy`, `medium`, `hard`) |
| `sakura detect` | Print probed hardware (GPU, CPU, RAM, OS) |
| `sakura run -m MODEL` | Run the full benchmark |
| `sakura run -m MODEL -c CAT` | Run tasks in a specific category |
| `sakura run -m MODEL --think` | Enable model reasoning before code output |
| `sakura run -m MODEL -c terminal --steps N` | Run terminal-agent episodes (max N tool calls per task) |
| `sakura run -m MODEL --variant Q4_K_M/7.6B/qwen2` | Label the model build (quantization/params/family) shown on the leaderboard; auto-detected from Ollama when omitted |
| `sakura run -m MODEL --submit` | Run and submit to leaderboard |
| `sakura submit FILE.json` | Submit a saved `.results/` file |
| `sakura compare RUN1 RUN2` | Compare two runs side-by-side |
| `sakura report RUN.json` | Generate Markdown report |

## Task categories (27 curated tasks)

- **codegen (6)** — algorithms and utilities (Fibonacci, Two Sum, Palindrome, Linked Lists, Max Subarray, JSON-to-CSV)
- **bugfix (4)** — common defect patterns (Off-by-One, Divide-by-Zero, Null Handling, Regex Catastrophic Backtracking)
- **sql (6)** — queries against in-memory SQLite (Joins, Aggregates, Top-N Per Group, Recursive Hierarchy, Sessionization, Gaps & Islands)
- **refactor (3)** — structure and readability (Extract Method, Flatten Nested Logic, Replace Conditionals)
- **systems (2)** — stateful systems problems (O(1) LRU Cache, Token Bucket Rate Limiter)
- **protocol (2)** — serialization and network specifications (Redis RESP2 Protocol, SemVer 2.0.0 Comparator)
- **terminal (4)** — agent episodes in a sandboxed shell (fix a failing test suite, triage a log file, git surgery, repair a misconfigured service)

### Terminal-agent mode

Terminal tasks (`kind: "terminal"`) evaluate a model as an agent: it sees
`/workspace` plus an optional setup command, then takes up to
`SAKURA_AGENT_MAX_STEPS` tool calls (default 20, overridable with `--steps`)
running shell commands via Ollama's native tool-calling API. When the agent
finishes (or runs out of steps), **hidden test files are copied into the
container and `tests_cmd` is run** — exit code 0 means solved. The agent cannot
read the hidden tests mid-episode because they are only installed at scoring
time.

Run only terminal tasks:

```bash
sakura run --model qwen2.5-coder:7b -c terminal
```

### Authoring a terminal task

Drop a JSON file in `benchmark/tasks/` and register it in `manifest.json`. Required
fields differ by kind:

```jsonc
// terminal task
{
  "id": "terminal_my_task",
  "category": "systems",
  "kind": "terminal",
  "prompt": "Instructions the agent sees.",
  "tags": ["all", "terminal", "medium"],
  "environment_files": { "pkg/app.py": "..." },   // visible to the agent
  "setup_cmd": "cd /workspace && pip install -e . 2>/dev/null || true", // trusted, pre-episode
  "tests_cmd": "python /opt/tests/check.py",       // runs AFTER the episode; exit 0 == solved
  "test_files": { "check.py": "..." },             // HIDDEN until scoring time
  "max_steps": 25                                  // optional per-task cap
}
```

Add more tasks by dropping a JSON file in `benchmark/tasks/` and updating `manifest.json`. Run `pytest tests/test_tasks_reference.py` for one-shot tasks or `sakura list -c terminal` to verify terminal tasks load.

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
| `SAKURA_SANDBOX_IMAGE` | `sakura-executor:0.3.0` | Docker image tag for sandbox |
| `SAKURA_SANDBOX_TIMEOUT`| `30` | Wall-clock execution timeout in seconds |
| `SAKURA_SANDBOX_MEM_MB` | `512` | Memory limit in MB |
| `SAKURA_SANDBOX_CPUS`   | `0.5` | CPU quota allocation |
| `SAKURA_SANDBOX_PIDS`   | `128` | Max process limit |
| `SAKURA_AGENT_MAX_STEPS` | `20` | Max tool calls per terminal-agent episode |
| `SAKURA_AGENT_STEP_TIMEOUT` | `30` | Per-command wall-clock timeout in seconds (terminal mode) |
| `SAKURA_WORKSPACE_MB` | `256` | Size of the writable `/workspace` tmpfs for terminal episodes |
| `SAKURA_MODEL_VARIANT` | *(auto)* | Manual variant label `QUANT/PARAMS/FAMILY`; overrides Ollama `/api/show` detection |

## License

MIT — Copyright 2026 vansh visariya
