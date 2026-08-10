"""TLS certificate pinning for Kalshi API — SPKI verification.

Uses SubjectPublicKeyInfo (SPKI) pinning: pins the public key rather than
the full certificate, so pin survives planned certificate renewals as long
as the key pair stays the same. Ported from the retired v1 client with
strict typing and without the deprecated ``default_backend()`` argument
(cryptography ≥ 42 loads certificates with the default backend implicitly).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import socket
import ssl
from typing import Self

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import Certificate

logger = logging.getLogger(__name__)

# Kalshi API SPKI pins — SHA-256 of DER-encoded SubjectPublicKeyInfo, base64-encoded.
# To regenerate: openssl s_client -connect external-api.kalshi.com:443 \
#   | openssl x509 -pubkey -noout \
#   | openssl pkey -pubin -outform DER \
#   | openssl dgst -sha256 -binary \
#   | base64
#
# Pins are per-environment: the production key pair differs from the demo
# key pair. Verify against the live cert before deploying (2026-08-04:
# the previous single prod pin was stale and rejected every connection).
KALSHI_SPKI_PIN = "2B+aWtZC/si8bNsxJp7edFMzcB5jcv3THsSVSrwUCLQ="
KALSHI_DEMO_SPKI_PIN = "CD9oS1WLUdVocVL6CrZeFPzFL88Dc79bhWrgnRh98PY="

# Environment name -> trusted SPKI pins for that environment.
_ENV_PINS: dict[str, frozenset[str]] = {
    "production": frozenset({KALSHI_SPKI_PIN}),
    "demo": frozenset({KALSHI_DEMO_SPKI_PIN}),
}


class CertPinningError(RuntimeError):
    """TLS certificate public key does not match any trusted SPKI pin."""


def compute_spki_pin(cert_der: bytes) -> str:
    """Compute base64-encoded SHA-256 of the DER-encoded SPKI from a certificate."""
    cert: Certificate = x509.load_der_x509_certificate(cert_der)
    pub_key = cert.public_key()
    spki_der = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(hashlib.sha256(spki_der).digest()).decode()


def verify_spki_pin(cert_der: bytes, trusted_pins: frozenset[str]) -> str:
    """Verify a cert's SPKI matches a trusted pin. Returns the matched pin.

    Raises:
        CertPinningError: if no pin matches.
    """
    actual = compute_spki_pin(cert_der)
    if actual not in trusted_pins:
        raise CertPinningError(
            f"SPKI pin mismatch: got {actual}, expected one of {sorted(trusted_pins)}"
        )
    logger.debug("SPKI pin verified: %s", actual)
    return actual


class PinnedSSLContext(ssl.SSLContext):
    """SSLContext that verifies SPKI pin after every TLS handshake.

    Performs standard CA verification + hostname checking first, then
    checks the peer cert's SPKI against trusted pins. Rejects connections
    where the server's public key doesn't match any trusted pin.
    """

    def __new__(cls, trusted_pins: frozenset[str] | None = None) -> Self:
        return super().__new__(cls, ssl.PROTOCOL_TLS_CLIENT)

    def __init__(self, trusted_pins: frozenset[str] | None = None) -> None:
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED
        self.minimum_version = ssl.TLSVersion.TLSv1_2
        self._trusted_pins: frozenset[str] = (
            trusted_pins if trusted_pins is not None else frozenset({KALSHI_SPKI_PIN})
        )
        self.load_default_certs()

    def wrap_socket(
        self,
        sock: socket.socket,
        server_side: bool = False,
        do_handshake_on_connect: bool = True,
        suppress_ragged_eofs: bool = True,
        server_hostname: str | bytes | None = None,
        session: ssl.SSLSession | None = None,
    ) -> ssl.SSLSocket:
        ssock = super().wrap_socket(
            sock,
            server_side=server_side,
            do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs,
            server_hostname=server_hostname,
            session=session,
        )
        cert_der = ssock.getpeercert(binary_form=True)
        if cert_der is None:
            raise CertPinningError("No peer certificate after TLS handshake")
        _ = verify_spki_pin(cert_der, self._trusted_pins)
        return ssock


def trusted_pins_for(environment: str) -> frozenset[str]:
    """Return the trusted SPKI-pin set for an environment.

    Args:
        environment: ``"production"`` or ``"demo"``.

    Raises:
        KeyError: if the environment is not known.
    """
    return _ENV_PINS[environment]


def create_pinned_ssl_context(
    trusted_pins: frozenset[str] | None = None,
) -> PinnedSSLContext:
    """Create TLS SSL context with SPKI pinning for Kalshi API.

    Args:
        trusted_pins: Optional explicit trusted pin set. Defaults to the
            production pin; pass an environment's pins to match that env.
    """
    return PinnedSSLContext(trusted_pins)
