# CLAUDE.md

Agent guidance for future Claude Code / Codex / Copilot sessions on this repo.

## What this repo is

Multi-strategy autonomous trading system for **Kalshi** (RSA-PSS auth,
V2 orders at `POST /portfolio/events/orders`) and **Polymarket US** at
`api.polymarket.us` (Ed25519 auth, 23 REST endpoints, slug-based market IDs,
20 rps global). The architecture, math, and 12-week schedule are in
`README.md` and `docs/build-order.md`. Read both before making changes.

Polymarket international (`clob.polymarket.com`) is **disabled** in v1. Do
not write code that authenticates there unless `compliance.allowed_venues`
explicitly includes `polymarket-intl`.

## Non-negotiables

1. **Schemas are the single source of truth.** Any field crossing a service
   boundary lands first in `packages/schemas/proto/*.proto`, then codegen
   runs (`make proto`), then services consume the generated types. Never
   inline a JSON dict across services. The `codegen-check.yml` CI job fails
   the build on stale codegen.

2. **The risk engine has veto power.** No strategy talks to an executor
   directly. Every order flows `Intent → risk.approved/rejected → Order`.
   The risk engine is in `services/cpp/risk-engine/`.

3. **Trading-mode state machine.** Each strategy is in one of
   `disabled | paper | shadow | live`. State lives in Supabase and is read
   by the executor on every order. Changing modes requires the
   `/api/trading-mode` route — never bypass.

4. **Order-construction invariants** the risk engine enforces:
   - Every PM US order: `manualOrderIndicator = MANUAL_ORDER_INDICATOR_AUTOMATIC`.
   - Every Kalshi V2 order: explicit `self_trade_prevention_type` and
     `client_order_id`.
   - Every order has an `intent_id` traceable back to the originating
     signal snapshot in Supabase.

5. **Latency budget.** C++ hot-path services must not allocate in steady
   state. Use `boost::lockfree::spsc_queue` between threads. No
   `std::shared_ptr` on the hot path. No `std::cout` — use the structured
   log buffer that ships to Cloud Logging asynchronously. No `std::regex`
   on the hot path — pre-compile to `flat_hash_map`.

6. **The cost model is not optional.** Every strategy go/no-go calls
   `research/backtest/cost_model.py` (or its C++ port) with the live book,
   intended size, and current fee schedule. If the strategy can't justify
   it in writing, it doesn't run.

7. **Compliance config is load-bearing.** `infra/config/compliance.yaml`
   lists allowed venues, banned-market regex, and position-limit overrides.
   The risk engine refuses to start if the venue list is empty or the file
   is missing. Edits go through PR review.

## Conventions

- **C++17.** CMake + Conan. clang-format from `.clang-format`. Prefer
  `std::expected` over exceptions on the hot path.
- **Go 1.22+.** `go vet`, `golangci-lint`, errors wrapped with `%w`.
- **Python 3.11+.** Managed by `uv`. `mypy --strict`. `ruff format` +
  `ruff check`.
- **TS 5.4+.** Next.js 15 App Router. React Server Components by default.
- **Protobuf 3.** Field IDs never reused. No `oneof` overloading.
- **Tests** live in `tests/` next to source. Integration tests in
  `tests/integration/` run against the dockerized stack.

## Copilot / Cursor / Codex guardrails

- Don't generate code that calls live endpoints in tests. Use
  `KALSHI_DEMO_BASE_URL` / `POLY_US_PAPER_MODE` env flags.
- Don't widen `risk-engine` thresholds without a comment citing the
  empirical evidence (markout numbers, paper PnL window, etc.).
- Don't add a new proto field without updating codegen output and the
  consumer on the other side in the same PR.
- Authentication helpers are sensitive code. Changes to the Kalshi RSA-PSS
  signer or the PM US Ed25519 wrapper need test vectors.

## Useful commands

```bash
make proto              # regenerate protobuf types for C++/Go/Py/TS
make build-cpp          # build all C++ services into Docker
make build-go           # build all Go services
make test               # run all tests
docker compose -f infra/docker-compose.vm.yml up -d   # local VM stack
gcloud auth login && gcloud config set project <id>
```
