const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://127.0.0.1:8787"
  : "";

const REFRESH_MS = 60_000;

function pct(value) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function fmtNum(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toFixed(digits);
}

function hardwareLabel(entry) {
  const parts = [];
  if (entry.gpu_name) {
    parts.push(entry.gpu_vram_gb != null ? `${entry.gpu_name} (${fmtNum(entry.gpu_vram_gb)} GB)` : entry.gpu_name);
  }
  if (entry.cpu_cores) parts.push(`${entry.cpu_cores} cores`);
  if (entry.ram_gb) parts.push(`${fmtNum(entry.ram_gb)} GB RAM`);
  return parts.length ? parts.join(" · ") : "—";
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

function renderRows(entries) {
  const tbody = document.querySelector("#leaderboard-body");
  const meta = document.querySelector("#leaderboard-meta");
  if (!tbody || !meta) return;

  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">No submissions yet. Be the first — run <code>sakura run --model YOUR_MODEL --submit</code>.</td></tr>`;
    meta.textContent = "Waiting for community runs";
    return;
  }

  tbody.innerHTML = entries
    .map(
      (entry, index) => `
      <tr>
        <td>${index + 1}</td>
        <td><strong>${escapeHtml(entry.model)}</strong></td>
        <td>${pct(entry.pass_rate)} <span class="muted">${entry.solved_count}/${entry.task_count}</span></td>
        <td>${fmtNum(entry.throughput)} tok/s</td>
        <td>${escapeHtml(hardwareLabel(entry))}</td>
        <td>${timeAgo(entry.created_at)}</td>
      </tr>`
    )
    .join("");
  meta.textContent = `${entries.length} submission(s) · auto-refreshes every minute`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadLeaderboard() {
  const tbody = document.querySelector("#leaderboard-body");
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Loading leaderboard…</td></tr>`;
  }
  try {
    const response = await fetch(`${API_BASE}/api/v1/leaderboard?limit=50`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderRows(data.entries ?? []);
  } catch (err) {
    const meta = document.querySelector("#leaderboard-meta");
    if (meta) meta.textContent = "Could not reach API — retrying in 1 minute";
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Could not load leaderboard (<code>/api/v1/leaderboard</code> unreachable). If the site loads but this fails, remove duplicate Worker routes in Cloudflare and redeploy.</td></tr>`;
    }
    console.warn("leaderboard fetch failed", err);
  }
}

loadLeaderboard();
setInterval(loadLeaderboard, REFRESH_MS);
