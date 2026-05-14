#!/usr/bin/env python3
"""CLI wrapper around the Kalshi signer.

Examples:
  # Generate a test key pair (for local development only)
  python kalshi_signer.py keygen --out ~/.kalshi/private.pem

  # Sign a request and print headers
  python kalshi_signer.py sign \\
      --key-id $KALSHI_KEY_ID \\
      --private-key-pem ~/.kalshi/private.pem \\
      --method GET --path /trade-api/v2/portfolio/balance

  # End-to-end: hit the demo balance endpoint
  python kalshi_signer.py request \\
      --key-id $KALSHI_KEY_ID \\
      --private-key-pem ~/.kalshi/private.pem \\
      --base-url https://external-api.demo.kalshi.co \\
      --method GET --path /trade-api/v2/portfolio/balance
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import typer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_auth import KalshiSigner

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def keygen(
    out: Path = typer.Option(..., "--out", help="Path to write private key PEM"),
    bits: int = typer.Option(2048, "--bits", help="RSA key size"),
) -> None:
    """Generate a 2048-bit RSA private key in PKCS#8 PEM. For local dev only."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        typer.echo(f"Refusing to overwrite existing key at {out}", err=True)
        raise typer.Exit(1)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    out.write_bytes(pem)
    out.chmod(0o600)
    typer.echo(f"Wrote {bits}-bit RSA private key to {out}")


@app.command()
def sign(
    key_id: str = typer.Option(..., "--key-id"),
    private_key_pem: Path = typer.Option(..., "--private-key-pem"),
    method: str = typer.Option("GET", "--method"),
    path: str = typer.Option(..., "--path"),
    timestamp_ms: int | None = typer.Option(None, "--timestamp-ms"),
) -> None:
    """Sign a request and print the three Kalshi headers as JSON."""
    signer = KalshiSigner(key_id=key_id, private_key_pem=private_key_pem)
    headers = signer.sign(method=method, path=path, timestamp_ms=timestamp_ms)
    typer.echo(json.dumps(headers.to_dict(), indent=2))


@app.command()
def request(
    key_id: str = typer.Option(..., "--key-id"),
    private_key_pem: Path = typer.Option(..., "--private-key-pem"),
    base_url: str = typer.Option(
        "https://external-api.demo.kalshi.co",
        "--base-url",
        help="Use demo by default; production reads from KALSHI_BASE_URL env",
    ),
    method: str = typer.Option("GET", "--method"),
    path: str = typer.Option(..., "--path"),
    body: str | None = typer.Option(None, "--body", help="JSON body for POST/PUT"),
    timeout: float = typer.Option(10.0, "--timeout"),
) -> None:
    """Sign and send a request, printing status + body."""
    signer = KalshiSigner(key_id=key_id, private_key_pem=private_key_pem)
    headers = signer.sign(method=method, path=path).to_dict()
    headers["Content-Type"] = "application/json"
    url = base_url.rstrip("/") + path
    json_body = json.loads(body) if body else None
    with httpx.Client(timeout=timeout) as client:
        resp = client.request(method=method.upper(), url=url, headers=headers, json=json_body)
    typer.echo(f"HTTP {resp.status_code}")
    typer.echo(resp.text)
    if resp.status_code >= 400:
        sys.exit(1)


if __name__ == "__main__":
    app()
