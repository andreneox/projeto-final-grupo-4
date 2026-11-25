from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx


class DesktopStartError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class DesktopStartClient:
    """POST without body or query parameters; desktop replies with JSON integer 0/1."""

    def __init__(self, url: str = "", timeout_seconds: float = 10.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.strip()
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._lock = asyncio.Lock()

    async def start(self) -> int:
        if not self.url:
            raise DesktopStartError(503, "API do desktop ainda não configurada.")
        try:
            parsed = urlsplit(self.url)
            parsed.port  # Validate an explicit port, if present.
        except ValueError as exc:
            raise DesktopStartError(503, "Endereço da API do desktop inválido.") from exc
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise DesktopStartError(503, "Endereço da API do desktop inválido. Configure uma URL HTTP/HTTPS sem parâmetros.")
        if self._lock.locked():
            raise DesktopStartError(409, "Já existe uma solicitação de Start em andamento.")
        async with self._lock:
            try:
                # No retries: repeating a command could start the process twice.
                async with asyncio.timeout(self.timeout_seconds):
                    async with httpx.AsyncClient(
                        timeout=self.timeout_seconds, transport=self._transport,
                        trust_env=False, follow_redirects=False,
                    ) as client:
                        response = await client.post(self.url)
                        response.raise_for_status()
                        result = response.json()
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise DesktopStartError(504, "Tempo de resposta do desktop excedido. Confira no desktop se o processo iniciou antes de tentar novamente.") from exc
            except httpx.HTTPStatusError as exc:
                raise DesktopStartError(502, "A API do desktop respondeu com erro HTTP.") from exc
            except httpx.RequestError as exc:
                raise DesktopStartError(502, "Não foi possível comunicar com a API do desktop. Confira no desktop antes de repetir o Start.") from exc
            except httpx.InvalidURL as exc:
                raise DesktopStartError(503, "Endereço da API do desktop inválido.") from exc
            except ValueError as exc:
                raise DesktopStartError(502, "Resposta inválida da API do desktop: esperado o número inteiro 0 ou 1.") from exc
            if type(result) is not int or result not in (0, 1):
                raise DesktopStartError(502, "Resposta inválida da API do desktop: esperado o número inteiro 0 ou 1.")
            return result
