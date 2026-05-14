// kalshi-connector — entrypoint.
//
// Responsibilities (in this order, none yet implemented):
//   1. Read KALSHI_KEY_ID / KALSHI_PRIVATE_KEY_PATH / KALSHI_BASE_URL /
//      KALSHI_WS_URL from env (Secret Manager mounts secrets as files).
//   2. Load the RSA private key. Construct the RSA-PSS-SHA256 signer.
//   3. Open the WS connection at KALSHI_WS_URL. Subscribe to the configured
//      market tickers. Stream book deltas and trade prints into NATS at
//      subjects md.kalshi.<ticker>.{book,trade}.
//   4. Maintain a REST client for order placement against
//      KALSHI_BASE_URL + /trade-api/v2/portfolio/events/orders, signing every
//      request with the three KALSHI-ACCESS-* headers.
//
// For now this binary just verifies the environment is set up and exits.
// Replace with the full event loop once OpenSSL + nats.c are wired through
// Conan in the build.

#include "trade/fixed_point.hpp"

#include <cstdio>
#include <cstdlib>
#include <string>

namespace {

std::string env_or_die(const char* name) {
    const char* v = std::getenv(name);
    if (!v || !*v) {
        std::fprintf(stderr, "error: required env var %s not set\n", name);
        std::exit(2);
    }
    return std::string(v);
}

}  // namespace

int main() {
    const std::string base_url = env_or_die("KALSHI_BASE_URL");
    const std::string ws_url   = env_or_die("KALSHI_WS_URL");
    const std::string key_id   = env_or_die("KALSHI_KEY_ID");
    const std::string pkey_path = env_or_die("KALSHI_PRIVATE_KEY_PATH");

    // Smoke test the price parser so build wiring is verified.
    const auto bps = trade::parse_price_usd("0.5500");
    const auto rendered = trade::format_price_usd(bps);

    std::printf(
        "kalshi-connector boot OK\n"
        "  base_url=%s\n"
        "  ws_url=%s\n"
        "  key_id=%s\n"
        "  pkey_path=%s\n"
        "  parse_price_usd(\"0.5500\") -> %d bps -> %s\n",
        base_url.c_str(), ws_url.c_str(), key_id.c_str(), pkey_path.c_str(),
        bps, rendered.c_str());

    // TODO: open WS, subscribe to markets, publish to NATS, accept REST orders.
    return 0;
}
