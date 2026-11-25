# README — IT Digital E07

Instrução de Trabalho Digital do posto E07 (Montagem de Tubulação). A tela troca de passo sozinha, acompanhando o ciclo real do posto 07 no CLP.

## Abrir

Com o receptor em execução (`README_Dashboard.md`), abra no monitor do posto E07:

```
http://<ip-do-computador>:8081/instrucao/e07
```

ou clique em **IT Digital E07** na Dashboard. Use **Tela cheia** no canto superior.

## O que aparece

| Momento | Tela |
|---|---|
| Fora do ciclo | Capa (finalidade, condições de início, referência de ciclo) |
| 0–7 s do ciclo do P07 | Passo 01 – Conferir unidade e kit |
| 7–14 s | Passo 02 – Posicionar no gabarito |
| 14–29 s | Passo 03 – Fixar as conexões |
| 29–36 s | Passo 04 – Inspecionar e registrar |
| Andon em qualquer posto | Capa com "Linha parada – Parada em Pnn · categoria" |
| Andon liberado | "Aguardando próximo ciclo" (recomeça no próximo ciclo) |
| Sem comunicação | "Sem sincronização" |

O rodapé mostra o passo atual e o tempo do ciclo (0 a 36 s).

## Requisitos para sincronizar

- O receptor precisa estar conectado ao Gateway por OPC UA ("OPC UA conectado" na Dashboard).
- O Gateway precisa ler o estado dos postos (`process_status_address = 651` no `config.toml` da Raspberry).
- O ciclo começa quando o P07 **muda** para o estado 2 (`D01657`). Se a tela for aberta com o posto já processando, ela espera o próximo ciclo.

## Personalizar

As imagens dos passos ficam em `simulador/web/static/instructions/e07/slide-01.png` a `slide-05.png`. Os tempos dos passos estão em `simulador/domain/work_instruction.py` (`STEP_ENDS = (7, 14, 29, 36)`). As fotos atuais são ilustrativas e devem ser substituídas pelas fotos aprovadas do posto.

## Ver também

- Documentação técnica: `docs/Documentacao_Tecnica/05_IT_Digital.md`
