-- =====================================================================
-- order: AcmeShopping "Order" -> canonical customer_order
--
-- Orders are not merged across sources: each canonical row belongs to
-- exactly one source, identified by (source_system_id, source_order_key).
-- Re-running the model updates the same rows (same order_id) instead
-- of duplicating them.
--
-- Conversions
--   dollars -> cents (INTEGER)
--   OrderStatus  'Pending'->PLACED, 'Shipped'->SHIPPED,
--                'Delivered'->DELIVERED, 'Cancelled'->CANCELLED,
--                'Returned'->RETURNED. An unknown status maps to NULL
--                and fails the NOT NULL constraint, so it is never
--                loaded silently.
--   OrderDate (UTC) -> created_at and placed_at: Acme only records
--                completed checkouts.
--   channel      -> 'WEB' (AcmeShopping is a web store) unless already set.
--   CustomerId   -> canonical customer via source_key_map ('Customer');
--                NULL (guest) until a customer model loads Acme
--                customers.
--
-- Totals are loaded as recorded in Acme, because they are what was
-- charged. If they do not add up, the canonical CHECK on grand_total
-- rejects the load.
--
-- Not loaded here: ShipToPostalCode/ShipToCountry (-> address +
-- order_address) and PromotionId (-> applied_discount).
--
-- Acme has no last-modified column, so every run reprocesses all
-- Acme orders.
-- =====================================================================
{{
  config(
    alias = 'customer_order',
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'order_id',
    full_refresh = false
  )
}}

with acme_system as (

    select source_system_id
    from {{ source('canonical', 'source_system') }}
    where source_system_code = 'ACME'

),

src as (

    select
        cast(o.OrderId as text)                           as source_order_key,
        trim(o.OrderNumber)                               as order_number,
        o.CustomerId                                      as acme_customer_id,
        lower(trim(o.CustomerEmail))                      as customer_email,
        case upper(trim(o.OrderStatus))
            when 'PENDING'   then 'PLACED'
            when 'SHIPPED'   then 'SHIPPED'
            when 'DELIVERED' then 'DELIVERED'
            when 'CANCELLED' then 'CANCELLED'
            when 'RETURNED'  then 'RETURNED'
        end                                               as order_status,
        upper(trim(o.CurrencyCode))                       as currency_code,
        cast(round(o.SubTotal      * 100) as integer)     as subtotal_amount,
        cast(round(o.DiscountTotal * 100) as integer)     as discount_total,
        cast(round(o.TaxTotal      * 100) as integer)     as tax_total,
        cast(round(o.ShippingTotal * 100) as integer)     as shipping_total,
        cast(round(o.GrandTotal    * 100) as integer)     as grand_total,
        strftime('%Y-%m-%dT%H:%M:%fZ', o.OrderDate)       as ordered_at
    from {{ source('acme', 'Order') }} as o

),

matched as (

    select
        s.*,
        a.source_system_id,
        (select t.order_id from {{ this }} as t
          where t.source_system_id = a.source_system_id
            and t.source_order_key = s.source_order_key)               as existing_order_id,
        (select min(m.canonical_id)
           from {{ source('canonical', 'source_key_map') }} as m
          where m.source_system_id   = a.source_system_id
            and m.source_entity_name = 'Customer'
            and m.source_key         = cast(s.acme_customer_id as text)) as customer_id
    from src as s
    cross join acme_system as a

),

keyed as (

    select
        m.*,
        coalesce(
            m.existing_order_id,
            (select coalesce(max(order_id), 0) from {{ this }})
              + row_number() over (partition by m.existing_order_id is null
                                   order by m.source_order_key)
        ) as order_id
    from matched as m

)

select
    k.order_id,
    k.source_system_id,
    k.source_order_key,
    k.order_number,
    k.customer_id,
    k.customer_email,
    k.order_status,
    coalesce(e.channel, 'WEB')                            as channel,
    e.device_type                                         as device_type,
    e.session_token                                       as session_token,
    k.currency_code,
    k.subtotal_amount,
    k.discount_total,
    k.tax_total,
    k.shipping_total,
    k.grand_total,
    coalesce(e.created_at, k.ordered_at)                  as created_at,
    case
        when e.order_id is null                 then k.ordered_at
        when e.order_status <> k.order_status   then strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        else e.updated_at
    end                                                   as updated_at,
    k.ordered_at                                          as placed_at,
    case when k.order_status = 'CANCELLED'
         then coalesce(e.closed_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    end                                                   as closed_at,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')                 as loaded_at
from keyed as k
left join {{ this }} as e
       on e.order_id = k.order_id
