select order_id, customer_unique_id, seller_key
from {{ ref('fact_orders_dashboard') }}
where not regexp_full_match(order_id, 'order_id_[0-9a-f]{16}')
   or not regexp_full_match(customer_unique_id, 'customer_unique_id_[0-9a-f]{16}')
   or not regexp_full_match(seller_key, 'seller_id_[0-9a-f]{16}')
