export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  ALLOWED_ORIGIN: string;
}

type SubmissionPayload = {
  model: string;
  version: string;
  model_variant?: {
    quantization?: string | null;
    parameter_size?: string | null;
    family?: string | null;
  };
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
  model_quantization: string | null;
  model_parameter_size: string | null;
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

function _safeInt(value: string | null, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
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
  if (!Array.isArray(payload.task_results) || payload.task_results.length === 0) {
    return "task_results must be a non-empty array";
  }

  const passRate = payload.metrics.pass_rate;
  if (typeof passRate !== "number" || passRate < 0 || passRate > 1) {
    return "metrics.pass_rate must be a number between 0 and 1";
  }

  const solvedCount = payload.metrics.solved_count;
  if (typeof solvedCount === "number" && solvedCount < 0) {
    return "metrics.solved_count cannot be negative";
  }

  const taskCount = payload.metrics.task_count;
  if (typeof taskCount === "number" && taskCount <= 0) {
    return "metrics.task_count must be greater than 0";
  }

  const throughput = payload.metrics.throughput_tokens_per_sec;
  if (throughput != null && (typeof throughput !== "number" || throughput < 0)) {
    return "metrics.throughput_tokens_per_sec must be non-negative";
  }

  const ttft = payload.metrics.avg_time_to_first_token_ms;
  if (ttft != null && (typeof ttft !== "number" || ttft < 0)) {
    return "metrics.avg_time_to_first_token_ms must be non-negative";
  }

  const totalTime = payload.metrics.total_time_s;
  if (totalTime != null && (typeof totalTime !== "number" || totalTime < 0)) {
    return "metrics.total_time_s must be non-negative";
  }

  const cpuCores = payload.hardware.cpu_cores;
  if (cpuCores != null && (typeof cpuCores !== "number" || cpuCores <= 0)) {
    return "hardware.cpu_cores must be positive";
  }

  const ramTotal = payload.hardware.ram_total_gb;
  if (ramTotal != null && (typeof ramTotal !== "number" || ramTotal <= 0)) {
    return "hardware.ram_total_gb must be positive";
  }

  const variant = payload.model_variant;
  if (variant != null) {
    if (typeof variant !== "object" || Array.isArray(variant)) {
      return "model_variant must be an object";
    }
    for (const key of ["quantization", "parameter_size", "family"] as const) {
      const value = variant[key];
      if (value != null && typeof value !== "string") {
        return `model_variant.${key} must be a string`;
      }
      if (typeof value === "string" && value.length > 64) {
        return `model_variant.${key} must be at most 64 characters`;
      }
    }
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

async function leaderboard(
  env: Env,
  options: {
    limit?: number;
    offset?: number;
    model?: string;
    sortBy?: string;
    sortOrder?: string;
  } = {}
): Promise<{ entries: LeaderboardRow[]; total_count: number }> {
  const limit = Math.min(Math.max(options.limit ?? 50, 1), 100);
  const offset = Math.max(options.offset ?? 0, 0);
  const model = options.model?.trim() || "";

  const sortCols: Record<string, string> = {
    pass_rate: "pass_rate",
    throughput: "throughput",
    avg_ttft_ms: "avg_ttft_ms",
    created_at: "created_at",
    solved_count: "solved_count",
  };
  const sortCol = sortCols[options.sortBy ?? "pass_rate"] ?? "pass_rate";
  const sortDir = options.sortOrder?.toUpperCase() === "ASC" ? "ASC" : "DESC";

  let whereClause = "";
  const params: unknown[] = [];
  if (model) {
    whereClause = "WHERE model LIKE ?";
    params.push(`%${model}%`);
  }

  const countQuery = `SELECT COUNT(*) as cnt FROM submissions ${whereClause}`;
  const countStmt = env.DB.prepare(countQuery);
  const totalRow = await (params.length ? countStmt.bind(...params) : countStmt).first<{ cnt: number }>();
  const total_count = totalRow?.cnt ?? 0;

  const query = `
    SELECT id, model, pass_rate, solved_count, task_count,
           throughput, avg_ttft_ms, gpu_name, gpu_vram_gb,
           cpu_cores, ram_gb, platform,
           json_extract(payload, '$.model_variant.quantization') as model_quantization,
           json_extract(payload, '$.model_variant.parameter_size') as model_parameter_size,
           created_at
    FROM submissions
    ${whereClause}
    ORDER BY ${sortCol} ${sortDir}, throughput DESC, created_at DESC
    LIMIT ? OFFSET ?
  `;
  const queryParams = [...params, limit, offset];
  const result = await env.DB.prepare(query).bind(...queryParams).all<LeaderboardRow>();

  return { entries: result.results ?? [], total_count };
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
    const viewUrl = `${env.ALLOWED_ORIGIN}/leaderboard?id=${id}`;
    return json({ id, url: viewUrl }, 201, cors);
  }

  if (request.method === "GET" && url.pathname === "/api/v1/leaderboard") {
    const limit = Math.min(_safeInt(url.searchParams.get("limit"), 50), 100);
    const offset = Math.max(_safeInt(url.searchParams.get("offset"), 0), 0);
    const model = url.searchParams.get("model") ?? undefined;
    const sortBy = url.searchParams.get("sort_by") ?? undefined;
    const sortOrder = url.searchParams.get("sort_order") ?? undefined;

    const { entries, total_count } = await leaderboard(env, {
      limit,
      offset,
      model,
      sortBy,
      sortOrder,
    });
    return json({ entries, total_count, offset, limit, updated_at: new Date().toISOString() }, 200, cors);
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
  let assetPath = url.pathname;
  if (assetPath === "/" || assetPath === "/index.html") {
    assetPath = "/index.html";
  } else if (assetPath === "/leaderboard" || assetPath === "/leaderboard/") {
    assetPath = "/leaderboard.html";
  }
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
      const origin = request.headers.get("Origin") ?? env.ALLOWED_ORIGIN;
      const cors = corsHeaders(origin, env.ALLOWED_ORIGIN);
      try {
        return await handleApi(request, env);
      } catch (err) {
        const message = err instanceof Error ? err.message : "internal error";
        return json({ error: message }, 500, cors);
      }
    }

    if (request.method === "GET" || request.method === "HEAD") {
      return serveWebsite(request, env);
    }

    return new Response("Method not allowed", { status: 405 });
  },
};

