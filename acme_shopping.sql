-- =====================================================================
-- AcmeShopping - Source Schema
-- Dialect: SQLite 3
--
-- Naming style: Quoted PascalCase, "Id" suffix on keys, full words.
-- Modeling habits (on purpose, for the lesson):
--   * Fairly normalized: Brand -> Model, with Model linked to a category tree.
--   * Money is stored as NUMERIC dollars (e.g. 19.99).
--   * Discount percentages are stored as whole numbers (15.00 = 15%).
--   * Promotions can be event-based (Black Friday) or tied to a specific
--     model, brand, or category, and OrderItem records which promo was applied.
--   * "Order" is a reserved word, so it must always be quoted.
--   * Money is NUMERIC affinity in SQLite, so 19.99 is stored as a
--     floating-point REAL -- another legacy habit to clean up in ETL.
-- =====================================================================
--
-- SQLite notes: no BOOLEAN type (flags are INTEGER 0/1), timestamps and
-- dates are TEXT (CURRENT_TIMESTAMP = UTC 'YYYY-MM-DD HH:MM:SS'), and
-- VARCHAR/NUMERIC sizes are documentation only, not enforced.
-- Foreign keys are only enforced when PRAGMA foreign_keys = ON.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS "OrderItem";
DROP TABLE IF EXISTS "Order";
DROP TABLE IF EXISTS "Promotions";
DROP TABLE IF EXISTS "Model";
DROP TABLE IF EXISTS "Brand";
DROP TABLE IF EXISTS "CatalogCategory";

-- ---------------------------------------------------------------------
-- CatalogCategory: self-referencing hierarchy (Electronics > TVs > OLED)
-- ---------------------------------------------------------------------
CREATE TABLE "CatalogCategory" (
    "CategoryId"        INTEGER       PRIMARY KEY,
    "ParentCategoryId"  INTEGER       NULL REFERENCES "CatalogCategory" ("CategoryId"),
    "CategoryName"      VARCHAR(200)  NULL,     -- e.g. 'OLED'
    "CategoryLongDesc"  VARCHAR(500)  NULL,
    "CategoryShortDesc" VARCHAR(200)  NULL,
    "SortOrder"         SMALLINT      NOT NULL DEFAULT 0,
    "IsActive"          INTEGER       NOT NULL DEFAULT 1, -- active is used to phase in category and retire old categories
    "EffectiveDate"     TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP, -- the timestamp of when the record became effective
    "CreatedDate"       TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP, -- the timestamp of when the record was created
    "LastUpdate"       TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP -- the timestamp of when the record was last updated
);

-- ---------------------------------------------------------------------
-- Brand: the manufacturer
-- ---------------------------------------------------------------------
CREATE TABLE "Brand" (
    "BrandId"           INTEGER       PRIMARY KEY,
    "BrandName"         VARCHAR(100)  NOT NULL UNIQUE, -- example, Apple, Sony, Samsung, LG
    "ManufacturerName"  VARCHAR(150)  NULL,          -- legal name, may differ from BrandName
    "CountryOfOrigin"   CHAR(2)       NULL,          -- ISO 3166 alpha-2
    "WebsiteUrl"        VARCHAR(255)  NULL,         -- example, https://www.sony.com
    "IsActive"          INTEGER       NOT NULL DEFAULT 1,
    "CreatedDate"       TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP, -- the timestamp of when the record was created
    "LastUpdate"        TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Model: the sellable product (Acme calls a product a "Model")
-- ---------------------------------------------------------------------
CREATE TABLE "Model" (
    "ModelId"           INTEGER       PRIMARY KEY,
    "BrandId"           INTEGER       NOT NULL REFERENCES "Brand" ("BrandId"),
    "CategoryId"        INTEGER       NOT NULL REFERENCES "CatalogCategory" ("CategoryId"),
    "ModelNumber"       VARCHAR(50)   NOT NULL,      -- manufacturer's model number
    "ModelName"         VARCHAR(200)  NOT NULL,      -- the name to display on a page
    "Sku"               VARCHAR(30)   NOT NULL UNIQUE,  -- not all products will have a SKU
    "UpcCode"           VARCHAR(14)   NULL,          -- UPC barcode should be on most products
    "MSRP"              NUMERIC(10,2) NOT NULL,      -- dollars
    "CurrencyCode"      VARCHAR(3)    NOT NULL DEFAULT 'USD',
    "WeightLbs"         NUMERIC(8,3)  NULL,          -- metric
    "ReleaseDate"       TEXT          NULL,
    "EffectiveDate"     TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP, -- the timestamp of when the record became effective
    "ExpirationDate"    TEXT          NULL,          -- the timestamp of when the record is no longer effective
    "CreatedDate"       TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP, -- the timestamp of when the record was created
    "LastUpdate"        TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "IsDiscontinued"    INTEGER       NOT NULL DEFAULT 0,
    UNIQUE ("BrandId", "ModelNumber")
);

-- ---------------------------------------------------------------------
-- Promotions: event-based or product-specific discounts
--   PromotionType: 'EVENT', 'MODEL', 'BRAND', 'CATEGORY', 'ORDER'
--   Exactly one of the "Applies..." columns is usually filled in
--   (none of them for EVENT/ORDER-wide promos).
-- ---------------------------------------------------------------------
CREATE TABLE "Promotions" (
    "PromotionId"           INTEGER       PRIMARY KEY,
    "PromotionCode"         VARCHAR(30)   NULL UNIQUE,  -- NULL = applied automatically
    "PromotionName"         VARCHAR(150)  NOT NULL,
    "PromotionType"         VARCHAR(20)   NOT NULL,
    "EventName"             VARCHAR(100)  NULL,          -- 'Black Friday', 'Back to School'
    "AppliesToModelId"      INTEGER       NULL REFERENCES "Model" ("ModelId"),
    "AppliesToBrandId"      INTEGER       NULL REFERENCES "Brand" ("BrandId"),
    "AppliesToCategoryId"   INTEGER       NULL REFERENCES "CatalogCategory" ("CategoryId"),
    "DiscountPercent"       NUMERIC(5,2)  NULL,          -- 15.00 means 15%
    "DiscountAmount"        NUMERIC(10,2) NULL,          -- flat dollars off
    "MinimumOrderAmount"    NUMERIC(10,2) NULL,
    "AssociatedCompany"     VARCHAR(100)  NULL,          -- if the promotion is associated with external company
    "EffectiveDate"         TEXT          NOT NULL DEFAULT CURRENT_TIMESTAMP, -- when the promotion is effective
    "ExpirationDate"        TEXT          NULL,          -- NULL = open-ended
    "IsActive"              INTEGER       NOT NULL DEFAULT 1,
    "IsStackable"           INTEGER       NOT NULL DEFAULT 0,
    CHECK ("PromotionType" IN ('EVENT','MODEL','BRAND','CATEGORY','ORDER'))
);

-- ---------------------------------------------------------------------
-- Order: header for a completed checkout
-- ---------------------------------------------------------------------
CREATE TABLE "Order" (
    "OrderId"               INTEGER       PRIMARY KEY,
    "OrderNumber"           VARCHAR(20)   NOT NULL UNIQUE,  -- A human readable order number they can use with customer service
    "CustomerId"            INTEGER       NULL, -- a customer can checkout without creating account
    "CustomerEmail"         VARCHAR(255)  NOT NULL,         -- email of the customer that made the order
    "OrderDate"             TEXT          NOT NULL,         -- stored in UTC
    "OrderStatus"           VARCHAR(20)   NOT NULL,         -- 'Pending','Shipped','Delivered','Cancelled','Returned'
    "PromotionId"      INTEGER       NULL REFERENCES "Promotions" ("PromotionId"), -- this means order can only have 1 promotion and doesn't allow multiple on a single order
    "SubTotal"              NUMERIC(12,2) NOT NULL,         -- sum of all OrderItem.LineTotal
    "DiscountTotal"         NUMERIC(12,2) NOT NULL DEFAULT 0, -- the total of all discounts applied
    "TaxTotal"              NUMERIC(12,2) NOT NULL DEFAULT 0,
    "ShippingTotal"         NUMERIC(12,2) NOT NULL DEFAULT 0,
    "GrandTotal"            NUMERIC(12,2) NOT NULL,
    "CurrencyCode"          CHAR(3)       NOT NULL DEFAULT 'USD',
    "ShipToPostalCode"      VARCHAR(10)   NULL,             -- the zip code of the shipping address
    "ShipToCountry"         CHAR(2)       NULL
);

-- ---------------------------------------------------------------------
-- OrderItem: one row per model purchased in an order
-- ---------------------------------------------------------------------
CREATE TABLE "OrderItem" (
    "OrderItemId"           INTEGER       PRIMARY KEY,
    "OrderId"               INTEGER       NOT NULL REFERENCES "Order" ("OrderId"),
    "LineNumber"            SMALLINT      NOT NULL,
    "ModelId"               INTEGER       NOT NULL REFERENCES "Model" ("ModelId"),
    "Quantity"              INTEGER       NOT NULL CHECK ("Quantity" > 0),
    "UnitPrice"             NUMERIC(10,2) NOT NULL,      -- price at time of sale
    "LineDiscount"          NUMERIC(10,2) NOT NULL DEFAULT 0,  -- if promotion was applied to the item, the discount amount
    "LineTotal"             NUMERIC(12,2) NOT NULL,      -- (Quantity * UnitPrice) - LineDiscount
    "IsGift"                INTEGER       NOT NULL DEFAULT 0,  -- 0 = no, 1 = yes
    "GiftMessage"           VARCHAR(500)  NULL,          -- the message to print for the gift
    "GiftWrap"              INTEGER       NOT NULL DEFAULT 0,  -- if the item should be gift wrapped 0 = no, 1 = yes
    UNIQUE ("OrderId", "LineNumber")
);
