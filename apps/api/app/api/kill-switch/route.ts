// POST /api/kill-switch
// Body: { reason: string, detail?: string, affected_venues?: string[] }
// Writes a kill_switch_events row; the risk-engine watches this table and
// fans the cancel-all out to both executors.

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const ALLOWED_VENUES = new Set(["kalshi", "polymarket_us", "polymarket_intl"]);

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "missing JSON body" }, { status: 400 });
  }
  const { reason, detail, affected_venues } = body as Record<string, unknown>;

  if (typeof reason !== "string" || reason.length === 0) {
    return NextResponse.json({ error: "reason required" }, { status: 400 });
  }
  const venues = Array.isArray(affected_venues)
    ? affected_venues.filter((v): v is string => typeof v === "string" && ALLOWED_VENUES.has(v))
    : ["kalshi", "polymarket_us"];

  const SUPABASE_URL = process.env.SUPABASE_URL;
  const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;
  if (!SUPABASE_URL || !SUPABASE_KEY) {
    return NextResponse.json({ error: "supabase env not configured" }, { status: 500 });
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
  const { data, error } = await supabase
    .from("kill_switch_events")
    .insert({
      reason,
      actor: req.headers.get("x-actor") ?? "manual:dashboard",
      detail: typeof detail === "string" ? detail : null,
      affected_venues: venues,
    })
    .select("id, ts")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, event: data });
}
