# Build order

Each week has one deliverable that *must demo end-to-end* before moving on.
The line between weeks is intentional — no overlapping work.

## Week 1 — VM and bus

- [ ] `gcloud projects create trade-prod` (or use existing); enable billing.
- [ ] `gcloud services enable compute.googleapis.com pubsub.googleapis.com
      secretmanager.googleapis.com artifactregistry.googleapis.com
      logging.googleapis.com monitoring.googleapis.com`
- [ ] `cd infra/terraform && terraform init && terraform apply`
- [ ] SSH via IAP: `gcloud compute ssh trade --zone us-east4-a --tunnel-through-iap`
- [ ] Verify Docker + Ops Agent up.
- [ ] `docker compose -f infra/docker-compose.vm.yml up -d nats clickhouse`
- [ ] Run a "hello world" C++ container that publishes one message to NATS;
      verify ClickHouse `SELECT 1` works.
- [ ] Apply `infra/supabase/migrations/0001_init.sql` to Supabase.

## Week 2 — Schemas and signer

- [ ] `make proto` regenerates all four language bindings.
- [ ] CI codegen-check is green.
- [ ] `pytest services/python/kalshi-auth/tests/` is green.
- [ ] `python kalshi_signer.py request --base-url https://external-api.demo.kalshi.co
      --path /trade-api/v2/portfolio/balance` returns HTTP 200 from demo.
- [ ] Port the signer to C++ (OpenSSL EVP_DigestSign with RSA_PKCS1_PSS_PADDING,
      mgf1 = SHA256, salt_length = 32). Add round-trip test in C++ that
      verifies a generated signature.

## Week 3 — Kalshi connector + book builder

- [ ] WS subscribes to `markets` channel for a configured market list.
- [ ] REST polls `GET /portfolio/balance` and publishes a `VenueStatus` heartbeat.
- [ ] Book deltas land in NATS at `md.kalshi.<ticker>.book` as `BookDelta` protos.
- [ ] `book-builder` consumes deltas + initial snapshots and emits L2
      snapshots on `state.<market>.book_snapshot` every 100ms.
- [ ] Ticks persist to ClickHouse table `kalshi_book_deltas`.
- [ ] Reconnection test: kill the WS, observe automatic reconnect with
      backoff, verify no message gaps.

## Week 4 — Polymarket US connector

- [ ] Complete KYC + Ed25519 key generation at polymarket.us/developer.
- [ ] `KALSHI_KEY_ID` and `POLY_US_*` go into Secret Manager.
- [ ] `poly-us-connector` authenticates, subscribes to /v1/ws/markets for a
      configured slug list.
- [ ] Book + trade prints land in NATS at `md.poly_us.<slug>.{book,trade}`.
- [ ] Token-bucket throttle verified: synthetic 100-call burst → 5s elapsed time.
- [ ] Dual-venue book test: same conceptual market on both venues; books
      visible side-by-side via NATS subjects.

## Week 5 — Dashboard

- [ ] `pnpm install` at repo root succeeds.
- [ ] `cd apps/web && pnpm dev` boots Next.js at :3000 with placeholder layout.
- [ ] Go service `ws-gateway` fans NATS subjects to browser WSS on :7070.
- [ ] Dashboard subscribes to `md.kalshi.*.book` and `md.poly_us.*.book`
      and renders live L2.
- [ ] `/api/trading-mode` POST persists to Supabase strategy_modes.
- [ ] `/api/kill-switch` POST writes a kill_switch_events row.
- [ ] Kill switch button on the dashboard exercises the route.

## Week 6 — Backtest harness

- [ ] ClickHouse schema for replay: `kalshi_book_deltas`, `kalshi_trades`,
      `poly_us_book_deltas`, `poly_us_trades`.
- [ ] `python -m backtest.replay --from … --to … --strategy yesno_triangle`
      runs end-to-end on captured ticks.
- [ ] PnL accounting uses `backtest/cost_model.py` exactly. The same
      function ports to C++ for live use.
- [ ] Sanity report compares paper PnL to hindsight optimal — gap is what
      live execution will need to capture.

## Week 7 — Strategy 1 (intra-Kalshi YES+NO)

- [ ] Strategy emits `OrderIntent` when `c_yes + c_no > 1 + fees` on any
      Kalshi market.
- [ ] Risk engine approves; executor sends to Kalshi demo.
- [ ] Confirmed fills appear in Supabase `fills` table.
- [ ] Position visible in the dashboard.
- [ ] Promote mode `paper → shadow → live` against a $100 cap.

## Week 8 — Risk engine v1 + chaos tests

- [ ] All pre-trade checks enforced (concentration, banned regex, STP,
      manual indicator, throttle).
- [ ] Reconciler runs every 30s, diffs exchange positions vs Supabase ledger.
- [ ] Kill switch fans cancel-all to both executors in < 2s.
- [ ] Chaos tests in CI:
  - WS disconnect mid-burst (random injection)
  - duplicate fill delivery
  - cancel-after-fill race
  - 429 burst from venue
  - process restart with open orders → state recovers from Supabase
  - wall-clock skew injection
  - VM reboot → orders reconciled before strategies resume

## Week 9 — LLM event matcher

- [ ] `event-matcher` Cloud Run service ingests both venues' market lists
      and proposes pairs.
- [ ] Each pair carries an explicit resolution_source + cutoff_time match
      check; pairs with mismatches go to human review.
- [ ] Pair registry persists to Supabase; live pairs publish to NATS
      `state.<pair_id>.pair`.
- [ ] LLM cost capped at $20/day; if exceeded, fall back to cached pairs.

## Week 10 — Strategy 2 (PM US MM)

- [ ] Identify ≥ 3 long-tail Polymarket US markets with weak existing MM.
- [ ] `mm-engine` quotes both legs with `participateDontInitiate=true`.
- [ ] Markout-at-60s tracker is positive over 3 weeks of paper.
- [ ] Promote to shadow → live $50/market → live $500/market only after
      paper Sharpe ≥ 1.5 and markout consistently positive.

## Week 11 — Strategy 3 (cross-venue locked arb)

- [ ] Uses pair registry from Week 9.
- [ ] Cost model gates: `E[Π] > 2 * stdev(slippage)` and worst-case loss
      ≤ 0.5% of capital.
- [ ] Paper only this week.

## Week 12 — Go live

- [ ] Capital top-up; capital_total_usd in compliance.yaml updated.
- [ ] Strategies promote to live with $1K/market arb caps and $500/market
      MM caps initially.
- [ ] First-PnL retrospective; decide next strategy to develop.
