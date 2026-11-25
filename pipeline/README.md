# Pipeline — cliente e banco

Esta pasta só indica onde o pipeline está implementado. O código fica em `simulador/`, porque compartilha configuração, modelos e protocolo com o simulador e a Dashboard.

| Função | Implementação |
|---|---|
| Cliente OPC UA (assinatura e comandos) | [communications/opcua_client.py](../simulador/communications/opcua_client.py) |
| Receptor TCP de Andon e banco SQLite (ponto de entrada) | [tools/reference_receiver.py](../simulador/tools/reference_receiver.py) |
| Histórico de ciclos e plano de produção | [persistence/runtime_store.py](../simulador/persistence/runtime_store.py) |
| Tratamento dos eventos de produção | [services/runtime_receiver.py](../simulador/services/runtime_receiver.py) |
| Última telemetria em memória | [services/telemetry.py](../simulador/services/telemetry.py) |
| Formato do pacote de Andon | [protocol/tcp_codec.py](../simulador/protocol/tcp_codec.py) |
| Fila durável na borda | [hardware/gateway/persistence.py](../hardware/gateway/persistence.py) |

**Executar:** `start.py`, na raiz, inicia o receptor. O receptor e a Dashboard ([app](../app/README.md)) são um único processo.

**Interfaces:** [cartões de conexão](../docs/cartoes_conexao.md) e [APIs](../docs/Documentacao_Tecnica/06_APIs.md).
