# Evidências — dados brutos e como reproduzir

Esta pasta guarda a demonstração; os dados brutos e os scripts de análise ficam em `dados/`, na raiz do projeto. Eles sustentam os números e as figuras do relatório (`docs/Relatorio_Final/`) e da documentação técnica (`docs/Documentacao_Tecnica/`).

## Origem das evidências

| Origem | Arquivos | Observação |
|---|---|---|
| **Execução real com o CLP** (27–28/09/2026) | `hardware/logs/gateway.log`, `hardware/data/gateway.db`, `simulador/data/reference_receiver.db`; extrato em `dados/amostras/gateway_events.json` | Os três arquivos originais **não estão incluídos na entrega**; o extrato, com os 18 eventos do CLP, está. |
| **Testes automatizados** (21/11/2026) | `dados/amostras/testes/` (`junit_*.xml`, `pytest_*.txt`, `tests_summary.json`) | 98 aprovados no Simulador; 64 aprovados e 2 pulados no Gateway. |
| **Demonstração com CLP emulado** (21/11/2026) | `dados/amostras/execucao_1_demo/`, `dados/amostras/execucao_2_it_digital/`, `dados/amostras/desktop/` | Gateway, receptor e Dashboard reais; só o CLP é emulado. |

Sem os originais, os totais do `gateway.log` (32.140 linhas) e do banco do receptor (127 recepções), citados no relatório e na documentação técnica, não podem ser conferidos a partir desta entrega.

Os testes foram repetidos em 24/11/2026; o resultado está na seção 9 do [README principal](../../README.md).

## Reproduzir a demonstração

Usa portas próprias (Modbus 5020, OPC UA 4850/4851, Dashboard 8091/8092, TCP 15010/15011), então não interfere na instalação nem nos bancos reais.

```powershell
cd docs\Evidencias\demonstracao
..\..\..\venv\Scripts\python.exe run_demo.py      # ~5 min: base, Start, 3 Andons, capturas, reset
..\..\..\venv\Scripts\python.exe run_it.py        # ~2,5 min: capturas da IT Digital por passo
..\..\..\venv\Scripts\python.exe run_desktop.py   # ~30 s: janela do Desktop e Dashboard em modo simulador
```

| Arquivo | Função |
|---|---|
| `clp_emulado.py` | Servidor Modbus RTU (pymodbus) com o mapa do Ladder: fila `D100`/`P10000`, relógio `P10001`, base `D17001`, Start `P10002`, reset `P10003`, 12 postos (estados 0–3), `D16052`, Andons programados. |
| `gateway.toml` | Configuração do Gateway real apontando para `socket://127.0.0.1:5020`. |
| `mockdesktop.toml` | Receptor e Dashboard apontando para o Gateway da demonstração. |
| `base_demo.csv` | 12 conjuntos de Takt/ciclo (P07 = 36 s). |
| `cdp_shot.py` | Captura de tela do Microsoft Edge sem janela (DevTools), esperando em tempo real. |

Os scripts de `dados/analise/` geraram as tabelas e os gráficos. Eles têm caminhos da máquina original e devem ser ajustados antes de rodar de novo; a entrada e a saída de cada um estão em [dados/README](../../dados/README.md).

> As medições da demonstração mostram o comportamento do **software real**. O CLP emulado simplifica o Ladder: não reproduz as redes reais dos postos nem os tempos elétricos de E/S.
