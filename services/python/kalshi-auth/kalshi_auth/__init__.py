"""Kalshi RSA-PSS request signing.

Kalshi API requests authenticate with three headers:

    KALSHI-ACCESS-KEY        — your API key id
    KALSHI-ACCESS-TIMESTAMP  — request time in unix milliseconds
    KALSHI-ACCESS-SIGNATURE  — base64( RSA-PSS-SHA256( ts || METHOD || path_no_query ) )

Salt length equals the SHA-256 digest length (32 bytes). The private key is a
2048-bit RSA key (PKCS#8 PEM). The path is the URL path component only,
without query string.

References:
  https://docs.kalshi.com/getting_started/api_keys
  https://github.com/Kalshi/kalshi-starter-code-python/blob/main/clients.py
"""

from .signer import KalshiSigner, SignedHeaders, sign_pss

__all__ = ["KalshiSigner", "SignedHeaders", "sign_pss"]
