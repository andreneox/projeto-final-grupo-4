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
            f"Certificado OPC UA ausente: {certificate_path}"
        )
    if not key_path.is_file():
        raise CertificateConfigurationError(f"Chave OPC UA ausente: {key_path}")
    certificate = _load_certificate(certificate_path)
    now = datetime.now(timezone.utc)
    if now < certificate.not_valid_before_utc or now > certificate.not_valid_after_utc:
        raise CertificateConfigurationError("Certificado OPC UA fora da validade")
    try:
        usages = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
        if ExtendedKeyUsageOID.SERVER_AUTH not in usages:
            raise CertificateConfigurationError(
                "Certificado OPC UA nao permite autenticacao de servidor"
            )
        sans = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        uris = sans.get_values_for_type(x509.UniformResourceIdentifier)
    except x509.ExtensionNotFound as exc:
        raise CertificateConfigurationError(
            "Certificado OPC UA sem ApplicationUri ou ExtendedKeyUsage"
        ) from exc
    if application_uri not in uris:
        raise CertificateConfigurationError(
            "ApplicationUri do servidor nao corresponde ao certificado"
        )
    try:
        with key_path.open("rb") as stream:
            key = load_pem_private_key(stream.read(), password=None)
    except Exception as exc:
        raise CertificateConfigurationError(f"Chave OPC UA invalida: {exc}") from exc
    if certificate.public_key().public_numbers() != key.public_key().public_numbers():
        raise CertificateConfigurationError(
            "Certificado e chave OPC UA nao correspondem"
        )


def load_trusted_certificates(directory: Path) -> list[x509.Certificate]:
    if not directory.is_dir():
        raise CertificateConfigurationError(
            f"Diretorio de clientes confiaveis ausente: {directory}"
        )
    certificates: list[x509.Certificate] = []
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() not in {".der", ".pem", ".crt", ".cer"}:
            continue
        certificates.append(_load_certificate(path))
    if not certificates:
        raise CertificateConfigurationError(
            f"Nenhum certificado de cliente confiavel em: {directory}"
        )
    return certificates


def validate_client_certificate(
    certificate: x509.Certificate,
    application_uri: str,
    trusted_fingerprints: set[bytes],
) -> None:
    now = datetime.now(timezone.utc)
    if now < certificate.not_valid_before_utc or now > certificate.not_valid_after_utc:
        raise CertificateConfigurationError("Certificado de cliente fora da validade")
    if certificate.fingerprint(hashes.SHA256()) not in trusted_fingerprints:
        raise CertificateConfigurationError("Certificado de cliente desconhecido")
    try:
        usages = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
        if ExtendedKeyUsageOID.CLIENT_AUTH not in usages:
            raise CertificateConfigurationError(
                "Certificado nao permite autenticacao de cliente"
            )
        sans = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        uris = sans.get_values_for_type(x509.UniformResourceIdentifier)
    except x509.ExtensionNotFound as exc:
        raise CertificateConfigurationError(
            "Certificado de cliente sem ApplicationUri ou ExtendedKeyUsage"
        ) from exc
    if application_uri not in uris:
        raise CertificateConfigurationError(
            "ApplicationUri do cliente nao corresponde ao certificado"
        )


def _load_certificate(path: Path) -> x509.Certificate:
    try:
        data = path.read_bytes()
        if b"-----BEGIN CERTIFICATE-----" in data:
            return x509.load_pem_x509_certificate(data)
        return x509.load_der_x509_certificate(data)
    except Exception as exc:
        raise CertificateConfigurationError(
            f"Certificado invalido em {path}: {exc}"
        ) from exc
