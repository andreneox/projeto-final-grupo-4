# README — Raspberry Pi (Gateway)

Serviço que roda na Raspberry Pi, lê o CLP LS XGK por Modbus RTU (USB-RS232), envia os Andons ao receptor por TCP, publica a telemetria por OPC UA, ajusta o relógio do CLP por SNTP e comanda o motor da esteira (DRV8825).

## Pré-requisitos

- Raspberry Pi com Raspberry Pi OS (64 bits), Python 3.11 ou superior e acesso SSH.
- Adaptador **USB-RS232 verdadeiro**. A UART dos GPIOs é TTL e não deve ser ligada direto em RS-232.
- Daemon `pigpiod`, se o motor for usado.
- Rede até o computador do receptor (TCP 15000) e liberação da porta OPC UA 4840.

## Instalação

```bash
# 1. Copie a pasta hardware para a Raspberry como ~/Gateway (no Windows)
scp -r hardware pi@<ip-da-raspberry>:~/Gateway

# 2. Na Raspberry, descubra a porta serial estável
ls -l /dev/serial/by-id/

# 3. Instale (servidor central, porta serial, ID do gateway)
cd ~/Gateway
sudo bash deploy/install.sh 192.168.1.10 /dev/serial/by-id/usb-FTDI_..._port0 LINHA_A
```

O instalador coloca o código em `/opt/lean-gateway`, a configuração em `/etc/lean-gateway/config.toml`, o banco em `/var/lib/lean-gateway/` e o log em `/var/log/lean-gateway/`, e inicia o serviço `gateway`. O passo a passo completo (cartão SD, SSH, certificados, motor e diagnóstico) está em `hardware/README_INSTALACAO_RASPBERRY.md`.

## Operação

```bash
sudo systemctl status gateway --no-pager     # estado
sudo journalctl -u gateway -f                 # log ao vivo
sudo systemctl restart gateway                # reiniciar após editar a configuração
sudo systemctl stop gateway                   # parar
```

Mensagens esperadas no log: `Gateway LINHA_A started`, `Modbus: connected`, `OPC UA: active and secure`, `SNTP: synchronized` e, a cada Andon, `TCP: event N confirmed`.

## Configuração principal (`/etc/lean-gateway/config.toml`)

| Seção | Chave | Valor | Observação |
|---|---|---|---|
| `[modbus]` | `port` | `/dev/serial/by-id/...` | Porta estável do adaptador. |
| `[modbus]` | `baudrate`, `device_id` | `115200`, `1` | Iguais ao *MODBUS Setup* do XG5000. |
| `[modbus]` | `process_status_address` / `production_count_address` | `651` / `15052` | Habilitam estados e contador na Dashboard. |
| `[tcp]` | `host` / `port` | IP do Windows / `15000` | Receptor de eventos. |
| `[ntp]` | `server` | IP do servidor de hora | UDP 123. |
| `[motor_output]` | `enabled`, `step_pin`, `dir_pin`, `en_pin` | `true`, `18`, `25`, `15` | DRV8825 (EN ativo em nível baixo). |

## Teste no Windows (sem Raspberry)

```powershell
cd hardware
Copy-Item config.example.toml config.toml   # ajuste port = "COM3" etc.
.\run_gateway.ps1                            # Ctrl+C encerra de forma ordenada
```

## Problemas comuns

| Sintoma | Solução |
|---|---|
| `Modbus: unavailable: No response` | Confira o cabo, a estação (`device_id`), 115200 8N1 e se o CLP está em RUN. |
| `could not open port` repetido | O adaptador foi desconectado ou mudou de nome; use `/dev/serial/by-id/`. O serviço reconecta sozinho a cada 2 s. |
| Eventos não chegam ao Windows | Verifique o `[tcp] host` e o firewall do Windows (porta 15000). Os eventos ficam guardados no SQLite e são reenviados. |
| Motor não gira | `pigpiod` ativo? `D112 = 1` e `D1200 > 0` no CLP? `[motor_output] enabled = true`? |

## Ver também

- Documentação técnica: `docs/Documentacao_Tecnica/03_Raspberry_Gateway.md`
- Guia completo: `hardware/README_INSTALACAO_RASPBERRY.md` · Mapa e contrato: `hardware/README.md`
