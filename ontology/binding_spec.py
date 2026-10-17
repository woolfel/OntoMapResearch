"""Bindings from the core concepts to each store's database.

This is the source for the per-source part of commerce_binding.ttl. A
binding says, for one source system:

  ConceptBinding   which rows of which table are instances of a core class
                   (table + key columns + optional row filter)
  AttributeBinding which column or SQL expression gives a datatype
                   property, in which value format
  RelationBinding  how a row links to another bound concept (foreign key,
                   expression, many-to-many table, or a lookup by natural
                   key such as an ISO country code)
  ValueBinding     how a source code maps onto a core code-list individual

Expressions are SQLite and are written relative to the binding's table,
so `SELECT <expression> FROM <table> WHERE <filter>` is always valid.
build_ontologies.py runs exactly that against each schema to prove every
column and expression exists.

To bind a new store: add a Source(...) to SOURCES. Nothing in the core
ontology changes.
"""
from dataclasses import dataclass, field
from typing import Optional, Union


# ---------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------

@dataclass
class C:
    """A column, read in a value format."""
    column: str
    fmt: str = 'Text'


@dataclass
class E:
    """A SQL expression over the binding's table, read in a value format."""
    sql: str
    fmt: str = 'Text'


@dataclass
class K:
    """A constant (literal for attributes, key value for relations)."""
    value: Union[str, int, bool]


Source_ = Union[str, C, E, K]


@dataclass
class Rel:
    """Object property to another concept binding of the same source.
    `via` lists columns/expressions matched positionally to the target
    binding's key."""
    target: str
    via: list


@dataclass
class Ref:
    """Object property resolved by a natural key of the range class,
    e.g. a Country by its cc:countryCode."""
    match_on: str
    value: Source_


@dataclass
class Through:
    """Object property through a many-to-many table."""
    table: str
    subject_columns: list
    object_columns: list
    target: str
    filter: Optional[str] = None


@dataclass
class V:
    """Code value mapped to a code-list individual. `mapping` is a dict
    source value -> core notation, or 'notation' when the source already
    uses the core codes."""
    value: Source_
    mapping: Union[dict, str] = 'notation'


@dataclass
class Concept:
    cls: str
    table: Optional[str]                  # None = virtual (one implied row)
    key: list
    id: Optional[str] = None              # defaults to cls
    filter: Optional[str] = None
    note: str = ''
    attrs: dict = field(default_factory=dict)
    rels: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)

    def __post_init__(self):
        self.id = self.id or self.cls


@dataclass
class Source:
    code: str
    name: str
    schema: str
    sample_db: Optional[str]
    note: str
    concepts: list


# ---------------------------------------------------------------------
# Value formats: how a source stores a value, the SQLite template that
# converts it to the core convention, and the inverse template that
# converts a core value back into the format ({v} = column or expression).
# ---------------------------------------------------------------------
FORMATS = {
    'Text': ('Text', 'Text, used as is.',
        '{v}',
        '{v}'),
    'TrimmedText': ('Trimmed text', 'Free text; trim and treat empty as missing.',
        "nullif(trim({v}), '')",
        '{v}'),
    'Integer': ('Integer', 'Whole number.',
        'CAST({v} AS INTEGER)',
        'CAST({v} AS INTEGER)'),
    'Decimal': ('Decimal', 'Decimal number, used as is.',
        '{v}',
        '{v}'),
    'MoneyMajor': ('Money, major units', 'Amount in major currency units (19.99).',
        '{v}',
        'ROUND({v}, 2)'),
    'MoneyMinor': ('Money, minor units', 'Amount in minor units (1999 = 19.99). Divide by 10^minorUnitDigits of the currency; 100 for USD/CAD/EUR/GBP.',
        '{v} / 100.0',
        'CAST(ROUND({v} * 100) AS INTEGER)'),
    'PercentWhole': ('Percent, whole number', '15.00 means 15%.',
        '{v} / 100.0',
        '{v} * 100.0'),
    'PercentFraction': ('Percent, fraction', '0.15 means 15%.',
        '{v}',
        '{v}'),
    'TimestampUTC': ('Timestamp UTC text', "UTC 'YYYY-MM-DD HH:MM:SS'.",
        "strftime('%Y-%m-%dT%H:%M:%SZ', {v})",
        "strftime('%Y-%m-%d %H:%M:%S', {v})"),
    'TimestampUTCOpenEnded': ('Timestamp UTC, open-ended sentinel', "UTC 'YYYY-MM-DD HH:MM:SS'; '9999-12-31 23:59:59' means no end.",
        "strftime('%Y-%m-%dT%H:%M:%SZ', nullif({v}, '9999-12-31 23:59:59'))",
        "coalesce(strftime('%Y-%m-%d %H:%M:%S', {v}), '9999-12-31 23:59:59')"),
    'TimestampISO': ('Timestamp ISO-8601 UTC', "UTC 'YYYY-MM-DDTHH:MM:SS.SSSZ', already canonical.",
        '{v}',
        "strftime('%Y-%m-%dT%H:%M:%fZ', {v})"),
    'TimestampLocalUSCentral': ('Timestamp, US/Central local', "Local store time 'YYYY-MM-DD HH:MM:SS' with no zone. Convert from America/Chicago to UTC in the ETL tool; SQLite has no time-zone database.",
        '/* America/Chicago -> UTC */ {v}',
        "/* UTC -> America/Chicago */ strftime('%Y-%m-%d %H:%M:%S', {v})"),
    'DateISO': ('Date ISO', "'YYYY-MM-DD'.",
        'date({v})',
        'date({v})'),
    'DateYYYYMMDD': ('Date text YYYYMMDD', "Legacy 'YYYYMMDD' text; '' or NULL means none.",
        "date(substr({v},1,4)||'-'||substr({v},5,2)||'-'||substr({v},7,2))",
        "strftime('%Y%m%d', {v})"),
    'FlagYN': ('Flag Y/N', "'Y' or 'N'.",
        "CASE upper({v}) WHEN 'Y' THEN 1 WHEN 'N' THEN 0 END",
        "CASE WHEN {v} THEN 'Y' ELSE 'N' END"),
    'Flag01': ('Flag 0/1', 'INTEGER 0 or 1.',
        '{v}',
        'CASE WHEN {v} THEN 1 ELSE 0 END'),
    'WeightPounds': ('Weight, pounds', 'Pounds; convert to grams.',
        'CAST(ROUND({v} * 453.59237) AS INTEGER)',
        'ROUND({v} / 453.59237, 2)'),
    'WeightGrams': ('Weight, grams', 'Grams.',
        '{v}',
        'CAST(ROUND({v}) AS INTEGER)'),
    'Email': ('Email', 'Email address; compare lower-case.',
        'lower(trim({v}))',
        'lower({v})'),
    'CountryAlpha2': ('Country ISO alpha-2', 'ISO 3166-1 alpha-2 code.',
        'upper(trim({v}))',
        '{v}'),
    'CountryFreeText': ('Country free text', "Names or codes typed by hand ('USA', 'United States ', 'JP'); resolve to ISO alpha-2 through cc:countryName/cc:countryCode.",
        'trim({v})',
        '{v}'),
    'CurrencyCode': ('Currency ISO 4217', 'ISO 4217 code.',
        'upper(trim({v}))',
        '{v}'),
    'RegionCode': ('Region ISO 3166-2', "e.g. 'US-NJ'.",
        'upper(trim({v}))',
        '{v}'),
    'BrandFreeText': ('Brand free text', "Brand typed by people ('Sony', 'SONY', 'Sony Electronics'); normalise and resolve aliases before matching cc:brandName.",
        'trim({v})',
        '{v}'),
    'BrowsePath': ('Browse path', "'garden>watering-irrigation': the whole path is the category code; the last segment is the name; the path without it is the parent.",
        '{v}',
        '{v}'),
    'Code': ('Code', 'A source code mapped through a value map.',
        '{v}',
        '{v}'),
}

UPPER_BRAND = 'upper(trim(PRD_BRAND_TEXT))'

# ---------------------------------------------------------------------
# AcmeShopping
# ---------------------------------------------------------------------
ACME = Source(
    code='acme', name='AcmeShopping', schema='acme_shopping.sql', sample_db='acme_data/acme.db',
    note='Single-retailer web store (garden, home improvement, DIY tools). Money in NUMERIC dollars, '
         'percent as whole numbers, timestamps UTC text.',
    concepts=[
        Concept('Seller', None, [K('acme-shopping')], note='AcmeShopping is its own (only) seller.',
                attrs={'sellerHandle': K('acme-shopping'), 'sellerName': K('AcmeShopping'),
                       'isFirstParty': K(True)}),
        Concept('Category', 'CatalogCategory', ['CategoryId'],
                attrs={'categoryName': C('CategoryName', 'TrimmedText'),
                       'categoryDescription': C('CategoryLongDesc', 'TrimmedText'),
                       'sortOrder': C('SortOrder', 'Integer'), 'isActive': C('IsActive', 'Flag01'),
                       'effectiveFrom': C('EffectiveDate', 'TimestampUTC'),
                       'createdAt': C('CreatedDate', 'TimestampUTC'), 'updatedAt': C('LastUpdate', 'TimestampUTC')},
                rels={'parentCategory': Rel('Category', ['ParentCategoryId'])}),
        Concept('Manufacturer', 'Brand', ['ManufacturerName'], filter='ManufacturerName IS NOT NULL',
                note='Acme stores the manufacturer as a column of Brand; one instance per distinct name.',
                attrs={'manufacturerName': C('ManufacturerName', 'TrimmedText')}),
        Concept('Brand', 'Brand', ['BrandId'],
                attrs={'brandName': C('BrandName', 'TrimmedText'), 'websiteUrl': C('WebsiteUrl'),
                       'isActive': C('IsActive', 'Flag01'), 'createdAt': C('CreatedDate', 'TimestampUTC'),
                       'updatedAt': C('LastUpdate', 'TimestampUTC')},
                rels={'ownedBy': Rel('Manufacturer', ['ManufacturerName']),
                      'countryOfOrigin': Ref('countryCode', C('CountryOfOrigin', 'CountryAlpha2'))}),
        Concept('ProductModel', 'Model', ['ModelId'],
                note='Acme has no separate model table: each Model row is both a product and its model.',
                attrs={'modelNumber': C('ModelNumber', 'TrimmedText'), 'modelName': C('ModelName', 'TrimmedText'),
                       'modelYear': E("strftime('%Y', ReleaseDate)", 'Integer'),
                       'releaseDate': C('ReleaseDate', 'DateISO'),
                       'discontinuedDate': E('CASE WHEN IsDiscontinued THEN coalesce(ExpirationDate, LastUpdate) END',
                                             'DateISO')},
                rels={'ofBrand': Rel('Brand', ['BrandId'])}),
        Concept('Product', 'Model', ['ModelId'], note="Acme calls a product a 'Model'.",
                attrs={'sku': C('Sku'), 'upc': C('UpcCode'), 'productName': C('ModelName', 'TrimmedText'),
                       'weightInGrams': C('WeightLbs', 'WeightPounds'), 'msrp': C('MSRP', 'MoneyMajor'),
                       'isActive': E('NOT IsDiscontinued', 'Flag01'),
                       'effectiveFrom': C('EffectiveDate', 'TimestampUTC'),
                       'effectiveUntil': C('ExpirationDate', 'TimestampUTC'),
                       'createdAt': C('CreatedDate', 'TimestampUTC'), 'updatedAt': C('LastUpdate', 'TimestampUTC')},
                rels={'hasModel': Rel('ProductModel', ['ModelId']), 'hasBrand': Rel('Brand', ['BrandId']),
                      'inCategory': Rel('Category', ['CategoryId']),
                      'hasCurrency': Ref('currencyCode', C('CurrencyCode', 'CurrencyCode'))}),
        Concept('Offer', 'Model', ['ModelId'], note='List price of the single seller = MSRP.',
                attrs={'price': C('MSRP', 'MoneyMajor'), 'effectiveFrom': C('EffectiveDate', 'TimestampUTC'),
                       'effectiveUntil': C('ExpirationDate', 'TimestampUTC')},
                rels={'offeredBy': Rel('Seller', [K('acme-shopping')]), 'offerFor': Rel('Product', ['ModelId']),
                      'hasCurrency': Ref('currencyCode', C('CurrencyCode', 'CurrencyCode'))},
                values={'itemCondition': V(K('NEW'))}),
        Concept('Promotion', 'Promotions', ['PromotionId'],
                attrs={'promotionCode': C('PromotionCode'), 'promotionName': C('PromotionName', 'TrimmedText'),
                       'eventName': C('EventName', 'TrimmedText'), 'partnerCompany': C('AssociatedCompany', 'TrimmedText'),
                       'discountPercent': C('DiscountPercent', 'PercentWhole'),
                       'amountOff': C('DiscountAmount', 'MoneyMajor'),
                       'minimumOrderAmount': C('MinimumOrderAmount', 'MoneyMajor'),
                       'effectiveFrom': C('EffectiveDate', 'TimestampUTC'),
                       'effectiveUntil': C('ExpirationDate', 'TimestampUTC'),
                       'isActive': C('IsActive', 'Flag01'), 'isStackable': C('IsStackable', 'Flag01')},
                rels={'appliesToProduct': Rel('Product', ['AppliesToModelId']),
                      'appliesToBrand': Rel('Brand', ['AppliesToBrandId']),
                      'appliesToCategory': Rel('Category', ['AppliesToCategoryId']),
                      'hasCurrency': Ref('currencyCode', K('USD'))},
                values={'promotionScope': V(C('PromotionType', 'Code'),
                                            {'EVENT': 'SITEWIDE', 'ORDER': 'ORDER', 'MODEL': 'ITEM',
                                             'BRAND': 'ITEM', 'CATEGORY': 'ITEM'}),
                        'fundedBy': V(E("CASE WHEN AssociatedCompany IS NOT NULL THEN 'PARTNER' ELSE 'PLATFORM' END",
                                        'Code'))}),
        Concept('Customer', 'Order', ['CustomerId'], filter='CustomerId IS NOT NULL',
                note='Acme has no customer table; customers are known only from their orders.',
                attrs={'customerNumber': C('CustomerId'), 'email': C('CustomerEmail', 'Email')}),
        Concept('Address', 'Order', ['OrderId'], id='ShipToAddress',
                filter='ShipToPostalCode IS NOT NULL OR ShipToCountry IS NOT NULL',
                note='Partial ship-to address held on the order.',
                attrs={'postalCode': C('ShipToPostalCode', 'TrimmedText')},
                rels={'addressCountry': Ref('countryCode', C('ShipToCountry', 'CountryAlpha2'))}),
        Concept('Order', 'Order', ['OrderId'], note='Acme records only completed checkouts.',
                attrs={'orderNumber': C('OrderNumber'), 'customerEmail': C('CustomerEmail', 'Email'),
                       'createdAt': C('OrderDate', 'TimestampUTC'), 'placedAt': C('OrderDate', 'TimestampUTC'),
                       'subtotalAmount': C('SubTotal', 'MoneyMajor'), 'discountTotal': C('DiscountTotal', 'MoneyMajor'),
                       'taxTotal': C('TaxTotal', 'MoneyMajor'), 'shippingTotal': C('ShippingTotal', 'MoneyMajor'),
                       'grandTotal': C('GrandTotal', 'MoneyMajor')},
                rels={'placedBy': Rel('Customer', ['CustomerId']), 'shippingAddress': Rel('ShipToAddress', ['OrderId']),
                      'hasCurrency': Ref('currencyCode', C('CurrencyCode', 'CurrencyCode'))},
                values={'orderStatus': V(C('OrderStatus', 'Code'),
                                         {'Pending': 'PLACED', 'Shipped': 'SHIPPED', 'Delivered': 'DELIVERED',
                                          'Cancelled': 'CANCELLED', 'Returned': 'RETURNED'}),
                        'salesChannel': V(K('WEB'))}),
        Concept('OrderLine', 'OrderItem', ['OrderItemId'],
                attrs={'lineNumber': C('LineNumber', 'Integer'), 'quantity': C('Quantity', 'Integer'),
                       'unitPrice': C('UnitPrice', 'MoneyMajor'), 'lineDiscount': C('LineDiscount', 'MoneyMajor'),
                       'lineTotal': C('LineTotal', 'MoneyMajor'), 'isGift': C('IsGift', 'Flag01'),
                       'giftMessage': C('GiftMessage', 'TrimmedText'), 'giftWrap': C('GiftWrap', 'Flag01')},
                rels={'lineOf': Rel('Order', ['OrderId']), 'ofProduct': Rel('Product', ['ModelId']),
                      'soldBy': Rel('Seller', [K('acme-shopping')])}),
        Concept('AppliedDiscount', 'OrderItem', ['OrderItemId'], id='LineDiscount', filter='LineDiscount > 0',
                note="Line discount; its promotion is the order's PromotionId.",
                attrs={'discountAmount': C('LineDiscount', 'MoneyMajor')},
                rels={'appliedToLine': Rel('OrderLine', ['OrderItemId']), 'appliedToOrder': Rel('Order', ['OrderId']),
                      'fromPromotion': Rel('Promotion', [E('(SELECT o.PromotionId FROM "Order" o '
                                                           'WHERE o.OrderId = OrderItem.OrderId)')])}),
        Concept('AppliedDiscount', 'Order', ['OrderId'], id='OrderDiscount',
                filter='PromotionId IS NOT NULL AND DiscountTotal > (SELECT coalesce(sum(i.LineDiscount), 0) '
                       'FROM OrderItem i WHERE i.OrderId = "Order".OrderId)',
                note='Order-level discount = order discount total minus line discounts.',
                attrs={'discountAmount': E('DiscountTotal - (SELECT coalesce(sum(i.LineDiscount), 0) '
                                           'FROM OrderItem i WHERE i.OrderId = "Order".OrderId)', 'MoneyMajor')},
                rels={'appliedToOrder': Rel('Order', ['OrderId']), 'fromPromotion': Rel('Promotion', ['PromotionId'])}),
    ])

# ---------------------------------------------------------------------
# BigRiver
# ---------------------------------------------------------------------
BIGRIVER = Source(
    code='bigriver', name='BigRiver', schema='big_river.sql', sample_db='big_river/big_river.db',
    note='Marketplace with third-party stores. UUID keys, multi-currency, percent as fractions, '
         'timestamps UTC text, brand as free text, attributes as key/value tags.',
    concepts=[
        Concept('Seller', 'STORE', ['STR_UUID'],
                attrs={'sellerHandle': C('STR_HANDLE'), 'sellerName': C('STR_DISPLAY_NAME', 'TrimmedText'),
                       'isFirstParty': C('STR_IS_FIRST_PARTY', 'Flag01'), 'sellerRating': C('STR_RATING', 'Decimal'),
                       'shipsFromRegion': C('STR_DRP_SHP_REGION', 'RegionCode'),
                       'fulfilledByPlatform': C('STR_FBBR', 'Flag01'),
                       'onboardedAt': C('STR_ONBOARDED_DATE', 'TimestampUTC'),
                       'effectiveFrom': C('STR_EFF_DATE', 'TimestampUTC'),
                       'effectiveUntil': C('STR_EXP_DATE', 'TimestampUTC')},
                rels={'sellerCountry': Ref('countryCode', C('STR_COUNTRY_ISO', 'CountryAlpha2')),
                      'defaultCurrency': Ref('currencyCode', C('STR_DEFAULT_CCY', 'CurrencyCode'))},
                values={'sellerStatus': V(C('STR_STATUS', 'Code'))}),
        Concept('Brand', 'PRODUCT', [E(UPPER_BRAND)], filter='PRD_BRAND_TEXT IS NOT NULL',
                note='No brand table: one brand per distinct seller-typed spelling; aliases must be resolved.',
                attrs={'brandName': C('PRD_BRAND_TEXT', 'BrandFreeText')}),
        Concept('ProductModel', 'PRODUCT', [E(UPPER_BRAND), 'PRD_MFR_PART_NO'],
                filter='PRD_MFR_PART_NO IS NOT NULL', note='Model implied by brand + manufacturer part number.',
                attrs={'modelNumber': C('PRD_MFR_PART_NO', 'TrimmedText')},
                rels={'ofBrand': Rel('Brand', [E(UPPER_BRAND)])}),
        Concept('Category', 'PRODUCT', ['PRD_BROWSE_PATH'], filter='PRD_BROWSE_PATH IS NOT NULL',
                note='Categories exist only as browse paths on products. Parent paths may have no '
                     'product of their own.',
                attrs={'categoryCode': C('PRD_BROWSE_PATH', 'BrowsePath'),
                       'categoryName': E("replace(PRD_BROWSE_PATH, rtrim(PRD_BROWSE_PATH, "
                                         "replace(PRD_BROWSE_PATH, '>', '')), '')", 'TrimmedText')},
                rels={'parentCategory': Rel('Category', [E("nullif(rtrim(rtrim(PRD_BROWSE_PATH, "
                                                           "replace(PRD_BROWSE_PATH, '>', '')), '>'), '')")])}),
        Concept('Product', 'PRODUCT', ['PRD_UUID'],
                note='Duplicate listings of one product (same UPC, different PRD_ID) are separate rows.',
                attrs={'marketplaceProductId': C('PRD_ID'), 'productName': C('PRD_NAME', 'TrimmedText'),
                       'productLongName': C('PRD_LONG_NAME', 'TrimmedText'),
                       'upc': E('CASE WHEN length(PRD_UPC) = 12 THEN PRD_UPC END'),
                       'ean': E('CASE WHEN length(PRD_UPC) = 13 THEN PRD_UPC END'),
                       'gtin': E('CASE WHEN length(PRD_UPC) = 14 THEN PRD_UPC END'),
                       'weightInGrams': C('PRD_WEIGHT_GRAMS', 'WeightGrams'),
                       'isAdultOnly': C('PRD_IS_ADULT', 'Flag01'), 'isActive': C('PRD_IS_ACTIVE', 'Flag01')},
                rels={'hasBrand': Rel('Brand', [E(UPPER_BRAND)]),
                      'hasModel': Rel('ProductModel', [E(UPPER_BRAND), 'PRD_MFR_PART_NO']),
                      'inCategory': Rel('Category', ['PRD_BROWSE_PATH']),
                      'countryOfOrigin': Ref('countryCode', C('PRD_CNTRY_ORGN', 'CountryAlpha2'))}),
        Concept('ProductAttribute', 'PRODUCT_TAGS', ['TAG_ID'],
                attrs={'attributeKey': C('TAG_KEY'), 'attributeValue': C('TAG_VALUE'),
                       'confidence': C('TAG_CONFIDENCE', 'PercentFraction'),
                       'createdAt': C('TAG_CREATED_DATE', 'TimestampUTC')},
                rels={'attributeOf': Rel('Product', ['TAG_PRD_UUID'])},
                values={'attributeSource': V(C('TAG_SOURCE', 'Code'))}),
        Concept('Offer', 'ITEM', ['ITM_STR_UUID', 'ITM_PRD_UUID', 'ITM_PRICE_CCY', 'ITM_OFFER_PRICE'],
                note='No offer table: offers are the distinct store/product/price combinations seen on cart items.',
                attrs={'price': C('ITM_OFFER_PRICE', 'MoneyMajor')},
                rels={'offeredBy': Rel('Seller', ['ITM_STR_UUID']), 'offerFor': Rel('Product', ['ITM_PRD_UUID']),
                      'hasCurrency': Ref('currencyCode', C('ITM_PRICE_CCY', 'CurrencyCode'))},
                values={'itemCondition': V(K('NEW'))}),
        Concept('Customer', 'SHOPPING_CART', ['SC_ACCOUNT_ID'], filter='SC_ACCOUNT_ID IS NOT NULL',
                note='No customer table: registered customers are the account ids on carts.',
                attrs={'customerNumber': C('SC_ACCOUNT_ID'), 'email': C('SC_CUSTOMER_EMAIL', 'Email')}),
        Concept('Address', 'SHOPPING_CART', ['SC_UUID'], id='ShipRegion', filter='SC_SHIP_REGION IS NOT NULL',
                note='Only the ship-to region is known.',
                attrs={'regionCode': C('SC_SHIP_REGION', 'RegionCode')},
                rels={'addressCountry': Ref('countryCode', E('substr(SC_SHIP_REGION, 1, 2)', 'CountryAlpha2'))}),
        Concept('Order', 'SHOPPING_CART', ['SC_UUID'], note='Carts and orders are the same table; SC_STATE '
                'says which. No order number or totals are stored.',
                attrs={'customerEmail': C('SC_CUSTOMER_EMAIL', 'Email'),
                       'createdAt': C('SC_CREATED_DATE', 'TimestampUTC'),
                       'updatedAt': C('SC_UPDATED_DATE', 'TimestampUTC'),
                       'placedAt': C('SC_PURCHASED_DATE', 'TimestampUTC'),
                       'closedAt': E("CASE WHEN SC_STATE = 'EXPIRED' THEN SC_UPDATED_DATE END", 'TimestampUTC')},
                rels={'placedBy': Rel('Customer', ['SC_ACCOUNT_ID']), 'shippingAddress': Rel('ShipRegion', ['SC_UUID']),
                      'hasCurrency': Ref('currencyCode', C('SC_DISPLAY_CCY', 'CurrencyCode'))},
                values={'orderStatus': V(C('SC_STATE', 'Code'),
                                         {'ACTIVE': 'CART', 'SAVED_FOR_LATER': 'SAVED_FOR_LATER',
                                          'PURCHASED': 'PLACED', 'EXPIRED': 'EXPIRED'}),
                        'salesChannel': V(C('SC_DEVICE', 'Code'),
                                          {'DESKTOP': 'WEB', 'IOS': 'APP', 'ANDROID': 'APP', 'ALEXA': 'VOICE'}),
                        'deviceType': V(C('SC_DEVICE', 'Code'))}),
        Concept('OrderLine', 'ITEM', ['ITM_UUID'],
                note="Prices are in the store's currency (ITM_PRICE_CCY), which can differ from the cart's.",
                attrs={'quantity': C('ITM_QTY', 'Integer'),
                       'unitPrice': E('CASE WHEN ITM_PRICE_CCY = (SELECT c.SC_DISPLAY_CCY FROM SHOPPING_CART c '
                                      'WHERE c.SC_UUID = ITEM.ITM_SC_UUID) THEN ITM_OFFER_PRICE END', 'MoneyMajor'),
                       'originalUnitPrice': C('ITM_OFFER_PRICE', 'MoneyMajor'),
                       'exchangeRateToUSD': C('ITM_FX_RATE_TO_USD', 'Decimal'),
                       'lineDiscount': C('ITM_PRM_SAVINGS', 'MoneyMajor'),
                       'lineTotal': E('ITM_QTY * ITM_OFFER_PRICE - ITM_PRM_SAVINGS', 'MoneyMajor'),
                       'isSubscription': C('ITM_IS_SUBSCRIBE_SAVE', 'Flag01'), 'isGift': C('ITM_IS_GIFT', 'Flag01'),
                       'giftMessage': C('ITM_GIFT_MSG', 'TrimmedText'), 'giftWrap': C('ITM_GIFT_WRAP', 'Flag01'),
                       'addedAt': C('ITM_ADDED_DATE', 'TimestampUTC')},
                rels={'lineOf': Rel('Order', ['ITM_SC_UUID']), 'ofProduct': Rel('Product', ['ITM_PRD_UUID']),
                      'soldBy': Rel('Seller', ['ITM_STR_UUID']),
                      'fromOffer': Rel('Offer', ['ITM_STR_UUID', 'ITM_PRD_UUID', 'ITM_PRICE_CCY', 'ITM_OFFER_PRICE']),
                      'originalCurrency': Ref('currencyCode', C('ITM_PRICE_CCY', 'CurrencyCode'))}),
        Concept('Promotion', 'PROMOTIONS', ['PRM_UUID'],
                attrs={'promotionCode': C('PRM_COUPON_CODE'), 'promotionName': C('PRM_LABEL', 'TrimmedText'),
                       'discountPercent': C('PRM_PCT_OFF', 'PercentFraction'),
                       'amountOff': C('PRM_AMT_OFF', 'MoneyMajor'),
                       'buyQuantity': C('PRM_BUY_QTY', 'Integer'), 'getQuantity': C('PRM_GET_QTY', 'Integer'),
                       'maxRedemptions': C('PRM_MAX_REDEMPTIONS', 'Integer'),
                       'targetAttributeKey': C('PRM_TARGET_TAG_KEY'), 'targetAttributeValue': C('PRM_TARGET_TAG_VALUE'),
                       'effectiveFrom': C('PRM_START_DATE', 'TimestampUTC'),
                       'effectiveUntil': C('PRM_END_DATE', 'TimestampUTCOpenEnded')},
                rels={'fundingSeller': Rel('Seller', ['PRM_STR_UUID']),
                      'appliesToProduct': Rel('Product', ['PRM_TARGET_PRD_UUID']),
                      'hasCurrency': Ref('currencyCode', C('PRM_AMT_CCY', 'CurrencyCode'))},
                values={'promotionScope': V(C('PRM_SCOPE', 'Code'), {'SITEWIDE': 'SITEWIDE', 'PRODUCT': 'ITEM',
                                                                     'TAG': 'ITEM', 'CART': 'ORDER'}),
                        'fundedBy': V(C('PRM_FUNDED_BY', 'Code'), {'PLATFORM': 'PLATFORM', 'STORE': 'SELLER'})}),
        Concept('AppliedDiscount', 'ITEM', ['ITM_UUID'], id='ItemPromotion', filter='ITM_PRM_UUID IS NOT NULL',
                attrs={'discountAmount': C('ITM_PRM_SAVINGS', 'MoneyMajor'),
                       'appliedAt': C('ITM_ADDED_DATE', 'TimestampUTC')},
                rels={'fromPromotion': Rel('Promotion', ['ITM_PRM_UUID']), 'appliedToLine': Rel('OrderLine', ['ITM_UUID']),
                      'appliedToOrder': Rel('Order', ['ITM_SC_UUID'])}),
        Concept('AppliedDiscount', 'SHOPPING_CART', ['SC_UUID'], id='CartCoupon', filter='SC_CART_PRM_UUID IS NOT NULL',
                note='Cart-level coupon. BigRiver does not record the amount it saved.',
                rels={'fromPromotion': Rel('Promotion', ['SC_CART_PRM_UUID']), 'appliedToOrder': Rel('Order', ['SC_UUID'])}),
    ])

# ---------------------------------------------------------------------
# BobsUncle
# ---------------------------------------------------------------------
BOBS_LINE = 'cart_item'
BOBSUNCLE = Source(
    code='bobsuncle', name='BobsUncle', schema='bobs_uncle.sql', sample_db='bobs_uncle/bobs_uncle.db',
    note='Convenience-store franchise. Wide legacy tables, money in INTEGER cents, Y/N flags, '
         "'YYYYMMDD' text dates, US/Central local timestamps, returns as negative quantities.",
    concepts=[
        Concept('Seller', None, [K('bobs-uncle')], note="BobsUncle is its own (only) seller.",
                attrs={'sellerHandle': K('bobs-uncle'), 'sellerName': K("Bob's Uncle"), 'isFirstParty': K(True)}),
        Concept('Manufacturer', 'brand', ['mfr_cd'],
                note='brand has one row per manufacturer + model, so manufacturer values repeat and '
                     'mfr_nm is spelled inconsistently between rows.',
                attrs={'manufacturerCode': C('mfr_cd'), 'manufacturerName': C('mfr_nm', 'BrandFreeText'),
                       'phone': C('mfr_contact_phone'), 'supportEmail': C('mfr_contact_email', 'Email'),
                       'websiteUrl': C('mfr_website_url')},
                rels={'headquartersCountry': Ref('countryCode', C('mfr_hq_country', 'CountryFreeText'))}),
        Concept('Brand', 'brand', ['mfr_cd'], note='Brand = manufacturer; there is no separate brand name.',
                attrs={'brandName': C('mfr_nm', 'BrandFreeText')},
                rels={'ownedBy': Rel('Manufacturer', ['mfr_cd'])}),
        Concept('ProductModel', 'brand', ['brand_id'],
                attrs={'modelNumber': C('model_no', 'TrimmedText'), 'modelName': C('model_nm', 'TrimmedText'),
                       'modelYear': C('model_yr', 'Integer'), 'releaseDate': C('avail_dt', 'DateYYYYMMDD'),
                       'discontinuedDate': C('discontinue_dt', 'DateYYYYMMDD'), 'isActive': C('active_flg', 'FlagYN')},
                rels={'ofBrand': Rel('Brand', ['mfr_cd'])}),
        Concept('Category', 'product', [E('upper(trim(dept_nm))')], filter='dept_nm IS NOT NULL',
                note="Free-text departments; 'Snacks', 'SNACKS' and 'Salty Snacks' must be mapped to one category.",
                attrs={'categoryCode': E('upper(trim(dept_nm))'), 'categoryName': C('dept_nm', 'TrimmedText')}),
        Concept('Product', 'product', ['sku'],
                attrs={'sku': C('sku'), 'upc': C('upc_cd'), 'ean': C('ean_cd'), 'gtin': C('gtin_cd'),
                       'productName': C('short_desc', 'TrimmedText'), 'productDescription': C('long_desc', 'TrimmedText'),
                       'weightInGrams': C('wt_lbs', 'WeightPounds'), 'isTaxable': C('taxable_flg', 'FlagYN'),
                       'isActive': E('(SELECT b.active_flg FROM brand b WHERE b.brand_id = product.brand_id)', 'FlagYN'),
                       'createdAt': C('created_dt', 'TimestampLocalUSCentral'),
                       'updatedAt': C('last_upd_ts', 'TimestampLocalUSCentral')},
                rels={'hasModel': Rel('ProductModel', ['brand_id']),
                      'hasBrand': Rel('Brand', [E('(SELECT b.mfr_cd FROM brand b WHERE b.brand_id = product.brand_id)')]),
                      'inCategory': Rel('Category', [E('upper(trim(dept_nm))')]),
                      'hasWarranty': Rel('WarrantyPlan', ['sku'])}),
        Concept('ProductAttribute', 'product', ['sku', K('color')], id='ColorAttribute', filter='color_desc IS NOT NULL',
                note='Fixed column turned into an attribute.',
                attrs={'attributeKey': K('color'), 'attributeValue': C('color_desc', 'TrimmedText')},
                rels={'attributeOf': Rel('Product', ['sku'])}, values={'attributeSource': V(K('SELLER'))}),
        Concept('ProductAttribute', 'product', ['sku', K('size')], id='SizeAttribute', filter='size_desc IS NOT NULL',
                note='Fixed column turned into an attribute.',
                attrs={'attributeKey': K('size'), 'attributeValue': C('size_desc', 'TrimmedText')},
                rels={'attributeOf': Rel('Product', ['sku'])}, values={'attributeSource': V(K('SELLER'))}),
        Concept('WarrantyPlan', 'product', ['sku'], filter="warr_type IN ('MFR', 'EXTENDED')",
                note='Warranty terms repeated on every product row.',
                attrs={'durationMonths': C('warr_months', 'Integer'), 'warrantyProvider': C('warr_provider', 'TrimmedText'),
                       'coversParts': C('warr_parts_flg', 'FlagYN'), 'coversLabor': C('warr_labor_flg', 'FlagYN'),
                       'warrantyTerms': C('warr_terms_txt', 'TrimmedText')},
                rels={'warrantyProduct': Rel('Product', [E("CASE WHEN warr_type = 'EXTENDED' THEN sku END")])},
                values={'warrantyType': V(C('warr_type', 'Code'), {'MFR': 'MANUFACTURER', 'EXTENDED': 'EXTENDED'})}),
        Concept('Offer', 'product', ['sku'], note='Retail price and cost of the single seller.',
                attrs={'price': C('retail_price_cents', 'MoneyMinor'), 'cost': C('cost_cents', 'MoneyMinor')},
                rels={'offeredBy': Rel('Seller', [K('bobs-uncle')]), 'offerFor': Rel('Product', ['sku']),
                      'hasCurrency': Ref('currencyCode', K('USD'))},
                values={'itemCondition': V(K('NEW'))}),
        Concept('Warehouse', 'inventory', ['whse_cd'], note='Stores and the distribution center, known only by code.',
                attrs={'warehouseCode': C('whse_cd')}, rels={'operatedBy': Rel('Seller', [K('bobs-uncle')])}),
        Concept('InventoryPosition', 'inventory', ['sku', 'whse_cd'],
                attrs={'quantityOnHand': C('qty_on_hand', 'Integer'), 'quantityReserved': C('qty_reserved', 'Integer'),
                       'quantityOnOrder': C('qty_on_order', 'Integer'), 'reorderPoint': C('reorder_pt', 'Integer'),
                       'binLocation': C('bin_loc'), 'lastCountedDate': C('last_cnt_dt', 'DateYYYYMMDD')},
                rels={'stockOf': Rel('Product', ['sku']), 'heldAt': Rel('Warehouse', ['whse_cd'])}),
        Concept('Customer', 'cart', ['cust_ref'], filter='cust_ref IS NOT NULL',
                note='cust_ref holds a loyalty number or an email address.',
                attrs={'customerNumber': C('cust_ref'),
                       'loyaltyNumber': E("CASE WHEN cust_ref NOT LIKE '%@%' THEN cust_ref END"),
                       'email': E("CASE WHEN cust_ref LIKE '%@%' THEN cust_ref END", 'Email')}),
        Concept('Address', 'cart', ['cart_no'], id='ShipZip', filter='ship_zip IS NOT NULL',
                note='Only the US ZIP code of web orders is known.',
                attrs={'postalCode': C('ship_zip', 'TrimmedText')},
                rels={'addressCountry': Ref('countryCode', K('US'))}),
        Concept('Order', 'cart', ['cart_no'], note='Carts and orders are the same table. A checked-out cart '
                'whose lines are all negative is a return (see ReturnAuthorization).',
                attrs={'orderNumber': C('cart_no'),
                       'customerEmail': E("CASE WHEN cust_ref LIKE '%@%' THEN cust_ref END", 'Email'),
                       'createdAt': C('created_ts', 'TimestampLocalUSCentral'),
                       'placedAt': C('checkout_ts', 'TimestampLocalUSCentral'),
                       'subtotalAmount': E("(SELECT sum(i.qty * i.unit_price_cents) FROM cart_item i "
                                           "WHERE i.cart_no = cart.cart_no AND i.removed_flg = 'N')", 'MoneyMinor'),
                       'discountTotal': E("(SELECT sum(i.disc_cents) FROM cart_item i "
                                          "WHERE i.cart_no = cart.cart_no AND i.removed_flg = 'N')", 'MoneyMinor'),
                       'taxTotal': C('tax_cents', 'MoneyMinor'), 'shippingTotal': C('ship_cents', 'MoneyMinor'),
                       'grandTotal': C('total_cents', 'MoneyMinor')},
                rels={'placedBy': Rel('Customer', ['cust_ref']), 'shippingAddress': Rel('ShipZip', ['cart_no']),
                      'hasCurrency': Ref('currencyCode', K('USD'))},
                values={'orderStatus': V(C('cart_stat', 'Code'),
                                         {'O': 'CART', 'C': 'PLACED', 'A': 'ABANDONED', 'X': 'CANCELLED'}),
                        'salesChannel': V(C('channel_cd', 'Code'))}),
        Concept('OrderLine', BOBS_LINE, ['cart_no', 'line_seq'], filter='qty > 0',
                note='Negative-quantity lines are returns and bind to ReturnLine instead.',
                attrs={'lineNumber': C('line_seq', 'Integer'), 'quantity': C('qty', 'Integer'),
                       'unitPrice': C('unit_price_cents', 'MoneyMinor'), 'lineDiscount': C('disc_cents', 'MoneyMinor'),
                       'lineTotal': E('qty * unit_price_cents - disc_cents', 'MoneyMinor'),
                       'addedAt': C('added_ts', 'TimestampLocalUSCentral'), 'isRemoved': C('removed_flg', 'FlagYN')},
                rels={'lineOf': Rel('Order', ['cart_no']), 'ofProduct': Rel('Product', ['sku']),
                      'soldBy': Rel('Seller', [K('bobs-uncle')]), 'fulfilledFrom': Rel('Warehouse', ['fulfil_whse_cd']),
                      'addOnFor': Rel('OrderLine', ['cart_no', E('(SELECT m.line_seq FROM cart_item m WHERE '
                                                                  'm.cart_no = cart_item.cart_no AND m.ext_warr_sku = cart_item.sku)')])}),
        Concept('AppliedDiscount', BOBS_LINE, ['cart_no', 'line_seq'], filter='disc_cents <> 0 AND qty > 0',
                note='Discounts are free-text reasons; matching them to a promotion is fuzzy.',
                attrs={'discountAmount': C('disc_cents', 'MoneyMinor'), 'discountReason': C('disc_reason', 'TrimmedText')},
                rels={'appliedToLine': Rel('OrderLine', ['cart_no', 'line_seq']), 'appliedToOrder': Rel('Order', ['cart_no']),
                      'fromPromotion': Rel('Promotion', [E("(SELECT min(p.promo_id) FROM promotion p WHERE p.promo_cd IS NOT NULL "
                                                           "AND upper(cart_item.disc_reason) LIKE '%' || upper(p.promo_cd) || '%')")])}),
        Concept('Promotion', 'promotion', ['promo_id'],
                attrs={'promotionCode': C('promo_cd'), 'promotionName': C('promo_desc', 'TrimmedText'),
                       'discountPercent': C('discount_pct', 'PercentWhole'), 'amountOff': C('discount_cents', 'MoneyMinor'),
                       'minimumOrderAmount': C('min_order_cents', 'MoneyMinor'),
                       'effectiveFrom': C('effective_dt', 'TimestampLocalUSCentral'),
                       'effectiveUntil': C('expiration_dt', 'TimestampLocalUSCentral'),
                       'isActive': C('active_flg', 'FlagYN'), 'isStackable': C('stackable_flg', 'FlagYN')},
                rels={'fundingBrand': Rel('Brand', ['mfr_cd']), 'hasCurrency': Ref('currencyCode', K('USD'))},
                values={'promotionScope': V(C('scope', 'Code'), {'SITEWIDE': 'SITEWIDE', 'PRODUCT': 'ITEM',
                                                                'DEPT': 'ITEM', 'CART': 'ORDER'}),
                        'fundedBy': V(C('funded_by', 'Code'), {'RETAILER': 'PLATFORM', 'MFR': 'MANUFACTURER'})}),
        Concept('ReturnAuthorization', 'cart', ['cart_no'],
                filter='EXISTS (SELECT 1 FROM cart_item i WHERE i.cart_no = cart.cart_no AND i.qty < 0)',
                note='No RMA table: a cart with negative-quantity lines is an in-store return.',
                attrs={'rmaNumber': C('cart_no'), 'requestedAt': C('created_ts', 'TimestampLocalUSCentral'),
                       'returnClosedAt': C('checkout_ts', 'TimestampLocalUSCentral')},
                rels={'requestedBy': Rel('Customer', ['cust_ref'])},
                values={'returnStatus': V(K('COMPLETED'))}),
        Concept('ReturnLine', BOBS_LINE, ['cart_no', 'line_seq'], filter='qty < 0',
                note='Returned units; the original order line is not recorded.',
                attrs={'quantity': E('-qty', 'Integer')},
                rels={'inReturn': Rel('ReturnAuthorization', ['cart_no']), 'returnedProduct': Rel('Product', ['sku'])},
                values={'returnReason': V(K('UNSPECIFIED')), 'requestedResolution': V(K('REFUND'))}),
        Concept('Refund', 'cart', ['cart_no'], filter='total_cents < 0', note='Negative cart total = cash refunded.',
                attrs={'refundAmount': E('-total_cents', 'MoneyMinor'),
                       'refundedAt': C('checkout_ts', 'TimestampLocalUSCentral')},
                rels={'forReturn': Rel('ReturnAuthorization', ['cart_no']), 'hasCurrency': Ref('currencyCode', K('USD'))},
                values={'refundStatus': V(K('COMPLETED'))}),
    ])

# ---------------------------------------------------------------------
# Canonical model (it is just another binding of the same concepts)
# ---------------------------------------------------------------------
TS, MM = 'TimestampISO', 'MoneyMinor'
CANONICAL = Source(
    code='canonical', name='Canonical E-Commerce Model', schema='canonical_ecommerce.sql', sample_db=None,
    note='The normalized integration model. Money in INTEGER minor units, percent as fractions, '
         'ISO-8601 UTC timestamps, codes equal to the core skos:notation values.',
    concepts=[
        Concept('Country', 'country', ['country_code'],
                attrs={'countryCode': C('country_code', 'CountryAlpha2'), 'countryName': C('country_name')}),
        Concept('Currency', 'currency', ['currency_code'],
                attrs={'currencyCode': C('currency_code', 'CurrencyCode'), 'currencyName': C('currency_name'),
                       'minorUnitDigits': C('minor_unit_digits', 'Integer')}),
        Concept('Category', 'category', ['category_id'],
                attrs={'categoryCode': C('category_code'), 'categoryName': C('category_name'),
                       'categoryDescription': C('long_description'), 'sortOrder': C('sort_order', 'Integer'),
                       'isActive': C('is_active', 'Flag01'), 'effectiveFrom': C('effective_at', TS),
                       'effectiveUntil': C('expires_at', TS), 'createdAt': C('created_at', TS),
                       'updatedAt': C('updated_at', TS)},
                rels={'parentCategory': Rel('Category', ['parent_category_id'])}),
        Concept('Manufacturer', 'brand', ['manufacturer_name'], filter='manufacturer_name IS NOT NULL',
                note='Manufacturer details are merged into the brand table.',
                attrs={'manufacturerName': C('manufacturer_name'), 'manufacturerCode': C('brand_code'),
                       'phone': C('support_phone'), 'supportEmail': C('support_email', 'Email')},
                rels={'headquartersCountry': Ref('countryCode', C('country_code', 'CountryAlpha2'))}),
        Concept('Brand', 'brand', ['brand_id'],
                attrs={'brandName': C('brand_name'), 'websiteUrl': C('website_url'), 'isActive': C('is_active', 'Flag01'),
                       'createdAt': C('created_at', TS), 'updatedAt': C('updated_at', TS)},
                rels={'ownedBy': Rel('Manufacturer', ['manufacturer_name']),
                      'countryOfOrigin': Ref('countryCode', C('country_code', 'CountryAlpha2'))}),
        Concept('ProductModel', 'product', ['brand_id', 'model_number'], filter='model_number IS NOT NULL',
                note='Model details are merged into the product table.',
                attrs={'modelNumber': C('model_number'), 'modelName': C('model_name'),
                       'modelYear': C('model_year', 'Integer'), 'releaseDate': C('release_date', 'DateISO'),
                       'discontinuedDate': C('discontinued_date', 'DateISO')},
                rels={'ofBrand': Rel('Brand', ['brand_id'])}),
        Concept('Product', 'product', ['product_id'],
                attrs={'sku': C('sku'), 'productName': C('product_name'), 'productLongName': C('long_name'),
                       'productDescription': C('description'), 'weightInGrams': C('weight_grams', 'WeightGrams'),
                       'msrp': C('msrp_amount', MM), 'isTaxable': C('is_taxable', 'Flag01'),
                       'isAdultOnly': C('is_adult', 'Flag01'), 'isActive': C('is_active', 'Flag01'),
                       'effectiveFrom': C('effective_at', TS), 'effectiveUntil': C('expires_at', TS),
                       'createdAt': C('created_at', TS), 'updatedAt': C('updated_at', TS),
                       **{prop: E(f"(SELECT min(pi.identifier_value) FROM product_identifier pi WHERE "
                                  f"pi.product_id = product.product_id AND pi.identifier_type = '{code}')")
                          for prop, code in [('upc', 'UPC'), ('ean', 'EAN'), ('gtin', 'GTIN'),
                                             ('marketplaceProductId', 'MARKETPLACE_ID')]}},
                rels={'hasModel': Rel('ProductModel', ['brand_id', 'model_number']), 'hasBrand': Rel('Brand', ['brand_id']),
                      'inCategory': Rel('Category', ['category_id']),
                      'countryOfOrigin': Ref('countryCode', C('country_of_origin', 'CountryAlpha2')),
                      'hasCurrency': Ref('currencyCode', C('msrp_currency_code', 'CurrencyCode')),
                      'hasWarranty': Through('product_warranty', ['product_id'], ['warranty_plan_id'], 'WarrantyPlan')}),
        Concept('ProductAttribute', 'product_attribute', ['product_attribute_id'],
                attrs={'attributeKey': E('(SELECT d.attribute_key FROM attribute_definition d '
                                         'WHERE d.attribute_id = product_attribute.attribute_id)'),
                       'attributeValue': C('attribute_value'), 'confidence': C('confidence', 'PercentFraction'),
                       'createdAt': C('created_at', TS)},
                rels={'attributeOf': Rel('Product', ['product_id'])},
                values={'attributeSource': V(C('value_source', 'Code'))}),
        Concept('WarrantyPlan', 'warranty_plan', ['warranty_plan_id'],
                attrs={'durationMonths': C('duration_months', 'Integer'), 'warrantyProvider': C('provider_name'),
                       'coversParts': C('covers_parts', 'Flag01'), 'coversLabor': C('covers_labor', 'Flag01'),
                       'warrantyTerms': C('terms_text')},
                rels={'warrantyProduct': Rel('Product', ['warranty_product_id'])},
                values={'warrantyType': V(C('warranty_type', 'Code'))}),
        Concept('Seller', 'seller', ['seller_id'],
                attrs={'sellerHandle': C('seller_handle'), 'sellerName': C('display_name'),
                       'isFirstParty': C('is_first_party', 'Flag01'), 'sellerRating': C('rating', 'Decimal'),
                       'shipsFromRegion': C('ships_from_region', 'RegionCode'),
                       'fulfilledByPlatform': C('fulfilled_by_platform', 'Flag01'),
                       'onboardedAt': C('onboarded_at', TS), 'createdAt': C('created_at', TS),
                       'updatedAt': C('updated_at', TS)},
                rels={'sellerCountry': Ref('countryCode', C('country_code', 'CountryAlpha2')),
                      'defaultCurrency': Ref('currencyCode', C('default_currency_code', 'CurrencyCode'))},
                values={'sellerStatus': V(C('seller_status', 'Code'))}),
        Concept('Offer', 'offer', ['offer_id'],
                attrs={'price': C('price_amount', MM), 'cost': C('cost_amount', MM),
                       'effectiveFrom': C('effective_at', TS), 'effectiveUntil': C('expires_at', TS),
                       'createdAt': C('created_at', TS)},
                rels={'offeredBy': Rel('Seller', ['seller_id']), 'offerFor': Rel('Product', ['product_id']),
                      'hasCurrency': Ref('currencyCode', C('currency_code', 'CurrencyCode'))},
                values={'itemCondition': V(C('item_condition', 'Code'))}),
        Concept('Address', 'address', ['address_id'],
                attrs={'recipientName': C('recipient_name'),
                       'streetAddress': E("line1 || coalesce(char(10) || line2, '')", 'TrimmedText'),
                       'city': C('city'), 'regionCode': C('region_code', 'RegionCode'),
                       'postalCode': C('postal_code'), 'phone': C('phone'), 'createdAt': C('created_at', TS)},
                rels={'addressCountry': Ref('countryCode', C('country_code', 'CountryAlpha2'))}),
        Concept('Warehouse', 'warehouse', ['warehouse_id'],
                attrs={'warehouseCode': C('warehouse_code'), 'warehouseName': C('warehouse_name'),
                       'isActive': C('is_active', 'Flag01')},
                rels={'operatedBy': Rel('Seller', ['seller_id']), 'hasAddress': Rel('Address', ['address_id'])}),
        Concept('InventoryPosition', 'inventory', ['product_id', 'warehouse_id'],
                attrs={'quantityOnHand': C('quantity_on_hand', 'Integer'),
                       'quantityReserved': C('quantity_reserved', 'Integer'),
                       'quantityOnOrder': C('quantity_on_order', 'Integer'), 'reorderPoint': C('reorder_point', 'Integer'),
                       'binLocation': C('bin_location'), 'lastCountedDate': C('last_counted_date', 'DateISO'),
                       'updatedAt': C('updated_at', TS)},
                rels={'stockOf': Rel('Product', ['product_id']), 'heldAt': Rel('Warehouse', ['warehouse_id'])}),
        Concept('Customer', 'customer', ['customer_id'],
                attrs={'customerNumber': C('customer_number'), 'email': C('email', 'Email'),
                       'loyaltyNumber': C('loyalty_number'), 'firstName': C('first_name'), 'lastName': C('last_name'),
                       'phone': C('phone'), 'marketingOptIn': C('marketing_opt_in', 'Flag01'),
                       'createdAt': C('created_at', TS), 'updatedAt': C('updated_at', TS)},
                rels={'preferredCurrency': Ref('currencyCode', C('preferred_currency_code', 'CurrencyCode')),
                      'hasAddress': Through('customer_address', ['customer_id'], ['address_id'], 'Address'),
                      'defaultBillingAddress': Through('customer_address', ['customer_id'], ['address_id'], 'Address',
                                                       'is_default_billing = 1'),
                      'defaultShippingAddress': Through('customer_address', ['customer_id'], ['address_id'], 'Address',
                                                        'is_default_shipping = 1')},
                values={'customerStatus': V(C('customer_status', 'Code'))}),
        Concept('Order', 'customer_order', ['order_id'],
                attrs={'orderNumber': C('order_number'), 'customerEmail': C('customer_email', 'Email'),
                       'subtotalAmount': C('subtotal_amount', MM), 'discountTotal': C('discount_total', MM),
                       'taxTotal': C('tax_total', MM), 'shippingTotal': C('shipping_total', MM),
                       'grandTotal': C('grand_total', MM), 'createdAt': C('created_at', TS),
                       'updatedAt': C('updated_at', TS), 'placedAt': C('placed_at', TS), 'closedAt': C('closed_at', TS)},
                rels={'placedBy': Rel('Customer', ['customer_id']),
                      'hasCurrency': Ref('currencyCode', C('currency_code', 'CurrencyCode')),
                      'billingAddress': Through('order_address', ['order_id'], ['address_id'], 'Address',
                                                "address_type = 'BILLING'"),
                      'shippingAddress': Through('order_address', ['order_id'], ['address_id'], 'Address',
                                                 "address_type = 'SHIPPING'")},
                values={'orderStatus': V(C('order_status', 'Code')), 'salesChannel': V(C('channel', 'Code')),
                        'deviceType': V(C('device_type', 'Code'))}),
        Concept('OrderLine', 'order_item', ['order_item_id'],
                note='fx_rate converts the original (seller) currency into the order currency, not into USD, '
                     'so it is not bound to cc:exchangeRateToUSD.',
                attrs={'lineNumber': C('line_number', 'Integer'), 'quantity': C('quantity', 'Integer'),
                       'unitPrice': C('unit_price', MM), 'originalUnitPrice': C('original_unit_price', MM),
                       'lineDiscount': C('discount_amount', MM), 'lineTax': C('tax_amount', MM),
                       'lineTotal': C('line_total', MM), 'isSubscription': C('is_subscribe_save', 'Flag01'),
                       'isGift': C('is_gift', 'Flag01'), 'giftMessage': C('gift_message'),
                       'giftWrap': C('gift_wrap', 'Flag01'), 'addedAt': C('added_at', TS),
                       'removedAt': C('removed_at', TS), 'isRemoved': E('removed_at IS NOT NULL', 'Flag01')},
                rels={'lineOf': Rel('Order', ['order_id']), 'ofProduct': Rel('Product', ['product_id']),
                      'soldBy': Rel('Seller', ['seller_id']), 'fromOffer': Rel('Offer', ['offer_id']),
                      'fulfilledFrom': Rel('Warehouse', ['fulfillment_warehouse_id']),
                      'addOnFor': Rel('OrderLine', ['parent_order_item_id']),
                      'originalCurrency': Ref('currencyCode', C('original_currency_code', 'CurrencyCode'))}),
        Concept('Promotion', 'promotion', ['promotion_id'],
                attrs={'promotionCode': C('promotion_code'), 'promotionName': C('promotion_name'),
                       'promotionDescription': C('description'), 'eventName': C('event_name'),
                       'partnerCompany': C('partner_company'), 'discountPercent': C('discount_percent', 'PercentFraction'),
                       'amountOff': C('discount_amount', MM), 'minimumOrderAmount': C('minimum_order_amount', MM),
                       'buyQuantity': C('buy_quantity', 'Integer'), 'getQuantity': C('get_quantity', 'Integer'),
                       'maxRedemptions': C('max_redemptions', 'Integer'), 'isStackable': C('is_stackable', 'Flag01'),
                       'isActive': C('is_active', 'Flag01'), 'effectiveFrom': C('starts_at', TS),
                       'effectiveUntil': C('ends_at', TS),
                       'targetAttributeKey': E("(SELECT min(d.attribute_key) FROM promotion_target t JOIN "
                                               "attribute_definition d ON d.attribute_id = t.attribute_id WHERE "
                                               "t.promotion_id = promotion.promotion_id AND t.target_type = 'ATTRIBUTE')"),
                       'targetAttributeValue': E("(SELECT min(t.attribute_value) FROM promotion_target t WHERE "
                                                 "t.promotion_id = promotion.promotion_id AND t.target_type = 'ATTRIBUTE')")},
                rels={'fundingSeller': Rel('Seller', ['seller_id']), 'fundingBrand': Rel('Brand', ['funding_brand_id']),
                      'hasCurrency': Ref('currencyCode', C('currency_code', 'CurrencyCode')),
                      **{prop: Through('promotion_target', ['promotion_id'], [col], target,
                                       f"target_type = '{tt}' AND is_exclusion = 0")
                         for prop, col, target, tt in [('appliesToProduct', 'product_id', 'Product', 'PRODUCT'),
                                                       ('appliesToBrand', 'brand_id', 'Brand', 'BRAND'),
                                                       ('appliesToCategory', 'category_id', 'Category', 'CATEGORY')]}},
                values={'promotionScope': V(C('scope', 'Code')), 'fundedBy': V(C('funded_by', 'Code'))}),
        Concept('AppliedDiscount', 'applied_discount', ['applied_discount_id'],
                attrs={'discountAmount': C('discount_amount', MM), 'discountReason': C('discount_reason'),
                       'appliedAt': C('applied_at', TS)},
                rels={'fromPromotion': Rel('Promotion', ['promotion_id']), 'appliedToOrder': Rel('Order', ['order_id']),
                      'appliedToLine': Rel('OrderLine', ['order_item_id'])}),
        Concept('Payment', 'payment', ['payment_id'],
                attrs={'paymentAmount': C('amount', MM), 'cardBrand': C('card_brand'), 'cardLast4': C('card_last4'),
                       'processorReference': C('processor_reference'), 'authorizedAt': C('authorized_at', TS),
                       'capturedAt': C('captured_at', TS), 'createdAt': C('created_at', TS)},
                rels={'paysFor': Rel('Order', ['order_id']), 'billingAddress': Rel('Address', ['billing_address_id']),
                      'hasCurrency': Ref('currencyCode', C('currency_code', 'CurrencyCode'))},
                values={'paymentMethod': V(C('payment_method', 'Code')), 'paymentStatus': V(C('payment_status', 'Code'))}),
        Concept('Shipment', 'shipment', ['shipment_id'],
                attrs={'carrier': C('carrier'), 'serviceLevel': C('service_level'),
                       'trackingNumber': C('tracking_number'), 'shippingCost': C('shipping_cost', MM),
                       'shippedAt': C('shipped_at', TS), 'deliveredAt': C('delivered_at', TS)},
                rels={'shipmentOf': Rel('Order', ['order_id']), 'shippedBy': Rel('Seller', ['seller_id']),
                      'shippedFrom': Rel('Warehouse', ['from_warehouse_id']),
                      'shipTo': Rel('Address', ['ship_to_address_id']),
                      'hasCurrency': Ref('currencyCode', E('(SELECT o.currency_code FROM customer_order o '
                                                           'WHERE o.order_id = shipment.order_id)', 'CurrencyCode'))},
                values={'shipmentStatus': V(C('shipment_status', 'Code'))}),
        Concept('ShipmentLine', 'shipment_item', ['shipment_id', 'order_item_id'],
                attrs={'quantity': C('quantity', 'Integer')},
                rels={'inShipment': Rel('Shipment', ['shipment_id']), 'shipsLine': Rel('OrderLine', ['order_item_id'])}),
        Concept('ReturnAuthorization', 'rma', ['rma_id'],
                attrs={'rmaNumber': C('rma_number'), 'requestedAt': C('requested_at', TS),
                       'approvedAt': C('approved_at', TS), 'receivedAt': C('received_at', TS),
                       'returnClosedAt': C('closed_at', TS)},
                rels={'returnFor': Rel('Order', ['order_id']), 'requestedBy': Rel('Customer', ['customer_id']),
                      'returnTo': Rel('Warehouse', ['return_warehouse_id'])},
                values={'returnStatus': V(C('rma_status', 'Code'))}),
        Concept('ReturnLine', 'rma_item', ['rma_item_id'],
                attrs={'quantity': C('quantity', 'Integer'), 'restockingFee': C('restocking_fee', MM)},
                rels={'inReturn': Rel('ReturnAuthorization', ['rma_id']), 'returnsLine': Rel('OrderLine', ['order_item_id']),
                      'returnedProduct': Rel('Product', [E('(SELECT i.product_id FROM order_item i '
                                                           'WHERE i.order_item_id = rma_item.order_item_id)')]),
                      'replacementOrder': Rel('Order', ['replacement_order_id'])},
                values={'returnReason': V(C('return_reason_code', 'Code')),
                        'requestedResolution': V(C('requested_resolution', 'Code')),
                        'receivedCondition': V(C('received_condition', 'Code')),
                        'disposition': V(C('disposition', 'Code'))}),
        Concept('Refund', 'refund', ['refund_id'],
                attrs={'refundAmount': C('amount', MM), 'processorReference': C('processor_reference'),
                       'refundedAt': C('refunded_at', TS), 'createdAt': C('created_at', TS)},
                rels={'refundFor': Rel('Order', ['order_id']), 'forReturn': Rel('ReturnAuthorization', ['rma_id']),
                      'refundOfPayment': Rel('Payment', ['payment_id']),
                      'hasCurrency': Ref('currencyCode', C('currency_code', 'CurrencyCode'))},
                values={'refundStatus': V(C('refund_status', 'Code'))}),
    ])

SOURCES = [ACME, BIGRIVER, BOBSUNCLE, CANONICAL]
