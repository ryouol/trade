// Fixed-point prices in basis points of $1 (1 bp = $0.0001).
// Range: [1, 9999] for tradeable binary contracts (clipped from [0.01, 0.99]).
// Quantities in milli-contracts (1000 = 1 contract).
//
// Float math is forbidden on the hot path; this header is the only place we
// round between protocol-level USD strings and our integer representation.

#pragma once

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace trade {

using PriceBps = std::int32_t;
using QtyMilli = std::int64_t;

constexpr PriceBps kPriceMin = 1;
constexpr PriceBps kPriceMax = 9999;

constexpr PriceBps clip_price(PriceBps p) noexcept {
    return std::clamp(p, kPriceMin, kPriceMax);
}

// Parse a USD price string like "0.55" into bps. Up to 4 decimals supported.
// Throws std::invalid_argument on malformed input.
inline PriceBps parse_price_usd(std::string_view s) {
    // Strict parser: optional leading '0', a '.', then 1-4 decimals.
    if (s.empty()) throw std::invalid_argument("empty price");
    bool seen_dot = false;
    std::int64_t whole = 0;
    std::int64_t frac = 0;
    std::int64_t frac_div = 1;
    int frac_digits = 0;
    for (char c : s) {
        if (c == '.') {
            if (seen_dot) throw std::invalid_argument("two dots in price");
            seen_dot = true;
            continue;
        }
        if (c < '0' || c > '9') throw std::invalid_argument("non-digit in price");
        if (!seen_dot) {
            whole = whole * 10 + (c - '0');
            if (whole > 1) throw std::invalid_argument("price >= 2 not allowed");
        } else {
            if (frac_digits >= 4) throw std::invalid_argument("too many decimals");
            frac = frac * 10 + (c - '0');
            frac_div *= 10;
            frac_digits++;
        }
    }
    // Convert: bps = round_half_up( (whole + frac/frac_div) * 10000 )
    std::int64_t numerator = whole * 10000 * frac_div + frac * 10000;
    std::int64_t bps = (numerator + frac_div / 2) / frac_div;
    if (bps < 0 || bps > 10000)
        throw std::invalid_argument("price out of range");
    return static_cast<PriceBps>(bps);
}

// Render bps as a USD string ("0.55"). Always 4 decimals for round-trip safety.
inline std::string format_price_usd(PriceBps bps) {
    std::int32_t whole = bps / 10000;
    std::int32_t frac = bps % 10000;
    char buf[16];
    int n = std::snprintf(buf, sizeof buf, "%d.%04d", whole, frac);
    return std::string(buf, n);
}

// Parse a Kalshi count (number of contracts) — strings up to 2 decimals.
inline QtyMilli parse_count(std::string_view s) {
    if (s.empty()) throw std::invalid_argument("empty count");
    bool seen_dot = false;
    std::int64_t whole = 0;
    std::int64_t frac = 0;
    int frac_digits = 0;
    for (char c : s) {
        if (c == '.') {
            if (seen_dot) throw std::invalid_argument("two dots in count");
            seen_dot = true;
            continue;
        }
        if (c < '0' || c > '9') throw std::invalid_argument("non-digit in count");
        if (!seen_dot) {
            whole = whole * 10 + (c - '0');
        } else {
            if (frac_digits >= 2) throw std::invalid_argument("too many decimals");
            frac = frac * 10 + (c - '0');
            frac_digits++;
        }
    }
    while (frac_digits < 3) {
        frac *= 10;
        frac_digits++;
    }
    return whole * 1000 + frac;
}

}  // namespace trade
