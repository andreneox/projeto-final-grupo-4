# Mock da Linha

Aplicativo desktop em Python/PyQt6 que simula os 12 postos da linha e envia cada
transição pelo protocolo TCP industrial. O mock também publica telemetria em um
servidor OPC UA seguro. O receptor persiste os eventos, assina as tags OPC UA e
serve uma dashboard web em tempo real.

## Execução

Requisitos: Windows e Python 3.11. Os lançadores procuram primeiro
`simulador/venv` e depois o `venv` existente na pasta pai.

```powershell
Copy-Item config.example.toml config.toml
..\venv\Scripts\python.exe -m pip install -r requirements.txt
```

O arquivo `config.toml` é local e não deve ser versionado. Sem ele, a aplicação
usa diretamente `config.example.toml`. O banco SQLite é criado em `data/` na
primeira execução.

Inicie o receptor TCP, cliente OPC UA e dashboard web:

```powershell
.\run_receiver.ps1
```

Em outro terminal, inicie o mock:

```powershell
.\run_mock.ps1
```

A dashboard fica disponível no endereço definido em `[dashboard]` (nesta
instalação, `http://127.0.0.1:8081`). Os processos podem ser iniciados em qualquer
ordem; o cliente OPC UA reconecta automaticamente.

## Comportamento

- Os postos visuais `01` a `12` são transmitidos como inteiros de 1 a 12.
- Cada posto possui Qualidade, Equipamento, Processo e Material independentes.
- Um clique captura uma única data/hora lógica, alterna apenas o botão escolhido e,
  na mesma transação SQLite, grava o estado e o pacote imutável de 16 bytes.
- A interface só muda depois do `COMMIT`. Se o banco falhar, o estado visual não
  muda e uma mensagem de erro é apresentada.
- A fila é global e estritamente FIFO pelo ID autoincremental. Somente um evento
  fica em voo; o próximo aguarda o ACK válido do anterior.
- Falhas usam esperas de 1, 2, 5, 10 e 30 segundos, permanecendo em 30 segundos.
  Reiniciar o programa recupera os estados e retoma o primeiro evento pendente.
- Takt time e último ciclo começam com os valores da configuração, podem ser
  editados por posto e são publicados nas tags OPC UA pelo botão `Executar`.
- A sincronização de relógio é uma operação separada da fila. `sync_on_start=true`
  executa uma tentativa na inicialização; falhas não bloqueiam eventos.

## Protocolo TCP

Todos os inteiros de 16 bits usam big-endian. Um evento possui exatamente 16 bytes:

| Bytes | Campo |
|---|---|
| 0-1 | Tipo `00 01` (evento de Andon) |
| 2-3 | Posto, de 1 a 12 |
| 4-11 | Mês, ano final, hora, dia, segundo, minuto, ano inicial e dia da semana em BCD |
| 12-13 | Botão: Qualidade 1, Equipamento 2, Processo 3, Material 4 |
| 14-15 | Estado: ON 1, OFF 2 |

O dia da semana segue domingo 0 a sábado 6. O ACK válido contém exatamente 22
bytes ASCII: vinte caracteres `0` seguidos de `15`, sem quebra de linha.

A solicitação de hora é `00 01` seguida de 14 bytes zero. A resposta contém 8
bytes BCD no mesmo layout temporal. O relógio lógico usa `time.monotonic()` após
a sincronização e nunca altera o relógio do Windows nem eventos já enfileirados.

## OPC UA seguro

### Tempos manuais e importação

Ao alterar manualmente qualquer campo de Takt time ou Último ciclo, o botão
`Executar` é habilitado. Ele publica os 24 valores no OPC UA e volta a ficar
desabilitado. `Limpar base` interrompe uma importação em andamento, restaura os
valores padrão de `config.toml` e os publica no OPC UA.

`Importar base` aceita `.xlsx`, `.xlsm` e `.csv`. O formato recomendado usa a
coluna A para os postos e pares de colunas para cada conjunto de valores:

| A | B | C | D | E |
|---|---|---|---|---|
| Posto | Takt 1 | Último ciclo 1 | Takt 2 | Último ciclo 2 |
| P01 | 60 | 57,5 | 61 | 58 |
| P02 | 60 | 57,5 | 61 | 58 |
| ... | ... | ... | ... | ... |
| P12 | 60 | 57,5 | 61 | 58 |

O par B/C é publicado junto para todos os postos; um segundo depois é publicado
o par D/E, e assim sucessivamente. Também é aceita a orientação transposta: uma
linha de cabeçalho `P01` a `P12`, seguida por pares de linhas Takt/Último ciclo.
Durante a reprodução, os campos e o botão `Executar` ficam bloqueados. Ao final,
os campos permanecem com o último conjunto e podem ser editados novamente.

As 26 planilhas de demonstração ficam em `bases_exemplo/`. Cada arquivo contém
12 postos, com 12 pares de takt e tempo de ciclo por posto. O guia de
balanceamento na mesma pasta descreve os exemplos 21 a 26.

Endpoint padrão: `opc.tcp://0.0.0.0:4840/mock-linha/`.

O servidor OPC UA pertence ao processo `run_mock.ps1`. O processo
`run_receiver.ps1` atua como cliente OPC UA seguro e assina as 72 variáveis para
alimentar a dashboard. Eventos recebidos pelo socket são gravados no SQLite e
nunca alteram tags OPC UA. Se o OPC UA falhar, o receptor TCP, a persistência e a
dashboard continuam ativos; os indicadores em tempo real aparecem desconectados.

O servidor anuncia exclusivamente `Basic256Sha256` com `SignAndEncrypt`. Não há
endpoint `None`, modo somente assinado ou fallback inseguro. A identidade anônima
é aceita somente dentro desse canal, depois da validação do certificado de
aplicação do cliente. O servidor verifica confiança explícita, validade,
`ExtendedKeyUsage=clientAuth` e correspondência do `ApplicationUri`.

Gere credenciais de desenvolvimento explicitamente:

```powershell
..\venv\Scripts\python.exe -m tools.generate_dev_certificates `
  --kind server --name "Mock Linha" `
  --application-uri "urn:mock-linha:servidor" `
  --output-dir certificates

..\venv\Scripts\python.exe -m tools.generate_dev_certificates `
  --kind client --name "Dashboard Web" `
  --application-uri "urn:freeopcua:client" `
  --output-dir certificates\client

New-Item -ItemType Directory -Force certificates\trusted\clients
Copy-Item certificates\client\client_cert.der certificates\trusted\clients\
```

O cliente integrado usa o URI `urn:freeopcua:client`, confia explicitamente em
`certificates/server_cert.der` e usa o certificado e a chave em
`certificates/client`. Para acesso por outro endereço, gere o certificado do
servidor com `--dns-name` ou `--ip-address` adicionais. As chaves privadas nunca
devem ser trocadas nem versionadas. Em produção, substitua os certificados
autoassinados pelos da infraestrutura responsável.

O cliente integrado do receptor é configurado na seção `[opcua_client]`. Seu
`application_uri`, certificado e chave devem corresponder, e o certificado deve
estar na pasta `trusted_clients_dir` do servidor.

O cliente tambem oferece `set_motor_speed(0..100)` e
`set_line_stopped(bool)`. Essas funcoes chamam os metodos OPC UA
`Linha/DefinirVelocidadeMotor` e `Linha/DefinirParada` expostos pelo Gateway.

### Tabela de NodeIds

Namespace URI: `urn:mock-linha:telemetria:v1`. Todos os identificadores são
NodeIds string e as 72 variáveis são somente leitura para clientes.

| Posto | Qualidade | Equipamento | Processo | Material | Takt | Último ciclo |
|---|---|---|---|---|---|---|
| P01 | `P01/Andon/Qualidade` | `P01/Andon/Equipamento` | `P01/Andon/Processo` | `P01/Andon/Material` | `P01/TaktTime` | `P01/UltimoCiclo` |
| P02 | `P02/Andon/Qualidade` | `P02/Andon/Equipamento` | `P02/Andon/Processo` | `P02/Andon/Material` | `P02/TaktTime` | `P02/UltimoCiclo` |
| P03 | `P03/Andon/Qualidade` | `P03/Andon/Equipamento` | `P03/Andon/Processo` | `P03/Andon/Material` | `P03/TaktTime` | `P03/UltimoCiclo` |
| P04 | `P04/Andon/Qualidade` | `P04/Andon/Equipamento` | `P04/Andon/Processo` | `P04/Andon/Material` | `P04/TaktTime` | `P04/UltimoCiclo` |
| P05 | `P05/Andon/Qualidade` | `P05/Andon/Equipamento` | `P05/Andon/Processo` | `P05/Andon/Material` | `P05/TaktTime` | `P05/UltimoCiclo` |
| P06 | `P06/Andon/Qualidade` | `P06/Andon/Equipamento` | `P06/Andon/Processo` | `P06/Andon/Material` | `P06/TaktTime` | `P06/UltimoCiclo` |
| P07 | `P07/Andon/Qualidade` | `P07/Andon/Equipamento` | `P07/Andon/Processo` | `P07/Andon/Material` | `P07/TaktTime` | `P07/UltimoCiclo` |
| P08 | `P08/Andon/Qualidade` | `P08/Andon/Equipamento` | `P08/Andon/Processo` | `P08/Andon/Material` | `P08/TaktTime` | `P08/UltimoCiclo` |
| P09 | `P09/Andon/Qualidade` | `P09/Andon/Equipamento` | `P09/Andon/Processo` | `P09/Andon/Material` | `P09/TaktTime` | `P09/UltimoCiclo` |
| P10 | `P10/Andon/Qualidade` | `P10/Andon/Equipamento` | `P10/Andon/Processo` | `P10/Andon/Material` | `P10/TaktTime` | `P10/UltimoCiclo` |
| P11 | `P11/Andon/Qualidade` | `P11/Andon/Equipamento` | `P11/Andon/Processo` | `P11/Andon/Material` | `P11/TaktTime` | `P11/UltimoCiclo` |
| P12 | `P12/Andon/Qualidade` | `P12/Andon/Equipamento` | `P12/Andon/Processo` | `P12/Andon/Material` | `P12/TaktTime` | `P12/UltimoCiclo` |

## Receptor de referência

O receptor aceita uma conexão por requisição, lê os 16 bytes completos e só envia
ACK de Andon depois do `COMMIT`. Cada recepção e cada ocorrência são auditadas no
banco próprio. O terminal imprime uma linha por evento com posto, botão, estado,
resultado persistido e confirmação do ACK. A política adotada para os casos
excepcionais é:

| Situação | Resultado persistido |
|---|---|
| ON com ocorrência já aberta | `ON_REPETIDO` |
| OFF sem ocorrência aberta | `OFF_SEM_ABERTURA` |
| Evento anterior à referência da chave | `ATRASADO` |

A regra de atraso é aplicada primeiro. A referência `(posto, botão)` avança em todo
evento não atrasado. Todos esses resultados recebem ACK após persistência. Formato
inválido, cadastro desconhecido ou falha de banco fecham a conexão sem ACK.
O tempo total parado usa a união dos intervalos sobrepostos. O receptor aceita
Andon TCP nos formatos 00 01 e 00 02.

## Dashboard web

O painel usa a interface e os cálculos da versão do Desktop. Ele inclui gráficos
por posto, plano do turno e a instrução E07. O botão Start usa a URL em
`[desktop_api].start_url`, quando configurada.

Com o cliente OPC UA ativo e `[desktop_api].start_url` vazio, **Importar base**
envia os 12 tempos de ciclo de cada posto ao Gateway. Use uma planilha com
12 sequências de tempos para os postos P01 a P12. A dashboard habilita **Start**
após a conferência dos 288 registradores, com todos os postos no estado 0 e os
Andons livres. O Start envia o pulso em `P10002` e só abre a sessão de medição
quando o Gateway informa a confirmação do Ladder.
Depois de uma importação confirmada, a seção **Postos da linha** mostra o nome
do arquivo e usa o primeiro Takt da planilha para cada posto.

Em **Editar plano do turno**, informe a meta em peças e o tempo disponível em
minutos. A dashboard usa os valores salvos para recalcular a estimativa e o
desempenho no período em curso.

**Limpar base** pulsa `P10003` por dois segundos, inclusive durante o processamento. Depois
de o Gateway conferir o reset, o receptor limpa os registros de produção,
defeitos e paradas do dia. Um novo Start confirmado inicia a próxima medição.

Andons TCP continuam chegando pelo receptor na porta definida em `[receiver]`.
Em instalações TCP, os indicadores de parada usam o turno configurado.
Quando o Gateway publica `Linha/TotalProduzido`, a **Produção atual** usa o valor
do contador `D16052` do CLP. A contagem acompanha os incrementos e as zeragens
do Ladder. No simulador Desktop, os ciclos do P12 chegam pelo endpoint
`POST /api/runtime/events` junto com planos e sessões de medição.
O Gateway publica os estados de `D1651–D1662` em `Linha/StatusProcesso`. Em cada
coluna, 0 e 1 deixam o fundo amarelo, 2 faz o verde piscar e 3 mantém o verde
constante. Um Andon ativo deixa a coluna do posto vermelha.

Na **IT Digital E07**, o receptor acompanha o estado do P07 em `D1657`.
A entrada no estado 2 inicia os quatro passos, com trocas aos 7, 14 e 29 s.
A instrução volta à capa quando o P07 conclui ou quando a sequência chega a 36 s.
Um Andon interrompe a instrução até o próximo início de ciclo. Se o receptor
se conectar com o P07 já processando, a tela aguarda o próximo ciclo observado.
O painel publica a API `/api/snapshot` e atualiza pelo WebSocket `/ws`.

## Limite de duplicidade

O protocolo atual não possui ID de evento. Se o receptor confirmar e a conexão cair
antes de o mock receber o ACK, o mesmo pacote será reenviado. Dois eventos legítimos
também podem produzir bytes idênticos no mesmo segundo; por isso, deduplicar apenas
pelos 16 bytes perderia dados. Esta versão garante fila durável e entrega com nova
tentativa, mas não promete processamento exatamente uma vez. Para essa garantia, o
protocolo precisa ser revisado com um identificador antes da homologação.

## Organização e testes

`domain/` e `protocol/` contêm regras puras; `persistence/` mantém o SQLite do mock
em uma thread proprietária; `communications/` abriga TCP, servidor OPC UA do mock
e cliente OPC UA do receptor; `services/` contém telemetria e cálculos; `ui/` contém
os widgets desktop; `web/` contém a dashboard; `tools/` contém certificados e o
receptor TCP/web.

```powershell
..\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
..\venv\Scripts\python.exe -m pytest -q
```

Os testes cobrem os exemplos binários ON/OFF, posto 12 como `00 0C`, BCD e dia da
semana, rollback local, reinício, coexistência de categorias, FIFO/reenvio, ACK
fragmentado, política do receptor, cálculos diários, API/WebSocket e integração OPC
UA segura com 72 tags, assinatura do cliente web, escrita remota negada, certificado
desconhecido e certificado de servidor incorreto.
