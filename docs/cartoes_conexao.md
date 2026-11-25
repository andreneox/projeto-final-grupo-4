# Cartões de conexão — Equipe 4 (Cenário 25)

Dados para outro grupo da rede federada ler a nossa linha. O conteúdo foi conferido no código em 24/11/2026.

| Campo | Valor |
|---|---|
| Linha | Montagem de ar-condicionado, 12 postos (`P01` a `P12`) |
| Posto em foco | E07, Montagem de Tubulação (`P07` no OPC UA) |
| IP do Gateway ou simulador | Informado no dia da demonstração |
| IP do receptor/Dashboard | Informado no dia da demonstração |
| Conexão T2T (gêmeo a gêmeo) | Não implementada (`twin/` ausente) |

## Cartão 1 — OPC UA (telemetria e comandos)

| Campo | Valor |
|---|---|
| Endpoint | `opc.tcp://<ip>:4840/mock-linha/` |
| Namespace | `urn:mock-linha:telemetria:v1` (obter o índice pelo URI, sem fixar o número) |
| NodeId | *string*, por exemplo `ns=<índice>;s=P07/UltimoCiclo` |
| Segurança | Somente `Basic256Sha256` + `SignAndEncrypt`, com certificado de aplicação |
| ApplicationUri do servidor | `urn:mock-linha:servidor` |
| Autorização | Certificado do cliente na pasta de confiança do servidor |
| Permissão | Variáveis somente leitura; comandos apenas pelos métodos |

### Variáveis

| Nó (`nn` = 01 a 12) | Tipo | Unidade / valores | Linha real (Gateway) | Simulador |
|---|---|---|:---:|:---:|
| `Pnn/Andon/Qualidade`, `Equipamento`, `Processo`, `Material` | Boolean | ligado / desligado | ✔ | ✔ |
| `Pnn/TaktTime` | Double | s | ✔ | ✔ |
| `Pnn/UltimoCiclo` | Double | s | ✔ | ✔ |
| `Linha/StatusProcesso` | Int32[12] | 0 espera, 1 preparação, 2 medição, 3 conclusão; −1 sem leitura | ✔ | – |
| `Linha/TotalProduzido` | Int32 | peças; −1 sem leitura | ✔ | – |
| **Total** | | | **74** | **72** |

### Métodos (somente na linha real)

Alteram a linha física. Um grupo externo só deve chamá-los com autorização da Equipe 4.

| Método (objeto `Linha`) | Entrada | Saída |
|---|---|---|
| `Linha/CarregarBaseCiclos` | Double[144]: 12 tempos por posto, de P01 a P12 (s) | String: vazia ou erro |
| `Linha/BaseCiclosCarregada` | – | Boolean |
| `Linha/IniciarSimulacao` | – | String (hora ISO; vazia se não confirmado), String (erro) |
| `Linha/LimparBase` | – | String (hora ISO), String (erro) |
| `Linha/DefinirVelocidadeMotor` | UInt16, 0 a 100 | Boolean |
| `Linha/DefinirParada` | Boolean | Boolean |

### Como obter acesso

1. O grupo cliente gera o próprio certificado de aplicação (validade vigente, `ExtendedKeyUsage = clientAuth` e `ApplicationUri` igual ao informado pelo cliente) e envia **somente** o arquivo público `.der`. A chave privada nunca é enviada. Com o nosso gerador, na pasta `simulador`:

   ```powershell
   ..\venv\Scripts\python.exe -m tools.generate_dev_certificates --kind client --name "Grupo X" --application-uri "urn:grupo-x:cliente" --output-dir certificates\grupo-x
   ```

2. A Equipe 4 copia o `.der` para a pasta de confiança e **reinicia o servidor**, que só lê os certificados ao iniciar:
   - Raspberry: `/etc/lean-gateway/certificates/trusted/clients/`
   - Simulador: `simulador/certificates/trusted/clients/`
3. A Equipe 4 envia ao grupo o certificado público do servidor (`server_cert.der`).

### Exemplo de leitura (Python, `asyncua`)

Testado em 24/11/2026 com Python 3.12 e `asyncua` 1.1.5 contra o servidor OPC UA do simulador, na mesma máquina. O `asyncua` 1.1.5 falha ao conectar no Python 3.14.

```python
import asyncio
from asyncua import Client
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

async def main():
    client = Client("opc.tcp://<ip>:4840/mock-linha/")
    client.application_uri = "urn:grupo-x:cliente"   # igual ao do certificado
    await client.set_security(
        SecurityPolicyBasic256Sha256,
        certificate="client_cert.der",
        private_key="client_key.pem",
        server_certificate="server_cert.der",
    )
    async with client:
        ns = await client.get_namespace_index("urn:mock-linha:telemetria:v1")
        print(await client.get_node(f"ns={ns};s=P07/UltimoCiclo").read_value())

asyncio.run(main())
```

## Cartão 2 — HTTP e WebSocket (Dashboard)

| Campo | Valor |
|---|---|
| Base | `http://<ip-do-receptor>:8080` (8081 na instalação do laboratório) |
| Estado completo | `GET /api/snapshot` |
| IT Digital E07 | `GET /api/instruction/e07` |
| Tempo real | `WS /ws` (1 s) e `WS /ws/instruction/e07` (100 ms) |
| Páginas | `/`, `/graficos`, `/instrucao/e07` |
| Autenticação | Nenhuma: usar apenas na rede da demonstração |

O `config.example.toml` usa `[dashboard] host = "127.0.0.1"`, que só aceita acesso local. Para outro grupo acessar, use `host = "0.0.0.0"` no `config.toml` e libere a porta no firewall.

## Cartão 3 — TCP (eventos de Andon)

| Campo | Valor |
|---|---|
| Endereço | `<ip-do-receptor>:15000` |
| Pacote | 16 bytes, inteiros *big-endian*; uma conexão por evento |
| Resposta | 22 bytes ASCII (`0` × 20 + `15`), após gravar no banco |

Formato do pacote e regras de reenvio: [06_APIs](Documentacao_Tecnica/06_APIs.md), seção 3. Um evento enviado aqui entra no histórico e nos indicadores da linha.

## Conexões com outros grupos

Nenhuma conexão registrada.
