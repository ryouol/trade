// POST /api/trading-mode
// Body: { strategy: string, mode: "disabled"|"paper"|"shadow"|"live", capital_cap_cents?: number }
// Persists to Supabase strategy_modes table; risk-engine reads on next intent.

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const VALID_MODES = new Set(["disabled", "paper", "shadow", "live"]);

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "missing JSON body" }, { status: 400 });
  }
  const { strategy, mode, capital_cap_cents } = body as Record<string, unknown>;

  if (typeof strategy !== "string" || strategy.length === 0) {
    return NextResponse.json({ error: "strategy required" }, { status: 400 });
  }
  if (typeof mode !== "string" || !VALID_MODES.has(mode)) {
    return NextResponse.json({ error: `mode must be one of ${[...VALID_MODES].join(", ")}` }, { status: 400 });
  }

  const SUPABASE_URL = process.env.SUPABASE_URL;
  const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;
  if (!SUPABASE_URL || !SUPABASE_KEY) {
    return NextResponse.json({ error: "supabase env not configured" }, { status: 500 });
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
  const { error } = await supabase.from("strategy_modes").upsert({
    strategy,
    mode,
    capital_cap_cents: typeof capital_cap_cents === "number" ? capital_cap_cents : 0,
    updated_at: new Date().toISOString(),
    updated_by: req.headers.get("x-actor") ?? "unknown",
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, strategy, mode });
}
