# README — CLP LS XGK-CPUE

O CLP executa o programa Ladder da linha (projeto `LAB_NEW_UPDATED`, XG5000 4.74). Ele lê os botões de Andon e os sensores, controla a sequência dos 12 postos, mede os tempos de ciclo e disponibiliza tudo ao Gateway por Modbus RTU.

## O que é preciso

- CPU LS XGK-CPUE com o projeto `LAB_NEW_UPDATED` carregado.
- XG5000 (versão 4.74 ou compatível) para editar e monitorar o Ladder.
- Cabo RS-232 até o adaptador USB-RS232 da Raspberry Pi.

## Configuração da comunicação

No XG5000: **Parameter → Basic Parameter → MODBUS Setup**.

| Parâmetro | Valor |
|---|---|
| Modo | Modbus RTU (escravo) |
| Estação | 1 |
| Velocidade | 115200 baud |
| Formato | 8 bits, sem paridade, 1 stop (8N1) |
| Áreas | Bit: `P0000` / `P1000` · Palavra: `D00000` / `D01000` |

## Endereços usados pelo Gateway

| Dado | Endereço no CLP |
|---|---|
| Evento de Andon (fila) | `D00100`–`D00108` |
| Andons atuais | `D00109`–`D00111` |
| Comando do motor | `D00112` (0/1) e velocidade `D01200` (0–100) |
| Takt e último ciclo | `D00113`–`D00160` |
| Estado dos postos | `D01651`–`D01662` (0 espera, 1 preparação, 2 processando, 3 fim) |
| Produção total | `D16052` |
| Base de tempos | `D17001`–`D17288` |
| Relógio (BCD) | `D01000`–`D01003` |
| Comandos | `P10000` ACK · `P10001` relógio · `P10002` Start · `P10003` reset |

## Operação

- **Andon:** pressionar o botão do posto liga o Andon; pressionar de novo desliga. Cada mudança vira um evento na fila `D00300`, entregue ao Gateway um por vez.
- **Start / Reset:** vêm da Dashboard (pulsos de 2 s em `P10002` e `P10003`). Não force essas bobinas manualmente com a linha em produção.
- **Relógio:** é ajustado automaticamente pelo Gateway (SNTP). O dia da semana vai de 0 (domingo) a 6 (sábado).

## Como verificar

1. No XG5000, monitore `D00050` (deve ficar em 1 sem eventos pendentes) e `D00100` (0 sem eventos).
2. Pressione um Andon: `D00100` vai a 8 e volta a 0 em poucos milissegundos, quando o Gateway confirma (`P10000`).
3. Na Dashboard, a coluna do posto fica vermelha.

Se `D00100` ficar em 8, o Gateway não está lendo o CLP: confira o cabo, a estação e a velocidade.

## Ver também

- Documentação técnica: `docs/Documentacao_Tecnica/04_CLP.md`
- Capturas e redes do Ladder: `docs/Documentacao_Tecnica/DOCUMENTACAO_CLP_LS_XGK.md` · Máquinas de estados: `docs/Fluxogramas/FLUXOGRAMA_MAQUINA_ESTADOS_CLP.md`
