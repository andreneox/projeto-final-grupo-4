# README — Desktop (Simulador da Linha)

Aplicativo Windows que simula os 12 postos da linha: cada clique em um Andon envia o evento ao receptor e atualiza a telemetria OPC UA, exatamente como o CLP e o Gateway fariam. Use-o para demonstrar e testar a Dashboard sem o hardware.

## Pré-requisitos

- Windows 10/11 com Python 3.11 ou 3.12.
- Ambiente virtual `venv` na raiz do projeto (criado uma vez, ver abaixo).
- Receptor e Dashboard em execução (`README_Dashboard.md`) para receber os eventos.

## Instalação (uma vez)

```powershell
# na raiz do projeto
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r simulador\requirements.txt
```

## Executar

Para iniciar o receptor, a Dashboard e o simulador juntos, use `start.py` na raiz do projeto. Para iniciar só o simulador:

```powershell
cd simulador
.\run_mock.ps1
```

Se aparecer "não está assinado digitalmente", desbloqueie os scripts uma vez (eles vêm marcados como baixados da internet):

```powershell
Unblock-File .\run_mock.ps1, .\run_receiver.ps1
```

Outra opção, sem alterar nada, é executar `powershell -ExecutionPolicy Bypass -File .\run_mock.ps1`.

## Usar

| Ação | Como |
|---|---|
| Ligar ou desligar um Andon | Clique no círculo da categoria (Qualidade, Equipamento, Processo, Material) do posto. |
| Mudar Takt ou último ciclo | Edite os campos e clique em **Executar** (publica no OPC UA). |
| Reproduzir uma base | **Importar base** → escolha um arquivo de `bases_exemplo\` (um par de valores por segundo). |
| Restaurar valores padrão | **Limpar base**. |

O rodapé mostra o estado do TCP e a fila ("Pendentes | Confirmados"). O cabeçalho mostra o estado do OPC UA ("ativo e seguro").

## Configuração (`config.toml`)

| Chave | Padrão | Para que serve |
|---|---|---|
| `[tcp] host` / `port` | `127.0.0.1` / `15000` | Endereço do receptor. |
| `[tcp] sync_on_start` | `false` | Pede a hora ao receptor ao iniciar. |
| `[opcua] endpoint` | `opc.tcp://0.0.0.0:4840/mock-linha/` | Servidor OPC UA do simulador. |
| `[application] takt_time_seconds` / `last_cycle_seconds` | `60` / `57.5` | Valores iniciais. |

Se o arquivo não existir, a aplicação usa `config.example.toml`.

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| "Ambiente virtual não encontrado" | Crie o `venv` na raiz do projeto (ver Instalação). |
| Rodapé "Pendentes" crescendo | O receptor não está ativo na porta 15000; inicie o `run_receiver.ps1`. Os eventos ficam guardados e são enviados depois. |
| Dashboard "OPC UA desconectado" | O `[opcua_client] endpoint` do receptor precisa apontar para este computador (`127.0.0.1:4840`) ou para o Gateway. |
| Porta 4840 em uso | Outro servidor OPC UA (por exemplo, um Gateway local) está ativo. Feche-o ou mude a porta. |

## Ver também

- Documentação técnica: `docs/Documentacao_Tecnica/01_Desktop.md`
- Detalhes do protocolo e do OPC UA: `simulador/README.md`
