# Documentação do CLP LS XGK-CPUE

Projeto `LAB_NEW_UPDATED` · XG5000 4.74 · Linha com 12 postos

O CLP executa o programa Ladder, trata os sinais dos postos, mede os ciclos e publica dados para a Raspberry Pi. Este documento reúne as redes visíveis nas capturas e o mapa utilizado pelo software do Gateway.

## Como o programa está organizado

| Programa | Função observada |
|---|---|
| `BUTTONS` | Processa bordas das entradas digitais `P00000` a `P0000B`, atualiza `D01501` e aciona marcas internas como `M00020`. |
| `ANDON` | Trata eventos de Andon e relógio, serve o buffer de comunicação, executa as sequências dos postos e gera sinais da linha. |
| `MENSAGEM_ANDON` | Sub-rotina de `ANDON` que grava na fila `D00300` o tipo de mensagem, o posto, a data/hora, o botão e o estado. |

No XG5000, os dois programas de varredura aparecem em **Scan Program**. A configuração serial fica em **Parameter → Basic Parameter → MODBUS Setup**. As figuras 01–03 mostram essas telas e a versão do software.

## Navegação

- [Comunicação e mapa Modbus](#comunicação-e-mapa-modbus)
- [Botões e eventos de Andon](#botões-e-eventos-de-andon)
- [Estados e tempos dos postos](#estados-e-tempos-dos-postos)
- [Comandos, relógio e motor](#comandos-relógio-e-motor)
- [Capturas do XG5000](#capturas-do-xg5000)

O [documento de arquitetura](../Arquiteturas/ARQUITETURA_COMUNICACAO_LINHA.md) mostra como o CLP, a Raspberry Pi e o Windows se comunicam.

<!-- page -->

## Comunicação e mapa Modbus

O Gateway é o cliente Modbus RTU. O CLP responde como estação `1`, pela interface serial RS-232, com `115200` baud e `8N1` (8 bits de dados, sem paridade e 1 bit de parada). O intervalo de consulta configurado no modelo da Raspberry Pi é de `250 ms`.

A figura 01 mostra as bases `P0000` e `P1000` para as áreas digitais e `D00000` e `D01000` para as áreas de palavras. No quadro, **Endereço Modbus** usa base zero e é interpretado dentro da respectiva área. `D00100` e `D100` referem-se à mesma palavra na notação usada no projeto.

| Endereço no XG5000 | Área e função | Endereço Modbus | Dados |
|---|---|---:|---|
| `D00100–D00160` | Input Registers, FC04 | `100–160` | Cabeçalho e evento, Andons, comando de motor e tempos. |
| `D01000–D01003` | Holding Registers, FC16 | `0–3` | Quatro palavras do relógio em BCD. |
| `D01200` | Holding Register, FC03 / FC06 | `200` | Referência de velocidade de 0 a 100. |
| `D01201.0` | Holding Register, FC03 / FC06 | `201`, bit 0 | Solicita parada em `1` e libera em `0`. |
| `D01651–D01662` | Holding Registers, FC03 | `651–662` | Estado de P01 a P12, uma palavra por posto. |
| `D16052` | Holding Register, FC03 | `15052` | Contador de produção, uma palavra sem sinal. |
| `D17001–D17288` | Holding Registers, FC16 / FC03 | `16001–16288` | Base de tempos dos 12 postos. |
| `P10000` | Coil, FC05 | `0` | Confirma a captura de um evento FIFO. |
| `P10001` | Coil, FC05 | `1` | Solicita a aplicação do relógio. |
| `P10002` | Coil, FC05 | `2` | Pulso de Start. |
| `P10003` | Coil, FC05 | `3` | Pulso de reset dos postos. |

Os endereços seguem o modelo de implantação `hardware/deploy/config.raspberry.toml`. Nesse modelo, os tempos de 32 bits são lidos com a palavra baixa primeiro (`low_high`) e convertidos de décimos de segundo para segundos (`0.1`). As opções `process_status_address` e `production_count_address` habilitam as leituras desses dados no Gateway. O exemplo genérico e o arquivo local de desenvolvimento têm valores diferentes para a ordem e a escala dos tempos.

<!-- page -->

## Botões e eventos de Andon

### Leitura e estados em BUTTONS

`D01501` recebe o valor inicial `100`. Para cada entrada, `n` identifica sua posição de 1 a 12. O exemplo da primeira entrada, `P00000`, corresponde à sequência `100 → 1 → 13 → 25 → 100`.

| Estado antes da borda | Borda da entrada correspondente | Próximo estado |
|---|---|---|
| `100` | Descida (`N`) | `n`, entre `1` e `12`. |
| `n` | Subida (`P`) | `n + 12`, entre `13` e `24`. |
| `n + 12` | Descida (`N`) | `n + 24`, entre `25` e `36`. |
| `n + 24` | Subida (`P`) | `100`. |

O Ladder agrupa as três fases de cada entrada para manter sua marca interna ativa. A figura 08 mostra `M00020` ativa quando `D01501` vale `1`, `13` ou `25`. As figuras 04–08 mostram as transições e as primeiras marcas.

### Geração e confirmação do evento

1. Uma borda na marca interna dispara a rede de `ANDON`. As redes exemplificadas usam `D00030` para o posto, `D00031` para o botão e `D00032` para o estado (`1` ligado, `2` desligado). O timestamp é lido por `DATERD` em `D00040–D00043`.
2. `MENSAGEM_ANDON` grava oito palavras na FIFO `D00300` com `FIWR`. O tipo do evento real é `1`. Os identificadores do botão são `1` Qualidade (amarelo), `2` Equipamento (azul), `3` Processo (verde) e `4` Material (vermelho).
3. Com `D00050 = 1` e fila não vazia, o Ladder copia o cabeçalho para `D00100` e retira as oito palavras para `D00101–D00108` com `FIFRDP`. `D00100` representa a quantidade pendente em palavras, em múltiplos de oito. `D00050 = 2` mantém o bloco disponível para a leitura do Gateway.
4. O Gateway persiste o evento em SQLite e só então aciona `P10000`. O CLP avança para `D00050 = 3`, zera as nove palavras publicadas e retorna ao estado `1`. A captura mostra o reset de `P10000` na rede que publica o próximo evento com a FIFO não vazia.

`D00109–D00111` são o estado instantâneo dos Andons no contrato do Gateway, quatro postos por palavra. Cada posto ocupa quatro bits, na ordem Qualidade, Equipamento, Processo e Material. As figuras 09–13 mostram a FIFO, a confirmação e exemplos de eventos.

<!-- page -->

## Estados e tempos dos postos

O Gateway lê `D01651–D01662` como um vetor de 12 estados para o nó OPC UA `Linha/StatusProcesso`. Nos postos capturados com sequência completa, `0` corresponde à espera, `1` à preparação, `2` à medição e `3` à etapa de conclusão. Os postos automáticos 08–10 mostrados nas capturas entram diretamente do estado `0` no `2` após a condição de entrada.

| Posto | Estado | Temporizador | Palavra inicial do último ciclo | O que a captura mostra |
|---|---|---|---|---|
| P01 | `D01651` | `T0001` | `D00115` | `M00101` habilita a sequência e `D16041` recebe o incremento. |
| P02 | `D01652` | `T0002` | `D00119` | `M00102` habilita o posto e `D16042` recebe o incremento. |
| P07 | `D01657` | `T0007` | `D00139` | Posto manual. A borda de `P0000D` leva ao estado `3`. |
| P08 | `D01658` | `T0008` | `D00143` | Entrada por `P0000D` e término pela borda de `P0000C`. |
| P09 | `D01659` | `T0009` | `D00147` | Entrada por `P0000C` e término pela borda de `P0000F`. |
| P10 | `D01660` | `T0010` | `D00151` | Entrada por `P0000F`, término pela borda de `P0000E` e sinal ao P11 por `M0011B`. |
| P11 | `D01661` |  |  | O trecho disponível mostra a entrada de `M0011B` e os primeiros estados. |

O bloco de telemetria reserva quatro palavras por posto a partir de `D00113`. As duas primeiras representam o Takt time e as duas seguintes, o último ciclo. Para o P12, são `D00157–D00158` e `D00159–D00160`. A produção total acompanha `D16052` quando essa leitura está habilitada no Gateway.

A IT Digital E07 usa a transição do P07 para o estado `2`. O receptor Windows controla o avanço da instrução. O Ladder registra o estado do posto em `D01657`.

As figuras 14–21 mostram entradas, marcas, temporizadores e exemplos da sequência. Os postos 03–06 e 12 integram o mapa de 12 estados, e as redes completas desses postos não aparecem nas imagens fornecidas.

<!-- page -->

## Comandos, relógio e motor

### Base de tempos, Start e reset

- **Base de tempos.** O Gateway aceita 12 tempos por posto, converte os segundos para décimos e grava duas cópias em 24 palavras por posto. São 288 palavras a partir de `D17001`, com leitura de conferência após cada gravação.
- **Start.** O Gateway exige base conferida, 12 estados em `0` e Andons livres. Pulsa `P10002` por 2 s. A figura 14 mostra a borda acionando `M00101`. A confirmação usa a entrada FC04 de execução, se configurada, ou o estado `2` de algum posto. O Gateway aguarda até 8 s pela confirmação.
- **Reset.** **Limpar base** pulsa `P10003` por 2 s. A rede capturada limpa estados, temporizadores e contadores. O Gateway verifica `D16052 = 0` e, quando a leitura de estados está configurada, exige os 12 postos em `0` ou `1`.

### Relógio interno

O Gateway escreve quatro palavras BCD, depois aciona `P10001`. No trecho capturado, `P10001` e `D01000` diferente de zero acionam `DATEWRP D01000`, e a própria rede limpa a solicitação. O dia da semana vai de `0` (domingo) a `6` (sábado).

| Palavra | Byte alto | Byte baixo |
|---|---|---|
| `D01000` | Mês | Ano com dois dígitos |
| `D01001` | Hora | Dia do mês |
| `D01002` | Segundo | Minuto |
| `D01003` | Século | Dia da semana |

### Sinais da linha e comando de motor

Na figura 21, as marcas `M00010–M00013` compõem `M00014`. A saída `D00112.0` é ligada quando `D01501 = 100` e ao menos um dos postos 08 a 10 está com estado diferente de zero. O Gateway lê o comando em `D00112` e a velocidade em `D01200`. A solicitação de parada do Gateway usa `D01201.0`, conforme o contrato de integração. A figura 21 mostra a condição da saída do motor e as marcas de sincronização.

### Fontes do projeto

[Mapa e contrato do CLP no Gateway](../../hardware/README.md#mapa-logico) · [Modelo de implantação](../../hardware/deploy/config.raspberry.toml) · [Transporte Modbus](../../hardware/gateway/modbus_transport.py) · [Controle de ciclos](../../hardware/gateway/cycle_control.py)

## Capturas do XG5000

As 21 figuras são recortes do projeto LAB_NEW_UPDATED. Os endereços nas legendas conservam os zeros à esquerda exibidos na tela.

- [Projeto e configuração Modbus](#projeto-e-configuração-modbus)
- [Programa BUTTONS](#programa-buttons)
- [Eventos de Andon e relógio](#eventos-de-andon-e-relógio)
- [Postos e sinais da linha](#postos-e-sinais-da-linha)

### Projeto e configuração Modbus

![Tela MODBUS Setup com parâmetros seriais e áreas de memória](../Relatorio_Final/Imagens/clp_01_configuracao_modbus.png)

**Figura 01.** Configuração Modbus RTU da estação `1`, a `115200` baud, com 8 bits de dados, sem paridade e 1 bit de parada. A tela exibe as áreas `P0000`, `P1000`, `D00000` e `D01000`.

![Árvore do projeto com o CLP XGK-CPUE e os programas ANDON e BUTTONS](../Relatorio_Final/Imagens/clp_02_arvore_projeto.png)

**Figura 02.** Árvore do projeto `LAB_NEW_UPDATED`, com a CPU LS XGK-CPUE e os programas `ANDON` e `BUTTONS` abaixo de *Scan Program*.

![Janela Sobre indicando XG5000 versão 4.74](../Relatorio_Final/Imagens/clp_03_versao_xg5000.png)

**Figura 03.** Versão `4.74` do XG5000, exibida na janela *About XG5000*.

### Programa BUTTONS

![Inicialização e primeiro conjunto de transições em D01501](../Relatorio_Final/Imagens/clp_04_buttons_inicializacao.png)

**Figura 04.** Inicialização de `D01501` em `100`. As bordas de descida das entradas `P00000` a `P0000B` selecionam os estados `1` a `12`.

![Bordas de subida acionando os estados 13 a 24](../Relatorio_Final/Imagens/clp_05_buttons_borda_subida.png)

**Figura 05.** As bordas de subida das mesmas entradas levam `D01501` dos estados `1–12` para `13–24`.

![Bordas de descida acionando os estados 25 a 36](../Relatorio_Final/Imagens/clp_06_buttons_borda_descida.png)

**Figura 06.** As bordas de descida seguintes levam `D01501` dos estados `13–24` para `25–36`.

![Condições de retorno ao estado 100](../Relatorio_Final/Imagens/clp_07_buttons_retorno.png)

**Figura 07.** Nos estados `25–36`, a borda de subida da entrada correspondente retorna `D01501` ao estado `100`.

![Trecho que relaciona estados D01501 às marcas M00020 em diante](../Relatorio_Final/Imagens/clp_08_buttons_marcas.png)

**Figura 08.** Exemplo de conversão dos estados em marcas usadas pelo `ANDON`. `M00020` fica ativa nos estados `1`, `13` ou `25`.

### Eventos de Andon e relógio

![Início do programa ANDON com leitura do relógio e retirada da FIFO](../Relatorio_Final/Imagens/clp_09_andon_leitura_fila.png)

**Figura 09.** `DATERD` lê o relógio em `D00040`. O trecho também mostra o início da retirada de dados da FIFO `D00300` para o bloco `D00100–D00108`.

![Final da retirada da FIFO e reconhecimento pelo Gateway](../Relatorio_Final/Imagens/clp_10_andon_ack_gateway.png)

**Figura 10.** `D00050 = 2` aguarda o ACK em `P10000`. Ao chegar ao estado `3`, a lógica zera as nove palavras a partir de `D00100` e retorna ao estado `1`.

![Rede de ajuste de data e hora e exemplo de Andon amarelo](../Relatorio_Final/Imagens/clp_11_andon_relogio_amarelo.png)

**Figura 11.** A solicitação em `P10001`, com `D01000` diferente de zero, aciona `DATEWRP` e limpa o bit da solicitação. A mesma captura mostra a rede do Andon amarelo.

![Redes de eventos dos Andons verde e vermelho](../Relatorio_Final/Imagens/clp_12_andon_verde_vermelho.png)

**Figura 12.** Exemplos das redes dos Andons verde e vermelho. As bordas em `M00022` e `M00023` disparam o preenchimento dos dados do evento.

![Sub-rotina MENSAGEM_ANDON com gravações FIWR](../Relatorio_Final/Imagens/clp_13_andon_gravacao_fila.png)

**Figura 13.** A sub-rotina `MENSAGEM_ANDON` usa `FIWR` para enfileirar o evento em `D00300`, incluindo identificação, data/hora, botão e estado.

### Postos e sinais da linha

![Redes de inicialização, limpeza e Start antes do Posto 01](../Relatorio_Final/Imagens/clp_14_inicializacao_start_reset.png)

**Figura 14.** Redes de inicialização e limpeza, com `P10003` no reset e `P10002` acionando a marca `M00101` para o Posto 01.

![Máquina de estados do Posto 01 com D01651 e temporizador T0001](../Relatorio_Final/Imagens/clp_15_posto_01.png)

**Figura 15.** Posto 01. O estado fica em `D01651` e o tempo medido em `T0001` é copiado para `D00115`.

![Máquina de estados do Posto 02 com D01652 e temporizador T0002](../Relatorio_Final/Imagens/clp_16_posto_02.png)

**Figura 16.** Posto 02. O estado fica em `D01652` e a conclusão incrementa o contador `D16042`.

![Posto 07 manual e início do Posto 08](../Relatorio_Final/Imagens/clp_17_posto_07_manual.png)

**Figura 17.** Posto 07 manual. O registrador `D01657` guarda o estado do posto e a borda de `P0000D` conduz a transição ao estado `3`.

![Posto 08 automático e início do Posto 09](../Relatorio_Final/Imagens/clp_18_posto_08_auto_1.png)

**Figura 18.** Posto 08 (Auto 1). `P0000D` habilita a temporização de entrada e a borda de `P0000C` encerra a medição.

![Máquina de estados do Posto 09 e início do Posto 10](../Relatorio_Final/Imagens/clp_19_posto_09_auto_2.png)

**Figura 19.** Posto 09 (Auto 2). O estado fica em `D01659`. A borda de `P0000F` encerra o ciclo e o tempo de `T0009` é copiado para `D00147`.

![Posto 10 automático e passagem ao Posto 11](../Relatorio_Final/Imagens/clp_20_posto_10_auto_3.png)

**Figura 20.** Posto 10 (Auto 3). Ao concluir o ciclo, a lógica registra o tempo em `D00151`, incrementa `D16050` e sinaliza o Posto 11 com `M0011B`.

![Geração do sinal M00014 e condição de comando do motor em D00112](../Relatorio_Final/Imagens/clp_21_sinais_e_motor.png)

**Figura 21.** As marcas `M00010–M00013` compõem `M00014`. A saída `D00112.0` depende de `D01501 = 100` e de pelo menos um dos Postos 08 a 10 estar com estado diferente de zero.
