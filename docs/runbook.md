# Runbook

Operational procedures for the trading stack. Keep this short and direct —
if you're reading it during an incident, you don't want to scroll.

## Daily checks (first thing in the morning)

1. Dashboard loads. Connector heartbeats green.
2. Realized PnL is reconciled to within $0.01 of exchange-reported totals.
3. `var_99` is below the soft cap (15% of capital).
4. No `risk_alerts` rows of severity ≥ WARN since last check.
5. UMA-dispute watcher (only relevant if PM intl ever enabled) reports zero.

## Promoting a strategy

`disabled → paper → shadow → live $100 → live $1K → scale`

You may only advance one step at a time. Each step has a gate:

| From → To              | Gate                                                  |
|------------------------|-------------------------------------------------------|
| disabled → paper       | Math primitives unit-tested green                     |
| paper → shadow         | ≥ 3 wks paper, Sharpe target, markout-at-60s positive |
| shadow → live $100     | ≥ 1 wk shadow, fill-prediction error < 5%             |
| live $100 → live $1K   | 2 wks at $100 cap with PnL within paper ± 1σ          |
| live $1K → scale       | 4 wks at $1K cap, no markout drift                    |

Promotion command:

```bash
curl -X POST https://your-domain/api/trading-mode \
  -H 'content-type: application/json' \
  -d '{"strategy":"mm_polyus","mode":"live","capital_cap_cents":100000}'
```

## Kill switch

**Manual:** dashboard → red KILL SWITCH button. Or:

```bash
curl -X POST https://your-domain/api/kill-switch \
  -H 'content-type: application/json' \
  -H 'x-actor: manual:<you>@<domain>' \
  -d '{"reason":"<why>","affected_venues":["kalshi","polymarket_us"]}'
```

**Automatic** triggers (no action required, but you must investigate):

- Connector heartbeat loss > 15 s on either venue
- ClickHouse write lag > 60 s
- Risk-engine crash (systemd watchdog)
- 24h realized drawdown > 4% of capital
- VaR_99 > 18% of capital (3% above the soft cap)

When the kill switch fires:

1. Confirm cancel-all completed on both venues (dashboard shows 0 open orders).
2. Read `kill_switch_events` for the reason.
3. Read `risk_alerts` for the 10 minutes before the event for context.
4. Reconcile positions: `reconciliation_runs` should show no drift.
5. Do not flip strategies back to `live` until the root cause is documented
   in `docs/incidents/<date>.md` and addressed.

## Common operations

### Deploy a single service to the VM

```bash
gh workflow run deploy-vm.yml \
  -f service=poly-us-connector \
  -f tag=<commit-sha>
```

### Tail logs

```bash
# All trading containers
gcloud compute ssh trade --zone us-east4-a --tunnel-through-iap \
  -- 'docker compose -f /opt/trade/compose/docker-compose.vm.yml logs -f'

# Cloud Logging (Cloud Run + VM Ops Agent)
gcloud logging tail "resource.labels.instance_id=$(gcloud compute instances describe trade --zone us-east4-a --format='value(id)')"
```

### Rotate Kalshi API key

1. Generate new key at kalshi.com → API.
2. Update Secret Manager: `gcloud secrets versions add kalshi-private-key --data-file=new-private.pem`.
3. Restart connector: `docker compose restart kalshi-connector` over IAP SSH.
4. Verify heartbeat green.
5. Revoke old key in Kalshi UI.

### Rotate Polymarket US API key

1. Generate new key pair at polymarket.us/developer.
2. Update Secret Manager: `gcloud secrets versions add poly-us-secret --data-file=<base64-secret>`.
3. Restart `docker compose restart poly-us-connector`.

## Incident review template

After any kill switch or production bug, create `docs/incidents/YYYY-MM-DD.md`:

```
## Summary
1 sentence: what broke, what we did, what the impact was.

## Timeline (UTC)
- HH:MM:SS — first symptom (link to log line / dashboard screenshot)
- HH:MM:SS — alert fired / kill switch tripped
- HH:MM:SS — manual action
- HH:MM:SS — service restored

## Root cause
Specific failure mode + the code/config path that allowed it.

## What helped
Detection, mitigation, automation that worked.

## What slowed us down
Specific. No platitudes.

## Action items
[ ] owner / due-date — concrete change.
```

The point of this file is the action items. If you have none, the review
is incomplete.

## Capital top-up procedure

1. Deposit USDC to Polymarket US wallet and/or wire to Kalshi.
2. Wait for funds to settle and appear in venue balance.
3. Update `capital_total_usd` in `infra/config/compliance.yaml`. Commit, PR, merge.
4. CI applies via `deploy-vm.yml` → risk-engine reloads on next intent.
5. Sanity check: dashboard `Capital` line matches new total.
