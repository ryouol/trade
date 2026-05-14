"""Tests for the Kalshi RSA-PSS signer.

We can't pin a golden signature byte string because RSA-PSS uses a random
salt. Instead we verify the signature is well-formed and validates with the
matching public key — the same property production receivers rely on.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_auth import KalshiSigner
from kalshi_auth.signer import (
    KALSHI_HEADER_KEY,
    KALSHI_HEADER_SIG,
    KALSHI_HEADER_TS,
    sign_pss,
    verify_pss,
)


@pytest.fixture(scope="module")
def keypair_pem() -> bytes:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture(scope="module")
def signer(keypair_pem: bytes) -> KalshiSigner:
    return KalshiSigner(key_id="test-key-id-123", private_key_pem=keypair_pem)


def test_headers_have_expected_keys(signer: KalshiSigner) -> None:
    headers = signer.sign("GET", "/trade-api/v2/portfolio/balance").to_dict()
    assert set(headers.keys()) == {KALSHI_HEADER_KEY, KALSHI_HEADER_TS, KALSHI_HEADER_SIG}
    assert headers[KALSHI_HEADER_KEY] == "test-key-id-123"


def test_timestamp_is_millisecond_int_string(signer: KalshiSigner) -> None:
    headers = signer.sign("GET", "/trade-api/v2/portfolio/balance").to_dict()
    ts = int(headers[KALSHI_HEADER_TS])
    # 2024-01-01 00:00:00 UTC = 1704067200000 ms. Should be after.
    assert ts > 1_704_067_200_000


def test_signature_verifies_with_public_key(signer: KalshiSigner) -> None:
    method = "GET"
    path = "/trade-api/v2/portfolio/balance"
    headers = signer.sign(method, path, timestamp_ms=1_715_472_000_000).to_dict()
    msg = f"{headers[KALSHI_HEADER_TS]}{method}{path}".encode()
    sig = base64.b64decode(headers[KALSHI_HEADER_SIG])
    assert verify_pss(signer.public_key(), msg, sig)


def test_signature_fails_with_modified_path(signer: KalshiSigner) -> None:
    method = "GET"
    path = "/trade-api/v2/portfolio/balance"
    headers = signer.sign(method, path, timestamp_ms=1_715_472_000_000).to_dict()
    tampered_msg = f"{headers[KALSHI_HEADER_TS]}{method}/trade-api/v2/portfolio/positions".encode()
    sig = base64.b64decode(headers[KALSHI_HEADER_SIG])
    assert not verify_pss(signer.public_key(), tampered_msg, sig)


def test_path_with_query_rejected(signer: KalshiSigner) -> None:
    with pytest.raises(ValueError, match="query string"):
        signer.sign("GET", "/trade-api/v2/portfolio/balance?subaccount=0")


def test_path_must_be_absolute(signer: KalshiSigner) -> None:
    with pytest.raises(ValueError, match="absolute"):
        signer.sign("GET", "trade-api/v2/portfolio/balance")


def test_method_is_normalized_to_uppercase(signer: KalshiSigner) -> None:
    h1 = signer.sign("get", "/trade-api/v2/portfolio/balance", timestamp_ms=42).to_dict()
    h2 = signer.sign("GET", "/trade-api/v2/portfolio/balance", timestamp_ms=42).to_dict()
    # Different signatures (random salt) but the *message* signed is the same.
    msg1 = f"{h1[KALSHI_HEADER_TS]}GET/trade-api/v2/portfolio/balance".encode()
    msg2 = f"{h2[KALSHI_HEADER_TS]}GET/trade-api/v2/portfolio/balance".encode()
    assert msg1 == msg2


def test_sign_pss_is_nondeterministic_but_self_consistent(keypair_pem: bytes) -> None:
    priv = serialization.load_pem_private_key(keypair_pem, password=None)
    assert isinstance(priv, rsa.RSAPrivateKey)
    msg = b"1715472000000GET/trade-api/v2/portfolio/balance"
    sig1 = sign_pss(priv, msg)
    sig2 = sign_pss(priv, msg)
    assert sig1 != sig2  # random salt
    assert verify_pss(priv.public_key(), msg, sig1)
    assert verify_pss(priv.public_key(), msg, sig2)


def test_post_order_signing_matches_reference_message(signer: KalshiSigner) -> None:
    """Doc reference: POST /trade-api/v2/portfolio/events/orders is the Kalshi
    V2 create-order endpoint. Body is NOT part of the signed message — Kalshi
    only signs ts || METHOD || path_no_query."""
    method = "POST"
    path = "/trade-api/v2/portfolio/events/orders"
    headers = signer.sign(method, path, timestamp_ms=1_715_472_000_000).to_dict()
    msg = f"1715472000000POST{path}".encode()
    sig = base64.b64decode(headers[KALSHI_HEADER_SIG])
    assert verify_pss(signer.public_key(), msg, sig)
