# Camada Semântica

Este documento define a camada semântica usada para consumo executivo.
O objetivo é reduzir ambiguidades de KPI entre pipeline, app e exportações.

## Objetivo

- padronizar definições de métricas;
- explicitar fórmulas e granularidade;
- alinhar fonte de dados por métrica;
- manter linguagem única para analytics e negócio.

## Escopo

Esta camada serve ao consumo publicado.
Ela não substitui a camada analítica interna detalhada.

## Fronteira de dados

- camada interna: `data/curated/analytics/`
- camada publicada: `data/published/dashboard/`
- recortes semânticos: `data/published/semantic/`

## Métricas principais

| metric_name | business_definition | formula | grain | source_layer | business_owner | notes |
| --- | --- | --- | --- | --- | --- | --- |
| Total Orders | Total de pedidos únicos no período analisado | `COUNT(DISTINCT order_id)` | período, estado, categoria, seller | `published/dashboard` | Analytics | `order_id` é pseudonimizado na camada publicada |
| GMV | Valor total dos itens e do frete no período | `SUM(total_item_value)` | período, estado, categoria, seller | `published/dashboard` | Business + Analytics | não representa margem líquida |
| Average Ticket | Receita média por pedido | `SUM(total_item_value) / COUNT(DISTINCT order_id)` | período, estado, categoria, seller | `published/dashboard` | Analytics | sensível a outliers |
| Valor médio por item | Média do valor total das linhas de item | `AVG(total_item_value)` | grão do recorte | recortes de seller, coorte, categoria e estado | Analytics | `avg_ticket` nesses recortes representa média por item |
| Desvio do prazo de entrega | Diferença entre entrega efetiva e estimada | `estimated_delay_days` | item | `published/dashboard` | Operations + Analytics | positivo após o prazo, negativo antes do prazo |
| Taxa de atraso | Proporção de itens atrasados | média de `is_delayed` | grão do recorte | recortes semânticos | Operations + Analytics | exige ambas as datas e entrega posterior à estimada |
| Data Quality Score | Indicador agregado de qualidade da execução | agregação dos checks por severidade | execução do pipeline | `curated/quality` e saídas publicadas | Data Governance | interpretar junto com tabela detalhada |
| Privacy Risk Score | Score explicável de risco de privacidade | composição ponderada de sinais LGPD e exposição | execução do pipeline | `src/lgpd_classifier.py`, `src/risk_scoring.py` | Data Governance | níveis: `low`, `medium`, `high` |
| Publication Readiness | Estado de prontidão para publicação | regra derivada de qualidade + risco + controles | execução do pipeline | `published/dashboard` e artefatos de governança | Data Governance + Analytics | estados: `Approved`, `Needs Review`, `Blocked` |

## Convenções de consumo

- sempre informar janela temporal aplicada;
- evitar comparação direta de métricas com grãos diferentes;
- manter mesma definição em app, relatório e exportação;
- exibir contexto do filtro no valor apresentado.

## Riscos de ambiguidade

### GMV

Neste dashboard, o valor bruto soma o preço e o frete dos itens.
Não deve ser comunicado como lucro.

### Average Ticket

O dashboard divide o valor total pelo número de pedidos distintos.
Os recortes com `avg_ticket` usam a média por linha de item.

### Delivery Delay

No Python, o desvio é a diferença entre a entrega efetiva e a estimada em segundos, dividida por 86.400. No dbt, DuckDB usa `datediff('day', data_estimada, data_efetiva)`, que conta limites de dias. O recorte logístico agrega `delivery_time_days`, a duração desde a compra, uma métrica distinta.

### Publication Readiness

É status operacional de governança.
Não é KPI de performance comercial.

## Uso executivo

A camada semântica facilita leitura executiva ao:

- centralizar definições de KPI;
- manter rastreabilidade mínima para auditoria;
- reduzir divergência entre narrativas de diferentes áreas.

## Limitações

- projeto orientado a portfólio com dados públicos/sintéticos;
- fórmulas podem exigir ajuste para regras financeiras reais;
- a camada publicada prioriza decisão executiva, não exploração analítica profunda.
