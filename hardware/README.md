# Gateway LS XGK

O [guia de instalação na Raspberry Pi](README_INSTALACAO_RASPBERRY.md) apresenta o passo a passo desde a preparação do sistema até a criação do serviço, começando com a Raspberry sem periféricos conectados.

Servico headless entre um CLP LS XGK-CPUE e a infraestrutura da linha. O
Gateway le o CLP por Modbus RTU/RS232C, publica a telemetria pelo mesmo OPC UA
seguro do Simulador e entrega eventos pelo mesmo protocolo TCP de 16 bytes.

O projeto e orientado para Raspberry Pi/Linux ARM64. O Windows e suportado para
desenvolvimento e testes.

## Garantias

- O evento e gravado no SQLite com `WAL` e `synchronous=FULL` antes de `P10000`.
- A fila TCP e global, persistente e FIFO.
- Um evento so e confirmado depois do ACK ASCII de 22 bytes do servidor.
- Falhas usam retentativa com backoff e eventos pendentes sobrevivem a reinicios.
- O identificador combina Gateway, data/hora do pacote e CRC32.
- Os 16 bytes originais sao sempre comparados; colisao CRC nunca descarta dados.
- O receiver aceita reenvio identico de forma idempotente e devolve novo ACK.
- Telemetria de alta frequencia permanece em memoria, reduzindo escrita no SD.
- O cliente SNTP tenta continuamente e nao bloqueia eventos quando a rede cai.

## Mapa logico

| Dispositivo | Conteudo |
|---|---|
| D100 | WORDs de eventos pendentes: 0, 8, 16, 24... |
| D101-D108 | Pacote de evento, 16 bytes sem alteracao; D101 = 1 |
| D109 | Andons P01-P04, quatro bits por posto |
| D110 | Andons P05-P08 |
| D111 | Andons P09-P12 |
| D112 | Comando do motor da Raspberry: 1 ligado, 0 desligado |
| D113-D114 | Takt P01, UInt32 |
| D115-D116 | Cycle P01, UInt32 |
| D117-D118 | Takt P02, seguindo o mesmo passo |
| D157-D158 | Takt P12 |
| D159-D160 | Cycle P12 |
| D1651-D1662 | Status do processo de P01 a P12, um WORD por posto |
| D16052 | Total de itens produzidos, um WORD sem sinal |
| D1000 | Mes (MSB) e ano com dois digitos (LSB), ambos BCD |
| D1001 | Hora (MSB) e dia do mes (LSB), ambos BCD |
| D1002 | Segundo (MSB) e minuto (LSB), ambos BCD |
| D1003 | Seculo (MSB) e dia da semana (LSB), ambos BCD |
| D1200 | Velocidade do motor, inteiro de 0 a 100 |
| D1201.bit0 | Comando de parada: 1 para parar, 0 para liberar |
| P10000 | Confirmacao do evento, bit 0 do WORD P1000 |
| P10001 | Solicitacao para aplicar o relogio, bit 1 do WORD P1000 |
| P10003 | Reset dos postos, pulso de 2 s na coil Modbus 3 |

Em cada nibble: bit 0 Qualidade, bit 1 Equipamento, bit 2 Processo e bit 3
Material. O Gateway le 61 Input Registers por FC04, de D100 a D160, a cada
250 ms.

O comando `D112` vem do CLP e aceita somente 0 ou 1. A cada ciclo, o Gateway
tambem consulta `D1200` por FC03, no Holding Register configurado por
`motor_speed_address` (200 quando o mapeamento AO inicia em D1000). D1200 aceita
somente inteiros de 0 a 100. O comando completo segue para uma thread dedicada
ao DRV8825, com STEP no GPIO 18, DIR no GPIO 25 e EN ativo LOW no GPIO 15.

Com D112=1 e D1200 maior que zero, o motor acelera ate a porcentagem solicitada.
A frequencia comandada segue `minimum_frequency + (maximum_frequency -
minimum_frequency) * porcentagem / 100`, com duty cycle de 50%. D112=0 ou
D1200=0 desaceleram ate zero e desabilitam EN. As rampas sao interrompidas por
novos comandos e usam `ramp_seconds` (0,5 segundo por padrao). Leituras repetidas
do mesmo comando preservam a rampa em andamento.

Falha de leitura ou comando invalido desabilitam EN sem rampa. Uma nova leitura
valida permite aplicar o estado atual do CLP. No encerramento do Gateway, a
thread interrompe a rampa, desabilita EN e libera os GPIOs. O sentido fica fixo
pela configuracao `clockwise_high`; o mapa atual nao tem registrador de sentido.

O cliente SNTP consulta o servidor central por UDP/123. Quando recebe uma
resposta valida, converte a hora para `America/Manaus` e escreve D1000-D1003 em
uma unica operacao FC16. Em seguida, seta P10001 para o CLP executar
`DATEWR D1000`; o CLP deve limpar P10001 depois da aplicacao. O formato segue a
instrucao LS `DATEWR`: domingo vale
0, segunda 1 e assim por diante ate sabado 6. O CLP aplica os quatro WORDs ao
relogio interno. Se NTP ou Modbus estiver indisponivel, o Gateway continua
operando e tenta novamente no intervalo configurado. Se o NTP nao responder na
partida, o Gateway aplica uma vez a hora atual do proprio sistema ao CLP e
continua tentando obter a hora autoritativa do servidor NTP.

## Identificacao dos Andons

O evento nao usa um ID global de 1 a 48. Sua identidade e a combinacao do posto
`station` com o `button_id`. O status do evento e `1` para ON e `2` para OFF.

| Andon | Cor | Categoria | station | button_id |
|---|---|---|---:|---:|
| AndonP1 | Amarelo | Qualidade | 1 | 1 |
| AndonP1 | Azul | Equipamento | 1 | 2 |
| AndonP1 | Verde | Processo | 1 | 3 |
| AndonP1 | Vermelho | Material | 1 | 4 |
| AndonP2 | Amarelo | Qualidade | 2 | 1 |
| AndonP2 | Azul | Equipamento | 2 | 2 |
| AndonP2 | Verde | Processo | 2 | 3 |
| AndonP2 | Vermelho | Material | 2 | 4 |
| AndonP3 | Amarelo | Qualidade | 3 | 1 |
| AndonP3 | Azul | Equipamento | 3 | 2 |
| AndonP3 | Verde | Processo | 3 | 3 |
| AndonP3 | Vermelho | Material | 3 | 4 |
| AndonP4 | Amarelo | Qualidade | 4 | 1 |
| AndonP4 | Azul | Equipamento | 4 | 2 |
| AndonP4 | Verde | Processo | 4 | 3 |
| AndonP4 | Vermelho | Material | 4 | 4 |
| AndonP5 | Amarelo | Qualidade | 5 | 1 |
| AndonP5 | Azul | Equipamento | 5 | 2 |
| AndonP5 | Verde | Processo | 5 | 3 |
| AndonP5 | Vermelho | Material | 5 | 4 |
| AndonP6 | Amarelo | Qualidade | 6 | 1 |
| AndonP6 | Azul | Equipamento | 6 | 2 |
| AndonP6 | Verde | Processo | 6 | 3 |
| AndonP6 | Vermelho | Material | 6 | 4 |
| AndonP7 | Amarelo | Qualidade | 7 | 1 |
| AndonP7 | Azul | Equipamento | 7 | 2 |
| AndonP7 | Verde | Processo | 7 | 3 |
| AndonP7 | Vermelho | Material | 7 | 4 |
| AndonP8 | Amarelo | Qualidade | 8 | 1 |
| AndonP8 | Azul | Equipamento | 8 | 2 |
| AndonP8 | Verde | Processo | 8 | 3 |
| AndonP8 | Vermelho | Material | 8 | 4 |
| AndonP9 | Amarelo | Qualidade | 9 | 1 |
| AndonP9 | Azul | Equipamento | 9 | 2 |
| AndonP9 | Verde | Processo | 9 | 3 |
| AndonP9 | Vermelho | Material | 9 | 4 |
| AndonP10 | Amarelo | Qualidade | 10 | 1 |
| AndonP10 | Azul | Equipamento | 10 | 2 |
| AndonP10 | Verde | Processo | 10 | 3 |
| AndonP10 | Vermelho | Material | 10 | 4 |
| AndonP11 | Amarelo | Qualidade | 11 | 1 |
| AndonP11 | Azul | Equipamento | 11 | 2 |
| AndonP11 | Verde | Processo | 11 | 3 |
| AndonP11 | Vermelho | Material | 11 | 4 |
| AndonP12 | Amarelo | Qualidade | 12 | 1 |
| AndonP12 | Azul | Equipamento | 12 | 2 |
| AndonP12 | Verde | Processo | 12 | 3 |
| AndonP12 | Vermelho | Material | 12 | 4 |

Os enderecos do protocolo Modbus nao devem ser inferidos diretamente dos nomes
`D100` e `P10000`. Configure os enderecos efetivamente mapeados no XGK em
`d100_address` e `ack_address`.

Os enderecos Modbus de `D1200` e `D1201` tambem sao configuraveis. Ao comandar
uma parada, o Gateway faz leitura-modificacao-escrita de D1201 e preserva todos
os bits diferentes do bit 0.

## Contrato do CLP

O CLP escreve primeiro D101-D108 e deixa o buffer imutavel. D100 informa a
quantidade total de WORDs pendentes e deve ser zero ou multiplo de 8. O Gateway
persiste o primeiro evento, executa o COMMIT e somente entao seta P10000 pela
Coil Modbus 0. O CLP consome o evento, reduz D100 em 8 e limpa P10000.

O WORD D101 e sempre `1` para identificar uma mensagem de evento de Andon.

O Gateway nao sintetiza eventos pelas mudancas dos bits de Andon. Esses bits
representam o estado atual para OPC UA; o buffer D101-D108 e a fonte oficial dos
eventos.

## Pontos a confirmar no XGK

Antes de habilitar o Modbus, confirme no projeto do CLP:

- endereco Modbus zero-based correspondente a D100;
- Holding Register 0 correspondente a D1000;
- Coil 0 correspondente a P10000;
- Coil 1 correspondente a P10001;
- Slave ID;
- ordem `high_low` ou `low_high` dos UInt32;
- escala dos tempos, por exemplo `0.001` para milissegundos;
- enderecos Modbus correspondentes a D1200 e D1201;
- IP ou DNS do servidor NTP central e liberacao de UDP/123.

O exemplo vem com `modbus.enabled=false` para impedir escrita acidental.

## Windows

```powershell
cd hardware
Copy-Item config.example.toml config.toml
..\venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_gateway.ps1
```

Edite `config.toml` antes de ativar o Modbus. No Windows, `port` pode ser
`COM3`, `COM4` etc.

## Raspberry Pi

Habilite a saida em `config.toml`:

```toml
[motor_output]
enabled = true
step_pin = 18
dir_pin = 25
en_pin = 15
minimum_frequency = 100.0
maximum_frequency = 5000.0
ramp_seconds = 0.5
clockwise_high = true
retry_interval_seconds = 2.0
```

Instale e inicie o daemon `pigpio` antes do Gateway. Os pacotes Python `pigpio`
e `gpiozero` sao instalados por `requirements.txt` somente no Linux. O controle
usa `gpiozero` com `PiGPIOFactory`. Se o daemon cair, o Gateway tenta reconectar.
EN deve ter o pull-up externo de 10k para 3V3 previsto na montagem do controlador.
Configuracoes antigas podem usar `gpio` como alias de `step_pin`; configure
explicitamente os tres pinos conforme a ligacao do DRV8825.

Utilize um adaptador USB-RS232 verdadeiro; a UART GPIO da Raspberry usa nivel
TTL e nao deve ser conectada diretamente a RS232.

Depois de copiar e extrair o pacote na Raspberry, descubra a porta serial:

```bash
ls -l /dev/serial/by-id/
```

Execute o instalador informando o servidor central, a porta serial e,
opcionalmente, o ID deste Gateway:

```bash
cd ~/Gateway
sudo bash deploy/install.sh 192.168.1.10 \
  /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_ABCD-if00-port0 LINHA_A
```

O instalador cria o usuario de servico, instala em `/opt/lean-gateway`, cria a
`venv`, instala dependencias, configura caminhos persistentes, habilita o motor
nos GPIOs STEP 18, DIR 25 e EN 15 e inicia `gateway.service`. Uma configuracao existente em
`/etc/lean-gateway/config.toml` nunca e sobrescrita por uma reinstalacao.

Prefira uma porta estavel como `/dev/serial/by-id/...` no `config.toml`. Para o
servico, o instalador configura banco e log em
`/var/lib/lean-gateway/gateway.db` e `/var/log/lean-gateway/gateway.log`.

Comandos de operacao:

```bash
sudo systemctl status gateway --no-pager
sudo journalctl -u gateway -f
sudo systemctl restart gateway
sudo systemctl stop gateway
```

## SNTP

Configure `[ntp].server` com o IP ou nome DNS do servidor central. Na partida, a
primeira consulta ocorre imediatamente. Falhas usam `retry_interval_seconds`;
depois de uma sincronizacao completa, uma nova consulta ocorre a cada
`sync_interval_seconds`. A implementacao valida modo, versao, stratum, estado
de sincronismo e o timestamp de origem antes de aceitar a resposta.

O servico nao altera o relogio do sistema operacional nem requer privilegio
`CAP_SYS_TIME`; ele usa diretamente a hora validada pela resposta SNTP para
atualizar o CLP.

## OPC UA

O Gateway expoe os mesmos 72 NodeIds do Simulador no namespace
`urn:mock-linha:telemetria:v1`: quatro Andons, TaktTime e UltimoCiclo por posto.
O endpoint aceita exclusivamente Basic256Sha256 com SignAndEncrypt.

O objeto OPC UA `Linha` expoe dois metodos de controle:

- `Linha/DefinirVelocidadeMotor(UInt16)`: aceita somente valores de 0 a 100 e
  escreve D1200;
- `Linha/DefinirParada(Boolean)`: define ou limpa apenas o bit 0 de D1201.

As chamadas entram na fila do poller e usam a mesma thread da porta serial. O
cliente OPC UA so recebe sucesso depois da escrita Modbus ser confirmada.

### Base de ciclos e Start da simulação

- `Linha/CarregarBaseCiclos` recebe 144 tempos em segundos, agrupados por posto, de P01 a P12. O Gateway converte para décimos de segundo, repete cada sequência de 12 e grava e confere 24 palavras por posto. A área começa no holding register `modbus.cycle_base_address` (`16001`, correspondente a `D17001`).
- `Linha/BaseCiclosCarregada` informa se os 12 blocos foram conferidos desde a partida do Gateway. Uma gravação parcial ou falha de leitura do CLP invalida a conferência. O Ladder deve utilizar a base completa após o pedido de Start.
- `Linha/IniciarSimulacao` pulsa `modbus.simulation_start_address` (`2`, correspondente a `P10002`) por 2 segundos. O Gateway mantém as leituras e tenta liberar a coil em caso de falha na escrita ou ao encerrar o serviço. O Ladder deve prever o retorno a zero se perder a comunicação durante o pulso.
- Antes do pulso, o Gateway confere a base carregada, a leitura dos 12 estados exatamente em 0 e os Andons livres.
- `modbus.simulation_running_address` é o endereço FC04 do estado do Ladder (`0` parado, `1` em execução). O Gateway aguarda até 8 segundos pela confirmação. Quando esse endereço está ausente, o estado 2 em um dos postos confirma o Start se `modbus.process_status_address` estiver configurado.
- `Linha/LimparBase` pulsa `modbus.reset_base_address` (`3`, correspondente a `P10003`) por 2 s, inclusive durante o processamento. Após liberar a coil, confere `D16052 = 0` e, quando os estados estão configurados, aguarda os 12 postos em 0 ou 1. O Ladder deve zerar o contador e devolver os postos ao estado inicial.

Para publicar o contador `D16052` em `Linha/TotalProduzido` no OPC UA, defina
`modbus.production_count_address = 15052`. Esse é o endereço FC03 com Holding
Register 0 em D1000. A dashboard usa a quantidade registrada pelo CLP.

Para substituicao transparente do mock, use de forma segura a mesma identidade
de servidor OPC UA, ou atualize o certificado fixado no cliente do receiver.
Certificados nunca sao gerados durante a inicializacao.

Credenciais de desenvolvimento podem ser geradas explicitamente:

```powershell
..\venv\Scripts\python.exe -m tools.generate_dev_certificates `
  --kind server --name "Gateway Linha" `
  --application-uri "urn:mock-linha:servidor" `
  --output-dir certificates
```

O certificado do cliente do receiver deve existir em
`certificates/trusted/clients`.

## Testes

```powershell
..\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
..\venv\Scripts\python.exe -m pytest -q
```

Os testes nao exigem CLP fisico: transporte Modbus, persistencia, colisao,
ordem COMMIT/P10000, SNTP, TCP e OPC UA sao exercitados com simuladores locais.
