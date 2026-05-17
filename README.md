# trade — dashboard (frontend)

Next.js 15 dashboard for the Polymarket × Kalshi autonomous trading system.
Deployed on Vercel. The **backend** (C++ services, Python signals, infra,
schemas, research) lives in the sibling repo
[`ryouol/Trade-backend`](https://github.com/ryouol/Trade-backend) and runs
on GCP.

## What this app does

- Live order books from Kalshi + Polymarket via WSS to the backend's
  `ws-gateway` (running on the GCE VM).
- Read-only views of positions, fills, PnL, and risk alerts from
  Supabase Postgres (the same DB the risk-engine writes to).
- Two privileged endpoints under `apps/api`:
  - `POST /api/trading-mode` — flip a strategy between
    `disabled | paper | shadow | live`.
  - `POST /api/kill-switch` — emergency cancel-all on both venues.
- Big red KILL SWITCH button on the dashboard.

## Repo layout

```
trade/
├── apps/
│   ├── web/                # Next.js dashboard
│   └── api/                # Next.js API routes (mode toggle, kill switch)
├── package.json            # pnpm + turbo root
├── pnpm-workspace.yaml
├── turbo.json
├── vercel.json             # Vercel monorepo build config
└── .github/workflows/
    └── web.yml             # lint + typecheck + build on PR
```

## Quickstart

```bash
pnpm install
pnpm dev                    # apps/web on :3000, apps/api on :3001
```

Environment variables expected by `apps/web` and `apps/api`:

| Var                     | Purpose                                         |
|-------------------------|-------------------------------------------------|
| `SUPABASE_URL`          | Supabase project URL                            |
| `SUPABASE_SERVICE_KEY`  | service_role key — server-side only            |
| `NEXT_PUBLIC_WS_GATEWAY_URL` | wss://… — your ws-gateway endpoint        |
| `NEXT_PUBLIC_VENUE_KALSHI_ENABLED` | "true"/"false"                       |
| `NEXT_PUBLIC_VENUE_POLY_ENABLED`   | "true"/"false"                       |

Drop these into `.env.local` for dev, or Vercel project settings for
production.

## Deploy

Vercel auto-deploys on push to `main` once the repo is linked:

```bash
vercel link              # one-time
vercel env pull          # sync .env.local from Vercel
vercel --prod            # manual production deploy
```

The Vercel project's **Root Directory** is set to `apps/web` (configured
when we ran `vercel link` from inside `apps/web`). Vercel auto-detects
Next.js, runs `pnpm install`, then `next build`. No `vercel.json` is
required.

## Backend coordinates

- Repo: https://github.com/ryouol/Trade-backend
- Runs on: GCE VM `trade` in `us-east4` + Cloud Run for slow-path
- Bus: NATS JetStream on the VM (fan-out to browser via `ws-gateway`)
- DB: Supabase Postgres (shared with this frontend, read-mostly)
