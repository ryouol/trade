-- trade Supabase Postgres schema, v1.
-- Conventions:
--   * Every monetary amount in *cents* (bigint) to avoid float drift.
--   * Every binary qty in *milli-units* (1000 = 1 contract) to match the
--     proto schema.
--   * All timestamps as timestamptz; UUIDs are UUIDv7 (sortable).
--
-- Run with `supabase db push` or apply directly via psql.

create extension if not exists "pgcrypto";
create extension if not exists "uuid-ossp";

-- ---- Venue + market reference ---------------------------------------------

create type venue as enum ('kalshi', 'polymarket_us', 'polymarket_intl');
create type outcome as enum ('yes', 'no');
create type action as enum ('buy', 'sell');
create type role_t as enum ('maker', 'taker');
create type trading_mode as enum ('disabled', 'paper', 'shadow', 'live');
create type order_status as enum (
  'pending', 'submitted', 'accepted', 'rejected',
  'partial_fill', 'filled', 'canceled', 'expired'
);

create table markets (
  id bigserial primary key,
  venue venue not null,
  venue_market_id text not null,        -- ticker (Kalshi) or slug (PM US)
  event_ticker text,
  display_title text,
  resolution_source text,
  close_ts timestamptz,
  created_at timestamptz not null default now(),
  unique (venue, venue_market_id)
);

create index markets_venue_close on markets (venue, close_ts);

-- ---- Trading-mode state machine -------------------------------------------

create table strategy_modes (
  strategy text primary key,
  mode trading_mode not null default 'disabled',
  capital_cap_cents bigint not null default 0,
  updated_at timestamptz not null default now(),
  updated_by text not null default 'system'
);

-- ---- Intents (pre-risk) ----------------------------------------------------

create table intents (
  intent_id uuid primary key,
  strategy text not null,
  market_id bigint not null references markets(id),
  ts timestamptz not null default now(),
  outcome outcome not null,
  action action not null,
  qty_milli bigint not null,
  limit_price_bps integer,        -- null for market orders
  tif text not null,
  signal_snapshot jsonb,
  rationale text
);

create index intents_strategy_ts on intents (strategy, ts desc);

-- ---- Risk decisions --------------------------------------------------------

create table risk_decisions (
  intent_id uuid primary key references intents(intent_id),
  approved boolean not null,
  reason text,
  approved_qty_milli bigint,
  ts timestamptz not null default now()
);

-- ---- Orders sent to venue --------------------------------------------------

create table orders (
  intent_id uuid primary key references intents(intent_id),
  venue venue not null,
  venue_order_id text,            -- assigned on submit
  status order_status not null default 'pending',
  qty_milli bigint not null,
  limit_price_bps integer,
  filled_qty_milli bigint not null default 0,
  avg_fill_price_bps integer,
  total_fee_cents bigint not null default 0,    -- signed; negative = rebate
  submitted_at timestamptz,
  last_update_at timestamptz not null default now(),
  -- venue-specific knobs we recorded for audit
  manual_indicator_automatic boolean,           -- PM US
  stp_type text,                                -- Kalshi
  post_only boolean
);

create index orders_status_ts on orders (status, last_update_at desc);

-- ---- Fills (immutable log) -------------------------------------------------

create table fills (
  id bigserial primary key,
  intent_id uuid not null references intents(intent_id),
  venue venue not null,
  venue_fill_id text not null,
  ts timestamptz not null default now(),
  outcome outcome not null,
  action action not null,
  price_bps integer not null,
  qty_milli bigint not null,
  fee_cents bigint not null,     -- signed; negative = rebate
  is_maker boolean not null,
  unique (venue, venue_fill_id)
);

create index fills_intent on fills (intent_id);

-- ---- Positions (denormalized snapshot, recomputed by reconciler) ----------

create table positions (
  venue venue not null,
  market_id bigint not null references markets(id),
  net_qty_milli bigint not null,
  avg_entry_bps integer,
  realized_pnl_cents bigint not null default 0,
  unrealized_pnl_cents bigint not null default 0,
  last_update_at timestamptz not null default now(),
  primary key (venue, market_id)
);

-- ---- PnL snapshots (timeseries) -------------------------------------------

create table pnl_snapshots (
  ts timestamptz not null default now(),
  total_realized_cents bigint not null,
  total_unrealized_cents bigint not null,
  capital_cents bigint not null,
  realized_by_strategy_json jsonb not null,
  primary key (ts)
);

-- ---- Risk + audit ----------------------------------------------------------

create table risk_alerts (
  id bigserial primary key,
  ts timestamptz not null default now(),
  severity text not null,
  source text not null,
  message text not null,
  related_intent_id uuid,
  related_market_id bigint
);

create table kill_switch_events (
  id bigserial primary key,
  ts timestamptz not null default now(),
  reason text not null,
  actor text not null,
  detail text,
  affected_venues venue[] not null default '{}'
);

create table audit_log (
  id bigserial primary key,
  ts timestamptz not null default now(),
  actor text not null,
  action text not null,
  details jsonb not null
);

-- ---- Reconciliation log ----------------------------------------------------

create table reconciliation_runs (
  id bigserial primary key,
  ts timestamptz not null default now(),
  venue venue not null,
  markets_checked integer not null,
  drift_detected integer not null,
  details jsonb
);

-- ---- News + signals (for audit-from-LLM) ----------------------------------

create table news_signals (
  signal_id text primary key,
  ts timestamptz not null default now(),
  market_id bigint references markets(id),
  delta_p_bps integer not null,
  sigma_bps integer not null,
  horizon_ms bigint not null,
  mechanism text not null,
  confidence_calibration double precision not null,
  source_url text,
  llm_model text
);
