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

function hardwareChips(entry) {
  const chips = [];
  if (entry.gpu_name) {
    const vram = entry.gpu_vram_gb != null ? ` (${fmtNum(entry.gpu_vram_gb)} GB)` : "";
    chips.push(`<span class="hw-chip hw-chip-gpu">${escapeHtml(entry.gpu_name)}${vram}</span>`);
  } else {
    chips.push(`<span class="hw-chip hw-chip-cpu">CPU only</span>`);
  }
  if (entry.ram_gb) {
    chips.push(`<span class="hw-chip">${fmtNum(entry.ram_gb)} GB RAM</span>`);
  }
  return chips.length ? chips.join(" ") : "—";
}

function timeAgo(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
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

  // Display top 5
  const topEntries = entries.slice(0, 5);

  tbody.innerHTML = topEntries
    .map(
      (entry, index) => `
      <tr onclick="window.location.href='/leaderboard.html?id=${entry.id}'" style="cursor: pointer;" title="Click to view details on full leaderboard">
        <td><span class="rank-badge rank-${index + 1 <= 3 ? index + 1 : 'other'}">${index + 1}</span></td>
        <td><strong>${escapeHtml(entry.model)}</strong></td>
        <td>
          <div class="pass-label">
            <strong>${pct(entry.pass_rate)}</strong>
            <span class="muted">${entry.solved_count}/${entry.task_count}</span>
          </div>
        </td>
        <td>${fmtNum(entry.throughput)} <span class="muted">tok/s</span></td>
        <td>${hardwareChips(entry)}</td>
        <td>${timeAgo(entry.created_at)}</td>
      </tr>`
    )
    .join("");

  meta.innerHTML = `Showing top ${topEntries.length} of ${entries.length} submission(s) · <a href="/leaderboard.html" class="view-all-link">View Full Leaderboard &amp; Compare Models &rarr;</a>`;
}

async function loadLeaderboard() {
  const tbody = document.querySelector("#leaderboard-body");
  if (tbody && !tbody.children.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Loading top models…</td></tr>`;
  }
  try {
    const response = await fetch(`${API_BASE}/api/v1/leaderboard?limit=10`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderRows(data.entries ?? []);
  } catch (err) {
    const meta = document.querySelector("#leaderboard-meta");
    if (meta) meta.textContent = "Could not reach API — retrying in 1 minute";
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Could not load preview. Check connection or view <a href="/leaderboard.html">Leaderboard page</a>.</td></tr>`;
    }
    console.warn("homepage leaderboard preview fetch failed", err);
  }
}

loadLeaderboard();
setInterval(loadLeaderboard, REFRESH_MS);
