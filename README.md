# trade — Polymarket US × Kalshi autonomous trading

Multi-strategy, latency-aware quant trading stack for Kalshi (RSA-PSS,
V2 REST + WS) and Polymarket US (Ed25519, the CFTC-regulated DCM at
`api.polymarket.us`). Hot path in C++, slow path in Python on Cloud Run,
dashboard in Next.js, bus is NATS JetStream on one GCE VM in `us-east4`.

> **Status:** scaffolding. The 12-week build schedule in `docs/build-order.md`
> takes this from empty to a first live PnL gated by paper → shadow → live
> progression with hard risk caps.

---

## Why these venues

- **Kalshi** is the US-regulated event-contracts exchange. RSA-PSS auth, V2
  order endpoints at `POST /portfolio/events/orders`, fee
  `taker = ceil(0.07 × C × p × (1−p))` cents/contract, maker = 25% of taker,
  LIP/VIP maker rebates up to 1% (application-gated, $7K/wk cap).
- **Polymarket US** (`api.polymarket.us`) is the CFTC-regulated DCM/DCO
  that opened public API in February 2026. Ed25519 auth, 23 REST endpoints,
  slug-based market IDs, 20 rps global, **0.30% taker / 0.20% maker
  rebate** — the rebate is what makes MM the structurally most attractive
  strategy here.
- Polymarket international (`clob.polymarket.com`) is geofenced from US
  users and is **disabled in v1**. A stub connector exists; enabling it
  requires `polymarket-intl` in `compliance.allowed_venues` and a
  non-US operating jurisdiction.

---

## Architecture

One GCE VM (`c3-highcpu-8` in `us-east4`, ~$200/mo) runs everything
stateful:

```
                            ┌──────────────────────────────────┐
                            │ Vercel — Next.js dashboard       │
                            └──────────────┬───────────────────┘
                                           │ HTTPS + WSS
                            ┌──────────────┴───────────────────┐
                            ▼                                  ▼
                    Cloud Run (stateless)         GCE VM us-east4
                  ┌────────────────────┐         ┌────────────────────────┐
                  │ event-matcher (LLM)│ Pub/Sub │ ws-gateway (Go)        │
                  │ news-ingestor      │◄───────►│ NATS JetStream         │
                  │ signal-pipeline    │         │ kalshi-connector (C++) │
                  │ backtest-runner    │         │ poly-us-connector (Py) │
                  └─────────┬──────────┘         │ book-builder (C++)     │
                            │                    │ mm-engine (C++)        │
                            ▼                    │ statarb-engine (C++)   │
                  Supabase Postgres ◄────────────│ risk-engine (C++)      │
                                                 │ executor-kalshi (C++)  │
                  GCS (cold parquet) ◄───────────│ executor-poly-us (Py)  │
                                                 │ reconciler (C++)       │
                                                 │ ClickHouse (ticks)     │
                                                 └────────────────────────┘
                                                          │
                                                          ▼
                                                   Kalshi REST + WS + FIX
                                                   Polymarket US REST + WS
```

---

## Trading-mode state machine

Per-strategy mode in Supabase:

```
disabled  → connectors authenticate; no Intents emitted
paper     → Intents emitted; simulated fills against live books
shadow    → Real orders, size = 0 (or demo sandbox); compares
            actual response to paper-mode prediction
live      → Real orders. Capital cap enforced.
            PM US: manualOrderIndicator = MANUAL_ORDER_INDICATOR_AUTOMATIC
            Kalshi: self_trade_prevention_type per strategy
```

Progression for each new strategy:
`disabled → paper (≥ 3 weeks, Sharpe target, markout positive) →
shadow (≥ 1 week, fill-prediction error < 5%) → live $100 → live $1K → scale`.

---

## Strategy ladder

1. **Polymarket US MM (Avellaneda–Stoikov).** Maker rebate flips MM
   from "speculative" to the most attractive structural strategy.
2. **Intra-Kalshi YES+NO triangulation.** Free money when it appears.
   End-to-end smoke test for the pipeline.
3. **Cross-venue locked arb** (Kalshi × Polymarket US). Resolution-
   mismatch ρ accounted for explicitly.
4. **Kalshi MM.** Requires earning LIP/VIP rebate tier.
5. **OU stat-arb** on matched pairs (half-life ≤ 12 h).
6. **LLM news directional** with transmission-mechanism gating.
7. **Smart-wallet copy** — deferred (PM US is centralized; no on-chain
   visibility).

---

## Math

**Fair value (precision-weighted Bayes):**
```
v_t  = (Σ τ_i v_i) / (Σ τ_i),   σ_t² = 1 / (Σ τ_i)
```
Inputs: microprice, OFI (Cont/Kukanov/Stoikov), LLM news, smart-wallet (intl),
cross-venue microprice. EWMA vol (λ=0.94).

**Avellaneda–Stoikov, binary-adapted:**
```
r_t = v_t − q γ σ² (T−t)
δ*  = (1/γ) ln(1 + γ/κ) + γ σ² (T−t) / 2
bid = clip(r_t − δ*, 0.01, 0.99)
ask = clip(r_t + δ*, 0.01, 0.99)
```
Widen extra when `|c − 0.5| > 0.4` (boundary adverse selection).

**OU pair trading:**
```
ADF → AR(1) fit of x_{t+Δt} − x_t = α + β x_t + ε
θ = −β/Δt,  μ = −α/β,  σ² = Var(ε)/Δt
halflife τ = ln(2)/θ      — reject pair if τ > 12 h
σ_x = σ / √(2θ),  z = (x − μ)/σ_x
Entry |z|>2, exit |z|<0.5, stop |z|>4 or t > 2τ
```

**Cost model (per round-trip):**
```
PM US:  taker = 30 bps,   maker = −20 bps (rebate)
Kalshi: taker_per_contract = ceil(0.07 c (1−c) × 100) cents
        maker_per_contract = 0.25 × taker  (plus LIP/VIP rebate if earned)
Slippage S = depth-aware book walk at target size
Carry ρ = K · r_f · Δt / 365
Trade only if E[Π] > 2 · stdev(S)
```

**Resolution mismatch:**
```
E[Π] = ρ · Π_match + (1 − ρ) · Π_mismatch    ρ ∈ [0.95, 0.99]
Worst-case loss Π_mismatch · size must be ≤ 0.5% of capital
```

**Portfolio VaR:**
```
Monte Carlo N = 10000 joint resolutions every 5 minutes
Hard cap VaR_99 ≤ 15% capital → auto-deleverage at 18%
```

---

## Risk + compliance (non-negotiable)

### Pre-trade checks (deterministic; no LLM in this path)

- Position concentration ≤ 5%/market, ≤ 15%/resolution-source.
- Order size ≤ `min(half-Kelly · capital, 5% · capital, mode-cap)`.
- `compliance.banned_markets` regex match → reject.
- `compliance.allowed_venues` must include the target venue, or refuse to boot.
- All PM US orders: `manualOrderIndicator = MANUAL_ORDER_INDICATOR_AUTOMATIC`.
- All Kalshi orders carry an explicit `self_trade_prevention_type`
  (`taker_at_cross` for MM, `maker` for taker strategies) and a
  `client_order_id` for idempotent retries.
- Per-venue token-bucket throttle: PM US 20 rps, Kalshi per tier.

### Real-time

- Markout-at-60s rolling tracker per strategy → auto-pause when
  `markout < −0.5 × captured_spread` for 1 hour.
- 3+ adverse fills in same direction within 5 min → auto-pause.
- `reconciler` diffs exchange positions vs ledger every 30 s; drift > 1
  contract → alert + auto-pause writes on that market.

### Kill switch (dashboard + auto)

Auto-triggers: connector heartbeat loss > 15 s, ClickHouse write lag > 60 s,
risk-engine crash (systemd watchdog), 24h drawdown > 4% capital, VaR_99 > 18%.

### Chaos tests (CI + nightly)

WS disconnect mid-burst · duplicate fill delivery · cancel-after-fill race ·
429 burst · process restart with open orders · wall-clock skew · VM reboot.

---

## Repo layout

```
trade/
├── apps/
│   ├── web/                       # Next.js dashboard → Vercel
│   └── api/                       # Next.js API routes (mode, kill-switch)
├── services/
│   ├── cpp/                       # hot path
│   │   ├── common/
│   │   ├── kalshi-connector/
│   │   ├── book-builder/
│   │   ├── mm-engine/
│   │   ├── statarb-engine/
│   │   ├── risk-engine/
│   │   ├── executor-kalshi/
│   │   └── reconciler/
│   ├── go/
│   │   └── ws-gateway/
│   └── python/
│       ├── kalshi-auth/           # RSA-PSS signer + tests
│       ├── poly-us-connector/     # official polymarket-us SDK + NATS
│       ├── event-matcher/         # → Cloud Run
│       ├── news-ingestor/         # → Cloud Run
│       └── signal-pipeline/       # → Cloud Run
├── packages/
│   ├── schemas/proto/             # protobuf — single source of truth
│   ├── ui/                        # shared React components
│   └── tsconfig/
├── research/
│   ├── backtest/                  # the math, runnable in Python
│   ├── notebooks/                 # scratchpad
│   └── data/                      # parquet samples (gitignored)
├── infra/
│   ├── terraform/                 # GCE VM, IAM, Pub/Sub
│   ├── systemd/                   # *.service units
│   ├── docker-compose.vm.yml      # everything on the VM
│   ├── cloudrun/                  # Cloud Run YAMLs
│   ├── config/                    # compliance.yaml, strategy.yaml
│   └── supabase/migrations/
├── tools/codegen/                 # protoc → C++/Go/Py/TS
├── .github/workflows/             # CI: build, codegen-check, deploy
├── docs/                          # build-order, runbook
├── CLAUDE.md                      # agent guidance for future sessions
└── README.md
```

---

## Quickstart

```bash
# Tooling
brew install pnpm protobuf cmake clickhouse gcloud terraform uv
uv sync && pnpm install

# Codegen
make proto

# Local dev (VM-style, on your laptop)
docker compose -f infra/docker-compose.vm.yml up -d nats clickhouse

# Kalshi auth smoke test (demo)
uv run python services/python/kalshi-auth/kalshi_signer.py \
  --key-id "$KALSHI_KEY_ID" \
  --private-key-pem ~/.kalshi/private.pem \
  --base-url https://external-api.demo.kalshi.co \
  --method GET --path /trade-api/v2/portfolio/balance

# Run the math tests
uv run pytest research/backtest/

# Backtest the intra-Kalshi triangulation strategy on historical ticks
uv run python research/backtest/run.py \
  --strategy yesno_triangle --venue kalshi \
  --start 2026-04-01 --end 2026-05-01
```

---

## What this README does not do

- Hand-wave on regulatory risk. Polymarket international is geofenced
  from US users and is disabled in v1. Sports on Kalshi remain contested
  state-by-state. KYC is required at both venues.
- Promise alpha. The market is hard. The median cross-venue arb spread is
  0.3% and the mean window is 2.7 s. You will lose money before you make
  any. The trading-mode state machine and risk caps exist to keep the
  loss bounded while the learning compounds.
