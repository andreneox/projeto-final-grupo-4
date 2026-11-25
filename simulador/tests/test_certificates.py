from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
import pytest

from security.certificates import (
    CertificateConfigurationError,
    validate_client_certificate,
)
from tools.generate_dev_certificates import generate


def test_expired_client_certificate_is_rejected(tmp_path) -> None:
    application_uri = "urn:mock-linha:expired-client"
    now = datetime.now(timezone.utc)
    certificate_path, _ = generate(
        tmp_path,
        "Expired Client",
        application_uri,
        "client",
        valid_from=now - timedelta(days=10),
        valid_until=now - timedelta(days=1),
    )
    certificate = x509.load_der_x509_certificate(certificate_path.read_bytes())
    fingerprints = {certificate.fingerprint(hashes.SHA256())}

    with pytest.raises(CertificateConfigurationError, match="fora da validade"):
        validate_client_certificate(certificate, application_uri, fingerprints)
