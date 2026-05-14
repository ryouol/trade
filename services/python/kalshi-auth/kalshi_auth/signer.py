"""RSA-PSS-SHA256 signer for Kalshi API requests."""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

KALSHI_HEADER_KEY: Final[str] = "KALSHI-ACCESS-KEY"
KALSHI_HEADER_TS: Final[str] = "KALSHI-ACCESS-TIMESTAMP"
KALSHI_HEADER_SIG: Final[str] = "KALSHI-ACCESS-SIGNATURE"


@dataclass(frozen=True, slots=True)
class SignedHeaders:
    """The three headers Kalshi requires on every authenticated request."""

    access_key: str
    timestamp_ms: str
    signature_b64: str

    def to_dict(self) -> dict[str, str]:
        return {
            KALSHI_HEADER_KEY: self.access_key,
            KALSHI_HEADER_TS: self.timestamp_ms,
            KALSHI_HEADER_SIG: self.signature_b64,
        }


def _load_private_key(pem_or_path: str | Path | bytes) -> rsa.RSAPrivateKey:
    """Load an RSA private key from PEM bytes, a path, or env-var content."""
    if isinstance(pem_or_path, (str, Path)):
        p = Path(pem_or_path)
        if p.is_file():
            data = p.read_bytes()
        else:
            data = str(pem_or_path).encode()
    else:
        data = pem_or_path
    key: PrivateKeyTypes = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError(f"Expected RSA private key, got {type(key).__name__}")
    return key


def sign_pss(private_key: rsa.RSAPrivateKey, message: bytes) -> bytes:
    """Sign `message` with RSA-PSS(SHA-256), MGF1(SHA-256), salt = digest_length.

    Kalshi requires salt length equal to the digest (32 bytes for SHA-256).
    """
    return private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256.digest_size,
        ),
        hashes.SHA256(),
    )


class KalshiSigner:
    """Stateful signer bound to one API key.

    Usage:
        signer = KalshiSigner(key_id="abc123", private_key_pem=open("priv.pem","rb").read())
        headers = signer.sign("GET", "/trade-api/v2/portfolio/balance")
        httpx.get(base_url + "/trade-api/v2/portfolio/balance", headers=headers.to_dict())
    """

    def __init__(self, key_id: str, private_key_pem: str | Path | bytes) -> None:
        if not key_id:
            raise ValueError("key_id is empty")
        self._key_id = key_id
        self._private_key = _load_private_key(private_key_pem)

    @classmethod
    def from_env(cls) -> "KalshiSigner":
        """Build a signer from KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH."""
        key_id = os.environ.get("KALSHI_KEY_ID")
        if not key_id:
            raise RuntimeError("KALSHI_KEY_ID env var not set")
        pem_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
        if not pem_path:
            raise RuntimeError("KALSHI_PRIVATE_KEY_PATH env var not set")
        return cls(key_id=key_id, private_key_pem=pem_path)

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(
        self,
        method: str,
        path: str,
        *,
        timestamp_ms: int | None = None,
    ) -> SignedHeaders:
        """Sign a request. `path` must NOT include query string."""
        if "?" in path:
            raise ValueError("path must not contain a query string")
        if not path.startswith("/"):
            raise ValueError(f"path must be absolute, got {path!r}")
        method = method.upper()
        ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        message = f"{ts}{method}{path}".encode()
        sig = sign_pss(self._private_key, message)
        return SignedHeaders(
            access_key=self._key_id,
            timestamp_ms=str(ts),
            signature_b64=base64.b64encode(sig).decode(),
        )

    def public_key(self) -> rsa.RSAPublicKey:
        return self._private_key.public_key()


def verify_pss(public_key: rsa.RSAPublicKey, message: bytes, signature: bytes) -> bool:
    """Verify an RSA-PSS-SHA256 signature with matching parameters. Test helper."""
    from cryptography.exceptions import InvalidSignature

    try:
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256.digest_size,
            ),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False
