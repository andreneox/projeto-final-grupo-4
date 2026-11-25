# Documentação técnica — APIs e protocolos

O sistema tem quatro interfaces: **(1)** API HTTP/WebSocket do receptor, **(2)** OPC UA do Gateway (e do Desktop), **(3)** protocolo binário de Andon sobre TCP e **(4)** mapa Modbus do CLP (ver `04_CLP.md`).

## 1. API HTTP e WebSocket (receptor, porta 8081)

Implementação: `simulador/web/dashboard.py` (FastAPI). Os corpos JSON são validados por Pydantic com `extra='forbid'`. Todas as respostas trazem `Cache-Control: no-store` e `X-Lean-Revision`.

| Método | Rota | Corpo / parâmetros | Resposta | Erros |
|---|---|---|---|---|
| GET | `/api/version` | – | `revision`, `features`, fórmula do desempenho | – |
| GET | `/api/snapshot` | – | `opcua` (conexão, 12 postos, Andons, Takt, ciclo, estado, contador) + `analytics` (indicadores, tempos, paradas, contagens) + `imported_cycle_base` | – |
| GET | `/api/process/production-plan` | – | `{production_target, available_time_minutes}` | 503 |
| PUT | `/api/process/production-plan` | `{"production_target": 90, "available_time_minutes": 60.0}` | o plano salvo | 422, 503 |
| GET | `/api/process/cycle-base` | – | `{available, ready}` | – |
| POST | `/api/process/cycle-base?filename=base.csv` | bytes da planilha (≤ 1 MB) | `{ready: true, message}` | 403, 409, 413, 422, 503, 504 |
| POST | `/api/process/start` | – | `{result: 0, confirmed: true/false, message}` | 403, 409, 503, 504 |
| POST | `/api/process/clear-base` | – | `{message}` | 403, 409, 503, 504 |
| GET/PUT | `/api/process/configuration` | `{stations: [{station, cycle_time_seconds, has_prototype}] × 12}` | configuração | 422, 503 |
| POST | `/api/runtime/events` | `{"kind": "andon"/"cycle"/"session_start"/"production_plan"/"reset_day", ...}` | `{event_id, result}` (idempotente por `event_id`) | 409, 422, 503 |
| GET | `/api/instruction/e07` | – | estado da IT Digital | – |
| WS | `/ws` | – | `/api/snapshot` a cada 1 s | – |
| WS | `/ws/instruction/e07` | – | estado da IT a cada 100 ms | – |

Códigos: **403**, comando ao CLP vindo de outra origem (cabeçalho `Origin` diferente da Dashboard); **409**, outro comando em andamento ou `event_id` reutilizado; **413**, planilha maior que 1 MB; **422**, validação; **503**, Gateway ou banco indisponível; **504**, o Gateway não confirmou o comando.

Exemplo de uso:

```powershell
curl.exe -s http://127.0.0.1:8081/api/version
curl.exe -s -X PUT http://127.0.0.1:8081/api/process/production-plan -H "Content-Type: application/json" -d '{\"production_target\":90,\"available_time_minutes\":60.0}'
curl.exe -s -X POST "http://127.0.0.1:8081/api/process/cycle-base?filename=base.csv" --data-binary "@base.csv"
curl.exe -s -X POST http://127.0.0.1:8081/api/process/start
```

### Evidência: chamadas reais (21/11/2026, Gateway real + CLP emulado)

| Hora | Requisição | Código | Resposta |
|---|---|---|---|
| 21:14:02 | GET `/api/version` | 200 | `revision 2026-11-20.01` |
| 21:14:03 | PUT `/api/process/production-plan` {90, 60,0} | 200 | plano salvo |
| 21:14:04 | GET `/api/process/cycle-base` | 200 | `{available: true, ready: false}` |
| 21:14:09 | POST `/api/process/cycle-base` (1.223 bytes) | 200 | "Base carregada e conferida no CLP." (≈5,3 s) |
| 21:14:09 | GET `/api/process/cycle-base` | 200 | `{available: true, ready: true}` |
| 21:14:10 | POST `/api/process/start` com `Origin: http://evil.example` | **403** | "Abra a dashboard para executar este comando do CLP." |
| 21:14:13 | POST `/api/process/start` | 200 | `{result: 0, confirmed: true}` (≈3,0 s) |
| 21:18:20 | GET `/api/instruction/e07` | 200 | `slide 4, running, plc-p07-4, 28,59 s` |
| 21:18:20 | POST `/api/runtime/events` com `station: 13` | **422** | "Input should be less than or equal to 12" |
| 21:18:23 | POST `/api/process/clear-base` | 200 | "Base do dia limpa…" (≈2,7 s) |
| 21:18:27 | GET `/api/snapshot` | 200 | `plc_production_count: 0` |

## 2. OPC UA

- Endpoint: `opc.tcp://<gateway>:4840/mock-linha/` · namespace `urn:mock-linha:telemetria:v1` · NodeIds *string*.
- Segurança: **somente** `Basic256Sha256` + `SignAndEncrypt`, sem endpoint `None`. O certificado do cliente precisa estar na pasta de confiança, dentro da validade, com `ExtendedKeyUsage = clientAuth` e `ApplicationUri` coerente. O cliente fixa o certificado do servidor.

| NodeId | Tipo | Origem / efeito |
|---|---|---|
| `Pnn/Andon/{Qualidade,Equipamento,Processo,Material}` | Boolean × 48 | `D109`–`D111` |
| `Pnn/TaktTime`, `Pnn/UltimoCiclo` | Double × 24 | `D113`–`D160` (s) |
| `Linha/StatusProcesso` | Int32[12] | `D1651`–`D1662` (−1 antes da 1ª leitura) |
| `Linha/TotalProduzido` | Int32 | `D16052` (−1 antes da 1ª leitura) |
| `Linha/CarregarBaseCiclos(144 tempos)` | método | grava e confere `D17001`–`D17288` |
| `Linha/BaseCiclosCarregada()` | método | base conferida? |
| `Linha/IniciarSimulacao()` | método | pulso de 2 s em `P10002` |
| `Linha/LimparBase()` | método | pulso de 2 s em `P10003`, confere `D16052 = 0` |
| `Linha/DefinirVelocidadeMotor(UInt16 0..100)` | método | escreve `D1200` |
| `Linha/DefinirParada(Boolean)` | método | bit 0 de `D1201` |

**Evidência:** "Cliente OPC UA: conectado" no receptor e "OPC UA: active and secure" no Gateway nas duas execuções. Os métodos de base, Start e reset foram chamados com sucesso. Os testes de integração comprovam os 72 nós e a recusa de certificado desconhecido, vencido ou de servidor incorreto.

## 3. Protocolo binário de Andon (TCP 15000)

| Bytes | Campo | Valores |
|---|---|---|
| 0–1 | Tipo | `00 01` (CLP/Desktop), `00 02` (simulador via API) |
| 2–3 | Posto | 1–12 |
| 4–11 | Data e hora (BCD) | mês, ano, hora, dia, segundo, minuto, século, dia da semana (0 = domingo) |
| 12–13 | Botão | 1 Qualidade, 2 Equipamento, 3 Processo, 4 Material |
| 14–15 | Estado | 1 ligado, 2 desligado |

- Inteiros de 16 bits em *big-endian*. Uma conexão por evento.
- **ACK:** 22 bytes ASCII (`0` × 20 + `15`), enviados somente **após o COMMIT** no receptor.
- **Pedido de hora:** `00 01` + 14 bytes zero, com resposta de 8 bytes BCD.
- **Política do receptor:** ON com ocorrência aberta → `ON_REPETIDO`; OFF sem abertura → `OFF_SEM_ABERTURA`; evento anterior ao último da chave → `ATRASADO`. Todos recebem ACK. Reenvio idêntico: novo ACK sem reaplicar. Formato inválido ou falha de banco: conexão fechada sem ACK, e o remetente tenta de novo.

**Evidência:** 18 eventos reais entregues com ACK TCP entre 23,4 e 39,9 ms após a captura; 127 recepções no receptor da instalação.

**Limite:** o pacote não tem identificador de evento, então a garantia é de "pelo menos uma vez" com deduplicação por conteúdo. Para "exatamente uma vez", seria preciso incluir um identificador no protocolo.

Relatório completo: `docs/Relatorio_Final/` (seção 8).
