# README — APIs

Guia rápido das interfaces para quem quer integrar outro sistema à linha.

| Interface | Onde | Para quê |
|---|---|---|
| HTTP/JSON + WebSocket | Receptor Windows, porta 8081 | Ler o estado da linha e os indicadores; enviar comandos (base, Start, reset). |
| OPC UA | Gateway (Raspberry), porta 4840 | Telemetria dos 12 postos e métodos de controle do CLP. |
| TCP binário | Receptor Windows, porta 15000 | Enviar eventos de Andon (16 bytes, ACK de 22 bytes). |
| Modbus RTU | CLP, RS-232 | Usado somente pelo Gateway. |

## HTTP — exemplos

```powershell
# Estado completo (postos, Andons, produção, OEE)
curl.exe -s http://127.0.0.1:8081/api/snapshot

# Plano do turno
curl.exe -s -X PUT http://127.0.0.1:8081/api/process/production-plan `
  -H "Content-Type: application/json" `
  -d '{\"production_target\":480,\"available_time_minutes\":480.0}'

# Base de tempos, Start e limpeza (acionam o CLP)
curl.exe -s -X POST "http://127.0.0.1:8081/api/process/cycle-base?filename=base.xlsx" --data-binary "@base.xlsx"
curl.exe -s -X POST http://127.0.0.1:8081/api/process/start
curl.exe -s -X POST http://127.0.0.1:8081/api/process/clear-base

# Estado da IT Digital
curl.exe -s http://127.0.0.1:8081/api/instruction/e07
```

Rotas: `GET /api/version`, `GET /api/snapshot`, `GET|PUT /api/process/production-plan`, `GET|POST /api/process/cycle-base`, `POST /api/process/start`, `POST /api/process/clear-base`, `GET|PUT /api/process/configuration`, `POST /api/runtime/events`, `GET /api/instruction/e07`, `WS /ws` (1 s), `WS /ws/instruction/e07` (100 ms).

Códigos de erro: **403** (comando vindo de outra página), **409** (outro comando em andamento), **413** (arquivo maior que 1 MB), **422** (dados inválidos), **503** (Gateway ou banco indisponível), **504** (CLP sem confirmação).

## OPC UA — conexão

- Endpoint `opc.tcp://<ip-da-raspberry>:4840/mock-linha/`, namespace `urn:mock-linha:telemetria:v1`.
- Política obrigatória: `Basic256Sha256` + `SignAndEncrypt` com certificado de aplicação.
- O certificado do cliente (`.der`) deve ser copiado para `/etc/lean-gateway/certificates/trusted/clients/` na Raspberry.
- Nós: `P01/Andon/Qualidade` … `P12/UltimoCiclo` (72), `Linha/StatusProcesso`, `Linha/TotalProduzido`.
- Métodos: `Linha/CarregarBaseCiclos`, `Linha/BaseCiclosCarregada`, `Linha/IniciarSimulacao`, `Linha/LimparBase`, `Linha/DefinirVelocidadeMotor`, `Linha/DefinirParada`.

## TCP — enviar um Andon (Python)

```python
import socket
# tipo 1, posto 3, 21/11/2026 20:24:50 sábado (BCD), botão 4 (Material), estado 1 (ligado)
pkt = bytes.fromhex("0001 0003 1126 2021 5024 2006 0004 0001".replace(" ", ""))
with socket.create_connection(("127.0.0.1", 15000), timeout=5) as s:
    s.sendall(pkt)
    print(s.recv(22))   # b'0000000000000000000015' = gravado no receptor
```

Sem ACK significa que o evento não foi gravado: envie de novo. Um reenvio idêntico é reconhecido e não é contado duas vezes.

## Ver também

- Documentação técnica completa, com evidências: `docs/Documentacao_Tecnica/06_APIs.md`
