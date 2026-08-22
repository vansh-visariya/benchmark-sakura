# Sakura API (Cloudflare Worker + D1)

Stores benchmark submissions and serves the live leaderboard and static website on `sakura.vaansh.dev`.

## Architecture

```
User machine                         sakura.vaansh.dev
─────────────                        ──────────────────
sakura run -m MODEL --submit  ──POST──▶  /api/v1/submissions  ──▶  D1
sakura submit results.json    ──POST──▶  /api/v1/submissions  ──▶  D1
Browser (website/)            ──GET───▶  /api/v1/leaderboard  ◀──  D1
Browser                       ──GET───▶  /                     ◀──  static assets
```

One Worker handles both the site and API. Do **not** add a separate Pages project on the same domain — that causes route conflicts.

## Setup

### 1. Install & create D1

```bash
cd workers
npm install
npx wrangler d1 create sakura
```

Copy the `database_id` into `wrangler.toml`.

### 2. Migrate schema

```bash
npm run db:migrate:local   # for wrangler dev
npm run db:migrate         # production
```

### 3. Deploy

```bash
npm run deploy
```

When prompted to update conflicting DNS records, choose **Yes**.

In the Cloudflare dashboard (**Workers → sakura-api → Domains**), keep only the **Production** custom domain. Delete any duplicate **Route** for `sakura.vaansh.dev`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/submissions` | Accept a run result JSON |
| `GET` | `/api/v1/leaderboard?limit=50` | Ranked submissions |
| `GET` | `/api/v1/submissions/:id` | Full submission detail |

## Local dev

```bash
npm run db:migrate:local
npm run dev
```

```bash
# another terminal
cd ..
set SAKURA_DATABASE_URL=http://127.0.0.1:8787
sakura run --model MODEL --tags sql --submit
```

Open `http://127.0.0.1:8787` for the site + API together.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 522 on `/api/*` only | Remove duplicate Worker **Route**; keep Custom Domain only |
| Redirect loop on `/` | Redeploy latest worker (`html_handling = "none"` in wrangler.toml) |
| Empty leaderboard | Run `npm run db:migrate`, then `sakura submit .results/your-run.json` |
