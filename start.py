"""Orquestrador: inicia e encerra os processos do projeto.

    python start.py           receptor + Dashboard + simulador Desktop (sem hardware)
    python start.py --real    receptor + Dashboard; o Gateway roda na Raspberry Pi

Usa somente a biblioteca padrão. Os processos rodam com o Python do ambiente virtual.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
SIMULADOR = ROOT / "simulador"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
SUPPORTED_PYTHON = ("3.11", "3.12")
START_TIMEOUT_SECONDS = 40
STOP_TIMEOUT_SECONDS = 25

# Cada processo observa o stdin. Quando o orquestrador fecha o pipe (ou deixa de
# existir), o processo encerra pelo caminho normal e libera banco e conexões.
_WATCHER = """
import os, runpy, sys, threading
sys.path.insert(0, os.getcwd())
def watch():
    while os.read(0, 1):
        pass
    {on_close}
threading.Thread(target=watch, daemon=True).start()
"""
_RECEIVER = _WATCHER.format(
    on_close="import _thread; _thread.interrupt_main()"
) + "runpy.run_module('tools.reference_receiver', run_name='__main__', alter_sys=True)"
# quit() direto de outra thread trava; a chamada precisa ser enfileirada no Qt.
_SIMULATOR = _WATCHER.format(
    on_close="""import time
    from PyQt6.QtCore import QCoreApplication, QMetaObject, Qt
    while (application := QCoreApplication.instance()) is None:
        time.sleep(0.1)
    QMetaObject.invokeMethod(application, 'quit', Qt.ConnectionType.QueuedConnection)"""
) + "runpy.run_path('main.py', run_name='__main__')"


class StartError(RuntimeError):
    pass


def find_python() -> Path:
    executable = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    for base in (SIMULADOR / "venv", ROOT / "venv"):
        if (base / executable).is_file():
            return base / executable
    raise StartError(
        "Ambiente virtual não encontrado. Na raiz do projeto, execute:\n"
        "  py -3.12 -m venv venv\n"
        "  .\\venv\\Scripts\\python.exe -m pip install "
        "-r simulador\\requirements.txt -r hardware\\requirements.txt"
    )


def check_python(python: Path, modules: list[str]) -> None:
    def run(code: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([python, "-c", code], capture_output=True, text=True)

    version = run("import sys; print('%d.%d' % sys.version_info[:2])").stdout.strip()
    if version not in SUPPORTED_PYTHON:
        raise StartError(
            f"O ambiente virtual usa Python {version or 'desconhecido'}; "
            f"use {' ou '.join(SUPPORTED_PYTHON)}. Recrie-o com: py -3.12 -m venv --clear venv"
        )
    result = run(f"import {', '.join(modules)}")
    if result.returncode:
        detail = (result.stderr.strip().splitlines() or ["erro desconhecido"])[-1]
        raise StartError(
            f"Dependências ausentes ({detail}). Execute:\n"
            f"  \"{python}\" -m pip install -r simulador\\requirements.txt"
        )


def load_config(path: Path | None) -> tuple[Path, dict]:
    import tomllib

    if path is not None and not path.is_file():
        raise StartError(f"Configuração não encontrada: {path}")
    if path is None:
        path = SIMULADOR / "config.toml"
        if not path.is_file():
            path = SIMULADOR / "config.example.toml"
    path = path.resolve()
    try:
        return path, tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise StartError(f"Configuração inválida em {path}: {exc}") from exc


def check_mode(config: dict, real: bool) -> None:
    host = urlsplit(config["opcua_client"]["endpoint"]).hostname
    if real and host in LOOPBACK:
        print(
            "Aviso: [opcua_client] endpoint aponta para este computador. "
            "Para a Raspberry Pi, informe o IP dela em simulador/config.toml."
        )
    if not real and host not in LOOPBACK:
        raise StartError(
            f"[opcua_client] endpoint aponta para {host}, e não para o simulador.\n"
            "A Dashboard comandaria a linha real. Use --real, ou aponte o endpoint para 127.0.0.1."
        )


def check_ports(config: dict, real: bool) -> None:
    ports = {
        "Dashboard": config["dashboard"]["port"],
        "receptor TCP": config["receiver"]["port"],
    }
    if not real:
        ports["OPC UA do simulador"] = urlsplit(config["opcua"]["endpoint"]).port
    for name, port in ports.items():
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise StartError(
                    f"A porta {port} ({name}) já está em uso. Encerre o outro processo."
                )


def check_certificates(python: Path, config_path: Path, config: dict, real: bool) -> None:
    server, client = config["opcua"], config["opcua_client"]

    def resolve(value: str) -> Path:
        return (config_path.parent / value).resolve()

    def ensure(kind: str, name: str, section: dict) -> Path:
        certificate = resolve(section["certificate_path"])
        key = resolve(section["private_key_path"])
        if certificate.is_file() and key.is_file():
            return certificate
        standard = (certificate.name, key.name) == (f"{kind}_cert.der", f"{kind}_key.pem")
        # Nunca sobrescreve um par incompleto nem gera credencial para a linha real.
        if real or not standard or certificate.parent != key.parent or (
            certificate.exists() or key.exists()
        ):
            raise StartError(
                f"Certificado OPC UA ausente ou incompleto: {certificate} e {key}. "
                "Veja a seção 2 do README.md."
            )
        print(f"Gerando certificado de desenvolvimento: {certificate}")
        subprocess.run(
            [python, "-m", "tools.generate_dev_certificates", "--kind", kind,
             "--name", name, "--application-uri", section["application_uri"],
             "--output-dir", certificate.parent],
            cwd=SIMULADOR, check=True, stdout=subprocess.DEVNULL,
        )
        return certificate

    client_certificate = ensure("client", "Dashboard Web", client)
    if not real:
        ensure("server", "Mock Linha", server)
        trusted = resolve(server["trusted_clients_dir"])
        trusted.mkdir(parents=True, exist_ok=True)
        content = client_certificate.read_bytes()
        if not any(p.is_file() and p.read_bytes() == content for p in trusted.iterdir()):
            target = trusted / client_certificate.name
            if target.exists():
                raise StartError(
                    f"{target} pertence a outro cliente. Copie {client_certificate} "
                    "para essa pasta com outro nome."
                )
            shutil.copy2(client_certificate, target)
    pinned = resolve(client["server_certificate_path"])
    if not pinned.is_file():
        raise StartError(f"Certificado do servidor OPC UA ausente: {pinned}")


def launch(python: Path, code: str, config_path: Path) -> subprocess.Popen:
    isolation: dict = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    return subprocess.Popen(
        [python, "-c", code, "--config", config_path],
        cwd=SIMULADOR,
        stdin=subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        **isolation,
    )


def wait_dashboard(process: subprocess.Popen, url: str) -> None:
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise StartError("O receptor encerrou durante a inicialização.")
        try:
            with urlopen(f"{url}/api/version", timeout=2):
                return
        except OSError:
            time.sleep(0.3)
    raise StartError(f"A Dashboard não respondeu em {START_TIMEOUT_SECONDS} s.")


def stop(processes: dict[str, subprocess.Popen]) -> None:
    # O receptor sai antes do simulador para fechar a sessão OPC UA com o servidor ativo.
    for name, process in processes.items():
        if process.poll() is None:
            print(f"Encerrando {name}...")
        process.stdin.close()
        try:
            process.wait(STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            print(f"{name} não respondeu; encerrando à força.")
            if os.name == "nt":  # o python.exe do venv é um lançador com processo filho
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                )
            else:
                process.kill()
            process.wait()


def run(args: argparse.Namespace) -> int:
    config_path, config = load_config(args.config)
    check_mode(config, args.real)
    python = find_python()
    check_python(python, ["asyncua", "fastapi", "openpyxl"] + ([] if args.real else ["PyQt6"]))
    check_ports(config, args.real)
    check_certificates(python, config_path, config, args.real)

    host = config["dashboard"]["host"]
    port = config["dashboard"]["port"]
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    processes: dict[str, subprocess.Popen] = {}
    print(f"Configuração: {config_path}")
    try:
        processes["receptor e Dashboard"] = launch(python, _RECEIVER, config_path)
        wait_dashboard(processes["receptor e Dashboard"], url)
        if not args.real:
            processes["simulador"] = launch(python, _SIMULATOR, config_path)
        print(f"\nDashboard: {url}\nIT Digital E07: {url}/instrucao/e07")
        print("Ctrl+C encerra tudo" + ("." if args.real else "; fechar o simulador também."))
        if not args.no_browser:
            webbrowser.open(url)
        while all(process.poll() is None for process in processes.values()):
            time.sleep(0.5)
        name, code = next(
            (n, p.returncode) for n, p in processes.items() if p.returncode is not None
        )
        print(f"\nO {name} encerrou (código {code}).")
        return code
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        stop(processes)


def main() -> int:
    if sys.version_info < (3, 11):
        print("Use Python 3.11 ou 3.12.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Inicia os processos do projeto")
    parser.add_argument(
        "--real", action="store_true", help="linha real: não inicia o simulador"
    )
    parser.add_argument("--config", type=Path, help="padrão: simulador/config.toml")
    parser.add_argument(
        "--sem-navegador", dest="no_browser", action="store_true",
        help="não abre a Dashboard no navegador",
    )
    try:
        return run(parser.parse_args())
    except StartError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
