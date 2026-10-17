-- =====================================================================
-- Canonical E-Commerce Model
-- Dialect: SQLite 3 (3.35+)
--
-- Purpose: one target model that ETL/ELT jobs load from three source
-- schemas, with exactly ONE table per business concept:
--   * acme_shopping.sql  (AcmeShopping)
--   * big_river.sql      (BigRiver marketplace)
--   * bobs_uncle.sql     (BobsUncle)
-- It also adds concepts none of the sources had: customer profile,
-- billing / shipping addresses, payments, shipments, and RMAs (returns).
--
-- One concept, one table:
--   * brand          : brand AND its manufacturer (AcmeShopping Brand,
--                      BobsUncle brand.mfr_*, BigRiver PRD_BRAND_TEXT).
--   * product        : the sellable item AND its manufacturer model
--                      (AcmeShopping Model, BigRiver PRODUCT, BobsUncle
--                      product + brand.model_*).
--   * customer_order : a cart and an order are the same thing at
--                      different points in its life. order_status runs
--                      CART -> PLACED -> SHIPPED -> ... A BigRiver
--                      SHOPPING_CART, a BobsUncle cart and an
--                      AcmeShopping Order all load here.
--   * order_item     : cart lines and order lines (AcmeShopping
--                      OrderItem, BigRiver ITEM, BobsUncle cart_item).
--   * customer       : account AND profile.
-- Child tables exist only for things that repeat per row (identifiers,
-- attributes, addresses, discounts, shipments, return lines).
--
-- Canonical conventions (every source is converted INTO these):
--   * Names        : lower snake_case, full words, no table prefixes.
--                    "order" is reserved, so the table is customer_order.
--   * Keys         : INTEGER PRIMARY KEY surrogate keys (SQLite rowid).
--                    Business/natural keys (sku, order_number, promotion
--                    code, ...) are UNIQUE columns. Source keys and raw
--                    source values live in source_key_map; orders, order
--                    lines, promotions, promotion targets and applied
--                    discounts also carry source_system_id + source key.
--   * Money        : INTEGER in the currency's minor unit (cents for USD;
--                    see currency.minor_unit_digits), always paired with a
--                    currency_code. SQLite has no exact decimal type, so
--                    integers keep totals and CHECKs exact.
--                    BobsUncle *_cents          -> load as is.
--                    AcmeShopping / BigRiver $  -> CAST(ROUND(x * 100) AS INTEGER).
--   * Percentages  : REAL fractions: 0.15 = 15%.
--                    AcmeShopping / BobsUncle 15.00 -> divide by 100.
--   * Timestamps   : TEXT, ISO-8601 UTC 'YYYY-MM-DDTHH:MM:SS.SSSZ'.
--                    Dates are TEXT 'YYYY-MM-DD'.
--                    AcmeShopping / BigRiver 'YYYY-MM-DD HH:MM:SS' (UTC)
--                      -> strftime('%Y-%m-%dT%H:%M:%fZ', x).
--                    BobsUncle local US/Central -> convert to UTC in the ETL tool;
--                      SQLite has no time-zone database.
--                    BobsUncle 'YYYYMMDD' text -> substr(x,1,4)||'-'||substr(x,5,2)||'-'||substr(x,7,2).
--   * Flags        : INTEGER 0/1 with CHECK. BobsUncle 'Y'/'N' -> 1/0.
--   * Weight       : grams (INTEGER). lbs * 453.59237.
--   * Countries    : ISO 3166-1 alpha-2; currencies: ISO 4217.
--   * Status codes : readable UPPER_CASE words enforced by CHECK constraints.
--   * Sizes        : VARCHAR(n) / CHAR(n) lengths document intent only;
--                    SQLite does not enforce them.
--   * Foreign keys : enforced only with PRAGMA foreign_keys = ON (set below,
--                    and must be set on every connection the ETL opens).
--
-- Concept crosswalk
--   canonical          AcmeShopping         BigRiver                 BobsUncle
--   -----------------  -------------------  -----------------------  -----------------------
--   category           CatalogCategory      PRD_BROWSE_PATH          product.dept_nm
--   brand              Brand                PRD_BRAND_TEXT           brand.mfr_*
--   product            Model                PRODUCT                  product + brand.model_*
--   product_identifier Model.Sku/UpcCode    PRD_ID, PRD_UPC          upc_cd/ean_cd/gtin_cd
--   product_attribute  -                    PRODUCT_TAGS             color_desc/size_desc
--   warranty_plan      -                    -                        product.warr_*
--   seller             (one 1st-party row)  STORE                    (one 1st-party row)
--   offer              Model.MSRP           ITEM price per STORE     retail/cost_cents
--   warehouse          -                    -                        inventory.whse_cd
--   inventory          -                    -                        inventory
--   promotion          Promotions           PROMOTIONS               promotion
--   promotion_target   Promotions.AppliesTo PRM_TARGET_*             promotion.scope
--   customer           Order.CustomerId     SC_ACCOUNT_ID            cart.cust_ref
--   address            ShipTo*              SC_SHIP_REGION           cart.ship_zip
--   customer_order     Order                SHOPPING_CART            cart
--   order_item         OrderItem            ITEM                     cart_item
--   applied_discount   Order/OrderItem      SC_CART_PRM, ITM_PRM_*   cart_item.disc_*
--   payment, shipment  NEW                  NEW                      NEW
--   rma, rma_item      NEW ('Returned')     NEW                      negative qty lines
--   refund             NEW                  NEW                      NEW
--
-- Status mapping into customer_order.order_status
--   AcmeShopping 'Pending'->PLACED, 'Shipped'->SHIPPED, 'Delivered'->DELIVERED,
--                'Cancelled'->CANCELLED, 'Returned'->RETURNED
--   BigRiver     'ACTIVE'->CART, 'SAVED_FOR_LATER'->SAVED_FOR_LATER,
--                'PURCHASED'->PLACED, 'EXPIRED'->EXPIRED
--   BobsUncle    'O'->CART, 'C'->PLACED, 'A'->ABANDONED, 'X'->CANCELLED
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS refund               ;
DROP TABLE IF EXISTS rma_item             ;
DROP TABLE IF EXISTS rma                  ;
DROP TABLE IF EXISTS return_reason        ;
DROP TABLE IF EXISTS shipment_item        ;
DROP TABLE IF EXISTS shipment             ;
DROP TABLE IF EXISTS payment              ;
DROP TABLE IF EXISTS applied_discount     ;
DROP TABLE IF EXISTS order_item           ;
DROP TABLE IF EXISTS order_address        ;
DROP TABLE IF EXISTS customer_order       ;
DROP TABLE IF EXISTS promotion_target     ;
DROP TABLE IF EXISTS promotion            ;
DROP TABLE IF EXISTS customer_address     ;
DROP TABLE IF EXISTS customer             ;
DROP TABLE IF EXISTS inventory            ;
DROP TABLE IF EXISTS warehouse            ;
DROP TABLE IF EXISTS address              ;
DROP TABLE IF EXISTS offer                ;
DROP TABLE IF EXISTS seller               ;
DROP TABLE IF EXISTS product_warranty     ;
DROP TABLE IF EXISTS warranty_plan        ;
DROP TABLE IF EXISTS product_attribute    ;
DROP TABLE IF EXISTS attribute_definition ;
DROP TABLE IF EXISTS product_identifier   ;
DROP TABLE IF EXISTS product              ;
DROP TABLE IF EXISTS brand                ;
DROP TABLE IF EXISTS category             ;
DROP TABLE IF EXISTS source_key_map       ;
DROP TABLE IF EXISTS source_system        ;
DROP TABLE IF EXISTS currency             ;
DROP TABLE IF EXISTS country              ;


-- =====================================================================
-- 1. REFERENCE DATA AND LINEAGE
-- =====================================================================

-- ---------------------------------------------------------------------
-- country: ISO 3166-1. Replaces free text like 'Japan', 'JP', 'Japan '.
-- ---------------------------------------------------------------------
CREATE TABLE country (
    country_code        CHAR(2)       PRIMARY KEY,   -- ISO 3166-1 alpha-2
    country_name        VARCHAR(100)  NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- currency: ISO 4217
-- ---------------------------------------------------------------------
CREATE TABLE currency (
    currency_code       CHAR(3)       PRIMARY KEY,   -- 'USD','CAD','EUR'
    currency_name       VARCHAR(60)   NOT NULL,
    minor_unit_digits   SMALLINT      NOT NULL DEFAULT 2
);

-- ---------------------------------------------------------------------
-- source_system / source_key_map: lineage back to the source systems.
--   * Rows that come from exactly one source (customer_order, order_item,
--     promotion, promotion_target, applied_discount) carry source_system_id
--     plus their source key or source field as columns.
--   * Master data that is merged across sources (brand, product, category,
--     customer, ...) can have several sources per row, so its lineage lives
--     in source_key_map instead.
-- Examples:
--   ('BOBSUNCLE', 'product', 'BU-0004521')        -> product 17
--   ('ACME',      'Model', '1042')                 -> product 17 (same TV)
--   ('BIGRIVER',  'PRODUCT.PRD_BRAND_TEXT', 'SONY') -> brand 3
--   ('BOBSUNCLE', 'brand.mfr_nm', 'SONY Corp.')     -> brand 3
-- The last two replace a separate brand-alias table: every raw brand
-- spelling resolves to one canonical brand.
-- ---------------------------------------------------------------------
CREATE TABLE source_system (
    source_system_id    INTEGER       PRIMARY KEY,
    source_system_code  VARCHAR(20)   NOT NULL UNIQUE,  -- 'CANONICAL','ACME','BIGRIVER','BOBSUNCLE'
    source_system_name  VARCHAR(100)  NOT NULL
);

CREATE TABLE source_key_map (
    source_key_map_id   INTEGER       PRIMARY KEY,
    source_system_id    INTEGER       NOT NULL REFERENCES source_system (source_system_id),
    source_entity_name  VARCHAR(60)   NOT NULL,      -- source table or table.column
    source_key          VARCHAR(150)  NOT NULL,      -- source PK or raw value, as text
    entity_name         VARCHAR(50)   NOT NULL,      -- canonical table name, e.g. 'product'
    canonical_id        INTEGER       NOT NULL,      -- PK value in that canonical table
    loaded_at           TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_system_id, source_entity_name, source_key)
);
CREATE INDEX ix_source_key_map_canonical ON source_key_map (entity_name, canonical_id);


-- =====================================================================
-- 2. CATALOG
-- =====================================================================

-- ---------------------------------------------------------------------
-- category: self-referencing tree (Electronics > TVs > OLED).
-- BigRiver browse paths and BobsUncle department names are parsed
-- into this tree.
-- ---------------------------------------------------------------------
CREATE TABLE category (
    category_id         INTEGER       PRIMARY KEY,
    parent_category_id  INTEGER       NULL REFERENCES category (category_id),
    category_code       VARCHAR(60)   NOT NULL UNIQUE,  -- stable slug, e.g. 'electronics-tv-oled'
    category_name       VARCHAR(200)  NOT NULL,
    short_description   VARCHAR(200)  NULL,
    long_description    VARCHAR(500)  NULL,
    sort_order          SMALLINT      NOT NULL DEFAULT 0,
    is_active           INTEGER       NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    effective_at        TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at          TEXT          NULL,
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (parent_category_id IS NULL OR parent_category_id <> category_id),
    CHECK (expires_at IS NULL OR expires_at > effective_at)
);
CREATE INDEX ix_category_parent ON category (parent_category_id);

-- ---------------------------------------------------------------------
-- brand: the consumer-facing brand and the company that makes it.
--   AcmeShopping Brand   -> one row each
--   BobsUncle brand      -> one row per distinct mfr_cd (model columns
--                           go to product)
--   BigRiver brand text  -> matched to an existing row via source_key_map
-- ---------------------------------------------------------------------
CREATE TABLE brand (
    brand_id            INTEGER       PRIMARY KEY,
    brand_name          VARCHAR(100)  NOT NULL UNIQUE,   -- 'Sony'
    brand_code          VARCHAR(10)   NULL UNIQUE,       -- BobsUncle mfr_cd, e.g. 'SNY'
    manufacturer_name   VARCHAR(150)  NULL,              -- legal name, 'Sony Group Corporation'
    country_code        CHAR(2)       NULL REFERENCES country (country_code), -- home country / HQ
    website_url         VARCHAR(255)  NULL,
    support_phone       VARCHAR(25)   NULL,              -- warranty inquiries
    support_email       VARCHAR(255)  NULL,
    is_active           INTEGER       NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ---------------------------------------------------------------------
-- product: one sellable item (one SKU), including its manufacturer
-- model details. Seller-independent; each seller's price is in offer.
-- Color/size variants of one model are separate rows sharing
-- brand_id + model_number.
-- ---------------------------------------------------------------------
CREATE TABLE product (
    product_id          INTEGER       PRIMARY KEY,
    sku                 VARCHAR(30)   NOT NULL UNIQUE,
    brand_id            INTEGER       NULL REFERENCES brand (brand_id),   -- NULL for unbranded goods
    category_id         INTEGER       NULL REFERENCES category (category_id),
    model_number        VARCHAR(60)   NULL,              -- manufacturer model / part number
    model_name          VARCHAR(200)  NULL,
    model_year          SMALLINT      NULL,
    product_name        VARCHAR(200)  NOT NULL,          -- short name for search results / cart
    long_name           VARCHAR(500)  NULL,              -- product detail page title
    description         TEXT          NULL,
    country_of_origin   CHAR(2)       NULL REFERENCES country (country_code),
    weight_grams        INTEGER       NULL CHECK (weight_grams >= 0),
    msrp_amount         INTEGER       NULL CHECK (msrp_amount >= 0),
    msrp_currency_code  CHAR(3)       NULL REFERENCES currency (currency_code),
    is_taxable          INTEGER       NOT NULL DEFAULT 1 CHECK (is_taxable IN (0,1)),
    is_adult            INTEGER       NOT NULL DEFAULT 0 CHECK (is_adult IN (0,1)),
    is_active           INTEGER       NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    release_date        TEXT          NULL,
    discontinued_date   TEXT          NULL,              -- NULL = still sold
    effective_at        TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at          TEXT          NULL,
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK ((msrp_amount IS NULL) = (msrp_currency_code IS NULL)),
    CHECK (model_number IS NULL OR brand_id IS NOT NULL),
    CHECK (discontinued_date IS NULL OR release_date IS NULL OR discontinued_date >= release_date),
    CHECK (expires_at IS NULL OR expires_at > effective_at)
);
CREATE INDEX ix_product_brand_model ON product (brand_id, model_number);
CREATE INDEX ix_product_category    ON product (category_id);

-- ---------------------------------------------------------------------
-- product_identifier: barcodes and external ids (a product can have
-- several), one row each instead of upc_cd / ean_cd / gtin_cd columns.
-- ---------------------------------------------------------------------
CREATE TABLE product_identifier (
    product_identifier_id INTEGER      PRIMARY KEY,
    product_id          INTEGER       NOT NULL REFERENCES product (product_id),
    identifier_type     VARCHAR(20)   NOT NULL,
    identifier_value    VARCHAR(60)   NOT NULL,
    UNIQUE (identifier_type, identifier_value),
    CHECK (identifier_type IN ('UPC','EAN','GTIN','ISBN','MARKETPLACE_ID'))
);
CREATE INDEX ix_product_identifier_product ON product_identifier (product_id);

-- ---------------------------------------------------------------------
-- attribute_definition / product_attribute: controlled vocabulary of
-- attributes (color, size, screen_size, eco) instead of free key/values.
-- ---------------------------------------------------------------------
CREATE TABLE attribute_definition (
    attribute_id        INTEGER       PRIMARY KEY,
    attribute_key       VARCHAR(50)   NOT NULL UNIQUE,   -- 'color','size','screen_size','eco'
    display_name        VARCHAR(100)  NOT NULL,
    data_type           VARCHAR(10)   NOT NULL DEFAULT 'TEXT',
    unit_of_measure     VARCHAR(20)   NULL,              -- 'in', 'cm', 'W'
    CHECK (data_type IN ('TEXT','NUMBER','BOOLEAN','DATE'))
);

CREATE TABLE product_attribute (
    product_attribute_id INTEGER       PRIMARY KEY,
    product_id          INTEGER       NOT NULL REFERENCES product (product_id),
    attribute_id        INTEGER       NOT NULL REFERENCES attribute_definition (attribute_id),
    attribute_value     VARCHAR(255)  NOT NULL,
    value_source        VARCHAR(10)   NOT NULL DEFAULT 'SELLER',
    confidence          REAL          NULL,
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (product_id, attribute_id, attribute_value),
    CHECK (value_source IN ('SELLER','BRAND','ML','CATALOG')),
    CHECK (confidence IS NULL OR (value_source = 'ML' AND confidence BETWEEN 0 AND 1))
);
CREATE INDEX ix_product_attribute_lookup ON product_attribute (attribute_id, attribute_value);

-- ---------------------------------------------------------------------
-- warranty_plan / product_warranty: warranty terms stored once and
-- linked to products (BobsUncle repeated them on every product row).
-- An extended warranty sold as an add-on is itself a product, linked
-- via warranty_product_id.
-- ---------------------------------------------------------------------
CREATE TABLE warranty_plan (
    warranty_plan_id    INTEGER       PRIMARY KEY,
    warranty_type       VARCHAR(20)   NOT NULL,
    provider_name       VARCHAR(100)  NULL,
    duration_months     SMALLINT      NULL CHECK (duration_months > 0),
    covers_parts        INTEGER       NOT NULL DEFAULT 1 CHECK (covers_parts IN (0,1)),
    covers_labor        INTEGER       NOT NULL DEFAULT 1 CHECK (covers_labor IN (0,1)),
    terms_text          TEXT          NULL,
    warranty_product_id INTEGER       NULL UNIQUE REFERENCES product (product_id), -- sellable extended warranty sku
    CHECK (warranty_type IN ('MANUFACTURER','EXTENDED'))
);

CREATE TABLE product_warranty (
    product_id          INTEGER       NOT NULL REFERENCES product (product_id),
    warranty_plan_id    INTEGER       NOT NULL REFERENCES warranty_plan (warranty_plan_id),
    is_included         INTEGER       NOT NULL DEFAULT 1 CHECK (is_included IN (0,1)),   -- 0 = optional add-on
    PRIMARY KEY (product_id, warranty_plan_id)
);


-- =====================================================================
-- 3. SELLERS, OFFERS, INVENTORY
-- =====================================================================

-- ---------------------------------------------------------------------
-- seller: who sells the product. AcmeShopping and BobsUncle each load
-- as a single first-party seller; BigRiver stores load one row each.
-- ---------------------------------------------------------------------
CREATE TABLE seller (
    seller_id           INTEGER       PRIMARY KEY,
    seller_handle       VARCHAR(60)   NOT NULL UNIQUE,   -- 'gadget-galaxy'
    display_name        VARCHAR(150)  NOT NULL,
    is_first_party      INTEGER       NOT NULL DEFAULT 0 CHECK (is_first_party IN (0,1)),
    country_code        CHAR(2)       NOT NULL REFERENCES country (country_code),
    default_currency_code CHAR(3)     NOT NULL REFERENCES currency (currency_code),
    rating              REAL          NULL CHECK (rating BETWEEN 0 AND 5),
    ships_from_region   VARCHAR(10)   NULL,              -- ISO 3166-2, 'US-NJ'
    fulfilled_by_platform INTEGER       NOT NULL DEFAULT 0 CHECK (fulfilled_by_platform IN (0,1)),
    seller_status       VARCHAR(12)   NOT NULL DEFAULT 'LIVE',
    onboarded_at        TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (seller_status IN ('LIVE','SUSPENDED','CLOSED'))
);

-- ---------------------------------------------------------------------
-- offer: a seller's price (and cost) for a product over a period of time.
-- ---------------------------------------------------------------------
CREATE TABLE offer (
    offer_id            INTEGER       PRIMARY KEY,
    seller_id           INTEGER       NOT NULL REFERENCES seller (seller_id),
    product_id          INTEGER       NOT NULL REFERENCES product (product_id),
    item_condition      VARCHAR(12)   NOT NULL DEFAULT 'NEW',
    price_amount        INTEGER       NOT NULL CHECK (price_amount >= 0),
    cost_amount         INTEGER       NULL CHECK (cost_amount >= 0),
    currency_code       CHAR(3)       NOT NULL REFERENCES currency (currency_code),
    is_subscribe_eligible INTEGER       NOT NULL DEFAULT 0 CHECK (is_subscribe_eligible IN (0,1)),
    effective_at        TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at          TEXT          NULL,
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (seller_id, product_id, item_condition, effective_at),
    CHECK (item_condition IN ('NEW','REFURBISHED','USED','OPEN_BOX')),
    CHECK (expires_at IS NULL OR expires_at > effective_at)
);
CREATE INDEX ix_offer_product ON offer (product_id);

-- ---------------------------------------------------------------------
-- address: a postal address, used by customers, warehouses, orders,
-- payments, shipments and RMAs. Street and city are nullable because
-- the sources often captured only a postal code or region
-- (AcmeShopping ShipToPostalCode, BigRiver SC_SHIP_REGION, BobsUncle
-- ship_zip). Treat rows as immutable once an order references them.
-- ---------------------------------------------------------------------
CREATE TABLE address (
    address_id          INTEGER       PRIMARY KEY,
    recipient_name      VARCHAR(150)  NULL,
    company_name        VARCHAR(150)  NULL,
    line1               VARCHAR(200)  NULL,
    line2               VARCHAR(200)  NULL,
    city                VARCHAR(100)  NULL,
    region_code         VARCHAR(10)   NULL,              -- ISO 3166-2 subdivision, 'US-NJ'
    postal_code         VARCHAR(20)   NULL,
    country_code        CHAR(2)       NOT NULL REFERENCES country (country_code),
    phone               VARCHAR(25)   NULL,
    is_validated        INTEGER       NOT NULL DEFAULT 0 CHECK (is_validated IN (0,1)),
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (((line1 IS NOT NULL) + (city IS NOT NULL) + (region_code IS NOT NULL) + (postal_code IS NOT NULL)) > 0)
);

-- ---------------------------------------------------------------------
-- warehouse / inventory: stock per product per location.
-- ---------------------------------------------------------------------
CREATE TABLE warehouse (
    warehouse_id        INTEGER       PRIMARY KEY,
    warehouse_code      VARCHAR(10)   NOT NULL UNIQUE,   -- 'NJ01','TX02'
    warehouse_name      VARCHAR(100)  NULL,
    seller_id           INTEGER       NULL REFERENCES seller (seller_id), -- NULL = platform-operated
    address_id          INTEGER       NULL REFERENCES address (address_id),
    is_active           INTEGER       NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
);

CREATE TABLE inventory (
    product_id          INTEGER       NOT NULL REFERENCES product (product_id),
    warehouse_id        INTEGER       NOT NULL REFERENCES warehouse (warehouse_id),
    quantity_on_hand    INTEGER       NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    quantity_reserved   INTEGER       NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0),
    quantity_on_order   INTEGER       NOT NULL DEFAULT 0 CHECK (quantity_on_order >= 0),
    reorder_point       INTEGER       NULL CHECK (reorder_point >= 0),
    bin_location        VARCHAR(15)   NULL,
    last_counted_date   TEXT          NULL,
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (product_id, warehouse_id)
);


-- =====================================================================
-- 4. CUSTOMERS
-- =====================================================================

-- ---------------------------------------------------------------------
-- customer: a registered account and its profile. Guest shoppers have
-- no customer row; the order keeps their email instead.
-- ---------------------------------------------------------------------
CREATE TABLE customer (
    customer_id         INTEGER       PRIMARY KEY,
    customer_number     VARCHAR(40)   NOT NULL UNIQUE,   -- account number / BigRiver SC_ACCOUNT_ID
    email               VARCHAR(255)  NOT NULL UNIQUE,
    loyalty_number      VARCHAR(40)   NULL UNIQUE,       -- BobsUncle cust_ref loyalty #
    first_name          VARCHAR(100)  NULL,
    last_name           VARCHAR(100)  NULL,
    display_name        VARCHAR(100)  NULL,
    phone               VARCHAR(25)   NULL,
    birth_date          TEXT          NULL,
    preferred_language  VARCHAR(10)   NULL,              -- BCP 47, 'en-US'
    preferred_currency_code CHAR(3)   NULL REFERENCES currency (currency_code),
    marketing_opt_in    INTEGER       NOT NULL DEFAULT 0 CHECK (marketing_opt_in IN (0,1)),
    sms_opt_in          INTEGER       NOT NULL DEFAULT 0 CHECK (sms_opt_in IN (0,1)),
    customer_status     VARCHAR(12)   NOT NULL DEFAULT 'ACTIVE',
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (customer_status IN ('ACTIVE','SUSPENDED','CLOSED'))
);

-- ---------------------------------------------------------------------
-- customer_address: a customer's address book. An address can be used
-- for billing, shipping, or both; at most one default of each kind.
-- ---------------------------------------------------------------------
CREATE TABLE customer_address (
    customer_id         INTEGER       NOT NULL REFERENCES customer (customer_id),
    address_id          INTEGER       NOT NULL REFERENCES address (address_id),
    nickname            VARCHAR(50)   NULL,              -- 'Home', 'Office'
    is_billing          INTEGER       NOT NULL DEFAULT 0 CHECK (is_billing IN (0,1)),
    is_shipping         INTEGER       NOT NULL DEFAULT 1 CHECK (is_shipping IN (0,1)),
    is_default_billing  INTEGER       NOT NULL DEFAULT 0 CHECK (is_default_billing IN (0,1)),
    is_default_shipping INTEGER       NOT NULL DEFAULT 0 CHECK (is_default_shipping IN (0,1)),
    PRIMARY KEY (customer_id, address_id),
    CHECK (is_billing OR is_shipping),
    CHECK (NOT is_default_billing  OR is_billing),
    CHECK (NOT is_default_shipping OR is_shipping)
);
CREATE UNIQUE INDEX ux_customer_default_billing
    ON customer_address (customer_id) WHERE is_default_billing;
CREATE UNIQUE INDEX ux_customer_default_shipping
    ON customer_address (customer_id) WHERE is_default_shipping;


-- =====================================================================
-- 5. PROMOTIONS
-- =====================================================================

-- ---------------------------------------------------------------------
-- promotion: union of AcmeShopping, BigRiver and BobsUncle promotions.
-- What it applies to lives in promotion_target (0..n rows), so one
-- promotion can target several products, brands or categories.
--
-- Lineage: every promotion comes from exactly one source system (they
-- are not merged across sources), so the source is stored on the row:
--   source_system_id      ACME, BIGRIVER, BOBSUNCLE, or CANONICAL
--   source_promotion_key  that system's key for the promotion
--                           ACME      "Promotions"."PromotionId"
--                           BIGRIVER  PROMOTIONS.PRM_UUID
--                           BOBSUNCLE promotion.promo_id
--   loaded_at             when the ETL last loaded/refreshed the row
-- promotion_code is only unique within a source: AcmeShopping and
-- BobsUncle can both run a 'BF2023' code.
-- ---------------------------------------------------------------------
CREATE TABLE promotion (
    promotion_id        INTEGER       PRIMARY KEY,
    source_system_id    INTEGER       NOT NULL REFERENCES source_system (source_system_id),
    source_promotion_key VARCHAR(64)  NOT NULL,          -- source PK as text
    promotion_code      VARCHAR(30)   NULL,              -- NULL = applied automatically
    promotion_name      VARCHAR(150)  NOT NULL,
    description         VARCHAR(500)  NULL,
    event_name          VARCHAR(100)  NULL,              -- 'Black Friday'
    scope               VARCHAR(12)   NOT NULL,          -- level the discount is applied at
    funded_by           VARCHAR(12)   NOT NULL DEFAULT 'PLATFORM',
    seller_id           INTEGER       NULL REFERENCES seller (seller_id),
    funding_brand_id    INTEGER       NULL REFERENCES brand (brand_id),
    partner_company     VARCHAR(100)  NULL,              -- external co-sponsor
    discount_percent    REAL          NULL CHECK (discount_percent > 0 AND discount_percent <= 1),
    discount_amount     INTEGER       NULL CHECK (discount_amount > 0),
    currency_code       CHAR(3)       NULL REFERENCES currency (currency_code),
    buy_quantity        SMALLINT      NULL CHECK (buy_quantity > 0),
    get_quantity        SMALLINT      NULL CHECK (get_quantity > 0),
    minimum_order_amount INTEGER       NULL CHECK (minimum_order_amount >= 0),
    max_redemptions     INTEGER       NULL CHECK (max_redemptions > 0),
    max_per_customer    INTEGER       NULL CHECK (max_per_customer > 0),
    is_stackable        INTEGER       NOT NULL DEFAULT 0 CHECK (is_stackable IN (0,1)),
    is_active           INTEGER       NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    starts_at           TEXT          NOT NULL,
    ends_at             TEXT          NULL,              -- NULL = open-ended
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    loaded_at           TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_system_id, source_promotion_key),
    UNIQUE (source_system_id, promotion_code),     -- multiple NULL codes allowed
    UNIQUE (promotion_id, source_system_id),       -- target of composite FKs below
    CHECK (scope IN ('SITEWIDE','ORDER','ITEM')),
    CHECK (funded_by IN ('PLATFORM','SELLER','MANUFACTURER','PARTNER')),
    CHECK (funded_by <> 'SELLER'       OR seller_id IS NOT NULL),
    CHECK (funded_by <> 'MANUFACTURER' OR funding_brand_id IS NOT NULL),
    CHECK (discount_percent IS NOT NULL
           OR discount_amount IS NOT NULL
           OR (buy_quantity IS NOT NULL AND get_quantity IS NOT NULL)),
    CHECK ((discount_amount IS NULL AND minimum_order_amount IS NULL) OR currency_code IS NOT NULL),
    CHECK ((buy_quantity IS NULL) = (get_quantity IS NULL)),
    CHECK (ends_at IS NULL OR ends_at > starts_at)
);

-- ---------------------------------------------------------------------
-- promotion_target: what a promotion applies to. Exactly one target
-- reference per row, matching target_type. No rows = applies to all.
--
-- Lineage: the sources have no target table of their own; targets are
-- unpacked from columns on the source promotion row. source_field names
-- the column each target came from, e.g.
--   ACME      "AppliesToModelId", "AppliesToBrandId", "AppliesToCategoryId"
--   BIGRIVER  PRM_TARGET_PRD_UUID, PRM_TARGET_TAG_KEY/PRM_TARGET_TAG_VALUE
-- source_system_id must match the parent promotion's (composite FK).
-- ---------------------------------------------------------------------
CREATE TABLE promotion_target (
    promotion_target_id INTEGER       PRIMARY KEY,
    promotion_id        INTEGER       NOT NULL,
    source_system_id    INTEGER       NOT NULL,
    source_field        VARCHAR(60)   NULL,              -- source column the target was derived from
    target_type         VARCHAR(12)   NOT NULL,
    product_id          INTEGER       NULL REFERENCES product (product_id),
    brand_id            INTEGER       NULL REFERENCES brand (brand_id),
    category_id         INTEGER       NULL REFERENCES category (category_id),
    attribute_id        INTEGER       NULL REFERENCES attribute_definition (attribute_id),
    attribute_value     VARCHAR(255)  NULL,
    is_exclusion        INTEGER       NOT NULL DEFAULT 0 CHECK (is_exclusion IN (0,1)),  -- 1 = "everything except"
    loaded_at           TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (promotion_id, source_system_id)
        REFERENCES promotion (promotion_id, source_system_id) ON DELETE CASCADE,
    CHECK (target_type IN ('PRODUCT','BRAND','CATEGORY','ATTRIBUTE')),
    CHECK (
        (target_type = 'PRODUCT'   AND product_id   IS NOT NULL AND ((brand_id IS NOT NULL) + (category_id IS NOT NULL) + (attribute_id IS NOT NULL)) = 0) OR
        (target_type = 'BRAND'     AND brand_id     IS NOT NULL AND ((product_id IS NOT NULL) + (category_id IS NOT NULL) + (attribute_id IS NOT NULL)) = 0) OR
        (target_type = 'CATEGORY'  AND category_id  IS NOT NULL AND ((product_id IS NOT NULL) + (brand_id IS NOT NULL) + (attribute_id IS NOT NULL)) = 0) OR
        (target_type = 'ATTRIBUTE' AND attribute_id IS NOT NULL AND attribute_value IS NOT NULL
                                   AND ((product_id IS NOT NULL) + (brand_id IS NOT NULL) + (category_id IS NOT NULL)) = 0)
    )
);
CREATE INDEX ix_promotion_target_promotion ON promotion_target (promotion_id);


-- =====================================================================
-- 6. ORDERS (carts included), PAYMENTS, SHIPMENTS
-- =====================================================================

-- ---------------------------------------------------------------------
-- customer_order: a cart or an order. A row starts as CART (or is
-- loaded directly as PLACED for AcmeShopping) and moves through:
--   CART / SAVED_FOR_LATER -> ABANDONED | EXPIRED          (never bought)
--   CART -> PLACED -> PAID -> SHIPPED -> DELIVERED -> RETURNED ...
-- Totals are kept current while it is a cart and frozen once PLACED,
-- because they are the record of what was charged.
--
-- Lineage: every order comes from exactly one source system, so the
-- source is stored on the row itself:
--   source_system_id  which system it came from (ACME, BIGRIVER, BOBSUNCLE,
--                     or CANONICAL for orders created directly here)
--   source_order_key  that system's primary key for the order
--                       ACME      "Order"."OrderId"
--                       BIGRIVER  SHOPPING_CART.SC_UUID
--                       BOBSUNCLE cart.cart_no
--   loaded_at         when the ETL last loaded/refreshed the row
-- order_number is only unique within a source: AcmeShopping and
-- BobsUncle can both have an order '100045'.
-- ---------------------------------------------------------------------
CREATE TABLE customer_order (
    order_id            INTEGER       PRIMARY KEY,
    source_system_id    INTEGER       NOT NULL REFERENCES source_system (source_system_id),
    source_order_key    VARCHAR(64)   NOT NULL,          -- source PK as text
    order_number        VARCHAR(20)   NOT NULL,          -- Acme OrderNumber, BobsUncle cart_no; generated for BigRiver
    customer_id        INTEGER       NULL REFERENCES customer (customer_id), -- NULL = guest
    customer_email      VARCHAR(255)  NULL,              -- snapshot; required once placed
    order_status        VARCHAR(20)   NOT NULL DEFAULT 'CART',
    channel             VARCHAR(10)   NULL,
    device_type         VARCHAR(10)   NULL,
    session_token       VARCHAR(64)   NULL,
    currency_code       CHAR(3)       NOT NULL REFERENCES currency (currency_code), -- currency the shopper saw / paid
    subtotal_amount     INTEGER       NOT NULL DEFAULT 0 CHECK (subtotal_amount >= 0),
    discount_total      INTEGER       NOT NULL DEFAULT 0 CHECK (discount_total >= 0),
    tax_total           INTEGER       NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    shipping_total      INTEGER       NOT NULL DEFAULT 0 CHECK (shipping_total >= 0),
    grand_total         INTEGER       NOT NULL DEFAULT 0 CHECK (grand_total >= 0),
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),  -- cart created
    updated_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    placed_at           TEXT          NULL,              -- checkout completed
    closed_at           TEXT          NULL,              -- abandoned / expired / cancelled
    loaded_at           TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_system_id, source_order_key),
    UNIQUE (source_system_id, order_number),
    UNIQUE (order_id, source_system_id),           -- target of order_item's composite FK
    CHECK (order_status IN ('CART','SAVED_FOR_LATER','ABANDONED','EXPIRED',
                            'PLACED','PAID','PARTIALLY_SHIPPED','SHIPPED','DELIVERED',
                            'CANCELLED','PARTIALLY_RETURNED','RETURNED')),
    CHECK (channel IN ('WEB','APP','POS','VOICE')),
    CHECK (device_type IN ('IOS','ANDROID','DESKTOP','ALEXA','KIOSK')),
    CHECK (order_status IN ('CART','SAVED_FOR_LATER','ABANDONED','EXPIRED','CANCELLED')
           OR (placed_at IS NOT NULL AND customer_email IS NOT NULL)),
    CHECK (grand_total = subtotal_amount - discount_total + tax_total + shipping_total)
);
CREATE INDEX ix_customer_order_order_number ON customer_order (order_number);
CREATE INDEX ix_customer_order_customer  ON customer_order (customer_id);
CREATE INDEX ix_customer_order_status    ON customer_order (order_status);
CREATE INDEX ix_customer_order_placed_at ON customer_order (placed_at);

-- ---------------------------------------------------------------------
-- order_address: the billing and shipping address of an order. For a
-- cart this may be just a postal code or region used for estimates.
-- ---------------------------------------------------------------------
CREATE TABLE order_address (
    order_id            INTEGER       NOT NULL REFERENCES customer_order (order_id) ON DELETE CASCADE,
    address_type        VARCHAR(10)   NOT NULL,
    address_id          INTEGER       NOT NULL REFERENCES address (address_id),
    PRIMARY KEY (order_id, address_type),
    CHECK (address_type IN ('BILLING','SHIPPING'))
);

-- ---------------------------------------------------------------------
-- order_item: one product line from one seller, in a cart or an order.
-- Lines taken out of a cart keep the row with removed_at set.
-- Quantities are always positive; returns go through rma_item
-- (BobsUncle used negative quantities).
--
-- Lineage: source_line_key is the source system's key for the line
--   ACME      "OrderItem"."OrderItemId"
--   BIGRIVER  ITEM.ITM_UUID
--   BOBSUNCLE cart_no || ':' || line_seq   (composite key in the source)
-- The source system is the parent order's; source_system_id is repeated
-- here so lines can be filtered and de-duplicated without a join, and a
-- composite foreign key guarantees it always matches the order.
-- ---------------------------------------------------------------------
CREATE TABLE order_item (
    order_item_id       INTEGER       PRIMARY KEY,
    order_id            INTEGER       NOT NULL,
    source_system_id    INTEGER       NOT NULL,
    source_line_key     VARCHAR(80)   NOT NULL,          -- source PK as text
    line_number         SMALLINT      NOT NULL,
    product_id          INTEGER       NOT NULL REFERENCES product (product_id),
    seller_id           INTEGER       NOT NULL REFERENCES seller (seller_id),
    offer_id            INTEGER       NULL REFERENCES offer (offer_id),
    parent_order_item_id INTEGER       NULL REFERENCES order_item (order_item_id), -- add-on, e.g. extended warranty for this line
    fulfillment_warehouse_id INTEGER   NULL REFERENCES warehouse (warehouse_id),
    quantity            INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price          INTEGER       NOT NULL CHECK (unit_price >= 0),  -- in the order's currency
    original_unit_price INTEGER       NULL CHECK (original_unit_price >= 0), -- in the seller's currency, if different
    original_currency_code CHAR(3)    NULL REFERENCES currency (currency_code),
    fx_rate             REAL          NULL CHECK (fx_rate > 0),           -- captured when added
    discount_amount     INTEGER       NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount          INTEGER       NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total          INTEGER       NOT NULL,
    is_subscribe_save   INTEGER       NOT NULL DEFAULT 0 CHECK (is_subscribe_save IN (0,1)),
    is_gift             INTEGER       NOT NULL DEFAULT 0 CHECK (is_gift IN (0,1)),
    gift_message        VARCHAR(500)  NULL,
    gift_wrap           INTEGER       NOT NULL DEFAULT 0 CHECK (gift_wrap IN (0,1)),
    added_at            TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    removed_at          TEXT          NULL,
    loaded_at           TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (order_id, source_system_id)
        REFERENCES customer_order (order_id, source_system_id) ON DELETE CASCADE,
    UNIQUE (source_system_id, source_line_key),
    UNIQUE (order_id, line_number),
    CHECK (gift_message IS NULL OR is_gift),
    CHECK ((original_unit_price IS NULL) = (original_currency_code IS NULL)),
    CHECK (line_total = quantity * unit_price - discount_amount)
);
CREATE INDEX ix_order_item_product ON order_item (product_id);
CREATE INDEX ix_order_item_seller  ON order_item (seller_id);

-- ---------------------------------------------------------------------
-- applied_discount: every discount granted on an order (header level
-- when order_item_id is NULL, line level otherwise). Allows several
-- promotions per order or line, and captures manual discounts with no
-- promotion (BobsUncle 'manager override').
--
-- Lineage: source_system_id is the source of the order the discount was
-- loaded from. Composite FKs make the order and the promotion agree with
-- it, so an AcmeShopping order can never point at a BigRiver promotion.
-- source_field names where the discount came from, e.g.
--   ACME      "Order"."PromotionId", "OrderItem"."LineDiscount"
--   BIGRIVER  SHOPPING_CART.SC_CART_PRM_UUID, ITEM.ITM_PRM_UUID
--   BOBSUNCLE cart_item.disc_cents
-- ---------------------------------------------------------------------
CREATE TABLE applied_discount (
    applied_discount_id INTEGER       PRIMARY KEY,
    order_id            INTEGER       NOT NULL,
    source_system_id    INTEGER       NOT NULL,
    source_field        VARCHAR(60)   NULL,              -- source column the discount was derived from
    order_item_id       INTEGER       NULL REFERENCES order_item (order_item_id) ON DELETE CASCADE,
    promotion_id        INTEGER       NULL,
    discount_reason     VARCHAR(100)  NULL,              -- required when there is no promotion
    discount_amount     INTEGER       NOT NULL CHECK (discount_amount >= 0),
    applied_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    loaded_at           TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (order_id, source_system_id)
        REFERENCES customer_order (order_id, source_system_id) ON DELETE CASCADE,
    FOREIGN KEY (promotion_id, source_system_id)
        REFERENCES promotion (promotion_id, source_system_id),
    CHECK (promotion_id IS NOT NULL OR discount_reason IS NOT NULL)
);
CREATE INDEX ix_applied_discount_order     ON applied_discount (order_id);
CREATE INDEX ix_applied_discount_promotion ON applied_discount (promotion_id);

-- ---------------------------------------------------------------------
-- payment: money collected for an order. Only tokens and display data
-- are stored, never full card numbers.
-- ---------------------------------------------------------------------
CREATE TABLE payment (
    payment_id          INTEGER       PRIMARY KEY,
    order_id            INTEGER       NOT NULL REFERENCES customer_order (order_id),
    billing_address_id  INTEGER       NULL REFERENCES address (address_id),
    payment_method      VARCHAR(20)   NOT NULL,
    processor_name      VARCHAR(50)   NULL,
    processor_reference VARCHAR(100)  NULL,              -- gateway transaction / token id
    card_brand          VARCHAR(20)   NULL,
    card_last4          CHAR(4)       NULL,
    amount              INTEGER       NOT NULL CHECK (amount > 0),
    currency_code       CHAR(3)       NOT NULL REFERENCES currency (currency_code),
    payment_status      VARCHAR(20)   NOT NULL DEFAULT 'AUTHORIZED',
    authorized_at       TEXT          NULL,
    captured_at         TEXT          NULL,
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (payment_method IN ('CARD','PAYPAL','APPLE_PAY','GOOGLE_PAY','GIFT_CARD','STORE_CREDIT','CASH','BANK_TRANSFER')),
    CHECK (payment_status IN ('AUTHORIZED','CAPTURED','VOIDED','FAILED','REFUNDED','PARTIALLY_REFUNDED'))
);
CREATE INDEX ix_payment_order ON payment (order_id);

-- ---------------------------------------------------------------------
-- shipment / shipment_item: a package sent from one seller/warehouse.
-- A marketplace order can ship in several packages.
-- ---------------------------------------------------------------------
CREATE TABLE shipment (
    shipment_id         INTEGER       PRIMARY KEY,
    order_id            INTEGER       NOT NULL REFERENCES customer_order (order_id),
    seller_id           INTEGER       NOT NULL REFERENCES seller (seller_id),
    from_warehouse_id   INTEGER       NULL REFERENCES warehouse (warehouse_id),
    ship_to_address_id  INTEGER       NOT NULL REFERENCES address (address_id),
    carrier             VARCHAR(30)   NULL,              -- 'UPS','FEDEX','USPS'
    service_level       VARCHAR(30)   NULL,              -- 'GROUND','2DAY'
    tracking_number     VARCHAR(60)   NULL,
    shipping_cost       INTEGER       NULL CHECK (shipping_cost >= 0),
    shipment_status     VARCHAR(12)   NOT NULL DEFAULT 'PENDING',
    shipped_at          TEXT          NULL,
    delivered_at        TEXT          NULL,
    CHECK (shipment_status IN ('PENDING','PACKED','SHIPPED','IN_TRANSIT','DELIVERED','EXCEPTION','RETURNED'))
);
CREATE INDEX ix_shipment_order ON shipment (order_id);

CREATE TABLE shipment_item (
    shipment_id         INTEGER       NOT NULL REFERENCES shipment (shipment_id) ON DELETE CASCADE,
    order_item_id       INTEGER       NOT NULL REFERENCES order_item (order_item_id),
    quantity            INTEGER       NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (shipment_id, order_item_id)
);


-- =====================================================================
-- 7. RETURNS / RMA
-- =====================================================================

-- ---------------------------------------------------------------------
-- return_reason: controlled list of why items come back.
-- ---------------------------------------------------------------------
CREATE TABLE return_reason (
    return_reason_code  VARCHAR(20)   PRIMARY KEY,       -- 'DEFECTIVE','WRONG_ITEM','NO_LONGER_NEEDED'
    description         VARCHAR(200)  NOT NULL,
    is_seller_fault     INTEGER       NOT NULL DEFAULT 0 CHECK (is_seller_fault IN (0,1))  -- drives who pays return shipping
);

-- ---------------------------------------------------------------------
-- rma: Return Merchandise Authorization header.
-- ---------------------------------------------------------------------
CREATE TABLE rma (
    rma_id              INTEGER       PRIMARY KEY,
    rma_number          VARCHAR(20)   NOT NULL UNIQUE,   -- given to the customer
    order_id            INTEGER       NOT NULL REFERENCES customer_order (order_id),
    customer_id         INTEGER       NULL REFERENCES customer (customer_id),
    seller_id           INTEGER       NULL REFERENCES seller (seller_id),
    return_warehouse_id INTEGER       NULL REFERENCES warehouse (warehouse_id),
    return_from_address_id INTEGER     NULL REFERENCES address (address_id),
    rma_status          VARCHAR(20)   NOT NULL DEFAULT 'REQUESTED',
    return_carrier      VARCHAR(30)   NULL,
    return_tracking_number VARCHAR(60) NULL,
    customer_comment    VARCHAR(1000) NULL,
    requested_at        TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    approved_at         TEXT          NULL,
    received_at         TEXT          NULL,
    closed_at           TEXT          NULL,
    expires_at          TEXT          NULL,              -- authorization window
    CHECK (rma_status IN ('REQUESTED','APPROVED','REJECTED','IN_TRANSIT','RECEIVED',
                          'INSPECTED','COMPLETED','CANCELLED'))
);
CREATE INDEX ix_rma_order ON rma (order_id);

-- ---------------------------------------------------------------------
-- rma_item: which order lines (and how many units) are coming back,
-- why, what condition they arrived in, and how they were resolved.
-- ---------------------------------------------------------------------
CREATE TABLE rma_item (
    rma_item_id         INTEGER       PRIMARY KEY,
    rma_id              INTEGER       NOT NULL REFERENCES rma (rma_id) ON DELETE CASCADE,
    order_item_id       INTEGER       NOT NULL REFERENCES order_item (order_item_id),
    quantity            INTEGER       NOT NULL CHECK (quantity > 0),
    return_reason_code  VARCHAR(20)   NOT NULL REFERENCES return_reason (return_reason_code),
    requested_resolution VARCHAR(15)  NOT NULL DEFAULT 'REFUND',
    received_condition  VARCHAR(15)   NULL,
    disposition         VARCHAR(20)   NULL,
    restocking_fee      INTEGER       NOT NULL DEFAULT 0 CHECK (restocking_fee >= 0),
    replacement_order_id INTEGER       NULL REFERENCES customer_order (order_id),
    UNIQUE (rma_id, order_item_id),
    CHECK (requested_resolution IN ('REFUND','REPLACEMENT','EXCHANGE','STORE_CREDIT','REPAIR')),
    CHECK (received_condition IN ('NEW','OPENED','USED','DAMAGED','DEFECTIVE','MISSING_PARTS')),
    CHECK (disposition IN ('RESTOCK','REFURBISH','RETURN_TO_VENDOR','LIQUIDATE','SCRAP'))
);

-- ---------------------------------------------------------------------
-- refund: money returned to the customer, for an RMA or a cancellation.
-- ---------------------------------------------------------------------
CREATE TABLE refund (
    refund_id           INTEGER       PRIMARY KEY,
    order_id            INTEGER       NOT NULL REFERENCES customer_order (order_id),
    rma_id              INTEGER       NULL REFERENCES rma (rma_id),
    payment_id          INTEGER       NULL REFERENCES payment (payment_id),  -- NULL = store credit
    amount              INTEGER       NOT NULL CHECK (amount > 0),
    currency_code       CHAR(3)       NOT NULL REFERENCES currency (currency_code),
    refund_status       VARCHAR(12)   NOT NULL DEFAULT 'PENDING',
    processor_reference VARCHAR(100)  NULL,
    refunded_at         TEXT          NULL,
    created_at          TEXT          NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (refund_status IN ('PENDING','COMPLETED','FAILED'))
);
CREATE INDEX ix_refund_order ON refund (order_id);


-- =====================================================================
-- 8. SEED REFERENCE DATA
-- =====================================================================

INSERT INTO source_system (source_system_id, source_system_code, source_system_name) VALUES
    (0, 'CANONICAL', 'Created directly in the canonical model'),
    (1, 'ACME',      'AcmeShopping'),
    (2, 'BIGRIVER',  'BigRiver Marketplace'),
    (3, 'BOBSUNCLE', 'BobsUncle');

INSERT INTO currency (currency_code, currency_name, minor_unit_digits) VALUES
    ('USD', 'US Dollar',         2),
    ('CAD', 'Canadian Dollar',   2),
    ('EUR', 'Euro',              2),
    ('GBP', 'Pound Sterling',    2),
    ('JPY', 'Yen',               0),
    ('KRW', 'Won',               0),
    ('CNY', 'Yuan Renminbi',     2);

INSERT INTO country (country_code, country_name) VALUES
    ('US', 'United States'),
    ('CA', 'Canada'),
    ('MX', 'Mexico'),
    ('GB', 'United Kingdom'),
    ('DE', 'Germany'),
    ('FR', 'France'),
    ('JP', 'Japan'),
    ('KR', 'Korea, Republic of'),
    ('CN', 'China'),
    ('TW', 'Taiwan'),
    ('VN', 'Viet Nam');

INSERT INTO return_reason (return_reason_code, description, is_seller_fault) VALUES
    ('DEFECTIVE',         'Item is defective or does not work',   1),
    ('DAMAGED_IN_TRANSIT','Item arrived damaged',                 1),
    ('WRONG_ITEM',        'Wrong item was sent',                  1),
    ('NOT_AS_DESCRIBED',  'Item does not match description',      1),
    ('MISSING_PARTS',     'Parts or accessories missing',         1),
    ('NO_LONGER_NEEDED',  'Customer no longer needs the item',    0),
    ('BETTER_PRICE',      'Found a better price elsewhere',       0),
    ('ORDERED_BY_MISTAKE','Ordered by mistake',                   0);
