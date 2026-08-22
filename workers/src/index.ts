export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  ALLOWED_ORIGIN: string;
}

type SubmissionPayload = {
  model: string;
  version: string;
  hardware: {
    gpus?: Array<{ name?: string; memory_total_gb?: number | null; is_cpu?: boolean }>;
    cpu_cores?: number;
    ram_total_gb?: number;
    platform?: string;
  };
  metrics: {
    pass_rate?: number;
    solved_count?: number;
    task_count?: number;
    throughput_tokens_per_sec?: number;
    avg_time_to_first_token_ms?: number;
    total_time_s?: number;
  };
  task_results: unknown[];
};

type LeaderboardRow = {
  id: string;
  model: string;
  pass_rate: number;
  solved_count: number;
  task_count: number;
  throughput: number | null;
  avg_ttft_ms: number | null;
  gpu_name: string | null;
  gpu_vram_gb: number | null;
  cpu_cores: number | null;
  ram_gb: number | null;
  platform: string | null;
  created_at: string;
};

const corsHeaders = (origin: string, allowed: string) => {
  const ok =
    origin === allowed ||
    origin.startsWith("http://localhost:") ||
    origin.startsWith("http://127.0.0.1:");
  return {
    "Access-Control-Allow-Origin": ok ? origin : allowed,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
};

function json(data: unknown, status = 200, extra: Record<string, string> = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...extra },
  });
}

function primaryGpu(hardware: SubmissionPayload["hardware"]) {
  const gpus = hardware.gpus ?? [];
  const discrete = gpus.find((g) => !g.is_cpu);
  return discrete ?? gpus[0] ?? null;
}

function validateSubmission(body: unknown): SubmissionPayload | string {
  if (!body || typeof body !== "object") return "body must be a JSON object";
  const payload = body as SubmissionPayload;
  if (!payload.model || typeof payload.model !== "string") return "model is required";
  if (!payload.version || typeof payload.version !== "string") return "version is required";
  if (!payload.hardware || typeof payload.hardware !== "object") return "hardware is required";
  if (!payload.metrics || typeof payload.metrics !== "object") return "metrics is required";
  if (!Array.isArray(payload.task_results)) return "task_results must be an array";
  const passRate = payload.metrics.pass_rate;
  if (typeof passRate !== "number" || passRate < 0 || passRate > 1) {
    return "metrics.pass_rate must be a number between 0 and 1";
  }
  return payload;
}

async function insertSubmission(env: Env, payload: SubmissionPayload) {
  const id = crypto.randomUUID();
  const gpu = primaryGpu(payload.hardware);
  await env.DB.prepare(
    `INSERT INTO submissions (
      id, model, version, pass_rate, solved_count, task_count,
      throughput, avg_ttft_ms, total_time_s,
      gpu_name, gpu_vram_gb, cpu_cores, ram_gb, platform, payload
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      id,
      payload.model.slice(0, 200),
      payload.version.slice(0, 32),
      payload.metrics.pass_rate ?? 0,
      payload.metrics.solved_count ?? 0,
      payload.metrics.task_count ?? payload.task_results.length,
      payload.metrics.throughput_tokens_per_sec ?? null,
      payload.metrics.avg_time_to_first_token_ms ?? null,
      payload.metrics.total_time_s ?? null,
      gpu?.name?.slice(0, 200) ?? null,
      gpu?.memory_total_gb ?? null,
      payload.hardware.cpu_cores ?? null,
      payload.hardware.ram_total_gb ?? null,
      payload.hardware.platform?.slice(0, 64) ?? null,
      JSON.stringify(payload)
    )
    .run();
  return id;
}

async function leaderboard(env: Env, limit = 50): Promise<LeaderboardRow[]> {
  const result = await env.DB.prepare(
    `SELECT id, model, pass_rate, solved_count, task_count,
            throughput, avg_ttft_ms, gpu_name, gpu_vram_gb,
            cpu_cores, ram_gb, platform, created_at
     FROM submissions
     ORDER BY pass_rate DESC, throughput DESC, created_at DESC
     LIMIT ?`
  )
    .bind(limit)
    .all<LeaderboardRow>();
  return result.results ?? [];
}

async function getSubmission(env: Env, id: string) {
  return env.DB.prepare(`SELECT payload, created_at FROM submissions WHERE id = ?`)
    .bind(id)
    .first<{ payload: string; created_at: string }>();
}

async function handleApi(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const origin = request.headers.get("Origin") ?? env.ALLOWED_ORIGIN;
  const cors = corsHeaders(origin, env.ALLOWED_ORIGIN);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  if (request.method === "POST" && url.pathname === "/api/v1/submissions") {
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid JSON" }, 400, cors);
    }
    const validated = validateSubmission(body);
    if (typeof validated === "string") {
      return json({ error: validated }, 400, cors);
    }
    const id = await insertSubmission(env, validated);
    const viewUrl = `${env.ALLOWED_ORIGIN}/#leaderboard`;
    return json({ id, url: viewUrl }, 201, cors);
  }

  if (request.method === "GET" && url.pathname === "/api/v1/leaderboard") {
    const limit = Math.min(Number(url.searchParams.get("limit") ?? "50"), 100);
    const entries = await leaderboard(env, limit);
    return json({ entries, updated_at: new Date().toISOString() }, 200, cors);
  }

  if (request.method === "GET" && url.pathname.startsWith("/api/v1/submissions/")) {
    const id = url.pathname.split("/").pop() ?? "";
    const row = await getSubmission(env, id);
    if (!row) return json({ error: "not found" }, 404, cors);
    return json({ id, created_at: row.created_at, ...JSON.parse(row.payload) }, 200, cors);
  }

  return json({ error: "not found" }, 404, cors);
}

async function serveWebsite(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const assetPath =
    url.pathname === "/" || url.pathname === "/index.html" ? "/index.html" : url.pathname;
  const assetRequest = new Request(new URL(assetPath, url.origin).toString(), {
    method: request.method,
    headers: request.headers,
    redirect: "manual",
  });
  return env.ASSETS.fetch(assetRequest);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      try {
        return await handleApi(request, env);
      } catch (err) {
        const message = err instanceof Error ? err.message : "internal error";
        return json({ error: message }, 500);
      }
    }

    if (request.method === "GET" || request.method === "HEAD") {
      return serveWebsite(request, env);
    }

    return new Response("Method not allowed", { status: 405 });
  },
};
