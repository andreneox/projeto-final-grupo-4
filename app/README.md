# App — Dashboard L4

Esta pasta só indica onde a Dashboard está implementada. O código fica em `simulador/web/`, servido pelo mesmo processo do receptor ([pipeline](../pipeline/README.md)). A pasta `simulador/app/` é outra coisa: a inicialização do simulador Desktop.

| Função | Implementação |
|---|---|
| Servidor FastAPI, API e WebSocket | [web/dashboard.py](../simulador/web/dashboard.py) |
| Páginas HTML | [web/templates](../simulador/web/templates) |
| JavaScript, estilos e slides da IT Digital | [web/static](../simulador/web/static) |
| Cálculo dos indicadores (OEE) | [services/analytics.py](../simulador/services/analytics.py) |
| Sincronismo da IT Digital com o P07 | [services/plc_work_instruction.py](../simulador/services/plc_work_instruction.py) |

| Página | Caminho |
|---|---|
| Dashboard e Andon Digital | `/` |
| Gráficos dos postos | `/graficos` |
| IT Digital E07 | `/instrucao/e07` |

**Executar:** `start.py`, na raiz. Endereço padrão: `http://127.0.0.1:8080`.

**Uso:** [README_Dashboard](../docs/README/README_Dashboard.md) e [README_IT_Digital](../docs/README/README_IT_Digital.md).
