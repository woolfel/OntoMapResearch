-- =====================================================================
-- model: AcmeShopping "Model" -> canonical product
--
-- AcmeShopping calls a sellable product a "Model"; the canonical table
-- is product (alias below). Like brand, product is shared master data,
-- so this model MERGES into it:
--   1. Find the canonical product for each Acme model: first through
--      source_key_map, then by sku.
--   2. Reuse that product_id, or assign the next free id.
--   3. Acme values win where Acme has them; columns Acme does not carry
--      (long_name, description, is_adult, ...) keep existing values.
--   4. post_hook records Acme ModelId -> product_id in source_key_map,
--      which orderitem.sql uses to find the product for each line.
--
-- Conversions
--   MSRP dollars          -> msrp_amount in cents
--   WeightLbs             -> weight_grams (the source comment says
--                            "metric", but the column name and values are
--                            pounds)
--   timestamps            -> ISO-8601 UTC
--   BrandId / CategoryId  -> canonical ids via source_key_map. category_id
--                            stays NULL until a category model loads
--                            CatalogCategory.
-- =====================================================================
-- depends_on: {{ ref('brand') }}
{{
  config(
    alias = 'product',
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'product_id',
    full_refresh = false,
    post_hook = "
      insert or ignore into {{ source('canonical', 'source_key_map') }}
          (source_system_id, source_entity_name, source_key, entity_name, canonical_id)
      select ss.source_system_id, 'Model', cast(m.ModelId as text), 'product', t.product_id
      from {{ source('acme', 'Model') }} as m
      join {{ this }} as t
        on t.sku = trim(m.Sku)
      join {{ source('canonical', 'source_system') }} as ss
        on ss.source_system_code = 'ACME'
    "
  )
}}

with acme_system as (

    select source_system_id
    from {{ source('canonical', 'source_system') }}
    where source_system_code = 'ACME'

),

lineage as (

    select source_entity_name, source_key, canonical_id
    from {{ source('canonical', 'source_key_map') }}
    where source_system_id = (select source_system_id from acme_system)

),

src as (

    select
        m.ModelId                                         as acme_model_id,
        m.BrandId                                         as acme_brand_id,
        m.CategoryId                                      as acme_category_id,
        trim(m.Sku)                                       as sku,
        trim(m.ModelNumber)                               as model_number,
        trim(m.ModelName)                                 as model_name,
        cast(strftime('%Y', m.ReleaseDate) as integer)    as model_year,
        date(m.ReleaseDate)                               as release_date,
        cast(round(m.MSRP * 100) as integer)              as msrp_amount,
        upper(trim(m.CurrencyCode))                       as msrp_currency_code,
        cast(round(m.WeightLbs * 453.59237) as integer)   as weight_grams,
        case when m.IsDiscontinued in (1, '1', 'true', 'TRUE', 't', 'Y') then 1 else 0 end
                                                          as is_discontinued,
        strftime('%Y-%m-%dT%H:%M:%fZ', m.EffectiveDate)   as effective_at,
        strftime('%Y-%m-%dT%H:%M:%fZ', m.ExpirationDate)  as expires_at,
        strftime('%Y-%m-%dT%H:%M:%fZ', m.CreatedDate)     as created_at,
        strftime('%Y-%m-%dT%H:%M:%fZ', m.LastUpdate)      as updated_at
    from {{ source('acme', 'Model') }} as m

),

matched as (

    select
        s.*,
        coalesce(
            (select min(l.canonical_id) from lineage as l
              where l.source_entity_name = 'Model'
                and l.source_key = cast(s.acme_model_id as text)),
            (select min(t.product_id) from {{ this }} as t
              where t.sku = s.sku)
        ) as existing_product_id,
        (select min(l.canonical_id) from lineage as l
          where l.source_entity_name = 'Brand'
            and l.source_key = cast(s.acme_brand_id as text))     as brand_id,
        (select min(l.canonical_id) from lineage as l
          where l.source_entity_name = 'CatalogCategory'
            and l.source_key = cast(s.acme_category_id as text))  as category_id
    from src as s

),

keyed as (

    select
        m.*,
        coalesce(
            m.existing_product_id,
            (select coalesce(max(product_id), 0) from {{ this }})
              + row_number() over (partition by m.existing_product_id is null
                                   order by m.sku)
        ) as product_id
    from matched as m

)

select
    k.product_id,
    coalesce(e.sku, k.sku)                                as sku,
    k.brand_id                                            as brand_id,
    coalesce(k.category_id, e.category_id)                as category_id,
    k.model_number                                        as model_number,
    k.model_name                                          as model_name,
    k.model_year                                          as model_year,
    k.model_name                                          as product_name,
    e.long_name                                           as long_name,
    e.description                                         as description,
    e.country_of_origin                                   as country_of_origin,
    coalesce(k.weight_grams, e.weight_grams)              as weight_grams,
    k.msrp_amount                                         as msrp_amount,
    k.msrp_currency_code                                  as msrp_currency_code,
    coalesce(e.is_taxable, 1)                             as is_taxable,
    coalesce(e.is_adult, 0)                               as is_adult,
    case when k.is_discontinued = 1 then 0 else 1 end     as is_active,
    k.release_date                                        as release_date,
    case when k.is_discontinued = 1
         then coalesce(e.discontinued_date,
                       date(coalesce(k.expires_at, k.updated_at)))
    end                                                   as discontinued_date,
    coalesce(k.effective_at, e.effective_at,
             strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))       as effective_at,
    k.expires_at                                          as expires_at,
    coalesce(e.created_at, k.created_at,
             strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))       as created_at,
    coalesce(k.updated_at,
             strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))       as updated_at
from keyed as k
left join {{ this }} as e
       on e.product_id = k.product_id
