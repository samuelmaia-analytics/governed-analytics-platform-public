-- Camada publicada para consumo do dashboard executivo.
-- Remove colunas sensíveis (IDs diretos, geolocalização detalhada) e
-- pseudonimiza order_id e customer_unique_id para publicação segura.
-- Equivalente à camada gerada por src/publish_dashboard.py.
with fact as (
    select * from {{ ref('fact_orders_enriched') }}
)

select
    -- Identificadores pseudonimizados (sem exposição de PII direta)
    'order_id_' || left(sha256('order_id:' || order_id), 16) as order_id,
    order_item_id,
    'customer_unique_id_' || left(sha256('customer_unique_id:' || customer_unique_id), 16) as customer_unique_id,

    -- Status e datas de ciclo de vida
    coalesce(order_status, 'unknown') as order_status,
    order_purchase_timestamp,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    order_date,
    order_year,
    order_month,
    purchase_cohort_month,
    cohort_order_month_number,

    -- Cohort e recorrência
    customer_order_sequence,
    is_first_order,

    -- Seller anonimizado (chave substituída, sem ID bruto)
    'seller_id_' || left(sha256('seller_id:' || seller_id), 16) as seller_key,
    coalesce(seller_volume_tier, 'long_tail') as seller_volume_tier,
    seller_order_count,
    seller_avg_delivery_days,
    seller_delay_rate,

    -- Logística
    delivery_time_days,
    seller_dispatch_time_days,
    carrier_delivery_time_days,
    estimated_delay_days,
    is_delayed,

    -- Financeiro
    price,
    freight_value,
    freight_to_price_ratio,
    total_item_value,
    coalesce(payment_type_mode, 'unknown') as payment_type_mode,

    -- Qualidade e avaliação
    review_score_mean,

    -- Produto e categoria (não sensíveis)
    product_category_name,
    product_category_name_english,

    -- Geografia agregada (estado — OK para publicação; cidade e CEP removidos)
    coalesce(customer_state, 'NA') as customer_state,
    coalesce(seller_state, 'NA') as seller_state

from fact
where order_purchase_timestamp is not null
