# Firmware — CLP no lugar do ESP32

O projeto não usa ESP32, por isso não há arquivo `.ino`. As funções do firmware estão divididas assim:

| Função | Onde está |
|---|---|
| Leitura de botões e sensores | CLP LS XGK-CPUE, programa Ladder |
| Máquinas de estados, tempos de ciclo e fila de Andon | CLP LS XGK-CPUE, programa Ladder |
| Pulsos do motor da esteira (DRV8825) | Raspberry Pi, [gateway/motor_output.py](../gateway/motor_output.py) |
| Comunicação serial com o CLP | Raspberry Pi, [gateway/modbus_transport.py](../gateway/modbus_transport.py) e [gateway/plc_poller.py](../gateway/plc_poller.py) |

## Programa Ladder

| Campo | Valor |
|---|---|
| Projeto | `LAB_NEW_UPDATED` |
| Ferramenta | XG5000 4.74 |
| Comunicação | Modbus RTU escravo, estação 1, 115200 8N1 |

**Limitação:** o projeto exportado do XG5000 não está no repositório; só há capturas de tela. Sem o arquivo, não é possível recarregar o CLP. Quando disponível, deve ser colocado nesta pasta.

- Capturas e redes: [DOCUMENTACAO_CLP_LS_XGK](../../docs/Documentacao_Tecnica/DOCUMENTACAO_CLP_LS_XGK.md)
- Endereços e operação: [README_CLP](../../docs/README/README_CLP.md)
- Máquinas de estados: [FLUXOGRAMA_MAQUINA_ESTADOS_CLP](../../docs/Fluxogramas/FLUXOGRAMA_MAQUINA_ESTADOS_CLP.md)
