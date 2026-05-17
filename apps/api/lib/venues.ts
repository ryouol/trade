// Active venues for v1. The canonical compliance list lives in
// infra/config/compliance.yaml in the backend repo; this constant must
// stay in sync. `polymarket_intl` is intentionally absent — geofenced from
// US users and disabled in v1.
export const ACTIVE_VENUES = ["kalshi", "polymarket_us"] as const;
export type Venue = (typeof ACTIVE_VENUES)[number];

export const ACTIVE_VENUE_SET: Set<string> = new Set(ACTIVE_VENUES);

export const TRADING_MODES = ["disabled", "paper", "shadow", "live"] as const;
export type TradingMode = (typeof TRADING_MODES)[number];

export const TRADING_MODE_SET: Set<string> = new Set(TRADING_MODES);
