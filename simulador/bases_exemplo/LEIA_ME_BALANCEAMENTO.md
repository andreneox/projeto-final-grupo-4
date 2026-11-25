# Bases de simulação do balanceamento de linha

Preparado em 22/10/2026 para o simulador de 12 postos.

## Arquivos e comparações

| Par | Antes | Depois | O que demonstra |
|---|---|---|---|
| Referência | 21_antes_referencia.xlsx | 22_depois_referencia.xlsx | Tempos fixos para comparar os estados com clareza. Comece por este par. |
| Variação de ritmo | 23_antes_variacao_ritmo.xlsx | 24_depois_variacao_ritmo.xlsx | Pequenas oscilações comuns, de até 0,3 s, mantendo as médias de referência. |
| Variação local | 25_antes_variacao_local.xlsx | 26_depois_variacao_local.xlsx | Oscilações de até 0,3 s nos demais postos, com E07/P07 e P12 fixos no ritmo limitante. |

Cada arquivo tem 12 postos, de P01 a P12, e 12 conjuntos de Takt time/Ciclo.
O simulador percorre os conjuntos e retorna ao primeiro continuamente.
Todos os tempos estão em segundos. Os números 21 a 26 permitem acrescentar
estes arquivos aos 20 exemplos existentes.

## Referência e dados simulados

Fonte: imagem enviada, slide 19, “Balanceamento de Linha — 12 Estações”.
As referências legíveis são: takt de 34,6 s; E07 de 55,1 s antes e 34,0 s depois;
oito postos acima do takt antes e todos abaixo depois; capacidade de cerca de
490 para 794 unidades por turno. No simulador, E07 corresponde a P07.

As barras com os demais tempos não aparecem legíveis na imagem. Por isso, os
valores dos outros postos foram propostos para esta demonstração. São dados
sintéticos, não medições de fábrica nem uma transcrição integral do gráfico.

Nos três pares, a soma dos tempos de trabalho é igual entre antes e depois,
conjunto a conjunto. O exemplo representa redistribuição da carga entre os
mesmos 12 postos. Na referência, essa soma é 399,4 s por unidade em ambos os estados.

## Tempos do par de referência

| Posto | Antes (s) | Depois (s) | Takt (s) |
|---|---:|---:|---:|
| P01 | 16,4 | 32,4 | 34,6 |
| P02 | 35,2 | 33,0 | 34,6 |
| P03 | 18,2 | 32,7 | 34,6 |
| P04 | 36,8 | 33,2 | 34,6 |
| P05 | 19,0 | 33,0 | 34,6 |
| P06 | 38,5 | 33,6 | 34,6 |
| P07 | 55,1 | 34,0 | 34,6 |
| P08 | 35,4 | 33,5 | 34,6 |
| P09 | 18,5 | 32,9 | 34,6 |
| P10 | 36,2 | 33,4 | 34,6 |
| P11 | 35,0 | 33,7 | 34,6 |
| P12 | 55,1 | 34,0 | 34,6 |

Antes, P02, P04, P06, P07, P08, P10, P11 e P12 excedem o takt.
Depois, nenhum posto excede o takt. Isso permanece verdadeiro nos doze conjuntos
inclusive nos dois pares com variações. As planilhas destacam os ciclos acima
do takt em vermelho claro e os demais em verde claro.

## Parâmetros para usar no dashboard

Adote os mesmos parâmetros para comparar todos os arquivos:

- Meta de Produção: **780 peças**.
- Tempo Disponível por turno: **450 minutos**, ou 7 h 30 min.
- Takt importado nas planilhas: **34,6 s**.

O turno de 450 min foi adotado para compatibilizar a capacidade informada no slide:

```text
Tempo disponível = 450 × 60 = 27.000 s
Capacidade teórica antes = 27.000 / 55,1 = 490,0 peças por turno
Capacidade teórica depois = 27.000 / 34,0 = 794,1 peças por turno
Takt pela meta = 27.000 / 780 = 34,615... s, aproximadamente 34,6 s
Redução do ciclo da E07 = (55,1 − 34,0) / 55,1 × 100 = 38,3%
Aumento da capacidade = (794,1 / 490,0 − 1) × 100 = 62,1%
```

A meta e o tempo disponível são preenchidos na tela do simulador. A importação
carrega os tempos de takt e ciclo, mas não altera automaticamente esses dois campos.
Os ganhos são teóricos para esta simulação, sem paradas nem defeitos. Como a
capacidade futura é maior que a meta de 780, o desempenho pode ficar ligeiramente
acima de 100%, conforme a fórmula já usada no programa.

## Como demonstrar

1. Localize as seis planilhas de balanceamento na pasta `bases_exemplo`.
2. Inicie o receptor/dashboard e o simulador. Preencha a meta 780 e o tempo 450 min.
3. Clique em **Limpar base**, aguarde a confirmação e importe `21_antes_referencia.xlsx`.
4. Mantenha os botões de parada desligados. Observe os oito postos com ciclo acima do takt.
   A primeira conclusão do P12 ocorre após aproximadamente 55,1 s, e então o
   dashboard incrementa a produção e calcula o desempenho.
5. Observe por cinco minutos. O valor teórico de produção no P12 nesse intervalo é 5 peças.
6. Clique em **Limpar base** e importe `22_depois_referencia.xlsx`, usando os mesmos parâmetros.
   Todos os ciclos ficam abaixo do takt. A primeira conclusão do P12 ocorre após
   aproximadamente 34,0 s. Em cinco minutos, o valor teórico é 8 peças.
7. Repita com os pares 23/24 e 25/26 para mostrar a comparação com pequenas oscilações.

Compare intervalos iguais. A sequência volta ao primeiro ciclo após o décimo segundo. As bases
contêm somente tempos; não acionam paradas ou defeitos automaticamente. Qualquer
parada manual pausa a linha inteira e muda o resultado observado.

## Como o P12 foi tratado

A versão atual do simulador executa o cronômetro de cada posto de forma independente
e conta a produção somente quando o P12 conclui seu ciclo. Ela não modela a
transferência de peças e estoques intermediários entre as estações.

Para que a saída do P12 represente o ritmo limitante nesta demonstração, seus
tempos foram alinhados aos da E07/P07. Assim, estes exemplos têm P07 e P12 no
mesmo tempo máximo. Isso permite observar no contador a diferença de capacidade
sem atribuir ao programa uma propagação de gargalo que ele ainda não calcula.

## Compatibilidade verificada

Os seis arquivos foram abertos pelo importador atual do projeto. Foram conferidos:
os 12 postos, os 12 conjuntos, o takt de 34,6 s, os oito postos acima antes,
todos abaixo depois e a conservação dos tempos de trabalho.
