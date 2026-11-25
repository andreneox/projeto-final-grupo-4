# README — Dashboard web

Painel no navegador que mostra os 12 postos em tempo real, a produção do turno, o OEE e as paradas por Andon. Também envia os comandos **Importar base**, **Start** e **Limpar base** ao CLP. É servido pelo receptor no Windows.

## Pré-requisitos

- Windows com Python 3.11 ou 3.12 e o `venv` na raiz do projeto (ver `README_Desktop.md`).
- Uma fonte de telemetria OPC UA: o **Gateway** na Raspberry Pi (linha real) ou o **Desktop** (simulação).

## Executar

```powershell
cd simulador
.\run_receiver.ps1
```

O terminal mostra `Dashboard web: http://0.0.0.0:8081`, `Receptor TCP ouvindo em 0.0.0.0:15000` e `Cliente OPC UA: conectado`. Abra **http://127.0.0.1:8081** no navegador, ou `http://<ip-do-computador>:8081` em outro equipamento da rede.

## Configuração (`simulador/config.toml`)

| Seção | Chave | Exemplo | Significado |
|---|---|---|---|
| `[opcua_client]` | `endpoint` | `opc.tcp://192.168.15.67:4840/mock-linha/` | Gateway (Raspberry). Use `127.0.0.1` para o Desktop local. |
| `[dashboard]` | `port` | `8081` | Porta do navegador. |
| `[dashboard]` | `shift_start` / `shift_duration_minutes` | `00:00` / `1440` | Turno usado quando não há Start. |
| `[receiver]` | `port` | `15000` | Porta TCP dos eventos de Andon. |
| `[receiver]` | `database_path` | `data/reference_receiver.db` | Histórico de eventos e produção. |

## Operação do turno

1. **Editar plano do turno:** informe a meta (peças) e o tempo disponível (min).
2. **Importar base:** escolha a planilha com 12 tempos de ciclo por posto. Aguarde "Base carregada e conferida no CLP".
3. **Start:** só fica habilitado com a base conferida, os 12 postos em "Aguardando" e nenhum Andon. A medição começa quando o CLP confirma.
4. Acompanhe: amarelo = aguardando, verde piscando = processando, verde = finalizou, vermelho = Andon ativo, cinza = linha parada.
5. **Limpar base:** reinicia o CLP (pulso em `P10003`) e zera produção, defeitos e paradas do dia.

**Gráficos por posto** mostra o último ciclo ou o Takt de cada posto. **IT Digital E07** abre a instrução de trabalho.

## Indicadores

- Disponibilidade = (tempo decorrido − tempo parado) / tempo decorrido
- Desempenho = produção atual / produção estimada
- Qualidade = boas / (boas + defeitos)
- OEE = Disponibilidade × Desempenho × Qualidade

## Problemas comuns

| Sintoma | Solução |
|---|---|
| "OPC UA desconectado" | Confira o `endpoint`, a rede e se o certificado do cliente (`certificates/client/client_cert.der`) está na pasta de confiança do Gateway. |
| Botão **Start** desabilitado | Importe a base e libere todos os Andons; os 12 postos precisam estar no estado 0. |
| "Há outro comando do CLP em andamento" (409) | Aguarde o comando anterior terminar (até ~8 s). |
| "O Gateway não confirmou o comando" (504) | Verifique o CLP e o cabo serial antes de repetir. |
| Script bloqueado pelo PowerShell | `Unblock-File .\run_receiver.ps1` |

## Ver também

- Documentação técnica: `docs/Documentacao_Tecnica/02_Dashboard.md`
- API: `README_APIs.md`
