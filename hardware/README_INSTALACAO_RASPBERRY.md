# Instalação do Gateway na Raspberry Pi

Este guia permite começar em casa com uma Raspberry Pi, instalar o programa, criar o serviço `gateway.service` e verificar a inicialização automática. As integrações com CLP, motor, receptor de eventos e OPC UA são ativadas depois, quando os equipamentos estiverem disponíveis.

O caminho inicial usa CLP, GPIOs, sincronização do CLP e OPC UA desativados na configuração. O resultado dessa primeira etapa é um serviço instalado, banco e logs funcionando e o programa aguardando eventos.

As instruções correspondem à versão com leitura de D1200 e controle STEP/DIR/EN. A instalação de referência foi verificada em 16/11/2026 numa Raspberry Pi 3 B+, Raspberry Pi OS 13 Trixie de 32 bits e Python 3.13.5.

## Navegação

- [Como usar e stack](#1-como-usar-este-guia)
- [Equipamentos necessários](#2-o-que-você-precisa-ter)
- [Sistema, rede e SSH](#3-preparar-o-sistema-e-acessar-a-raspberry)
- [Transferência do projeto](#4-transferir-o-projeto)
- [Preparação sem periféricos](#5-preparar-a-primeira-instalação-sem-periféricos)
- [Instalação e criação do serviço](#6-instalar-e-criar-o-serviço)
- [Configuração ativa](#7-editar-e-validar-a-configuração-ativa)
- [CLP e mapa Modbus](#8-conectar-o-clp-por-usbrs232)
- [Motor e pigpiod](#9-preparar-o-motor-e-o-pigpiod)
- [Receptor TCP no computador](#10-configurar-o-receptor-tcp)
- [Horário do CLP](#11-configurar-o-horário-do-clp)
- [OPC UA e certificados](#12-habilitar-opc-ua-com-certificados)
- [Referência dos parâmetros](#13-referência-dos-parâmetros)
- [Operação, backup e atualização](#14-operação-atualização-e-recuperação)
- [Solução de problemas](#15-diagnóstico-e-problemas-comuns)
- [Pacote para distribuição](#16-preparar-um-pacote-para-outra-pessoa)
- [Resultados para conferir](#17-resultados-para-conferir)

## 1. Como usar este guia

Faça as seções 2 a 6 para instalar usando somente a Raspberry. A seção 7 ensina a editar a configuração ativa. As seções 8 a 12 conectam os demais componentes. As seções finais cobrem operação, recuperação e problemas comuns.

Blocos `powershell` são executados no computador Windows. Blocos `bash` são executados no terminal da Raspberry, diretamente ou pela conexão SSH. Blocos `toml` mostram campos do arquivo de configuração.

Os valores abaixo são exemplos. Use o usuário, os endereços e a porta serial da sua instalação.

| Informação | Exemplo usado no guia |
|---|---|
| Usuário de acesso à Raspberry | `operador`, criado no Raspberry Pi Imager |
| Nome da Raspberry | `gateway-casa` |
| IP da Raspberry | `192.168.1.50` |
| IP do computador receptor de eventos | `192.168.1.10` |
| Identificação da linha | `LINHA_CASA` |
| Porta serial temporária, com Modbus desativado | `/dev/ttyUSB0` |
| Porta serial para operação | Caminho real em `/dev/serial/by-id/` |

O usuário `gateway` será criado pelo instalador para executar o serviço. O acesso SSH continua usando o usuário criado no Imager.

Neste projeto, o Gateway é o programa que faz a ponte entre o CLP e os computadores da rede. CLP significa controlador lógico programável, o equipamento que executa a lógica da máquina. Um serviço é um programa administrado pelo sistema operacional, com execução em segundo plano e início automático. O prefixo `sudo` permite executar uma tarefa com privilégios administrativos.

### Stack utilizada

| Camada | Tecnologia e função |
|---|---|
| Sistema operacional | Raspberry Pi OS com Linux e systemd |
| Linguagem | Python 3.11 ou superior, necessário também para `tomllib` |
| Ambiente Python | `venv` em `/opt/lean-gateway/.venv` |
| Configuração | TOML em `/etc/lean-gateway/config.toml` |
| Comunicação com CLP | Modbus RTU por USB–RS232, usando `pymodbus[serial]` 3.11.3 |
| Controle do motor | `gpiozero` 2.0.1 e cliente `pigpio` 1.78, com daemon `pigpiod` |
| Telemetria | Servidor OPC UA, usando `asyncua` 1.1.5 |
| Certificados | X.509, usando `cryptography` 44.0.2 |
| Eventos | TCP com protocolo próprio, pacote de 16 bytes e ACK de 22 bytes |
| Persistência | SQLite com WAL, fila persistente e reenvio de eventos |
| Horário do CLP | Cliente SNTP em UDP/123 |
| Execução automática | Serviço `gateway.service`, usuário `gateway`, grupo `dialout` |
| Diagnóstico | `systemctl`, `journalctl` e arquivo de log com rotação |

As versões Python das dependências ficam em `requirements.txt`. O pacote `tzdata` desse arquivo é destinado ao Windows. No Raspberry Pi OS, o fuso é fornecido pelo sistema.

O Gateway é executado em segundo plano. A interface de acompanhamento e o receptor de eventos pertencem ao computador que se conecta à Raspberry.

## 2. O que você precisa ter

### Para instalar usando somente a Raspberry

| Item | Uso |
|---|---|
| Raspberry Pi 3 B/B+ ou 4 | Caminho de hardware para reproduzir o controle de motor deste guia |
| Fonte adequada ao modelo | Alimentação estável da placa |
| Cartão microSD e leitor | Instalação do sistema. Um cartão de 32 GB é uma escolha prática |
| Computador Windows, Linux ou macOS | Preparar o cartão, transferir os arquivos e acessar por SSH |
| Rede Ethernet ou Wi-Fi | Comunicação entre o computador e a Raspberry |
| Internet durante a instalação | Download do sistema e das dependências |
| Pacote atualizado `Gateway.zip` | Código do projeto e arquivos de instalação |

Uma Raspberry Pi com sistema, rede e acesso SSH já configurados pode seguir a partir da verificação da seção 3.

Para o motor, a versão atual seleciona explicitamente `PiGPIOFactory`. Raspberry Pi 5 exige uma adaptação do código para uma implementação GPIO compatível, como `lgpio`. A instalação inicial com GPIOs desativados pode ser usada para verificar a aplicação nessa placa. O fluxo de acionamento do motor descrito aqui tem como referência Pi 3/4. [Compatibilidade das implementações GPIO](https://gpiozero.readthedocs.io/en/stable/api_pins.html)

### Para a operação integrada

| Componente | O que deve estar pronto |
|---|---|
| CLP LS XGK-CPUE | Programa da linha e mapa Modbus compatível com a seção 8 |
| Adaptador USB–RS232 | Conversor com níveis elétricos RS232 e driver reconhecido no Linux |
| Cabo serial | Pinagem compatível com a porta do CLP e com o adaptador |
| Driver DRV8825 | Montagem, limite de corrente e dissipação adequados ao motor |
| Motor | Motor de passo bipolar compatível com o driver e com a carga |
| Fonte do motor | Alimentação externa adequada ao conjunto motor/driver |
| Componentes da montagem | Cabos, referência de GND comum, pull-up de EN e desacoplamento do driver |
| Computador receptor | Aplicação que receba o protocolo TCP do Gateway e confirme os eventos |
| Fonte de horário | Servidor NTP acessível, local ou pela internet |
| Cliente OPC UA, se utilizado | Certificado próprio, chave privada e confiança no certificado da Raspberry |

A classe do projeto conserva o nome `MotorDC`. A interface instalada é STEP/DIR/EN para DRV8825 e motor de passo bipolar. Verifique o tipo do motor disponível antes de montar o circuito. [Especificação do DRV8825](https://www.ti.com/lit/ds/symlink/drv8825.pdf)

O pacote Gateway contém a aplicação da Raspberry. O projeto do CLP e o programa receptor de eventos são componentes adicionais que devem ser obtidos com o responsável pelo sistema.

## 3. Preparar o sistema e acessar a Raspberry

### 3.1. Instalar o Raspberry Pi OS

1. Instale o Raspberry Pi Imager no computador.
2. Selecione o modelo da sua placa e Raspberry Pi OS Lite. O ambiente de referência deste guia usa a edição de 32 bits.
3. Selecione o microSD correto. A gravação apaga o conteúdo desse cartão.
4. Nas opções de personalização, configure o nome `gateway-casa`, um usuário, uma senha própria e a rede Wi-Fi, se necessária.
5. Habilite o acesso SSH. Para começar com senha, habilite essa forma de autenticação no Imager.
6. Grave o cartão, coloque-o na Raspberry, conecte a rede e ligue a alimentação.

O Lite oferece um terminal para administrar a aplicação. A edição com área de trabalho também pode executar o Gateway. [Preparação oficial da Raspberry Pi](https://www.raspberrypi.com/documentation/computers/getting-started.html)

### 3.2. Conectar por SSH

No Windows, abra o PowerShell e execute usando o usuário criado no Imager.

```powershell
ssh operador@gateway-casa.local
```

Se o nome `.local` não resolver, encontre o endereço da placa na lista de dispositivos do roteador e conecte pelo IP.

```powershell
ssh operador@192.168.1.50
```

Na primeira conexão, confira o endereço do equipamento e aceite o registro da chave quando solicitado. Digite a senha do usuário. O terminal oculta os caracteres da senha durante a digitação. O mesmo comportamento ocorre quando `sudo` pede a senha.

Ao entrar, o terminal passa a executar comandos na Raspberry. Um prompt semelhante a `operador@gateway-casa:~$` indica usuário, equipamento e pasta atual. [Acesso SSH na documentação oficial](https://www.raspberrypi.com/documentation/computers/remote-access.html)

### 3.3. Verificar a placa e o Python

Na Raspberry, execute os comandos abaixo, um por vez.

```bash
hostname
hostname -I
tr '\0' '\n' < /proc/device-tree/model
cat /etc/os-release
python3 --version
```

Confirme que o nome e o IP correspondem à placa que você pretende configurar. O Python deve mostrar uma versão 3.11 ou superior.

```bash
python3 -c "import sys, tomllib; assert sys.version_info >= (3, 11); print('Python compatível')"
```

Se a versão for anterior, prepare um Raspberry Pi OS que ofereça Python 3.11 ou superior. A instalação de referência usa Trixie com Python 3.13.

### 3.4. Preparar as ferramentas e o horário

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip unzip nano ca-certificates
sudo timedatectl set-timezone America/Manaus
sudo timedatectl set-ntp true
timedatectl status
```

Adapte o fuso ao local de uso e use o mesmo valor em `application.timezone`. Confira data e hora antes de gerar ou usar certificados OPC UA. O relógio do sistema também é usado como alternativa para atualizar o CLP quando a primeira consulta NTP falha.

## 4. Transferir o projeto

Receba o pacote atualizado `Gateway.zip` com o responsável pelo projeto. A seção 16 explica como preparar esse pacote a partir do código-fonte.

No PowerShell do computador Windows, envie o ZIP para a Raspberry. O exemplo considera o arquivo na pasta Downloads.

```powershell
scp "$env:USERPROFILE\Downloads\Gateway.zip" operador@192.168.1.50:~/
```

Na Raspberry, extraia o pacote numa pasta nova para esta primeira instalação.

```bash
mkdir -p ~/Gateway
unzip ~/Gateway.zip -d ~/Gateway
cd ~/Gateway
ls main.py requirements.txt deploy/install.sh deploy/gateway.service
```

O resultado deve listar os quatro arquivos. A raiz do pacote deve conter esta estrutura.

```text
Gateway/
├── main.py
├── requirements.txt
├── requirements-dev.txt
├── config.example.toml
├── README.md
├── README_INSTALACAO_RASPBERRY.md
├── gateway/
├── tools/
├── tests/
└── deploy/
    ├── install.sh
    ├── gateway.service
    └── config.raspberry.toml
```

Se o ZIP tiver uma pasta adicional chamada `Gateway`, entre nela até encontrar `main.py` e `deploy/install.sh` juntos.

Prepare a pasta vazia de certificados e normalize os finais de linha dos arquivos de instalação vindos do Windows.

```bash
mkdir -p certificates/trusted/clients
sed -i 's/\r$//' deploy/install.sh deploy/gateway.service
```

A pasta de certificados é copiada pelo instalador mesmo quando OPC UA está desativado. Na instalação inicial, ela pode permanecer vazia.

## 5. Preparar a primeira instalação sem periféricos

O modelo distribuído em `deploy/config.raspberry.toml` vem com as integrações habilitadas. O instalador inicia o serviço ao terminar. Para começar somente com a Raspberry, desative as quatro integrações no modelo antes de instalar.

Execute o bloco completo dentro de `~/Gateway`. Ele altera os campos `enabled` das quatro seções indicadas e verifica o resultado usando o leitor TOML do Python.

```bash
cd ~/Gateway
python3 - <<'PY'
from pathlib import Path
import tomllib

path = Path('deploy/config.raspberry.toml')
disabled = {'modbus', 'motor_output', 'ntp', 'opcua'}
section = ''
lines = []
for line in path.read_text(encoding='utf-8').splitlines():
    stripped = line.strip()
    if stripped.startswith('[') and stripped.endswith(']'):
        section = stripped[1:-1]
    if section in disabled and stripped.startswith('enabled ='):
        line = 'enabled = false'
    lines.append(line)
text = '\n'.join(lines) + '\n'
settings = tomllib.loads(text)
assert all(settings[name]['enabled'] is False for name in disabled)
path.write_text(text, encoding='utf-8')
for name in sorted(disabled):
    print(f'{name}.enabled = {settings[name]["enabled"]}')
PY
```

O resultado deve mostrar `False` para `modbus`, `motor_output`, `ntp` e `opcua`.

O envio TCP possui uma thread que aguarda eventos. Com banco novo e leitura do CLP desativada, essa fila começa vazia.

## 6. Instalar e criar o serviço

Execute na Raspberry.

```bash
cd ~/Gateway
sudo bash deploy/install.sh 127.0.0.1 /dev/ttyUSB0 LINHA_CASA
sudo install -m 0644 README_INSTALACAO_RASPBERRY.md /opt/lean-gateway/README_INSTALACAO_RASPBERRY.md
```

Os três argumentos representam o servidor, a porta serial e a identificação da linha. Nesta instalação inicial, o servidor aponta para a própria placa e a porta serial é um valor temporário. Modbus e NTP estão desativados. Os valores reais serão configurados quando esses componentes estiverem disponíveis.

O instalador cria o usuário `gateway`, prepara o ambiente Python, instala as dependências, copia o programa e registra o serviço. Aguarde a conclusão dos downloads. Caso apareça um erro de instalação, consulte a seção 15 antes de continuar.

| Caminho instalado | Conteúdo |
|---|---|
| `/opt/lean-gateway` | Código utilizado pelo serviço |
| `/opt/lean-gateway/.venv` | Python e dependências da aplicação |
| `/etc/lean-gateway/config.toml` | Configuração ativa |
| `/etc/lean-gateway/certificates` | Certificados e chaves para OPC UA |
| `/var/lib/lean-gateway/gateway.db` | Banco de eventos e fila de envio |
| `/var/log/lean-gateway/gateway.log` | Log da aplicação |
| `/etc/systemd/system/gateway.service` | Definição do serviço |

Se `pigpiod` ainda estiver ausente, o instalador pode emitir um aviso sobre o daemon. Para a etapa inicial com `motor_output.enabled = false`, a validação do Gateway pode prosseguir. A seção 9 instala esse daemon antes do uso do motor. O serviço declara `pigpiod` com uma dependência `Wants`, que permite iniciar o Gateway mesmo se o daemon estiver indisponível. [Semântica de dependências do systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)

### 6.1. Conferir o resultado

```bash
systemctl is-active gateway.service
systemctl is-enabled gateway.service
sudo systemctl status gateway.service --no-pager --full
sudo journalctl -u gateway.service -n 40 --no-pager
```

Os dois primeiros comandos devem retornar, respectivamente, `active` e `enabled`. O status deve conter `Active: active (running)`.

Nos logs dessa etapa, procure `Gateway LINHA_CASA started`, `TCP: waiting for events` e mensagens indicando `disabled` para Modbus, motor, SNTP e OPC UA.

O estado `active` confirma a execução do processo. As mensagens de cada componente mostram se a integração correspondente está pronta. Se aparecerem erros repetidos de porta serial ou NTP nesta etapa, confira os campos `enabled` do arquivo instalado.

### 6.2. Confirmar a inicialização automática

```bash
sudo reboot
```

A conexão SSH será encerrada. Aguarde a placa voltar à rede e conecte novamente a partir do computador.

```powershell
ssh operador@192.168.1.50
```

Na Raspberry, confirme.

```bash
systemctl is-active gateway.service
systemctl is-enabled gateway.service
```

Os resultados devem continuar sendo `active` e `enabled`. Fechar o terminal SSH permite que o serviço siga executando em segundo plano.

## 7. Editar e validar a configuração ativa

Antes de uma edição, faça uma cópia com data.

```bash
sudo cp -p /etc/lean-gateway/config.toml "/etc/lean-gateway/config.toml.bak-$(date -u +%Y%m%dT%H%M%SZ)"
```

Depois da instalação, edite este arquivo.

```bash
sudo nano /etc/lean-gateway/config.toml
```

No Nano, use as setas para navegar. `Ctrl+W` procura um texto. Para salvar, pressione `Ctrl+O` e depois Enter. Para sair, pressione `Ctrl+X`.

Localize cada seção entre colchetes e atualize os campos mostrados nas próximas seções. Cada nome de seção deve aparecer uma única vez no TOML.

Valide a configuração com o mesmo usuário que executa o serviço.

```bash
cd /opt/lean-gateway
sudo -u gateway /opt/lean-gateway/.venv/bin/python - <<'PY'
from gateway.config import load_settings

settings = load_settings('/etc/lean-gateway/config.toml')
print('Configuração válida para', settings.application.gateway_id)
PY
```

O comando confere a leitura TOML e os limites aceitos pelo programa. A comunicação e a montagem elétrica são verificadas nas etapas seguintes.

Para aplicar uma edição válida e acompanhar o resultado.

```bash
sudo systemctl restart gateway.service
sudo journalctl -u gateway.service -f
```

Pressione `Ctrl+C` para sair da visualização dos logs. O serviço segue executando.

### Onde cada configuração é usada

| Arquivo | Uso |
|---|---|
| `~/Gateway/deploy/config.raspberry.toml` | Modelo utilizado para gerar o arquivo ativo na primeira instalação |
| `/etc/lean-gateway/config.toml` | Arquivo indicado pelo `ExecStart` do serviço |
| `~/Gateway/config.toml` | Configuração para execução direta a partir da pasta do projeto |
| `~/Gateway/config.example.toml` | Exemplo e configuração alternativa para execução direta |

O instalador preserva um `/etc/lean-gateway/config.toml` já existente. Os argumentos de uma reinstalação só são aplicados à configuração quando esse arquivo é criado. Em toda execução, o instalador também substitui a pasta de certificados instalada pela pasta recebida no pacote. A seção 14 apresenta uma atualização que preserva a identidade e os certificados da instalação.

## 8. Conectar o CLP por USB–RS232

### 8.1. Identificar o adaptador

Conecte o adaptador USB à Raspberry e execute.

```bash
ls -l /dev/serial/by-id/
```

Um resultado possível é `/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0`, apontando para `/dev/ttyUSB0`. Copie o caminho exibido na sua placa.

Se a pasta estiver ausente, confira os dispositivos e as últimas mensagens do kernel.

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
sudo dmesg | tail -n 40
```

Se esses dispositivos estiverem ausentes, a etapa depende de conectar ou identificar corretamente o adaptador. USB–TTL e USB–RS232 possuem interfaces elétricas diferentes. Use um adaptador RS232 apropriado à porta do CLP e a pinagem de cabo indicada para os dois equipamentos.

### 8.2. Configurar a porta e o mapa

No arquivo ativo, configure o caminho real.

```toml
[modbus]
enabled = true
port = "/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0"
baudrate = 115200
bytesize = 8
parity = "N"
stopbits = 1
device_id = 1
```

O código atual valida 115200 e enquadramento 8N1. O CLP precisa usar esses valores, Modbus RTU e o mesmo `device_id`.

Confirme o mapa no projeto do CLP. Os números da coluna de endereços são os endereços Modbus usados pelo código, com base zero e espaços distintos para Input Registers, Holding Registers e Coils.

| Campo de configuração | Valor do modelo | Mapeamento esperado |
|---|---:|---|
| `d100_address` | `100` | FC04, 61 Input Registers correspondentes a D100–D160 |
| `motor_speed_address` | `200` | FC03/FC06, Holding Register correspondente a D1200 |
| `line_control_address` | `201` | Holding Register correspondente a D1201 |
| `clock_address` | `0` | FC16, quatro Holding Registers correspondentes a D1000–D1003 |
| `ack_kind` e `ack_address` | `coil`, `0` | P10000, confirmação de evento |
| `clock_apply_kind` e `clock_apply_address` | `coil`, `1` | P10001, aplicação do relógio |

Nesse modelo, o início dos Holding Registers em D1000 faz o endereço 200 corresponder a D1200. O início e os demais mapeamentos precisam ser definidos de acordo com o projeto do XGK.

Na configuração desta linha, use `event_byte_order = "big"`, `uint32_word_order = "low_high"` e `time_scale_to_seconds = 0.1`. O Gateway lê a palavra baixa primeiro e converte de décimos de segundo para segundos. Essas duas opções de tempo são compartilhadas entre Takt e Cycle.

### 8.3. O programa do CLP

O projeto do CLP deve implementar o contrato de comunicação descrito no [README técnico](README.md#contrato-do-clp).

- D100 informa os WORDs de eventos pendentes, em múltiplos de oito.
- D101–D108 apresentam um evento de 16 bytes e ficam estáveis até a confirmação.
- Após persistir o evento, o Gateway seta P10000. O CLP consome o evento e limpa esse bit.
- D112 informa `0` para desligado ou `1` para ligado.
- D1200 informa a porcentagem inteira de velocidade, entre `0` e `100`.
- D1201.bit0 representa a solicitação de parada da linha. O programa do CLP relaciona esse comando à sua lógica de D112.
- Para o relógio, o CLP aplica D1000–D1003 quando P10001 é acionado e limpa a solicitação depois.

Valide o arquivo e reinicie o serviço conforme a seção 7. Com cabo, CLP e mapa corretos, procure `Modbus: connected` no log. Mantenha `motor_output.enabled = false` enquanto verifica a comunicação e prepara a montagem do motor.

## 9. Preparar o motor e o pigpiod

### 9.1. Instalar o daemon

Em Raspberry Pi OS com os pacotes disponíveis, execute.

```bash
sudo apt update
sudo apt install -y pigpiod pigpio-tools
sudo systemctl enable --now pigpiod.service
systemctl is-active pigpiod.service
```

O último comando deve mostrar `active`. Os pacotes foram encontrados pelo APT na instalação de referência com Trixie de 32 bits. A disponibilidade pode variar conforme a edição do sistema. Se o APT informar pacote ausente, use a compilação descrita na seção 15.6.

O pacote Python `pigpio` instalado no ambiente virtual é o cliente. O processo `pigpiod` é instalado no sistema e atende o cliente. Confira a definição usada na placa.

```bash
systemctl cat pigpiod.service --no-pager
```

Na instalação de referência, o daemon inicia com `pigpiod -l`, restringindo o acesso de rede ao próprio equipamento. O Gateway utiliza essa conexão local.

### 9.2. Liberar o GPIO 15

GPIO 15 também pode ser usado pelo UART do sistema. Como o projeto utiliza USB–RS232 para o CLP e GPIO 15 para EN, libere esse pino do console e do UART antes de conectar o driver.

```bash
sudo raspi-config
```

Abra **Interface Options → Serial Port**, responda **No** para o login pela serial e **No** para habilitar o hardware serial. Finalize e reinicie a Raspberry. Essa configuração trata do UART nos pinos da placa. O adaptador USB–RS232 continua sendo configurado pelo seu caminho em `/dev/serial/by-id/`. [Configuração de console e UART](https://www.raspberrypi.com/documentation/computers/configuration.html)

### 9.3. Montar STEP, DIR e EN

Faça as conexões com a Raspberry e a fonte do motor desligadas. Identifique a orientação do conector de 40 pinos pela documentação da placa.

| Sinal do driver | GPIO BCM | Pino físico da Raspberry |
|---|---:|---:|
| STEP | 18 | 12 |
| DIR | 25 | 22 |
| EN / ENABLE / nENBL | 15 | 10 |
| GND comum | GND | 6, por exemplo |
| Referência 3,3 V para a lógica prevista na montagem | 3V3 | 1, por exemplo |

Os campos `step_pin`, `dir_pin` e `en_pin` recebem números BCM. Confira a pinagem do módulo DRV8825 específico, incluindo os nomes das saídas das bobinas. [Numeração e conector GPIO da Raspberry](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio)

EN é ativo em nível baixo. O circuito previsto utiliza um resistor externo de 10 kΩ entre EN e 3,3 V. RESET e SLEEP precisam estar em nível lógico alto para o driver operar. O chip aceita interface lógica de 3,3 V. [Características elétricas do DRV8825](https://www.ti.com/lit/ds/symlink/drv8825.pdf)

Alimente VMOT pela fonte externa escolhida para o motor e o módulo. Confira o limite de corrente, a ventilação, os pinos de micropasso e a recomendação de capacitor do fabricante. Para o carrier Pololu, a documentação recomenda pelo menos 47 µF próximos a VMOT e GND para reduzir picos. A conexão ou desconexão de bobinas com o driver energizado pode danificá-lo. A alimentação de potência fica fora dos GPIOs da Raspberry. [Montagem e ajustes do carrier](https://www.pololu.com/product/2133/)

### 9.4. Configurar e habilitar o motor

Com a montagem pronta, CLP comunicando e D112 em zero, edite a seção existente no arquivo ativo.

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

`clockwise_high` define o nível inicial de DIR. O sentido físico depende da ligação das bobinas e do lado observado. O mapa atual utiliza um sentido fixo. Ajuste a polaridade com o motor parado.

O alvo de frequência para uma porcentagem maior que zero é calculado por `mínima + (máxima - mínima) × porcentagem / 100`. Por exemplo, 50% solicita 2550 Hz. Durante a partida e a parada, a rampa pode atravessar frequências abaixo da mínima configurada.

O `pigpio` seleciona frequências PWM dentre as opções suportadas pelo daemon. Portanto, a frequência efetivamente gerada pode ser arredondada. A porcentagem é uma referência de comando, e a rotação depende de passos por volta, micropassos e transmissão mecânica. O programa registra a frequência comandada. [Frequências PWM do pigpio](https://raw.githubusercontent.com/joan2937/pigpio/v79/pigpio.py)

Valide o arquivo e reinicie o serviço. Procure `Motor: speed 0%, commanded frequency 0 Hz` com D112 em zero.

### 9.5. Verificar sem mandar o motor girar

Com o serviço ativo, D112 em zero e os GPIOs padrão, execute este diagnóstico de leitura.

```bash
/opt/lean-gateway/.venv/bin/python - <<'PY'
import pigpio

client = pigpio.pi()
if not client.connected:
    raise SystemExit('Falha de conexão com pigpiod')
try:
    print('EN GPIO15, esperado 1:', client.read(15))
    print('DIR GPIO25:', client.read(25))
    print('STEP GPIO18, duty esperado 0:', client.get_PWM_dutycycle(18))
finally:
    client.stop()
PY
```

O EN deve estar em 1, correspondente ao driver desabilitado. O duty cycle de STEP deve estar em zero. Adapte os números do diagnóstico se tiver configurado outros pinos.

### 9.6. Testar o movimento com o CLP

1. Deixe o mecanismo numa condição apropriada para o teste e confira a alimentação e o limite de corrente do driver.
2. Pelo programa de monitoramento do CLP, deixe D112 em `0` e coloque D1200 em `5` para começar com uma referência baixa.
3. Coloque D112 em `1`. O Gateway deve habilitar EN e aplicar a rampa até a referência.
4. Altere D1200 para outra porcentagem dentro de `0` a `100`. O novo alvo interrompe a rampa anterior.
5. Coloque D112 em `0`. O motor recebe uma desaceleração de aproximadamente `ramp_seconds` e depois EN é desabilitado.
6. Confirme também D1200 em `0`, que solicita parada e desabilitação.

A detecção de D112 depende do ciclo Modbus de 250 ms e do tempo das leituras. A rampa padrão acrescenta cerca de 0,5 segundo à parada. O circuito de parada de emergência da máquina deve atuar conforme o projeto elétrico. Esse comando de software possui esses atrasos e depende do processo em execução.

Falha de leitura desabilita o motor sem rampa. Quando chegam novas leituras válidas, o Gateway pode retomar o comando atual do CLP. No encerramento normal do serviço, o programa interrompe a rampa e libera as saídas. Na montagem, considere também perda de alimentação e encerramento forçado do processo.

## 10. Configurar o receptor TCP

O computador receptor deve executar uma aplicação compatível com os eventos de 16 bytes. O Gateway espera um ACK formado por vinte caracteres ASCII `0` seguidos de `15`, totalizando 22 bytes.

### 10.1. Preparar o receptor de referência no Windows

A pasta `simulador` deste repositório oferece o receptor de referência e uma dashboard. Copie o repositório e instale Python 3.11 no computador receptor. O exemplo considera os arquivos em `C:\Projetos\projeto-final-grupo-4\simulador`.

No PowerShell desse computador, prepare o ambiente.

Os comandos abaixo são para uma cópia nova do projeto. Se já existe um `config.toml` configurado nesse computador, faça seu backup e abra-o diretamente no Notepad para editar os campos indicados.

```powershell
cd C:\Projetos\projeto-final-grupo-4\simulador
py -3.11 --version
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.toml config.toml
notepad config.toml
```

Para uma configuração nova, ajuste as seções abaixo dentro desse `config.toml`.

```toml
[receiver]
host = "0.0.0.0"
port = 15000
database_path = "data/reference_receiver.db"
timezone = "America/Manaus"

[opcua_client]
enabled = false
```

O cliente OPC UA será ativado depois da troca dos certificados. Confira também `dashboard.host = "127.0.0.1"` e `dashboard.port = 8080`, ou outra porta livre nesse computador.

Inicie o receptor pelo mesmo módulo utilizado pelo lançador do projeto.

```powershell
.\venv\Scripts\python.exe -m tools.reference_receiver --config config.toml
```

Procure `Receptor TCP ouvindo em 0.0.0.0:15000`. Abra `http://127.0.0.1:8080` no navegador desse computador para a dashboard, usando a porta que tiver configurado. O receptor depende desse processo em execução. `Ctrl+C` encerra o processo. O lançador `run_receiver.ps1` também executa esse módulo quando o PowerShell permite a execução do script.

### 10.2. Apontar a Raspberry para o receptor

No Gateway, edite os campos da seção `[tcp]` usando o IP real do receptor.

```toml
[tcp]
host = "192.168.1.10"
port = 15000
connect_timeout_seconds = 5.0
send_timeout_seconds = 5.0
response_timeout_seconds = 5.0
```

O computador receptor precisa estar ligado, na rede acessível pela Raspberry, com a aplicação escutando e o firewall permitindo entrada TCP nessa porta.

Teste a abertura da conexão a partir da Raspberry, substituindo o IP do exemplo.

```bash
python3 - <<'PY'
import socket

with socket.create_connection(('192.168.1.10', 15000), timeout=5):
    print('Porta TCP do receptor acessível')
PY
```

Esse diagnóstico verifica a conexão de rede. Para validar o protocolo, gere um evento real pelo programa do CLP e procure `event ... confirmed` no log. Confirme o mesmo evento no receptor.

`TCP: waiting for events` indica fila vazia. A conexão de envio é aberta quando existe um evento pendente. Em uma falha de rede, os eventos permanecem no SQLite e são reenviados com retentativa.

## 11. Configurar o horário do CLP

No arquivo ativo, configure um servidor NTP acessível. Em uma rede doméstica com internet, `pool.ntp.org` pode ser usado como fonte de horário. Em uma rede industrial, use o servidor definido para aquela rede. [Uso do NTP Pool](https://www.ntppool.org/en/use.html)

```toml
[ntp]
enabled = true
server = "pool.ntp.org"
port = 123
timeout_seconds = 2.0
retry_interval_seconds = 10.0
sync_interval_seconds = 3600.0
apply_timeout_seconds = 5.0
```

O Gateway consulta esse servidor, converte o horário para `application.timezone`, escreve D1000–D1003 e solicita a aplicação por P10001. O CLP deve possuir a lógica correspondente e a comunicação Modbus deve estar ativa.

Para testar somente a consulta de rede, usando o mesmo servidor da sua configuração.

```bash
cd /opt/lean-gateway
/opt/lean-gateway/.venv/bin/python - <<'PY'
from gateway.ntp_client import query_sntp

print(query_sntp('pool.ntp.org', 123, 2.0))
PY
```

O resultado é um horário com fuso UTC. Timeout pode indicar bloqueio de UDP/123, resolução DNS ou servidor indisponível. A sincronização do relógio do CLP é confirmada no log por `SNTP: synchronized at ...` e pelo relógio observado no próprio CLP.

O serviço usa a hora obtida para atualizar o CLP. O relógio do Linux é administrado separadamente, conforme a seção 3.4. Na partida, se o NTP falhar, o Gateway tenta usar o relógio do sistema para atualizar o CLP e continua tentando consultar o NTP.

## 12. Habilitar OPC UA com certificados

Esta etapa exige o certificado do cliente que acessará a telemetria. O cliente também precisa confiar no certificado de servidor gerado para a Raspberry. O programa requer ao menos um certificado de cliente no diretório de confiança ao iniciar OPC UA.

### 12.1. Gerar a identidade do servidor

Use o IP real da sua Raspberry no argumento `--ip-address`. O comando abaixo gera uma identidade de laboratório usando a ferramenta do projeto.

```bash
cd /opt/lean-gateway
sudo install -d -o root -g dialout -m 0750 /etc/lean-gateway/certificates/trusted/clients
sudo /opt/lean-gateway/.venv/bin/python -m tools.generate_dev_certificates \
  --kind server \
  --name "Gateway Casa" \
  --application-uri "urn:mock-linha:servidor" \
  --ip-address 192.168.1.50 \
  --output-dir /etc/lean-gateway/certificates
sudo chown root:dialout /etc/lean-gateway/certificates/server_cert.der /etc/lean-gateway/certificates/server_key.pem
sudo chmod 0640 /etc/lean-gateway/certificates/server_cert.der /etc/lean-gateway/certificates/server_key.pem
```

A ferramenta gera uma chave RSA e um certificado autoassinado. O comando substitui os arquivos com esses nomes. Em uma instalação já integrada, a renovação de identidade exige atualizar também a confiança do cliente.

### 12.2. Autorizar o cliente

Obtenha do computador cliente seu certificado público `.der`, `.pem`, `.cer` ou `.crt`. Para o receptor da pasta `simulador`, o arquivo normalmente é `certificates/client/client_cert.der` dentro da pasta desse projeto.

Para a primeira configuração do receptor da pasta `simulador`, gere esse certificado no computador Windows.

```powershell
cd C:\Projetos\projeto-final-grupo-4\simulador
.\venv\Scripts\python.exe -m tools.generate_dev_certificates --kind client --name "Receiver Casa" --application-uri "urn:freeopcua:client" --output-dir certificates/client
```

No PowerShell do computador, envie o certificado público. O caminho do exemplo deve ser adaptado à localização do arquivo.

```powershell
scp "C:\Projetos\projeto-final-grupo-4\simulador\certificates\client\client_cert.der" operador@192.168.1.50:~/client_cert.der
```

Na Raspberry, instale-o com as permissões necessárias ao serviço.

```bash
sudo install -o root -g dialout -m 0640 ~/client_cert.der /etc/lean-gateway/certificates/trusted/clients/client_cert.der
```

A chave privada do cliente fica no computador cliente. Para distribuir o certificado público do servidor da Raspberry, prepare uma cópia na pasta do usuário.

```bash
sudo cp /etc/lean-gateway/certificates/server_cert.der ~/gateway_server_cert.der
sudo chown "$(id -u):$(id -g)" ~/gateway_server_cert.der
```

No PowerShell, baixe essa cópia pública.

```powershell
scp operador@192.168.1.50:~/gateway_server_cert.der "$env:USERPROFILE\Downloads\gateway_server_cert.der"
```

Configure o cliente para confiar nesse certificado e para usar sua própria chave e certificado. A URI de aplicação do cliente precisa corresponder à URI gravada em seu certificado.

Depois de baixar o certificado público da Raspberry, coloque-o na pasta do receptor.

```powershell
Copy-Item "$env:USERPROFILE\Downloads\gateway_server_cert.der" C:\Projetos\projeto-final-grupo-4\simulador\certificates\gateway_server_cert.der
```

No arquivo do receptor, complete os campos de `[opcua_client]`.

```toml
[opcua_client]
enabled = true
endpoint = "opc.tcp://192.168.1.50:4840/mock-linha/"
namespace_uri = "urn:mock-linha:telemetria:v1"
application_uri = "urn:freeopcua:client"
certificate_path = "certificates/client/client_cert.der"
private_key_path = "certificates/client/client_key.pem"
server_certificate_path = "certificates/gateway_server_cert.der"
reconnect_seconds = 3.0
```

Reinicie o receptor depois de ativar o servidor da Raspberry na próxima etapa. O programa valida a identidade confiável configurada. Gerar um novo certificado de cliente em uma instalação existente exige atualizar sua cópia no diretório de confiança da Raspberry.

### 12.3. Ativar e conferir

No arquivo ativo da Raspberry, confira a seção existente.

```toml
[opcua]
enabled = true
endpoint = "opc.tcp://0.0.0.0:4840/mock-linha/"
namespace_uri = "urn:mock-linha:telemetria:v1"
application_uri = "urn:mock-linha:servidor"
certificate_path = "/etc/lean-gateway/certificates/server_cert.der"
private_key_path = "/etc/lean-gateway/certificates/server_key.pem"
trusted_clients_dir = "/etc/lean-gateway/certificates/trusted/clients"
```

Valide o arquivo e reinicie o serviço. A inicialização do OPC UA pode levar dezenas de segundos numa Pi 3. Na máquina de referência, a ativação ocorreu cerca de 23 segundos depois da partida do programa. Acompanhe até aparecer `OPC UA: active and secure`.

```bash
sudo journalctl -u gateway.service -f
```

Em outro terminal, confira a porta.

```bash
ss -ltn 'sport = :4840'
```

O cliente remoto deve usar `opc.tcp://192.168.1.50:4840/mock-linha/`, com o IP real da Raspberry, política `Basic256Sha256` e modo `SignAndEncrypt`. O endereço `0.0.0.0` configura a escuta do servidor em suas interfaces.

São publicados 72 valores de telemetria para os 12 postos e os métodos `Linha/DefinirVelocidadeMotor` e `Linha/DefinirParada`. O primeiro escreve D1200. O segundo altera o bit 0 de D1201. A confirmação do método depende da escrita Modbus.

Com Modbus desativado, o servidor OPC UA pode iniciar, mas a telemetria permanece com valores iniciais e os métodos que dependem do CLP retornam erro. Para validar a integração completa, observe a atualização de um valor real do CLP no cliente.

## 13. Referência dos parâmetros

### Aplicação e caminhos

| Campo em `[application]` | Significado |
|---|---|
| `gateway_id` | Identificação usada na persistência e nos identificadores dos eventos |
| `database_path` | Banco SQLite. Para o serviço, use `/var/lib/lean-gateway/gateway.db` |
| `log_path` | Log. Para o serviço, use `/var/log/lean-gateway/gateway.log` |
| `timezone` | Fuso para interpretar e aplicar horários, por exemplo `America/Manaus` |

O serviço possui permissão de escrita nos diretórios de banco e log indicados. Caminhos relativos de desenvolvimento podem apontar para locais sem permissão quando usados em `/etc/lean-gateway`.

### Comunicação Modbus

| Campo em `[modbus]` | Valor do modelo e função |
|---|---|
| `enabled` | Ativa a thread de comunicação com o CLP |
| `port` | Caminho Linux do adaptador serial |
| `baudrate`, `bytesize`, `parity`, `stopbits` | `115200`, `8`, `N`, `1`, validados pelo código atual |
| `device_id` | `1`, endereço do CLP, aceito de 1 a 247 |
| `timeout_seconds` | `0.2`, timeout do transporte Modbus |
| `retries` | `2`, retentativas do cliente Modbus |
| `reconnect_seconds` | `2.0`, espera após falha do ciclo |
| `poll_interval_seconds` | `0.25`, período nominal. O código aceita de 0,2 a 0,3 segundo |
| `d100_address` | `100`, início do bloco de Input Registers |
| `motor_speed_address` | `200`, Holding Register de D1200 |
| `line_control_address` | `201`, Holding Register de D1201 |
| `clock_address` | `0`, início dos quatro registradores de relógio |
| `clock_apply_kind` | `coil`, tipo de saída para solicitar aplicação do relógio |
| `clock_apply_address` | `1`, endereço dessa solicitação |
| `clock_apply_active_value` | `1`, valor ativo da solicitação |
| `event_byte_order` | `big`, ordem dos bytes dos WORDs de evento |
| `uint32_word_order` | `low_high`, palavra baixa primeiro nos tempos de 32 bits |
| `time_scale_to_seconds` | `0.1`, conversão de décimos de segundo para segundos |
| `ack_kind` | `coil`, tipo de saída de confirmação de evento |
| `ack_address` | `0`, endereço da confirmação |
| `ack_active_value` | `1`, valor ativo da confirmação |

`clock_apply_kind` e `ack_kind` também aceitam `holding_register` quando esse for o mapeamento adotado no CLP.

### Motor

| Campo em `[motor_output]` | Valor do modelo e função |
|---|---|
| `enabled` | Ativa a thread e o acesso aos GPIOs |
| `step_pin`, `dir_pin`, `en_pin` | `18`, `25`, `15`, números BCM distintos entre 0 e 27 |
| `minimum_frequency`, `maximum_frequency` | `100.0`, `5000.0`, limites de referência para converter a porcentagem |
| `ramp_seconds` | `0.5`, duração de uma mudança de frequência |
| `clockwise_high` | `true`, polaridade do sentido fixo em DIR |
| `retry_interval_seconds` | `2.0`, espera para tentar recuperar o controle após falha de hardware/daemon |

Frequências e intervalos devem ser positivos e finitos. A mínima deve ser menor ou igual à máxima.

### Horário, TCP e OPC UA

| Seção e campos | Valor do modelo e função |
|---|---|
| `ntp.enabled` | Ativa consultas SNTP e atualização do relógio do CLP |
| `ntp.server`, `ntp.port` | Servidor escolhido e porta `123` |
| `ntp.timeout_seconds` | `2.0`, timeout da consulta |
| `ntp.retry_interval_seconds` | `10.0`, intervalo de nova tentativa após falha |
| `ntp.sync_interval_seconds` | `3600.0`, intervalo após sincronização completa |
| `ntp.apply_timeout_seconds` | `5.0`, espera pela aplicação do comando no transporte Modbus |
| `tcp.host`, `tcp.port` | Computador receptor e porta `15000` |
| `tcp.connect_timeout_seconds` | `5.0`, timeout de conexão |
| `tcp.send_timeout_seconds` | `5.0`, timeout de envio |
| `tcp.response_timeout_seconds` | `5.0`, timeout para receber o ACK completo |
| `opcua.enabled` | Ativa o servidor OPC UA |
| `opcua.endpoint` | `opc.tcp://0.0.0.0:4840/mock-linha/`, endereço de escuta |
| `opcua.namespace_uri` | `urn:mock-linha:telemetria:v1`, namespace esperado pelo cliente |
| `opcua.application_uri` | `urn:mock-linha:servidor`, deve corresponder ao certificado |
| `opcua.certificate_path` | Caminho do certificado público do servidor |
| `opcua.private_key_path` | Caminho da chave privada correspondente |
| `opcua.trusted_clients_dir` | Diretório com os certificados públicos dos clientes autorizados |

### Portas e sentido das conexões

| Origem → destino | Protocolo/porta | Uso |
|---|---|---|
| Computador → Raspberry | TCP/22 | SSH e SCP |
| Cliente OPC UA → Raspberry | TCP/4840 | Telemetria e métodos OPC UA |
| Raspberry → receptor | TCP/15000 | Envio dos eventos |
| Raspberry → servidor de horário | UDP/123 | SNTP |
| Cliente GPIO local → pigpiod local | TCP/8888 | Controle dos pinos na própria Raspberry |

Confirme o IP do receptor na rede usada em casa. `127.0.0.1` aponta para a máquina que executa o programa. O recebimento TCP no computador depende também do firewall desse computador. A reserva de IP pelo roteador facilita manter estáveis os endereços configurados.

## 14. Operação, atualização e recuperação

### 14.1. Comandos de uso diário

| Objetivo | Comando |
|---|---|
| Ver o estado | `sudo systemctl status gateway.service --no-pager --full` |
| Confirmar execução | `systemctl is-active gateway.service` |
| Confirmar início automático | `systemctl is-enabled gateway.service` |
| Iniciar | `sudo systemctl start gateway.service` |
| Parar normalmente | `sudo systemctl stop gateway.service` |
| Aplicar nova configuração | `sudo systemctl restart gateway.service` |
| Acompanhar logs | `sudo journalctl -u gateway.service -f` |
| Ver últimas mensagens | `sudo journalctl -u gateway.service -n 80 --no-pager` |
| Ler log em arquivo | `sudo tail -n 80 /var/log/lean-gateway/gateway.log` |
| Desativar execução e início automático | `sudo systemctl disable --now gateway.service` |
| Reativar execução e início automático | `sudo systemctl enable --now gateway.service` |

Use `Ctrl+C` para sair do acompanhamento de logs. Em uma listagem paginada, use `Q` para sair. A opção `--no-pager` mostra a saída diretamente no terminal.

Antes de executar manualmente outra instância do Gateway ou um programa de teste que controle os mesmos GPIOs, pare `gateway.service`. O serviço é o processo que deve administrar a porta serial e o motor nessa instalação.

### 14.2. Fazer backup antes de atualizar

Pare o serviço para obter uma cópia consistente do banco, incluindo seus arquivos auxiliares, e crie um backup completo da instalação atual.

```bash
sudo systemctl stop gateway.service
gateway_backup="/var/backups/lean-gateway/$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 0700 "$gateway_backup"
sudo tar -czpf "$gateway_backup/installation.tar.gz" -C / \
  opt/lean-gateway \
  etc/lean-gateway \
  etc/systemd/system/gateway.service \
  var/lib/lean-gateway \
  var/log/lean-gateway
printf 'Backup criado em %s\n' "$gateway_backup"
```

Anote o caminho exibido. O arquivo contém o ambiente Python, o banco e chaves privadas, além do código e da configuração. Se estiver fazendo somente um backup para continuar usando a mesma versão, inicie o serviço depois da cópia.

```bash
sudo systemctl start gateway.service
```

### 14.3. Atualizar uma instalação existente

Receba a nova versão, extraia em uma pasta separada, confira suas instruções de migração e faça o backup da seção anterior. Se a nova versão usa campos de configuração adicionais, atualize o arquivo ativo de acordo com a versão recebida.

Para uma atualização do código no mesmo formato de pastas deste projeto, execute os comandos abaixo dentro da raiz da nova versão, onde estão `main.py`, `gateway/` e `tools/`.

```bash
sudo systemctl stop gateway.service
sudo cp -a gateway/. /opt/lean-gateway/gateway/
sudo cp -a tools/. /opt/lean-gateway/tools/
sudo install -m 0644 main.py /opt/lean-gateway/main.py
sudo install -m 0644 requirements.txt /opt/lean-gateway/requirements.txt
sudo install -m 0644 README.md /opt/lean-gateway/README.md
sudo install -m 0644 README_INSTALACAO_RASPBERRY.md /opt/lean-gateway/README_INSTALACAO_RASPBERRY.md
sudo chown -R root:root /opt/lean-gateway/gateway /opt/lean-gateway/tools
sudo /opt/lean-gateway/.venv/bin/python -m pip install -r /opt/lean-gateway/requirements.txt
sudo /opt/lean-gateway/.venv/bin/python -m pip check
```

Se algum comando falhar, resolva a causa ou restaure o backup antes de iniciar a nova versão. Valide o arquivo ativo conforme a seção 7. Depois inicie e confira os logs.

```bash
sudo systemctl start gateway.service
sudo systemctl status gateway.service --no-pager --full
sudo journalctl -u gateway.service -n 80 --no-pager
```

Esse procedimento atualiza o código e as dependências. A identidade OPC UA, a configuração da linha e o banco continuam nos respectivos diretórios instalados.

Se a definição de `gateway.service` também tiver sido alterada na versão recebida, instale o arquivo revisado e recarregue o systemd antes da partida.

```bash
sudo install -m 0644 deploy/gateway.service /etc/systemd/system/gateway.service
sudo systemctl daemon-reload
```

### 14.4. Restaurar o backup

Use o caminho que foi exibido ao criar o backup. O exemplo abaixo pede esse caminho no terminal e verifica os membros do arquivo antes de restaurar.

```bash
read -r -p "Pasta do backup: " gateway_backup
sudo tar -tzf "$gateway_backup/installation.tar.gz" | sed -n '1,20p'
```

Confira se o arquivo é o backup da própria instalação. O procedimento abaixo guarda as pastas da versão atual com um sufixo antes de extrair o backup, evitando misturar os arquivos das duas versões.

```bash
sudo systemctl stop gateway.service
gateway_failed=$(date -u +%Y%m%dT%H%M%SZ)
sudo mv /opt/lean-gateway "/opt/lean-gateway.falha-$gateway_failed"
sudo mv /etc/lean-gateway "/etc/lean-gateway.falha-$gateway_failed"
sudo mv /var/lib/lean-gateway "/var/lib/lean-gateway.falha-$gateway_failed"
sudo mv /var/log/lean-gateway "/var/log/lean-gateway.falha-$gateway_failed"
sudo tar -xzpf "$gateway_backup/installation.tar.gz" -C /
sudo systemctl daemon-reload
sudo systemctl start gateway.service
sudo systemctl status gateway.service --no-pager --full
```

O backup completo inclui o banco no momento da cópia. Restaurá-lo também retorna os eventos e a fila àquele momento. Para recuperar apenas código ou configuração preservando eventos mais recentes, selecione os arquivos a restaurar com o responsável técnico.

## 15. Diagnóstico e problemas comuns

### 15.1. Serviço ausente ou processo reiniciando

| Sintoma | Verificação e ação |
|---|---|
| `Unit gateway.service could not be found` | Confira `hostname` e IP. Verifique se o instalador terminou e se existe `/etc/systemd/system/gateway.service` |
| `activating (auto-restart)` ou `failed` | Leia `journalctl`. Um erro TOML, caminho ou dependência pode encerrar o processo |
| Serviço ativo e componente `unavailable` | Leia a mensagem do componente. CLP, TCP, NTP, motor e OPC UA possuem estados próprios |
| Arquivo editado sem efeito | Confira o `ExecStart` com `systemctl cat gateway.service --no-pager` e edite o arquivo indicado |
| `Permission denied` em banco ou log | Use os caminhos `/var/lib/lean-gateway` e `/var/log/lean-gateway`. Confira proprietário e permissões desses diretórios |

Se a aplicação foi instalada, mas a definição do serviço estiver ausente, a raiz do pacote contém o arquivo utilizado pelo instalador.

```bash
cd ~/Gateway
sudo install -m 0644 deploy/gateway.service /etc/systemd/system/gateway.service
sudo systemctl daemon-reload
sudo systemctl enable --now gateway.service
```

Esses comandos pressupõem que `/opt/lean-gateway/.venv/bin/python`, `/opt/lean-gateway/main.py` e `/etc/lean-gateway/config.toml` já existem. Se a instalação terminou com erro antes de criá-los, corrija a causa e conclua a instalação.

### 15.2. CLP e motor

| Sintoma | Causa a verificar |
|---|---|
| Porta serial inexistente | Adaptador desconectado, caminho incorreto ou dispositivo sem driver |
| Timeout Modbus | Alimentação do CLP, cabo e pinagem RS232, 115200/8N1, endereço do escravo e mapa |
| `D1200 motor speed must be ...` | D1200 fora de 0–100 ou endereço Modbus incorreto |
| `D112 motor command must be 0 or 1` | D112 fora do contrato ou bloco mapeado incorretamente |
| `Can't connect to pigpio` | Daemon parado, porta local indisponível ou hardware incompatível com o daemon |
| Motor habilitado, sem movimento | D112, D1200, VMOT, bobinas, STEP/DIR, RESET/SLEEP e limite de corrente |
| Motor gira no sentido oposto | Pare o motor e confira `clockwise_high` e a ligação das bobinas |
| Motor perde passos ou esquenta | Corrente, dissipação, fonte, micropassos, carga, alvo de frequência e rampa |

Com somente a Raspberry disponível, configure `modbus.enabled = false`, `motor_output.enabled = false` e `ntp.enabled = false` para a etapa local. A ausência dos dispositivos explica as falhas de comunicação enquanto essas integrações estiverem habilitadas.

### 15.3. Rede, horário e OPC UA

| Sintoma | Causa a verificar |
|---|---|
| Timeout TCP | IP do receptor, rede, aplicação escutando e firewall TCP/15000 |
| `waiting for events` | Fila vazia. Gere um evento pelo CLP para testar o envio completo |
| Timeout SNTP | IP/DNS, servidor respondendo NTP e saída UDP/123 |
| Falha ao aplicar relógio | Estado da comunicação Modbus e implementação de P10001 no CLP |
| Certificado ausente ou sem clientes confiáveis | Execute a seção 12 antes de habilitar OPC UA |
| Certificado fora da validade | Data/hora do sistema e validade dos certificados |
| `ApplicationUri` incompatível | URI configurada diferente da URI gravada no certificado correspondente |
| Porta 4840 ausente logo após partida | Aguarde a inicialização e leia o estado OPC UA no log |
| Cliente remoto sem conexão | Use o IP da Raspberry no endpoint, confira firewall e confiança mútua |

### 15.4. Instalação de dependências Python

O instalador utiliza um ambiente virtual. Execute os comandos de dependências com `/opt/lean-gateway/.venv/bin/python`.

Se o download falhar, confira internet, DNS, horário do Linux e as mensagens do `pip`. Para falha de compilação de dependências nativas, instale as ferramentas do sistema e repita a instalação no ambiente virtual.

```bash
sudo apt install -y build-essential python3-dev libffi-dev libssl-dev pkg-config rustc cargo
sudo /opt/lean-gateway/.venv/bin/python -m pip install -r ~/Gateway/requirements.txt
```

A compilação pode levar vários minutos em uma Pi 3. Se aparecer falta de memória durante a compilação, verifique se o sistema e os índices configurados oferecem wheels compatíveis com a arquitetura e versão de Python usadas.

O erro `No module named tomllib` indica Python anterior a 3.11. `set: ... invalid option` no instalador pode indicar finais de linha Windows. Para este último caso, execute a normalização da seção 4 e tente novamente.

### 15.5. Testes de software sem CLP físico

Na pasta de fontes, crie um ambiente de teste separado do serviço.

```bash
cd ~/Gateway
python3 -m venv .venv-teste
.venv-teste/bin/python -m pip install -r requirements-dev.txt
.venv-teste/bin/python -m pytest tests/test_motor_output.py tests/test_modbus_transport.py tests/test_plc_poller.py tests/test_config.py -q
```

Esses testes usam transporte e GPIOs simulados. O teste integral de OPC UA em `tests/test_opcua_integration.py` possui uma espera de inicialização de dez segundos. Essa janela foi insuficiente na Pi 3 de referência. A integração segura foi verificada separadamente com uma janela de sessenta segundos, incluindo 72 nós, telemetria e métodos.

Para verificar a aplicação instalada, use também os critérios das seções 6, 9 e 12. O status e os logs do serviço mostram a inicialização nas condições reais da placa.

### 15.6. Alternativa para instalar pigpiod a partir do código-fonte

Use esta etapa se o sistema da Pi 3/4 não oferecer `pigpiod` pelo APT. O projeto upstream disponibiliza a versão `v79` e compilação com `make`. Os comandos instalam o daemon nativo, sua biblioteca e o utilitário `pigs`. O cliente Python já é instalado pelo `requirements.txt` do Gateway. Essa alternativa foi conferida no Makefile upstream. A máquina de referência utilizou os pacotes APT. [Código do pigpio](https://github.com/joan2937/pigpio/tree/v79)

```bash
sudo apt install -y git build-essential
cd ~
git clone --depth 1 --branch v79 https://github.com/joan2937/pigpio.git pigpio-src
cd ~/pigpio-src
make -j2 pigpiod pigs
sudo install -d /usr/local/bin /usr/local/lib
sudo install -m 0755 pigpiod pigs /usr/local/bin/
sudo install -m 0755 libpigpio.so.1 /usr/local/lib/
sudo ldconfig
command -v pigpiod
```

Depois de os comandos acima concluírem, registre o daemon usando o caminho efetivamente instalado.

```bash
pigpio_binary=$(command -v pigpiod)
test -n "$pigpio_binary"
sudo tee /etc/systemd/system/pigpiod.service >/dev/null <<EOF
[Unit]
Description=Pigpio local GPIO daemon

[Service]
Type=forking
ExecStart=$pigpio_binary -l
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now pigpiod.service
sudo systemctl status pigpiod.service --no-pager --full
```

O arquivo segue a execução por daemon do upstream e usa `-l` para a conexão local. Depois de confirmar `active`, retome a seção 9. [Makefile](https://github.com/joan2937/pigpio/blob/v79/Makefile) · [Unidade upstream](https://github.com/joan2937/pigpio/blob/v79/util/pigpiod.service)

## 16. Preparar um pacote para outra pessoa

No computador que possui o código atualizado, abra o PowerShell na pasta Gateway. O comando abaixo cria um ZIP com o programa, instalador, exemplos, testes e documentação. Configuração ativa, bancos, logs e chaves privadas ficam fora dessa seleção.

```powershell
Compress-Archive -Path gateway,tools,tests,deploy,main.py,requirements.txt,requirements-dev.txt,config.example.toml,README.md,README_INSTALACAO_RASPBERRY.md -DestinationPath "$env:USERPROFILE\Downloads\Gateway.zip" -Force
```

Entregue esse ZIP à pessoa que seguirá o guia. A pasta vazia de certificados será criada na seção 4. Os certificados próprios para OPC UA serão preparados na seção 12.

Se o programa receptor e o projeto do CLP também forem necessários para a montagem completa, entregue-os com suas respectivas instruções. O instalador da Raspberry configura o Gateway e seu serviço.

## 17. Resultados para conferir

| Etapa concluída | Evidência |
|---|---|
| Instalação somente com a Raspberry | `gateway.service` ativo e habilitado, banco e log criados, integrações externas desativadas |
| Reinício da placa | Serviço volta a `active` depois do boot |
| CLP conectado | `Modbus: connected`, valores coerentes e mapa validado |
| Motor preparado | EN desabilitado com D112=0, STEP sem pulsos e montagem conferida |
| Movimento | D112 habilita e D1200 altera a referência de velocidade |
| Parada | D112=0 ou D1200=0 produz a rampa e a desabilitação previstas |
| Receptor TCP | Evento real aparece no receptor e o Gateway registra confirmação |
| Horário | Log de sincronização e relógio do CLP coerentes |
| OPC UA | `active and secure`, cliente confiável conecta e recebe telemetria real |
| Recuperação | Backup identificado e procedimento de restauração disponível |

O ambiente de referência teve o serviço, as dependências, o OPC UA e os níveis dos GPIOs verificados. Os testes de software foram executados com simulações. A instalação a partir de um cartão recém-gravado e o funcionamento com todos os dispositivos físicos exigem essas verificações no equipamento montado.
