// Placeholder dashboard. Live data wiring lands in Week 5 (ws-gateway → SSE
// or browser WSS). For now this just renders the static layout so we know
// the toolchain is healthy.

export default function HomePage() {
  return (
    <main style={{ padding: "2rem", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h1 style={{ margin: 0, fontSize: "1.5rem" }}>
          trade <span className="muted" style={{ fontSize: "0.9rem" }}>· control plane</span>
        </h1>
        <button className="kill" type="button" aria-label="Kill switch">
          KILL SWITCH
        </button>
      </header>

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        Polymarket US (DCM, Ed25519) × Kalshi (RSA-PSS V2). Stack is scaffolded —
        live data wiring lands in Week 5.
      </p>

      <section className="grid" style={{ marginTop: "1.5rem", gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Trading modes</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr className="muted">
                <th align="left">Strategy</th>
                <th align="left">Mode</th>
                <th align="right">Cap</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>yesno_triangle_kalshi</td><td>disabled</td><td align="right">$0</td></tr>
              <tr><td>mm_polyus</td><td>disabled</td><td align="right">$0</td></tr>
              <tr><td>cross_arb</td><td>disabled</td><td align="right">$0</td></tr>
              <tr><td>statarb_ou</td><td>disabled</td><td align="right">$0</td></tr>
              <tr><td>llm_news_directional</td><td>disabled</td><td align="right">$0</td></tr>
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Risk</h2>
          <dl style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.25rem" }}>
            <dt className="muted">Capital</dt><dd style={{ margin: 0 }}>—</dd>
            <dt className="muted">VaR<sub>99</sub></dt><dd style={{ margin: 0 }}>—</dd>
            <dt className="muted">24h drawdown</dt><dd style={{ margin: 0 }}>—</dd>
            <dt className="muted">Connectors</dt><dd style={{ margin: 0 }}>—</dd>
          </dl>
        </div>

        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Books</h2>
          <p className="muted">
            (book widget — live L2 from kalshi-connector + poly-us-connector via ws-gateway)
          </p>
        </div>
      </section>
    </main>
  );
}
