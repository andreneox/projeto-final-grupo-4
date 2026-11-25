from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import ExtendedKeyUsageOID


class CertificateConfigurationError(RuntimeError):
    pass


def validate_server_credentials(
    certificate_path: Path, key_path: Path, application_uri: str
) -> None:
    if not certificate_path.is_file():
        raise CertificateConfigurationError(
            f"OPC UA certificate is missing: {certificate_path}"
        )
    if not key_path.is_file():
        raise CertificateConfigurationError(f"OPC UA key is missing: {key_path}")
    certificate = load_certificate(certificate_path)
    now = datetime.now(timezone.utc)
    if now < certificate.not_valid_before_utc or now > certificate.not_valid_after_utc:
        raise CertificateConfigurationError("OPC UA certificate is outside its validity")
    try:
        usages = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
        sans = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as exc:
        raise CertificateConfigurationError(
            "OPC UA certificate lacks ApplicationUri or ExtendedKeyUsage"
        ) from exc
    if ExtendedKeyUsageOID.SERVER_AUTH not in usages:
        raise CertificateConfigurationError(
            "OPC UA certificate does not allow server authentication"
        )
    if application_uri not in sans.get_values_for_type(
        x509.UniformResourceIdentifier
    ):
        raise CertificateConfigurationError(
            "OPC UA ApplicationUri does not match the certificate"
        )
    try:
        with key_path.open("rb") as stream:
            key = load_pem_private_key(stream.read(), password=None)
    except Exception as exc:
        raise CertificateConfigurationError(f"Invalid OPC UA key: {exc}") from exc
    if certificate.public_key().public_numbers() != key.public_key().public_numbers():
        raise CertificateConfigurationError("OPC UA certificate and key do not match")


def load_trusted_certificates(directory: Path) -> list[x509.Certificate]:
    if not directory.is_dir():
        raise CertificateConfigurationError(
            f"Trusted OPC UA client directory is missing: {directory}"
        )
    certificates = [
        load_certificate(path)
        for path in sorted(directory.glob("*"))
        if path.suffix.lower() in {".der", ".pem", ".crt", ".cer"}
    ]
    if not certificates:
        raise CertificateConfigurationError(
            f"No trusted OPC UA client certificate in: {directory}"
        )
    return certificates


def validate_client_certificate(
    certificate: x509.Certificate,
    application_uri: str,
    trusted_fingerprints: set[bytes],
) -> None:
    now = datetime.now(timezone.utc)
    if now < certificate.not_valid_before_utc or now > certificate.not_valid_after_utc:
        raise CertificateConfigurationError("Client certificate is outside its validity")
    if certificate.fingerprint(hashes.SHA256()) not in trusted_fingerprints:
        raise CertificateConfigurationError("Unknown OPC UA client certificate")
    try:
        usages = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
        sans = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as exc:
        raise CertificateConfigurationError(
            "Client certificate lacks ApplicationUri or ExtendedKeyUsage"
        ) from exc
    if ExtendedKeyUsageOID.CLIENT_AUTH not in usages:
        raise CertificateConfigurationError(
            "Certificate does not allow client authentication"
        )
    if application_uri not in sans.get_values_for_type(
        x509.UniformResourceIdentifier
    ):
        raise CertificateConfigurationError(
            "Client ApplicationUri does not match the certificate"
        )


def load_certificate(path: Path) -> x509.Certificate:
    try:
        data = path.read_bytes()
        if b"-----BEGIN CERTIFICATE-----" in data:
            return x509.load_pem_x509_certificate(data)
        return x509.load_der_x509_certificate(data)
    except Exception as exc:
        raise CertificateConfigurationError(
            f"Invalid certificate at {path}: {exc}"
        ) from exc

