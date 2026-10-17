-- =====================================================================
-- orderitem: AcmeShopping "OrderItem" -> canonical order_item
--
-- Each line belongs to exactly one source, identified by
-- (source_system_id, source_line_key = OrderItemId). Re-running the
-- model updates the same rows (same order_item_id).
--
-- Lookups
--   order_id    the canonical order loaded by order.sql for this OrderId
--   product_id  Acme ModelId -> product via source_key_map (written by
--               model.sql's post_hook)
--   seller_id   AcmeShopping is a single first-party seller. pre_hook
--               creates its seller row ('acme-shopping') if missing.
--
-- Conversions
--   UnitPrice / LineDiscount dollars -> cents (INTEGER)
--   line_total  recomputed in cents as quantity * unit_price -
--               discount_amount (the formula Acme documents), so dollar
--               rounding cannot break the canonical CHECK. A dbt test
--               can compare it with round(LineTotal * 100).
--   tax_amount  0: Acme records tax only on the order header.
--   GiftMessage kept only when IsGift is set (canonical CHECK).
--   added_at    the order's OrderDate (Acme has no add-to-cart time).
--
-- Lines whose OrderId has no loaded order are skipped by the join. A
-- line whose model has not been loaded has a NULL product_id and fails
-- the NOT NULL constraint, so it is never loaded silently.
-- =====================================================================
-- depends_on: {{ ref('order') }}
-- depends_on: {{ ref('model') }}
{{
  config(
    alias = 'order_item',
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'order_item_id',
    full_refresh = false,
    pre_hook = "
      insert or ignore into {{ source('canonical', 'seller') }}
          (seller_handle, display_name, is_first_party, country_code, default_currency_code)
      values ('acme-shopping', 'AcmeShopping', 1, 'US', 'USD')
    "
  )
}}

with acme_system as (

    select source_system_id
    from {{ source('canonical', 'source_system') }}
    where source_system_code = 'ACME'

),

src as (

    select
        cast(i.OrderItemId as text)                       as source_line_key,
        cast(i.OrderId as text)                           as source_order_key,
        i.ModelId                                         as acme_model_id,
        i.LineNumber                                      as line_number,
        i.Quantity                                        as quantity,
        cast(round(i.UnitPrice    * 100) as integer)      as unit_price,
        cast(round(i.LineDiscount * 100) as integer)      as discount_amount,
        case when i.IsGift   in (1, '1', 'true', 'TRUE', 't', 'Y') then 1 else 0 end as is_gift,
        case when i.GiftWrap in (1, '1', 'true', 'TRUE', 't', 'Y') then 1 else 0 end as gift_wrap,
        nullif(trim(i.GiftMessage), '')                   as gift_message,
        strftime('%Y-%m-%dT%H:%M:%fZ', o.OrderDate)       as added_at
    from {{ source('acme', 'OrderItem') }} as i
    join {{ source('acme', 'Order') }} as o
      on o.OrderId = i.OrderId

),

matched as (

    select
        s.*,
        a.source_system_id,
        co.order_id,
        (select t.order_item_id from {{ this }} as t
          where t.source_system_id = a.source_system_id
            and t.source_line_key  = s.source_line_key)                as existing_order_item_id,
        (select min(m.canonical_id)
           from {{ source('canonical', 'source_key_map') }} as m
          where m.source_system_id   = a.source_system_id
            and m.source_entity_name = 'Model'
            and m.source_key         = cast(s.acme_model_id as text)
            and m.entity_name        = 'product')                      as product_id,
        (select sl.seller_id from {{ source('canonical', 'seller') }} as sl
          where sl.seller_handle = 'acme-shopping')                    as seller_id
    from src as s
    cross join acme_system as a
    join {{ ref('order') }} as co
      on co.source_system_id = a.source_system_id
     and co.source_order_key = s.source_order_key

),

keyed as (

    select
        m.*,
        coalesce(
            m.existing_order_item_id,
            (select coalesce(max(order_item_id), 0) from {{ this }})
              + row_number() over (partition by m.existing_order_item_id is null
                                   order by m.source_line_key)
        ) as order_item_id
    from matched as m

)

select
    k.order_item_id,
    k.order_id,
    k.source_system_id,
    k.source_line_key,
    k.line_number,
    k.product_id,
    k.seller_id,
    null                                                  as offer_id,
    null                                                  as parent_order_item_id,
    null                                                  as fulfillment_warehouse_id,
    k.quantity,
    k.unit_price,
    null                                                  as original_unit_price,
    null                                                  as original_currency_code,
    null                                                  as fx_rate,
    k.discount_amount,
    0                                                     as tax_amount,
    k.quantity * k.unit_price - k.discount_amount         as line_total,
    0                                                     as is_subscribe_save,
    k.is_gift,
    case when k.is_gift = 1 then k.gift_message end       as gift_message,
    k.gift_wrap,
    k.added_at,
    null                                                  as removed_at,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')                 as loaded_at
from keyed as k
