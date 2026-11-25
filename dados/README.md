# Dados — amostras e análises

## `amostras/`

| Arquivo ou pasta | Conteúdo | Origem |
|---|---|---|
| `gateway_events.json` | 18 eventos de Andon do posto P05, com latências do ACK ao CLP e do ACK TCP | **CLP real**, 27/09/2026 |
| `execucao_1_demo/` | Demonstração completa: linha do tempo (`timeline.jsonl`, 90 amostras), chamadas da API, saídas do Gateway, do receptor e do CLP emulado | CLP emulado, 21/11/2026 |
| `execucao_2_it_digital/` | Sincronismo da IT Digital E07 com o P07 (`it_timeline.json`) e saídas dos processos | CLP emulado, 21/11/2026 |
| `desktop/` | Saída do receptor com o simulador Desktop | Simulador, 21/11/2026 |
| `testes/` | Resultados dos testes automatizados (`junit_*.xml`, `pytest_*.txt`, `tests_summary.json`) | `pytest`, 21/11/2026 |

São dados brutos, mantidos como foram gerados. Na demonstração com CLP emulado, o Gateway, o receptor e a Dashboard são os reais. O log e os bancos da execução real não estão incluídos; veja [Evidências](../docs/Evidencias/README.md).

## `analise/`

| Script | O que produz | Entrada | Entrada incluída? |
|---|---|---|---|
| `fig_demo.py` | Gráficos da demonstração (estados, produção e OEE) | `timeline.jsonl` | Sim |
| `fig_real.py` | Gráficos da latência dos eventos e do log | `gateway_events.json`, `gateway.log` | Só o extrato de eventos |
| `finalize_imgs.py` | Imagens da IT Digital e gráfico de sincronismo | `it_timeline.json`, capturas, banco | Em parte |
| `junit_summary.py` | `tests_summary.json` | `junit_*.xml` | Sim |
| `gen_tex.py` | Tabelas do relatório (seção de testes e anexo) | `tests_summary.json`, `gateway_events.json` | Sim |
| `latency.py` | `gateway_events.json` e estatísticas de latência | Bancos SQLite | Não |
| `log_stats.py` | Totais do log do Gateway | `gateway.log` | Não |

Os scripts contêm caminhos absolutos da máquina em que foram executados. Ajuste esses caminhos antes de rodar. `gen_tex.py` sobrescreve `secao8_testes.tex` e `anexo.tex` na pasta de destino.

## Reproduzir

Gerar novos dados com o CLP emulado: [docs/Evidencias](../docs/Evidencias/README.md). Bases de tempos para o simulador: [simulador/bases_exemplo](../simulador/bases_exemplo/LEIA_ME_BALANCEAMENTO.md).
