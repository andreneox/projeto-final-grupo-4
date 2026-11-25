from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import socket
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def generate(
    output_dir: Path,
    name: str,
    application_uri: str,
    kind: str,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    dns_names: Iterable[str] = (),
    ip_addresses: Iterable[str] = (),
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    valid_from = valid_from or now - timedelta(minutes=5)
    valid_until = valid_until or now + timedelta(days=825)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    usage = (
        ExtendedKeyUsageOID.SERVER_AUTH
        if kind == "server"
        else ExtendedKeyUsageOID.CLIENT_AUTH
    )
    local_names = {"localhost", socket.gethostname(), socket.getfqdn(), *dns_names}
    sans: list[x509.GeneralName] = [x509.UniformResourceIdentifier(application_uri)]
    sans.extend(x509.DNSName(value) for value in sorted(local_names) if value)
    sans.extend(
        x509.IPAddress(ip_address(value))
        for value in {"127.0.0.1", *ip_addresses}
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_from)
        .not_valid_after(valid_until)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=True,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
        .sign(key, hashes.SHA256())
    )
    certificate_path = output_dir / f"{kind}_cert.der"
    key_path = output_dir / f"{kind}_key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.DER))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera certificado OPC UA de desenvolvimento")
    parser.add_argument("--kind", choices=("server", "client"), required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--application-uri", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dns-name", action="append", default=[])
    parser.add_argument("--ip-address", action="append", default=[])
    args = parser.parse_args()
    certificate, key = generate(
        args.output_dir,
        args.name,
        args.application_uri,
        args.kind,
        dns_names=args.dns_name,
        ip_addresses=args.ip_address,
    )
    print(f"Certificado: {certificate}")
    print(f"Chave privada: {key}")


if __name__ == "__main__":
    main()
