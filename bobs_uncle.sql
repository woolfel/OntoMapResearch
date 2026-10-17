-- =====================================================================
-- BobsUncle - Source Schema
-- Dialect: SQLite 3
--
-- Naming style: lower snake_case, heavy abbreviations (prod, mfr, qty, dt, cd).
-- Modeling habits (on purpose, for the lesson):
--   * Wide, denormalized tables: product carries barcodes, description and
--     every warranty detail; brand mixes manufacturer AND model info, so the
--     same manufacturer name repeats on every row.
--   * Natural keys: product is keyed by sku (text), not a surrogate id.
--   * Money is stored as INTEGER cents (1999 = $19.99).
--   * Some dates are stored as text in 'YYYYMMDD' format (legacy system).
--   * Flags are CHAR(1) 'Y'/'N' instead of booleans.
--   * Weak promotions: a promotion table exists, but discounts applied
--     on cart_item are just cents with a free-text reason, not linked
--     to a promotion row.
--   * Status codes are single letters: cart_stat 'O'=open, 'C'=checked out,
--     'A'=abandoned, 'X'=cancelled.
-- =====================================================================
--
-- SQLite notes: no BOOLEAN type (flags are INTEGER 0/1), timestamps and
-- dates are TEXT (CURRENT_TIMESTAMP = UTC 'YYYY-MM-DD HH:MM:SS'), and
-- VARCHAR/NUMERIC sizes are documentation only, not enforced.
-- Foreign keys are only enforced when PRAGMA foreign_keys = ON.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS promotion;
DROP TABLE IF EXISTS cart_item;
DROP TABLE IF EXISTS cart;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS brand;

-- ---------------------------------------------------------------------
-- brand: one row per manufacturer + model combination (wide)
-- ---------------------------------------------------------------------
CREATE TABLE brand (
    brand_id            INTEGER       PRIMARY KEY AUTOINCREMENT,
    mfr_cd              VARCHAR(10)   NOT NULL,      -- short code, e.g. 'SNY'
    mfr_nm              VARCHAR(120)  NOT NULL,      -- 'Sony', 'SONY Corp.', 'sony' (inconsistent!)
    mfr_hq_country      VARCHAR(60)   NULL,          -- free text: 'Japan', 'JP', 'Japan '
    mfr_contact_phone   VARCHAR(25)   NULL,          -- the phone number to display for warranty inquiries
    mfr_contact_email   VARCHAR(100)  NULL,          -- the email address to display for warranty inquiries
    mfr_website_url     VARCHAR(255)  NULL,          -- the website to display for warranty inquiries
    model_no            VARCHAR(40)   NOT NULL,      -- the model number for the product
    model_nm            VARCHAR(150)  NULL,          -- the model name to display on product page
    model_yr            SMALLINT      NULL,          -- the year the model was released
    avail_dt            VARCHAR(8)    NULL,          -- 'YYYYMMDD' text
    discontinue_dt      VARCHAR(8)    NULL,          -- 'YYYYMMDD' text, '' or NULL if still sold
    active_flg          CHAR(1)       NOT NULL DEFAULT 'Y',
    UNIQUE (mfr_cd, model_no)
);

-- ---------------------------------------------------------------------
-- product: wide table with identifiers, description and warranty
-- ---------------------------------------------------------------------
CREATE TABLE product (
    sku                 VARCHAR(20)   NOT NULL PRIMARY KEY,   -- 'BU-0004521'
    brand_id            INTEGER       NOT NULL REFERENCES brand (brand_id),
    upc_cd              VARCHAR(12)   NULL,          -- UPC-A
    ean_cd              VARCHAR(13)   NULL,          -- EAN-13
    gtin_cd             VARCHAR(14)   NULL,          -- GTIN-14
    short_desc          VARCHAR(80)   NOT NULL,
    long_desc           TEXT          NULL,
    dept_nm             VARCHAR(50)   NULL,          -- free-text category, e.g. 'TV & Video'
    color_desc          VARCHAR(30)   NULL,
    size_desc           VARCHAR(30)   NULL,
    wt_lbs              NUMERIC(7,2)  NULL,          -- imperial
    retail_price_cents  INTEGER       NOT NULL,
    cost_cents          INTEGER       NULL,
    taxable_flg         CHAR(1)       NOT NULL DEFAULT 'Y',
    warr_type           VARCHAR(20)   NULL,          -- 'MFR', 'EXTENDED', 'NONE'
    warr_months         SMALLINT      NULL,
    warr_provider       VARCHAR(100)  NULL,
    warr_parts_flg      CHAR(1)       NULL,
    warr_labor_flg      CHAR(1)       NULL,
    warr_terms_txt      TEXT          NULL,
    created_dt          TEXT          NOT NULL DEFAULT CURRENT_DATE,
    last_upd_ts         TEXT          NULL
);

-- ---------------------------------------------------------------------
-- inventory: stock per sku per warehouse
-- ---------------------------------------------------------------------
CREATE TABLE inventory (
    sku                 VARCHAR(20)   NOT NULL REFERENCES product (sku),
    whse_cd             VARCHAR(6)    NOT NULL,      -- 'NJ01', 'TX02'
    qty_on_hand         INTEGER       NOT NULL DEFAULT 0,
    qty_reserved        INTEGER       NOT NULL DEFAULT 0,
    qty_on_order        INTEGER       NOT NULL DEFAULT 0,
    reorder_pt          INTEGER       NULL,
    bin_loc             VARCHAR(15)   NULL,
    last_cnt_dt         VARCHAR(8)    NULL,          -- 'YYYYMMDD' text
    PRIMARY KEY (sku, whse_cd)
);

-- ---------------------------------------------------------------------
-- cart: one row per shopping cart (open, checked out, or abandoned)
-- ---------------------------------------------------------------------
CREATE TABLE cart (
    cart_no             VARCHAR(16)   NOT NULL PRIMARY KEY,   -- 'C26100500012'
    cust_ref            VARCHAR(40)   NULL,          -- loyalty #, email, or NULL for guest
    guest_flg           CHAR(1)       NOT NULL DEFAULT 'N',
    cart_stat           CHAR(1)       NOT NULL,      -- the status of the cart: 'O'=open, 'C'=checked out, 'A'=abandoned, 'X'=cancelled
    created_ts          TEXT          NOT NULL,      -- local store time (US/Central), no tz
    checkout_ts         TEXT          NULL,          -- timestamp of when cart checked out, NULL if still open
    channel_cd          VARCHAR(5)    NULL,          -- 'WEB', 'APP', 'POS'
    ship_zip            VARCHAR(10)   NULL,          -- shipping postal code in US, since international is not supported
    tax_cents           INTEGER       NULL,
    ship_cents          INTEGER       NULL,
    total_cents         INTEGER       NULL           -- only populated once checked out
);

-- ---------------------------------------------------------------------
-- cart_item: line items in a cart
-- ---------------------------------------------------------------------
CREATE TABLE cart_item (
    cart_no             VARCHAR(16)   NOT NULL REFERENCES cart (cart_no),
    line_seq            SMALLINT      NOT NULL,
    sku                 VARCHAR(20)   NOT NULL REFERENCES product (sku),
    qty                 SMALLINT      NOT NULL,      -- can be negative for returns!
    unit_price_cents    INTEGER       NOT NULL,
    disc_cents          INTEGER       NOT NULL DEFAULT 0,
    disc_reason         VARCHAR(60)   NULL,          -- free text: 'BF SALE', 'manager override', 'coupon 10OFF'
    ext_warr_sku        VARCHAR(20)   NULL,          -- add-on extended warranty sold with this line
    fulfil_whse_cd      VARCHAR(6)    NULL,
    added_ts            TEXT          NOT NULL,
    removed_flg         CHAR(1)       NOT NULL DEFAULT 'N',  -- soft delete: item taken out of cart
    PRIMARY KEY (cart_no, line_seq)
);

-- ---------------------------------------------------------------------
-- promotion: promotion and discounts
-- ---------------------------------------------------------------------
CREATE TABLE promotion (
    promo_id            INTEGER       PRIMARY KEY AUTOINCREMENT,
    promo_cd            VARCHAR(25)   NULL UNIQUE,   -- 'BF2023', '10OFF', NULL for automatic deals
    promo_desc          VARCHAR(150)  NOT NULL,
    funded_by           VARCHAR(10)   NOT NULL,      -- 'RETAILER' (BobsUncle) or 'MFR' (manufacturer co-op)
    mfr_cd              VARCHAR(10)   NULL,          -- set when manufacturer-funded, e.g. 'SNY' (matches brand.mfr_cd)
    scope               VARCHAR(12)   NOT NULL,      -- 'SITEWIDE','PRODUCT','DEPT','CART'
    discount_pct        DECIMAL(5,2)  NULL,          -- 15.00 means 15%
    discount_cents      INTEGER       NULL,          -- flat amount off, in cents
    min_order_cents     INTEGER       NULL,
    effective_dt        TEXT          NOT NULL,
    expiration_dt       TEXT          NULL,          -- NULL = open-ended
    active_flg          CHAR(1)       NOT NULL DEFAULT 'Y',
    stackable_flg       CHAR(1)       NOT NULL DEFAULT 'N'
);