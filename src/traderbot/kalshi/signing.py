"""RSA-PSS request signing for Kalshi API authentication."""

from __future__ import annotations

import base64
import secrets
import threading
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


_KEY_CACHE: dict[str, object] = {}
_key_cache_lock = threading.Lock()


def _load_key(private_key_pem: str) -> object:
    """Load and cache RSA private key objects by PEM content."""
    with _key_cache_lock:
        if private_key_pem not in _KEY_CACHE:
            key = serialization.load_pem_private_key(
                private_key_pem.encode(), password=None
            )
            _KEY_CACHE[private_key_pem] = key
        return _KEY_CACHE[private_key_pem]


def sign_request(private_key_pem: str, timestamp_ms: int, method: str, path: str) -> str:
    """Sign a request string using RSA-PSS/SHA256/MGF1.

    The private key object is cached after first load — PEM decoding is
    expensive and the key is immutable after construction.

    Args:
        private_key_pem: PEM-encoded RSA private key
        timestamp_ms: Current timestamp in milliseconds
        method: HTTP method (GET, POST, DELETE)
        path: API path (query params stripped before signing)

    Returns:
        Base64-encoded signature string
    """
    private_key = _load_key(private_key_pem)
    path_only = path.split("?")[0]
    msg_string = f"{timestamp_ms}{method}{path_only}"
    message = msg_string.encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def auth_headers(api_key: str, private_key_pem: str, method: str, path: str) -> dict[str, str]:
    """Generate Kalshi authentication headers for a request.

    Returns dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP.
    Includes a cryptographically secure nonce to prevent replay attacks (#26).
    """
    timestamp_ms = int(time.time() * 1000)
    nonce = secrets.token_urlsafe(16)  # 128-bit nonce for replay protection
    signature = sign_request(private_key_pem, timestamp_ms, method, f"{path}?nonce={nonce}")
    return {
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
        "KALSHI-ACCESS-NONCE": nonce,
    }
