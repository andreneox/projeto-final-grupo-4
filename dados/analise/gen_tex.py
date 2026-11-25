import json
from pathlib import Path
D = Path(r"C:\Users\johng\AppData\Local\Temp\claude\5d4b98baeb9c066d\2cfb3df3-19ce-4d01-a786-e84e1fafb8c3\scratchpad")
R = Path(r"C:\Users\johng\OneDrive\Documentos\Mestrado\Lean\LeanManufacturing\Docs\Relatorio_Final")
T = json.load(open(D / "tests_summary.json", encoding="utf-8"))
esc = lambda s: s.replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("%", "\\%").replace("&", "\\&").replace("#", "\\#")

DESC = {
 "mock": {
  "test_analytics": "Contador absoluto do CLP, união de paradas sobrepostas, ocorrência aberta e estabilidade por categoria.",
  "test_base_import": "Planilha em pares de linhas e de colunas, primeira aba do .xlsx e par incompleto.",
  "test_bcd": "Ida e volta BCD de 0 a 99 e rejeição de valores e nibbles inválidos.",
  "test_certificates": "Certificado de cliente vencido é recusado.",
  "test_database": "Clique atômico com fila, reinício com fila pendente, rollback e categorias simultâneas.",
  "test_example_bases": "Geração e importação das planilhas de exemplo.",
  "test_opcua_controls": "Métodos de motor e parada com tipos explícitos e validação.",
  "test_opcua_integration": "72 nós somente leitura, certificado de servidor errado, cliente desconhecido e assinatura pela Dashboard.",
  "test_process_configuration": "Importação e Start pelo Gateway, persistência, plano do turno, reset e 30 casos de valores inválidos.",
  "test_reference_receiver": "Política de exceções, COMMIT antes do ACK, reenvio idêntico e formatos 00 01/00 02.",
  "test_tcp_codec": "Exemplos ON/OFF documentados, posto 12 como 00 0C, dia da semana e pedido de hora.",
  "test_tcp_sender": "Reenvio do primeiro evento preservando a ordem FIFO.",
  "test_telemetry": "Telemetria alterada somente pelo OPC UA e ordem dos 12 estados.",
  "test_ui": "Janela com 12 postos, edição de métricas, importação com intervalo de 1 s.",
  "test_web_dashboard": "Página, API e WebSocket; página de gráficos e arquivos da E07.",
  "test_work_instruction": "Sequência de 36 s, interrupção por Andon, estado inválido e reconexão.",
 },
 "gateway": {
  "test_application": "Partida e parada do serviço sem hardware.",
  "test_config": "Configuração de exemplo segura (Modbus desabilitado) e portável.",
  "test_modbus_transport": "Endereços, FC03/04/05/06/16, base de ciclos, relógio, ACK, D1200 e bit 0 de D1201.",
  "test_motor_output": "Rampas, interrupção por novo comando ou falha, desligamento e validação de velocidade.",
  "test_ntp_client": "Decodificação SNTP, rejeição de resposta não sincronizada, nova tentativa e hora do sistema uma única vez.",
  "test_opcua_integration": "Servidor seguro com os mesmos 72 nós atualizados.",
  "test_persistence": "Captura durável, deduplicação do pacote, colisão de CRC32 e evento pendente após reinício.",
  "test_plc_clock": "Palavras BCD de DATEWR e segunda-feira = 1.",
  "test_plc_poller": "COMMIT antes de P10000, ACK repetido sem perda, Start, reset e serialização de comandos.",
  "test_protocol": "Pacote de 16 bytes e identificador com CRC32.",
  "test_register_map": "Nibbles de Andon, UInt32 até o P12, ordem de palavras e D112.",
  "test_tcp_sender": "Pacote exato com ACK fragmentado, ACK inválido e FIFO persistente.",
 }}
rows = []
for proj, label in [("mock", "Simulador"), ("gateway", "Gateway")]:
    for f, d in T[proj]["files"].items():
        ok, sk = d["passed"], d["skipped"]
        res = f"{ok}" + (f" (+{sk} pulados)" if sk else "")
        rows.append(f"{label} & \\cod{{{esc(f)}.py}} & {res} & {DESC[proj][f]} \\\\ \\hline")
sm, sg = T["mock"]["suite"], T["gateway"]["suite"]

tex = r"""\section{Verificação e testes automatizados}

Os testes foram executados em 21/11/2026 com \cod{pytest 8.3.5} no ambiente descrito na seção 1.1, a partir das pastas \cod{simulador/} e \cod{hardware/} (\cod{..\textbackslash venv\textbackslash Scripts\textbackslash python.exe -m pytest -v}). Nenhum teste exige hardware: o Modbus, o TCP, o SNTP e o OPC UA são exercitados com simuladores locais e servidores reais em portas efêmeras.

\begin{itemize}
    \item \textbf{Simulador:} """ + sm["tests"] + r""" testes, """ + sm["tests"] + r""" aprovados, 0 falhas, em """ + f"{float(sm['time']):.1f}".replace(".", ",") + r""" s.
    \item \textbf{Gateway:} """ + sg["tests"] + r""" testes, """ + str(int(sg["tests"]) - int(sg["skipped"])) + r""" aprovados, 0 falhas e """ + sg["skipped"] + r""" pulados, em """ + f"{float(sg['time']):.1f}".replace(".", ",") + r""" s. Os dois testes pulados (\cod{test\_gpio\_driver\_starts\_disabled\_and\_releases\_pins} e \cod{test\_gpio\_cleanup\_continues\_after\_one\_device\_close\_fails}) dependem da biblioteca \cod{gpiozero}, instalada somente na Raspberry Pi (\cod{sys\_platform == 'linux'}).
\end{itemize}

{\footnotesize
\begin{longtable}{|>{\raggedright\arraybackslash}p{2.0cm}|>{\raggedright\arraybackslash}p{4.2cm}|>{\centering\arraybackslash}p{1.6cm}|>{\raggedright\arraybackslash}p{6.8cm}|}
\caption{Testes automatizados por arquivo (resultado de \cod{--junitxml}).}\label{tab:testes}\\
\hline
\textbf{Projeto} & \textbf{Arquivo} & \textbf{Aprovados} & \textbf{O que verifica} \\ \hline
\endfirsthead
\hline
\textbf{Projeto} & \textbf{Arquivo} & \textbf{Aprovados} & \textbf{O que verifica} \\ \hline
\endhead
""" + "\n".join(rows) + r"""
\end{longtable}
}

Os testes complementam as execuções descritas nas seções anteriores: os comportamentos que dependem de falhas difíceis de provocar no hardware - colisão de CRC32, queda da conexão entre o COMMIT e o ACK, certificado vencido, ACK TCP fragmentado, falha do banco no meio de um clique - são verificados aqui de forma determinística.

\newpage
"""
(R / "secao8_testes.tex").write_text(tex, encoding="utf-8")

# ---------------- anexo -----------------
ev = json.load(open(D / "gateway_events.json"))
ev_rows = []
for e in ev:
    hx = " ".join(e["hex"][i:i + 2] for i in range(0, 32, 2))
    ev_rows.append(f"{e['id']} & {e['occurred'].replace('T', ' ')} & P{e['station']:02d} & {e['button']} & {e['status']} & \\cod{{{hx}}} & {e['cap_to_plcack_ms']:.1f} & {e['cap_to_tcpconf_ms']:.1f} \\\\ \\hline".replace(".", ",", 0))
clp = [("04_buttons_inicializacao", "BUTTONS: inicialização de \\cod{D01501} em 100 e bordas de descida que selecionam os estados 1 a 12."),
       ("05_buttons_borda_subida", "BUTTONS: bordas de subida levam \\cod{D01501} de 1-12 para 13-24."),
       ("06_buttons_borda_descida", "BUTTONS: bordas de descida seguintes levam \\cod{D01501} de 13-24 para 25-36."),
       ("07_buttons_retorno", "BUTTONS: nos estados 25-36, a subida da entrada devolve \\cod{D01501} a 100."),
       ("08_buttons_marcas", "BUTTONS: conversão dos estados em marcas; \\cod{M00020} ativa em 1, 13 ou 25."),
       ("03_versao_xg5000", "Janela \\textit{About XG5000}: versão 4.74."),
       ("11_andon_relogio_amarelo", "ANDON: aplicação do relógio (\\cod{P10001} e \\cod{DATEWRP D01000}) e rede do Andon amarelo."),
       ("12_andon_verde_vermelho", "ANDON: redes dos Andons verde e vermelho."),
       ("14_inicializacao_start_reset", "Redes de reset (\\cod{P10003}) e Start (\\cod{P10002} $\\rightarrow$ \\cod{M00101})."),
       ("16_posto_02", "Posto 02: \\cod{D01652}, \\cod{T0002} e incremento de \\cod{D16042}."),
       ("18_posto_08_auto_1", "Posto 08 (Auto 1): entrada por \\cod{P0000D} e término pela borda de \\cod{P0000C}."),
       ("19_posto_09_auto_2", "Posto 09 (Auto 2): estado em \\cod{D01659}; tempo de \\cod{T0009} copiado para \\cod{D00147}."),
       ("20_posto_10_auto_3", "Posto 10 (Auto 3): registro em \\cod{D00151}, incremento de \\cod{D16050} e sinal ao P11 por \\cod{M0011B}.")]
figs = "\n".join(r"""\begin{figure}[H]
    \centering
    \includegraphics[width=0.72\textwidth]{Imagens/clp_""" + n + r""".png}
    \caption{""" + c + r""" (arquivo: Imagens/clp\_""" + n.replace("_", "\\_") + r""".png)}
\end{figure}
""" for n, c in clp)
anexo = r"""\section*{Anexo - Tabelas e figuras complementares}
\addcontentsline{toc}{section}{Anexo - Tabelas e figuras complementares}
\setcounter{table}{0}\renewcommand{\thetable}{A\arabic{table}}
\setcounter{figure}{0}\renewcommand{\thefigure}{A\arabic{figure}}

{\footnotesize
\begin{longtable}{|>{\centering\arraybackslash}p{0.5cm}|>{\centering\arraybackslash}p{2.2cm}|>{\centering\arraybackslash}p{0.8cm}|>{\raggedright\arraybackslash}p{1.8cm}|>{\centering\arraybackslash}p{0.8cm}|>{\raggedright\arraybackslash}p{4.6cm}|>{\centering\arraybackslash}p{1.3cm}|>{\centering\arraybackslash}p{1.3cm}|}
\caption{Os 18 eventos de Andon capturados no CLP real pelo Gateway \cod{LINHA\_A} (\cod{Gateway/data/gateway.db}, 27/09/2026). ``ACK CLP'' e ``ACK TCP'': milissegundos desde a gravação no SQLite.}\\
\hline
\textbf{Id} & \textbf{Ocorrência (CLP)} & \textbf{Posto} & \textbf{Botão} & \textbf{Estado} & \textbf{Pacote (hex)} & \textbf{ACK CLP} & \textbf{ACK TCP} \\ \hline
\endfirsthead
\hline
\textbf{Id} & \textbf{Ocorrência (CLP)} & \textbf{Posto} & \textbf{Botão} & \textbf{Estado} & \textbf{Pacote (hex)} & \textbf{ACK CLP} & \textbf{ACK TCP} \\ \hline
\endhead
""" + "\n".join(r.replace(".", ",") if False else r for r in ev_rows) + r"""
\end{longtable}
}

\noindent As figuras a seguir completam as capturas do projeto \cod{LAB\_NEW\_UPDATED} no XG5000 apresentadas na seção 3.

""" + figs
# decimal comma in latency columns
import re
anexo = re.sub(r"& (\d+)\.(\d) & (\d+)\.(\d) \\\\", r"& \1,\2 & \3,\4 \\\\", anexo)
(R / "anexo.tex").write_text(anexo, encoding="utf-8")
print("ok", len(rows), len(ev_rows))
