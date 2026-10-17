-- =====================================================================
-- brand: AcmeShopping "Brand" -> canonical brand
--
-- brand is master data shared by every source (Sony from AcmeShopping,
-- BigRiver and BobsUncle is one row), so this model MERGES into it:
--   1. Find the canonical brand for each Acme brand: first through the
--      lineage map (source_key_map), then by case-insensitive name.
--   2. Reuse that brand_id, or assign the next free id for new brands.
--   3. Acme values win where Acme has them; columns Acme does not carry
--      (brand_code, support contacts, ...) keep what other sources loaded.
--   4. post_hook records Acme BrandId -> brand_id in source_key_map.
--
-- Loaded with delete+insert on brand_id into the existing canonical
-- table; full_refresh is disabled so dbt never drops it and its
-- constraints.
-- =====================================================================
{{
  config(
    materialized = 'incremental',
    incremental_strategy = 'delete+insert',
    unique_key = 'brand_id',
    full_refresh = false,
    post_hook = "
      insert or ignore into {{ source('canonical', 'source_key_map') }}
          (source_system_id, source_entity_name, source_key, entity_name, canonical_id)
      select ss.source_system_id, 'Brand', cast(b.BrandId as text), 'brand', t.brand_id
      from {{ source('acme', 'Brand') }} as b
      join {{ this }} as t
        on lower(t.brand_name) = lower(trim(b.BrandName))
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

src as (

    select
        b.BrandId                                         as acme_brand_id,
        trim(b.BrandName)                                 as brand_name,
        nullif(trim(b.ManufacturerName), '')              as manufacturer_name,
        upper(trim(b.CountryOfOrigin))                    as country_code,
        nullif(trim(b.WebsiteUrl), '')                    as website_url,
        case when b.IsActive in (1, '1', 'true', 'TRUE', 't', 'Y') then 1 else 0 end
                                                          as is_active,
        strftime('%Y-%m-%dT%H:%M:%fZ', b.CreatedDate)     as created_at,
        strftime('%Y-%m-%dT%H:%M:%fZ', b.LastUpdate)      as updated_at
    from {{ source('acme', 'Brand') }} as b

),

matched as (

    select
        s.*,
        coalesce(
            (select min(m.canonical_id)
               from {{ source('canonical', 'source_key_map') }} as m
              where m.source_system_id   = (select source_system_id from acme_system)
                and m.source_entity_name = 'Brand'
                and m.source_key         = cast(s.acme_brand_id as text)
                and m.entity_name        = 'brand'),
            (select min(t.brand_id)
               from {{ this }} as t
              where lower(t.brand_name) = lower(s.brand_name))
        ) as existing_brand_id
    from src as s

),

keyed as (

    select
        m.*,
        coalesce(
            m.existing_brand_id,
            (select coalesce(max(brand_id), 0) from {{ this }})
              + row_number() over (partition by m.existing_brand_id is null
                                   order by m.brand_name)
        ) as brand_id
    from matched as m

)

select
    k.brand_id,
    coalesce(e.brand_name, k.brand_name)                  as brand_name,   -- keep canonical spelling
    e.brand_code                                          as brand_code,   -- Acme has none
    coalesce(k.manufacturer_name, e.manufacturer_name)    as manufacturer_name,
    coalesce(c.country_code, e.country_code)              as country_code, -- only valid ISO codes
    coalesce(k.website_url, e.website_url)                as website_url,
    e.support_phone                                       as support_phone,
    e.support_email                                       as support_email,
    k.is_active                                           as is_active,
    coalesce(e.created_at, k.created_at,
             strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))       as created_at,
    coalesce(k.updated_at,
             strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))       as updated_at
from keyed as k
left join {{ this }} as e
       on e.brand_id = k.brand_id
left join {{ source('canonical', 'country') }} as c
       on c.country_code = k.country_code
