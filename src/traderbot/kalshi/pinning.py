"""TLS certificate pinning for Kalshi API — SPKI verification.

Uses SubjectPublicKeyInfo (SPKI) pinning: pins the public key rather than
the full certificate, so pin survives planned certificate renewals as long
as the key pair stays the same.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import ssl

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# Kalshi API SPKI pin — SHA-256 of DER-encoded SubjectPublicKeyInfo, base64-encoded.
# To regenerate: openssl s_client -connect api.elections.kalshi.com:443 \
#   | openssl x509 -pubkey -noout \
#   | openssl pkey -pubin -outform DER \
#   | openssl dgst -sha256 -binary \
#   | base64
KALSHI_SPKI_PIN = "Iu/+7wHLhGRvN84Vr2fyW7omLlvfmIcGNnaUf9uTkwA="


class CertPinningError(Exception):
    """TLS certificate public key does not match any trusted SPKI pin."""


def compute_spki_pin(cert_der: bytes) -> str:
    """Compute base64-encoded SHA-256 of the DER-encoded SPKI from a certificate."""
    cert = x509.load_der_x509_certificate(cert_der, default_backend())
    pub_key = cert.public_key()
    spki_der = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(hashlib.sha256(spki_der).digest()).decode()


def verify_spki_pin(cert_der: bytes, trusted_pins: frozenset[str]) -> str:
    """Verify a cert's SPKI matches a trusted pin. Returns the matched pin.

    Raises CertPinningError if no pin matches.
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

    def __init__(self, trusted_pins: frozenset[str] | None = None) -> None:
        super().__init__(ssl.PROTOCOL_TLS_CLIENT)
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED
        self.minimum_version = ssl.TLSVersion.TLSv1_2
        self._trusted_pins: frozenset[str] = (
            trusted_pins if trusted_pins is not None else frozenset({KALSHI_SPKI_PIN})
        )
        self.load_default_certs()

    def wrap_socket(self, sock, server_side=False, do_handshake_on_connect=True,
                    suppress_ragged_eofs=True, server_hostname=None, session=None):
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
        verify_spki_pin(cert_der, self._trusted_pins)
        return ssock


def create_pinned_ssl_context() -> PinnedSSLContext:
    """Create TLS SSL context with SPKI pinning for Kalshi API."""
    return PinnedSSLContext()
