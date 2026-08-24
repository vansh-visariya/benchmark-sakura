const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://127.0.0.1:8787"
  : "";

const REFRESH_MS = 60_000;
const PAGE_SIZE = 25;

let allEntries = [];
let filteredEntries = [];
let currentCategory = "all";
let currentSearch = "";
let currentSort = "pass_rate-desc";
let currentPage = 1;
let selectedCompareIds = new Set();
let submissionDetailsCache = new Map();

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
    chips.push(`<span class="hw-chip hw-chip-gpu" title="GPU">${escapeHtml(entry.gpu_name)}${vram}</span>`);
  } else {
    chips.push(`<span class="hw-chip hw-chip-cpu" title="CPU Only">CPU only</span>`);
  }
  if (entry.cpu_cores) {
    chips.push(`<span class="hw-chip" title="CPU Cores">${entry.cpu_cores}C</span>`);
  }
  if (entry.ram_gb) {
    chips.push(`<span class="hw-chip" title="System RAM">${fmtNum(entry.ram_gb)} GB RAM</span>`);
  }
  if (entry.platform) {
    chips.push(`<span class="hw-chip hw-chip-platform" title="Operating System">${escapeHtml(entry.platform)}</span>`);
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
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchSubmissionDetail(id) {
  if (submissionDetailsCache.has(id)) {
    return submissionDetailsCache.get(id);
  }
  try {
    const res = await fetch(`${API_BASE}/api/v1/submissions/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    submissionDetailsCache.set(id, data);
    return data;
  } catch (err) {
    console.error("Failed to load submission details", err);
    return null;
  }
}

function computePassRateForCategory(entry, detail, cat) {
  if (!detail || !detail.task_results || cat === "all") {
    return {
      passRate: entry.pass_rate,
      solved: entry.solved_count,
      total: entry.task_count,
    };
  }
  const tasksInCat = detail.task_results.filter((t) => (t.category || "").toLowerCase() === cat.toLowerCase());
  if (!tasksInCat.length) {
    return { passRate: 0, solved: 0, total: 0 };
  }
  const solved = tasksInCat.filter((t) => t.passed).length;
  return {
    passRate: solved / tasksInCat.length,
    solved,
    total: tasksInCat.length,
  };
}

function applyFiltersAndSort() {
  let list = [...allEntries];

  // Search filter
  if (currentSearch.trim()) {
    const q = currentSearch.trim().toLowerCase();
    list = list.filter((e) => {
      const matchModel = (e.model || "").toLowerCase().includes(q);
      const matchGpu = (e.gpu_name || "").toLowerCase().includes(q);
      const matchPlat = (e.platform || "").toLowerCase().includes(q);
      const matchQuant = (e.model_quantization || "").toLowerCase().includes(q);
      return matchModel || matchGpu || matchPlat || matchQuant;
    });
  }

  // Sort
  const [sortCol, sortDir] = currentSort.split("-");
  list.sort((a, b) => {
    let valA = a[sortCol];
    let valB = b[sortCol];

    if (sortCol === "model") {
      valA = (valA || "").toLowerCase();
      valB = (valB || "").toLowerCase();
      return sortDir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    if (sortCol === "created_at") {
      const tA = new Date(valA || 0).getTime();
      const tB = new Date(valB || 0).getTime();
      return sortDir === "asc" ? tA - tB : tB - tA;
    }

    valA = valA ?? (sortDir === "asc" ? Infinity : -Infinity);
    valB = valB ?? (sortDir === "asc" ? Infinity : -Infinity);
    return sortDir === "asc" ? valA - valB : valB - valA;
  });

  filteredEntries = list;
  updateResultsCount();
  renderTable();
  renderPagination();
}

function updateResultsCount() {
  const countEl = document.querySelector("#results-count");
  if (!countEl) return;
  const total = filteredEntries.length;
  countEl.textContent = `Showing ${total} submission${total === 1 ? "" : "s"}${
    currentCategory !== "all" ? ` in ${currentCategory}` : ""
  }`;
}

function renderTable() {
  const tbody = document.querySelector("#leaderboard-body");
  if (!tbody) return;

  if (!filteredEntries.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-row">No matching submissions found. Try adjusting filters or run <code>sakura run --submit</code>.</td></tr>`;
    return;
  }

  const startIdx = (currentPage - 1) * PAGE_SIZE;
  const pageEntries = filteredEntries.slice(startIdx, startIdx + PAGE_SIZE);

  tbody.innerHTML = pageEntries
    .map((entry, index) => {
      const rank = startIdx + index + 1;
      const passPct = Math.round((entry.pass_rate ?? 0) * 100);
      const isChecked = selectedCompareIds.has(entry.id) ? "checked" : "";
      const isHighlighted = new URLSearchParams(window.location.search).get("id") === entry.id ? "row-highlight" : "";

      return `
        <tr class="entry-row ${isHighlighted}" data-id="${entry.id}" id="row-${entry.id}">
          <td class="col-compare">
            <input type="checkbox" class="compare-checkbox" data-id="${entry.id}" data-model="${escapeHtml(entry.model)}" ${isChecked} aria-label="Select ${escapeHtml(entry.model)} for comparison">
          </td>
          <td class="col-rank">
            <span class="rank-badge rank-${rank <= 3 ? rank : 'other'}">${rank}</span>
          </td>
          <td class="col-model">
            <div class="model-name">
              <strong>${escapeHtml(entry.model)}</strong>
              ${entry.model_quantization ? `<span class="quant-badge" title="Quantization${entry.model_parameter_size ? ` / params ${escapeHtml(entry.model_parameter_size)}` : ""}">${escapeHtml(entry.model_quantization)}${entry.model_parameter_size ? ` · ${escapeHtml(entry.model_parameter_size)}` : ""}</span>` : ""}
            </div>
          </td>
          <td class="col-pass">
            <div class="pass-cell">
              <div class="pass-bar-wrap">
                <div class="pass-bar-fill" style="width: ${passPct}%;"></div>
              </div>
              <div class="pass-label">
                <strong>${passPct}%</strong>
                <span class="muted">${entry.solved_count}/${entry.task_count}</span>
              </div>
            </div>
          </td>
          <td class="col-speed">
            <span class="metric-val">${fmtNum(entry.throughput)}</span> <span class="metric-unit">tok/s</span>
          </td>
          <td class="col-ttft">
            <span class="metric-val">${entry.avg_ttft_ms ? fmtNum(entry.avg_ttft_ms, 0) : "—"}</span> <span class="metric-unit">ms</span>
          </td>
          <td class="col-hardware">
            <div class="hw-chips-wrap">
              ${hardwareChips(entry)}
            </div>
          </td>
          <td class="col-date" title="${entry.created_at || ''}">
            ${timeAgo(entry.created_at)}
          </td>
          <td class="col-expand">
            <button class="btn-expand" data-id="${entry.id}" aria-expanded="false" title="View per-task details">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </button>
          </td>
        </tr>
        <tr class="detail-row hidden" id="detail-${entry.id}">
          <td colspan="9" class="detail-cell">
            <div class="detail-container" id="detail-box-${entry.id}">
              <div class="loading-state">Loading task breakdown...</div>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  attachRowEventListeners();
}

function attachRowEventListeners() {
  // Checkboxes
  document.querySelectorAll(".compare-checkbox").forEach((cb) => {
    cb.addEventListener("change", (e) => {
      const id = e.target.getAttribute("data-id");
      if (e.target.checked) {
        if (selectedCompareIds.size >= 2) {
          e.target.checked = false;
          alert("You can compare a maximum of 2 models side-by-side. Uncheck one first.");
          return;
        }
        selectedCompareIds.add(id);
      } else {
        selectedCompareIds.delete(id);
      }
      updateCompareDock();
    });
  });

  // Expand buttons
  document.querySelectorAll(".btn-expand").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const id = btn.getAttribute("data-id");
      const detailRow = document.querySelector(`#detail-${id}`);
      const isExpanded = btn.getAttribute("aria-expanded") === "true";

      if (isExpanded) {
        detailRow.classList.add("hidden");
        btn.setAttribute("aria-expanded", "false");
        btn.classList.remove("open");
      } else {
        detailRow.classList.remove("hidden");
        btn.setAttribute("aria-expanded", "true");
        btn.classList.add("open");
        await renderDetailBox(id);
      }
    });
  });
}

async function renderDetailBox(id) {
  const box = document.querySelector(`#detail-box-${id}`);
  if (!box) return;

  const data = await fetchSubmissionDetail(id);
  if (!data || !data.task_results) {
    box.innerHTML = `<p class="muted">No granular task details recorded for this run.</p>`;
    return;
  }

  const tasks = data.task_results;
  const timing = data.metrics || {};

  box.innerHTML = `
    <div class="detail-metrics-bar">
      <div><strong>Timing &amp; Stats:</strong> Total Time: <code>${fmtNum(timing.total_time_s, 1)}s</code> · Avg TTFT: <code>${fmtNum(timing.avg_time_to_first_token_ms, 0)}ms</code> · Output Tokens: <code>${timing.total_output_tokens ?? "—"}</code></div>
      <div><strong>Benchmark Version:</strong> <code>${escapeHtml(data.version || "0.1.0")}</code></div>
    </div>
    <div class="tasks-drilldown-grid">
      ${tasks
        .map((t) => {
          const statusClass = t.passed ? "task-badge-pass" : "task-badge-fail";
          const statusText = t.passed ? "PASS" : "FAIL";
          const cat = t.category || "other";
          return `
            <div class="task-card ${statusClass}">
              <div class="task-card-header">
                <span class="task-cat-tag">${escapeHtml(cat)}</span>
                <span class="task-status">${statusText}</span>
              </div>
              <div class="task-card-name" title="${escapeHtml(t.task_id)}">${escapeHtml(t.task_id)}</div>
              ${
                !t.passed && t.test_details && t.test_details.length
                  ? `<div class="task-card-error" title="${escapeHtml(t.test_details[0].detail || '')}">${escapeHtml(t.test_details[0].detail || 'Test failed')}</div>`
                  : ""
              }
              ${t.steps_used != null ? `<div class="task-card-meta">${t.steps_used} step(s)</div>` : ""}
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderPagination() {
  const totalPages = Math.ceil(filteredEntries.length / PAGE_SIZE) || 1;
  const prevBtn = document.querySelector("#btn-prev-page");
  const nextBtn = document.querySelector("#btn-next-page");
  const indicator = document.querySelector("#page-indicator");

  if (prevBtn) prevBtn.disabled = currentPage <= 1;
  if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
  if (indicator) indicator.textContent = `Page ${currentPage} of ${totalPages}`;
}

function updateCompareDock() {
  const dock = document.querySelector("#compare-dock");
  const text = document.querySelector("#compare-selection-text");
  const actionBtn = document.querySelector("#btn-open-compare");
  if (!dock || !text || !actionBtn) return;

  const count = selectedCompareIds.size;
  if (count === 0) {
    dock.classList.add("hidden");
    actionBtn.disabled = true;
    actionBtn.textContent = "Compare (0/2)";
  } else {
    dock.classList.remove("hidden");
    const selectedModels = Array.from(selectedCompareIds)
      .map((id) => {
        const found = allEntries.find((e) => e.id === id);
        return found ? found.model : id.slice(0, 8);
      })
      .join(" vs ");

    text.textContent = count === 1 ? `Selected 1 model: ${selectedModels}. Select 1 more to compare.` : `Comparing: ${selectedModels}`;
    actionBtn.disabled = count < 2;
    actionBtn.textContent = `Compare (${count}/2)`;
  }
}

async function openCompareModal() {
  const modalBackdrop = document.querySelector("#compare-modal-backdrop");
  const modalBody = document.querySelector("#compare-modal-body");
  const modalTitle = document.querySelector("#compare-modal-title");
  if (!modalBackdrop || !modalBody) return;

  modalBackdrop.classList.remove("hidden");
  modalBody.innerHTML = `<div class="loading-state">Loading side-by-side comparison...</div>`;

  const ids = Array.from(selectedCompareIds);
  if (ids.length !== 2) return;

  const [d1, d2] = await Promise.all([fetchSubmissionDetail(ids[0]), fetchSubmissionDetail(ids[1])]);

  if (!d1 || !d2) {
    modalBody.innerHTML = `<p class="empty-row">Could not retrieve comparison details.</p>`;
    return;
  }

  modalTitle.textContent = `${d1.model} vs ${d2.model}`;

  const m1 = d1.metrics || {};
  const m2 = d2.metrics || {};
  const p1 = Math.round((m1.pass_rate ?? 0) * 100);
  const p2 = Math.round((m2.pass_rate ?? 0) * 100);
  const tp1 = m1.throughput_tokens_per_sec ?? 0;
  const tp2 = m2.throughput_tokens_per_sec ?? 0;
  const quant1 = d1.model_quantization || (d1.model_variant && d1.model_variant.quantization) || "";
  const quant2 = d2.model_quantization || (d2.model_variant && d2.model_variant.quantization) || "";

  // Task comparison map
  const tasks1 = new Map((d1.task_results || []).map((t) => [t.task_id, t]));
  const tasks2 = new Map((d2.task_results || []).map((t) => [t.task_id, t]));
  const allTaskIds = Array.from(new Set([...tasks1.keys(), ...tasks2.keys()])).sort();

  // Category comparison
  const catSet = new Set();
  (d1.task_results || []).forEach((t) => t.category && catSet.add(t.category));
  (d2.task_results || []).forEach((t) => t.category && catSet.add(t.category));
  const categories = Array.from(catSet).sort();

  modalBody.innerHTML = `
    <!-- Top Comparison Specs Card -->
    <div class="compare-specs-grid">
      <div class="compare-spec-col">
        <div class="model-badge-header">
          <h3>${escapeHtml(d1.model)}${quant1 ? ` <span class="quant-badge">${escapeHtml(quant1)}</span>` : ""}</h3>
          <span class="time-sub">${timeAgo(d1.created_at)}</span>
        </div>
        <div class="stat-highlight">
          <div class="stat-big ${p1 >= p2 ? 'stat-winner' : ''}">${p1}%</div>
          <div class="stat-sub">${m1.solved_count ?? 0}/${m1.task_count ?? 0} solved</div>
        </div>
        <ul class="spec-list">
          <li><strong>Throughput:</strong> <code>${fmtNum(tp1)} tok/s</code></li>
          <li><strong>Avg TTFT:</strong> <code>${fmtNum(m1.avg_time_to_first_token_ms, 0)} ms</code></li>
          <li><strong>Total Time:</strong> <code>${fmtNum(m1.total_time_s, 1)} s</code></li>
          <li><strong>Hardware:</strong> ${hardwareChips(d1)}</li>
        </ul>
      </div>

      <div class="compare-spec-col">
        <div class="model-badge-header">
          <h3>${escapeHtml(d2.model)}${quant2 ? ` <span class="quant-badge">${escapeHtml(quant2)}</span>` : ""}</h3>
          <span class="time-sub">${timeAgo(d2.created_at)}</span>
        </div>
        <div class="stat-highlight">
          <div class="stat-big ${p2 >= p1 ? 'stat-winner' : ''}">${p2}%</div>
          <div class="stat-sub">${m2.solved_count ?? 0}/${m2.task_count ?? 0} solved</div>
        </div>
        <ul class="spec-list">
          <li><strong>Throughput:</strong> <code>${fmtNum(tp2)} tok/s</code></li>
          <li><strong>Avg TTFT:</strong> <code>${fmtNum(m2.avg_time_to_first_token_ms, 0)} ms</code></li>
          <li><strong>Total Time:</strong> <code>${fmtNum(m2.total_time_s, 1)} s</code></li>
          <li><strong>Hardware:</strong> ${hardwareChips(d2)}</li>
        </ul>
      </div>
    </div>

    <!-- Category Breakdown Comparison -->
    ${
      categories.length
        ? `
      <div class="compare-section">
        <h4>Category Pass Rate Comparison</h4>
        <div class="category-bars-wrap">
          ${categories
            .map((cat) => {
              const c1 = computePassRateForCategory(d1, d1, cat);
              const c2 = computePassRateForCategory(d2, d2, cat);
              return `
                <div class="cat-bar-row">
                  <span class="cat-bar-label">${escapeHtml(cat)}</span>
                  <div class="cat-dual-bar">
                    <div class="cat-side">
                      <div class="bar-fill bar-fill-1" style="width: ${c1.passRate * 100}%;"></div>
                      <span class="bar-pct">${Math.round(c1.passRate * 100)}%</span>
                    </div>
                    <div class="cat-side">
                      <div class="bar-fill bar-fill-2" style="width: ${c2.passRate * 100}%;"></div>
                      <span class="bar-pct">${Math.round(c2.passRate * 100)}%</span>
                    </div>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
    `
        : ""
    }

    <!-- Per-Task Matrix -->
    <div class="compare-section">
      <h4>Task-by-Task Matrix (${allTaskIds.length} tasks)</h4>
      <div class="table-wrap">
        <table class="leaderboard-table compare-task-table">
          <thead>
            <tr>
              <th>Task ID</th>
              <th>Category</th>
              <th>${escapeHtml(d1.model)}</th>
              <th>${escapeHtml(d2.model)}</th>
              <th>Comparison</th>
            </tr>
          </thead>
          <tbody>
            ${allTaskIds
              .map((tid) => {
                const t1 = tasks1.get(tid);
                const t2 = tasks2.get(tid);
                const pass1 = t1 && t1.passed;
                const pass2 = t2 && t2.passed;
                const cat = (t1 && t1.category) || (t2 && t2.category) || "—";

                let diffBadge = "";
                if (pass1 && pass2) {
                  diffBadge = `<span class="diff-chip diff-both">Both Solved</span>`;
                } else if (!pass1 && !pass2) {
                  diffBadge = `<span class="diff-chip diff-neither">Both Failed</span>`;
                } else if (pass1 && !pass2) {
                  diffBadge = `<span class="diff-chip diff-m1">${escapeHtml(d1.model)} Solved</span>`;
                } else {
                  diffBadge = `<span class="diff-chip diff-m2">${escapeHtml(d2.model)} Solved</span>`;
                }

                return `
                  <tr>
                    <td><code>${escapeHtml(tid)}</code></td>
                    <td><span class="tag">${escapeHtml(cat)}</span></td>
                    <td>${pass1 ? '<span class="status-pass">PASS</span>' : '<span class="status-fail">FAIL</span>'}</td>
                    <td>${pass2 ? '<span class="status-pass">PASS</span>' : '<span class="status-fail">FAIL</span>'}</td>
                    <td>${diffBadge}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function closeCompareModal() {
  const modalBackdrop = document.querySelector("#compare-modal-backdrop");
  if (modalBackdrop) modalBackdrop.classList.add("hidden");
}

async function loadLeaderboard() {
  const tbody = document.querySelector("#leaderboard-body");
  if (tbody && !allEntries.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-row">Loading benchmark entries…</td></tr>`;
  }
  try {
    const res = await fetch(`${API_BASE}/api/v1/leaderboard?limit=100`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allEntries = data.entries || [];
    applyFiltersAndSort();

    // Check URL params for highlight or compare
    const urlParams = new URLSearchParams(window.location.search);
    const highlightId = urlParams.get("id");
    if (highlightId) {
      setTimeout(() => {
        const row = document.querySelector(`#row-${highlightId}`);
        if (row) {
          row.scrollIntoView({ behavior: "smooth", block: "center" });
          const btn = row.querySelector(".btn-expand");
          if (btn) btn.click();
        }
      }, 200);
    }
  } catch (err) {
    console.error("Leaderboard fetch failed", err);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="9" class="empty-row">Could not load leaderboard from <code>/api/v1/leaderboard</code>. Ensure backend is running.</td></tr>`;
    }
  }
}

// Event Listeners
document.addEventListener("DOMContentLoaded", () => {
  // Category pills
  document.querySelectorAll(".category-pills .pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".category-pills .pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      currentCategory = pill.getAttribute("data-cat");
      currentPage = 1;
      applyFiltersAndSort();
    });
  });

  // Search input
  const searchInput = document.querySelector("#filter-search");
  const searchClear = document.querySelector("#clear-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearch = e.target.value;
      if (searchClear) searchClear.classList.toggle("hidden", !currentSearch);
      currentPage = 1;
      applyFiltersAndSort();
    });
  }
  if (searchClear) {
    searchClear.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      currentSearch = "";
      searchClear.classList.add("hidden");
      currentPage = 1;
      applyFiltersAndSort();
    });
  }

  // Sort dropdown
  const sortSelect = document.querySelector("#sort-select");
  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      currentSort = e.target.value;
      applyFiltersAndSort();
    });
  }

  // Clickable column headers
  document.querySelectorAll(".detailed-table th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const sortField = th.getAttribute("data-sort");
      const [currentCol, currentDir] = currentSort.split("-");
      let nextDir = "desc";
      if (currentCol === sortField) {
        nextDir = currentDir === "desc" ? "asc" : "desc";
      } else if (sortField === "model" || sortField === "avg_ttft_ms") {
        nextDir = "asc";
      }

      currentSort = `${sortField}-${nextDir}`;
      if (sortSelect) sortSelect.value = currentSort;

      // Update header indicators
      document.querySelectorAll(".detailed-table th.sortable").forEach((h) => {
        h.classList.remove("active-sort");
        const icon = h.querySelector(".sort-icon");
        if (icon) icon.textContent = "";
      });
      th.classList.add("active-sort");
      const icon = th.querySelector(".sort-icon");
      if (icon) icon.textContent = nextDir === "asc" ? "▲" : "▼";

      applyFiltersAndSort();
    });
  });

  // Pagination buttons
  const prevBtn = document.querySelector("#btn-prev-page");
  const nextBtn = document.querySelector("#btn-next-page");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        renderTable();
        renderPagination();
        window.scrollTo({ top: 200, behavior: "smooth" });
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const totalPages = Math.ceil(filteredEntries.length / PAGE_SIZE);
      if (currentPage < totalPages) {
        currentPage++;
        renderTable();
        renderPagination();
        window.scrollTo({ top: 200, behavior: "smooth" });
      }
    });
  }

  // Compare buttons
  const openCompareBtn = document.querySelector("#btn-open-compare");
  const clearCompareBtn = document.querySelector("#btn-clear-compare");
  const closeModalBtn = document.querySelector("#btn-close-modal");
  const modalBackdrop = document.querySelector("#compare-modal-backdrop");
  const refreshBtn = document.querySelector("#btn-refresh");

  if (openCompareBtn) openCompareBtn.addEventListener("click", openCompareModal);
  if (clearCompareBtn) {
    clearCompareBtn.addEventListener("click", () => {
      selectedCompareIds.clear();
      updateCompareDock();
      document.querySelectorAll(".compare-checkbox").forEach((cb) => (cb.checked = false));
    });
  }
  if (closeModalBtn) closeModalBtn.addEventListener("click", closeCompareModal);
  if (modalBackdrop) {
    modalBackdrop.addEventListener("click", (e) => {
      if (e.target === modalBackdrop) closeCompareModal();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeCompareModal();
  });
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      submissionDetailsCache.clear();
      loadLeaderboard();
    });
  }

  loadLeaderboard();
  setInterval(loadLeaderboard, REFRESH_MS);
});
