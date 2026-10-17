"""Core commerce concepts, independent of any database.

This is the source for commerce_core.ttl. It describes WHAT the business
concepts are (classes, relationships, attributes, code lists) and the
value conventions every binding must convert into. It says nothing about
tables or columns; that is the job of the binding ontology.

Value conventions (stated once here, referenced by every binding):
  * money       xsd:decimal in MAJOR currency units (19.99), with the
                currency given by cc:hasCurrency on the same resource
  * percentages xsd:decimal fraction 0..1 (0.15 = 15%)
  * timestamps  xsd:dateTime in UTC
  * dates       xsd:date
  * weight      grams (property names carry the unit)
  * flags       xsd:boolean
  * codes       individuals of a code-list class; skos:notation holds
                the canonical code (e.g. 'PLACED')
"""

NS = 'https://ontoresearch.example/commerce/core#'
VERSION = '1.0.0'

# ---------------------------------------------------------------------
# Classes: name -> (parent or None, label, definition, alt labels)
#   alt labels list the words the source systems use for the concept,
#   which helps an agent recognise it in an unfamiliar schema.
# ---------------------------------------------------------------------
CLASSES = {
    # reference data
    'Country': (None, 'Country', 'A country, identified by its ISO 3166-1 alpha-2 code.', []),
    'Currency': (None, 'Currency', 'A currency, identified by its ISO 4217 code.', ['CCY']),

    # catalog
    'Category': (None, 'Category', 'A node in the merchandising hierarchy used to browse and '
                 'group products (Garden > Watering & Irrigation).',
                 ['CatalogCategory', 'department', 'dept', 'browse path']),
    'Manufacturer': (None, 'Manufacturer', 'The legal company that makes products and stands '
                     'behind their manufacturer warranty.', ['mfr', 'maker']),
    'Brand': (None, 'Brand', 'The consumer-facing name a product is sold under. A manufacturer '
              'can own several brands.', ['brand text', 'make']),
    'ProductModel': (None, 'Product model', "A manufacturer's model: the design identified by a "
                     'model or part number. Several sellable products (color or pack-size '
                     'variants) can share one model.', ['model', 'part number', 'mfr part no']),
    'Product': (None, 'Product', 'A sellable item (one SKU). Seller-independent: what a specific '
                'seller charges for it is an Offer.',
                ['Model (AcmeShopping)', 'SKU', 'listing']),
    'ProductAttribute': (None, 'Product attribute', 'A named characteristic of a product that is '
                         'not a fixed property, e.g. color=black or screen_size=65 in.',
                         ['tag', 'product tag', 'EAV attribute']),
    'WarrantyPlan': (None, 'Warranty plan', 'Terms under which a product is repaired or replaced, '
                     'either included by the manufacturer or sold as an extended plan.',
                     ['warranty', 'protection plan']),

    # sellers, offers, stock
    'Seller': (None, 'Seller', 'A party that sells products: the platform itself (first party) or '
               'a third-party store on a marketplace.', ['store', 'merchant', 'vendor']),
    'Offer': (None, 'Offer', "A seller's price for a product, in a currency, for a period of time.",
              ['listing price', 'retail price', 'offer price']),
    'Warehouse': (None, 'Warehouse', 'A location that holds stock: a distribution center or a '
                  'store.', ['whse', 'location', 'fulfillment center']),
    'InventoryPosition': (None, 'Inventory position', 'How much of one product is held at one '
                          'warehouse.', ['inventory', 'stock level']),

    # customers
    'Customer': (None, 'Customer', 'A registered shopper with an account and profile.',
                 ['account', 'cust_ref', 'shopper']),
    'Address': (None, 'Address', 'A postal address. Sources often hold only part of it, e.g. a '
                'postal code or region.', ['ship to', 'ship zip', 'ship region']),

    # orders
    'Order': (None, 'Order', 'A purchase from start to finish. A cart is an order that has not '
              'been placed yet; the order status says where it is in its life.',
              ['cart', 'shopping cart', 'basket', 'checkout']),
    'OrderLine': (None, 'Order line', 'One product, from one seller, in an order or cart.',
                  ['order item', 'cart item', 'line item', 'ITEM']),
    'Promotion': (None, 'Promotion', 'A rule that reduces price: a coupon code, an automatic '
                  'deal or an event sale.', ['promo', 'coupon', 'deal', 'discount rule']),
    'AppliedDiscount': (None, 'Applied discount', 'A discount actually granted on an order or '
                        'order line, with or without a promotion behind it.',
                        ['discount', 'savings', 'disc']),
    'Payment': (None, 'Payment', 'Money collected for an order.', ['tender', 'charge']),
    'Shipment': (None, 'Shipment', 'A package sent for an order from one seller or warehouse.',
                 ['parcel', 'package', 'fulfillment']),
    'ShipmentLine': (None, 'Shipment line', 'How many units of an order line a shipment holds.', []),
    'ReturnAuthorization': (None, 'Return authorization', 'Approval for a customer to send items '
                            'back (RMA).', ['RMA', 'return']),
    'ReturnLine': (None, 'Return line', 'Units of one product coming back under a return.',
                   ['return item', 'negative quantity line']),
    'Refund': (None, 'Refund', 'Money paid back to a customer.', []),

    # code lists (individuals below)
    'CodeList': (None, 'Code list', 'Superclass of all controlled vocabularies. Each member has a '
                 'skos:notation holding its canonical code.', []),
    'OrderStatus': ('CodeList', 'Order status', 'Where an order is in its life.', ['cart state', 'cart_stat']),
    'SalesChannel': ('CodeList', 'Sales channel', 'How the order was placed.', ['channel']),
    'DeviceType': ('CodeList', 'Device type', 'The device the shopper used.', ['device']),
    'SellerStatus': ('CodeList', 'Seller status', 'Whether a seller may sell.', []),
    'ItemCondition': ('CodeList', 'Item condition', 'Condition of the item being offered.', []),
    'PromotionScope': ('CodeList', 'Promotion scope', 'The level a promotion discounts at.', ['promotion type']),
    'FundingSource': ('CodeList', 'Funding source', 'Who pays for a promotion.', ['funded by']),
    'AttributeSource': ('CodeList', 'Attribute source', 'Who supplied a product attribute.', ['tag source']),
    'WarrantyType': ('CodeList', 'Warranty type', 'Kind of warranty.', []),
    'CustomerStatus': ('CodeList', 'Customer status', 'Whether a customer account is usable.', []),
    'PaymentMethod': ('CodeList', 'Payment method', 'How a payment was made.', ['tender type']),
    'PaymentStatus': ('CodeList', 'Payment status', 'Where a payment is in its life.', []),
    'ShipmentStatus': ('CodeList', 'Shipment status', 'Where a shipment is in its life.', []),
    'ReturnStatus': ('CodeList', 'Return status', 'Where a return authorization is in its life.', ['RMA status']),
    'ReturnReason': ('CodeList', 'Return reason', 'Why items came back.', []),
    'ReturnResolution': ('CodeList', 'Return resolution', 'What the customer gets for a return.', []),
    'ReturnedCondition': ('CodeList', 'Returned condition', 'Condition a returned item arrived in.', []),
    'Disposition': ('CodeList', 'Disposition', 'What happens to a returned item.', []),
    'RefundStatus': ('CodeList', 'Refund status', 'Where a refund is in its life.', []),
}

# Defined classes: an agent or reasoner can classify orders by status.
DEFINED_CLASSES = {
    'Cart': ('Order', 'Cart', 'An order that has not been placed (still shopping, saved, '
             'abandoned or expired).',
             ['OrderStatus_CART', 'OrderStatus_SAVED_FOR_LATER', 'OrderStatus_ABANDONED',
              'OrderStatus_EXPIRED']),
    'PlacedOrder': ('Order', 'Placed order', 'An order the customer has checked out.',
                    ['OrderStatus_PLACED', 'OrderStatus_PAID', 'OrderStatus_PARTIALLY_SHIPPED',
                     'OrderStatus_SHIPPED', 'OrderStatus_DELIVERED',
                     'OrderStatus_PARTIALLY_RETURNED', 'OrderStatus_RETURNED']),
}

# ---------------------------------------------------------------------
# Code lists: class -> [(notation, label, definition)]
#   Individual IRI = <Class>_<NOTATION>, e.g. cc:OrderStatus_PLACED
# ---------------------------------------------------------------------
CODE_LISTS = {
    'OrderStatus': [
        ('CART', 'Cart', 'Shopper is still adding items.'),
        ('SAVED_FOR_LATER', 'Saved for later', 'Shopper parked the cart.'),
        ('ABANDONED', 'Abandoned', 'Shopper left without buying.'),
        ('EXPIRED', 'Expired', 'Cart timed out without being bought.'),
        ('PLACED', 'Placed', 'Checked out, not yet paid or shipped.'),
        ('PAID', 'Paid', 'Payment captured.'),
        ('PARTIALLY_SHIPPED', 'Partially shipped', 'Some lines have shipped.'),
        ('SHIPPED', 'Shipped', 'All lines have shipped.'),
        ('DELIVERED', 'Delivered', 'Delivered to the customer.'),
        ('CANCELLED', 'Cancelled', 'Cancelled before fulfilment.'),
        ('PARTIALLY_RETURNED', 'Partially returned', 'Some units came back.'),
        ('RETURNED', 'Returned', 'Everything came back.'),
    ],
    'SalesChannel': [('WEB', 'Web', 'Website.'), ('APP', 'App', 'Mobile app.'),
                     ('POS', 'Point of sale', 'In-store register.'), ('VOICE', 'Voice', 'Voice assistant.')],
    'DeviceType': [('IOS', 'iOS', ''), ('ANDROID', 'Android', ''), ('DESKTOP', 'Desktop', ''),
                   ('ALEXA', 'Voice speaker', ''), ('KIOSK', 'Kiosk', '')],
    'SellerStatus': [('LIVE', 'Live', 'Selling.'), ('SUSPENDED', 'Suspended', 'Temporarily blocked.'),
                     ('CLOSED', 'Closed', 'No longer selling.')],
    'ItemCondition': [('NEW', 'New', ''), ('REFURBISHED', 'Refurbished', ''), ('USED', 'Used', ''),
                      ('OPEN_BOX', 'Open box', '')],
    'PromotionScope': [('SITEWIDE', 'Sitewide', 'Discounts every eligible line.'),
                       ('ORDER', 'Order level', 'Discounts the order or cart total.'),
                       ('ITEM', 'Item level', 'Discounts specific targeted lines.')],
    'FundingSource': [('PLATFORM', 'Platform', 'The retailer or marketplace pays.'),
                      ('SELLER', 'Seller', 'A third-party seller pays.'),
                      ('MANUFACTURER', 'Manufacturer', 'The brand or manufacturer pays.'),
                      ('PARTNER', 'Partner', 'An outside co-sponsor pays.')],
    'AttributeSource': [('SELLER', 'Seller', 'Entered by the seller.'),
                        ('BRAND', 'Brand', 'Supplied by the brand.'),
                        ('ML', 'Machine inferred', 'Inferred by a model; has a confidence.'),
                        ('CATALOG', 'Catalog', 'Curated by the catalog team.')],
    'WarrantyType': [('MANUFACTURER', 'Manufacturer warranty', 'Included by the manufacturer.'),
                     ('EXTENDED', 'Extended warranty', 'Sold separately.'),
                     ('NONE', 'No warranty', 'Explicitly no warranty.')],
    'CustomerStatus': [('ACTIVE', 'Active', ''), ('SUSPENDED', 'Suspended', ''), ('CLOSED', 'Closed', '')],
    'PaymentMethod': [('CARD', 'Card', ''), ('PAYPAL', 'PayPal', ''), ('APPLE_PAY', 'Apple Pay', ''),
                      ('GOOGLE_PAY', 'Google Pay', ''), ('GIFT_CARD', 'Gift card', ''),
                      ('STORE_CREDIT', 'Store credit', ''), ('CASH', 'Cash', ''),
                      ('BANK_TRANSFER', 'Bank transfer', '')],
    'PaymentStatus': [('AUTHORIZED', 'Authorized', ''), ('CAPTURED', 'Captured', ''), ('VOIDED', 'Voided', ''),
                      ('FAILED', 'Failed', ''), ('REFUNDED', 'Refunded', ''),
                      ('PARTIALLY_REFUNDED', 'Partially refunded', '')],
    'ShipmentStatus': [('PENDING', 'Pending', ''), ('PACKED', 'Packed', ''), ('SHIPPED', 'Shipped', ''),
                       ('IN_TRANSIT', 'In transit', ''), ('DELIVERED', 'Delivered', ''),
                       ('EXCEPTION', 'Exception', ''), ('RETURNED', 'Returned to sender', '')],
    'ReturnStatus': [('REQUESTED', 'Requested', ''), ('APPROVED', 'Approved', ''), ('REJECTED', 'Rejected', ''),
                     ('IN_TRANSIT', 'In transit', ''), ('RECEIVED', 'Received', ''),
                     ('INSPECTED', 'Inspected', ''), ('COMPLETED', 'Completed', ''),
                     ('CANCELLED', 'Cancelled', '')],
    'ReturnReason': [('DEFECTIVE', 'Defective', ''), ('DAMAGED_IN_TRANSIT', 'Damaged in transit', ''),
                     ('WRONG_ITEM', 'Wrong item', ''), ('NOT_AS_DESCRIBED', 'Not as described', ''),
                     ('MISSING_PARTS', 'Missing parts', ''), ('NO_LONGER_NEEDED', 'No longer needed', ''),
                     ('BETTER_PRICE', 'Better price elsewhere', ''),
                     ('ORDERED_BY_MISTAKE', 'Ordered by mistake', ''),
                     ('UNSPECIFIED', 'Unspecified', 'The source did not record a reason.')],
    'ReturnResolution': [('REFUND', 'Refund', ''), ('REPLACEMENT', 'Replacement', ''),
                         ('EXCHANGE', 'Exchange', ''), ('STORE_CREDIT', 'Store credit', ''),
                         ('REPAIR', 'Repair', '')],
    'ReturnedCondition': [('NEW', 'New', ''), ('OPENED', 'Opened', ''), ('USED', 'Used', ''),
                          ('DAMAGED', 'Damaged', ''), ('DEFECTIVE', 'Defective', ''),
                          ('MISSING_PARTS', 'Missing parts', '')],
    'Disposition': [('RESTOCK', 'Restock', ''), ('REFURBISH', 'Refurbish', ''),
                    ('RETURN_TO_VENDOR', 'Return to vendor', ''), ('LIQUIDATE', 'Liquidate', ''),
                    ('SCRAP', 'Scrap', '')],
    'RefundStatus': [('PENDING', 'Pending', ''), ('COMPLETED', 'Completed', ''), ('FAILED', 'Failed', '')],
}

# ---------------------------------------------------------------------
# Object properties: name -> (domain or None, range, label, definition,
#                             functional?, inverse name or None)
# ---------------------------------------------------------------------
OBJECT_PROPERTIES = {
    'hasCurrency': (None, 'Currency', 'has currency', 'Currency of the monetary amounts on this '
                    'resource.', True, None),
    'countryOfOrigin': (None, 'Country', 'country of origin', 'Where the product or brand comes from.',
                        True, None),
    'parentCategory': ('Category', 'Category', 'parent category', 'The broader category this one '
                       'sits under.', True, None),
    'ownedBy': ('Brand', 'Manufacturer', 'owned by', 'The manufacturer that owns the brand.', True, None),
    'headquartersCountry': ('Manufacturer', 'Country', 'headquarters country', '', True, None),
    'ofBrand': ('ProductModel', 'Brand', 'of brand', 'Brand the model is sold under.', True, None),
    'hasModel': ('Product', 'ProductModel', 'has model', 'Manufacturer model of the product.', True, None),
    'hasBrand': ('Product', 'Brand', 'has brand', 'Brand of the product. Usually the brand of its '
                 'model; stated directly when the model is unknown.', True, None),
    'inCategory': ('Product', 'Category', 'in category', 'Merchandising category.', False, None),
    'hasAttribute': ('Product', 'ProductAttribute', 'has attribute', '', False, 'attributeOf'),
    'attributeOf': ('ProductAttribute', 'Product', 'attribute of', '', True, 'hasAttribute'),
    'attributeSource': ('ProductAttribute', 'AttributeSource', 'attribute source', '', True, None),
    'hasWarranty': ('Product', 'WarrantyPlan', 'has warranty', '', False, None),
    'warrantyType': ('WarrantyPlan', 'WarrantyType', 'warranty type', '', True, None),
    'warrantyProduct': ('WarrantyPlan', 'Product', 'warranty product', 'The product sold to buy '
                        'this plan, for extended warranties.', True, None),
    'sellerCountry': ('Seller', 'Country', 'seller country', '', True, None),
    'defaultCurrency': ('Seller', 'Currency', 'default currency', '', True, None),
    'sellerStatus': ('Seller', 'SellerStatus', 'seller status', '', True, None),
    'offeredBy': ('Offer', 'Seller', 'offered by', '', True, None),
    'offerFor': ('Offer', 'Product', 'offer for', '', True, None),
    'itemCondition': ('Offer', 'ItemCondition', 'item condition', '', True, None),
    'operatedBy': ('Warehouse', 'Seller', 'operated by', '', True, None),
    'hasAddress': (None, 'Address', 'has address', 'A postal address of the resource.', False, None),
    'stockOf': ('InventoryPosition', 'Product', 'stock of', '', True, None),
    'heldAt': ('InventoryPosition', 'Warehouse', 'held at', '', True, None),
    'addressCountry': ('Address', 'Country', 'address country', '', True, None),
    'preferredCurrency': ('Customer', 'Currency', 'preferred currency', '', True, None),
    'customerStatus': ('Customer', 'CustomerStatus', 'customer status', '', True, None),
    'defaultBillingAddress': ('Customer', 'Address', 'default billing address', '', True, None),
    'defaultShippingAddress': ('Customer', 'Address', 'default shipping address', '', True, None),
    'placedBy': ('Order', 'Customer', 'placed by', 'Registered customer; absent for guests.', True, None),
    'orderStatus': ('Order', 'OrderStatus', 'order status', '', True, None),
    'salesChannel': ('Order', 'SalesChannel', 'sales channel', '', True, None),
    'deviceType': ('Order', 'DeviceType', 'device type', '', True, None),
    'billingAddress': (None, 'Address', 'billing address', 'Address used for billing (order or payment).',
                       True, None),
    'shippingAddress': ('Order', 'Address', 'shipping address', 'Where the order ships. May be '
                        'partial, e.g. postal code only.', True, None),
    'hasLine': ('Order', 'OrderLine', 'has line', '', False, 'lineOf'),
    'lineOf': ('OrderLine', 'Order', 'line of', '', True, 'hasLine'),
    'ofProduct': ('OrderLine', 'Product', 'of product', '', True, None),
    'soldBy': ('OrderLine', 'Seller', 'sold by', '', True, None),
    'fromOffer': ('OrderLine', 'Offer', 'from offer', '', True, None),
    'fulfilledFrom': ('OrderLine', 'Warehouse', 'fulfilled from', '', True, None),
    'addOnFor': ('OrderLine', 'OrderLine', 'add-on for', 'The line this add-on (e.g. a protection '
                 'plan) was sold with.', True, None),
    'originalCurrency': ('OrderLine', 'Currency', 'original currency', "Seller's currency when it "
                         'differs from the order currency.', True, None),
    'promotionScope': ('Promotion', 'PromotionScope', 'promotion scope', '', True, None),
    'fundedBy': ('Promotion', 'FundingSource', 'funded by', '', True, None),
    'fundingSeller': ('Promotion', 'Seller', 'funding seller', 'Seller paying for the promotion.', True, None),
    'fundingBrand': ('Promotion', 'Brand', 'funding brand', 'Brand whose manufacturer pays.', True, None),
    'appliesToProduct': ('Promotion', 'Product', 'applies to product', '', False, None),
    'appliesToModel': ('Promotion', 'ProductModel', 'applies to model', '', False, None),
    'appliesToBrand': ('Promotion', 'Brand', 'applies to brand', '', False, None),
    'appliesToCategory': ('Promotion', 'Category', 'applies to category', 'Includes sub-categories.',
                          False, None),
    'fromPromotion': ('AppliedDiscount', 'Promotion', 'from promotion', 'Absent for manual discounts.',
                      True, None),
    'appliedToOrder': ('AppliedDiscount', 'Order', 'applied to order', '', True, None),
    'appliedToLine': ('AppliedDiscount', 'OrderLine', 'applied to line', 'Absent for order-level '
                      'discounts.', True, None),
    'paysFor': ('Payment', 'Order', 'pays for', '', True, None),
    'paymentMethod': ('Payment', 'PaymentMethod', 'payment method', '', True, None),
    'paymentStatus': ('Payment', 'PaymentStatus', 'payment status', '', True, None),
    'shipmentOf': ('Shipment', 'Order', 'shipment of', '', True, None),
    'shippedBy': ('Shipment', 'Seller', 'shipped by', '', True, None),
    'shippedFrom': ('Shipment', 'Warehouse', 'shipped from', '', True, None),
    'shipTo': ('Shipment', 'Address', 'ship to', '', True, None),
    'shipmentStatus': ('Shipment', 'ShipmentStatus', 'shipment status', '', True, None),
    'inShipment': ('ShipmentLine', 'Shipment', 'in shipment', '', True, None),
    'shipsLine': ('ShipmentLine', 'OrderLine', 'ships line', '', True, None),
    'returnFor': ('ReturnAuthorization', 'Order', 'return for', 'Original order, when known.', True, None),
    'requestedBy': ('ReturnAuthorization', 'Customer', 'requested by', '', True, None),
    'returnStatus': ('ReturnAuthorization', 'ReturnStatus', 'return status', '', True, None),
    'returnTo': ('ReturnAuthorization', 'Warehouse', 'return to', '', True, None),
    'inReturn': ('ReturnLine', 'ReturnAuthorization', 'in return', '', True, None),
    'returnsLine': ('ReturnLine', 'OrderLine', 'returns line', 'Original order line, when known.', True, None),
    'returnedProduct': ('ReturnLine', 'Product', 'returned product', '', True, None),
    'returnReason': ('ReturnLine', 'ReturnReason', 'return reason', '', True, None),
    'requestedResolution': ('ReturnLine', 'ReturnResolution', 'requested resolution', '', True, None),
    'receivedCondition': ('ReturnLine', 'ReturnedCondition', 'received condition', '', True, None),
    'disposition': ('ReturnLine', 'Disposition', 'disposition', '', True, None),
    'replacementOrder': ('ReturnLine', 'Order', 'replacement order', '', True, None),
    'refundFor': ('Refund', 'Order', 'refund for', '', True, None),
    'forReturn': ('Refund', 'ReturnAuthorization', 'for return', '', True, None),
    'refundOfPayment': ('Refund', 'Payment', 'refund of payment', '', True, None),
    'refundStatus': ('Refund', 'RefundStatus', 'refund status', '', True, None),
}

# ---------------------------------------------------------------------
# Datatype properties: name -> (domain or None, xsd range, label,
#                               definition, value convention or '')
#   Sub-properties are declared in SUB_PROPERTIES below.
# ---------------------------------------------------------------------
MONEY = 'Major currency units of cc:hasCurrency (19.99).'
PCT = 'Fraction 0..1 (0.15 = 15%).'
UTC = 'UTC.'
DATA_PROPERTIES = {
    # generic
    'isActive': (None, 'boolean', 'is active', 'Whether the resource is currently in use.', ''),
    'createdAt': (None, 'dateTime', 'created at', 'When the source created the record.', UTC),
    'updatedAt': (None, 'dateTime', 'updated at', 'When the source last changed the record.', UTC),
    'effectiveFrom': (None, 'dateTime', 'effective from', 'Start of validity.', UTC),
    'effectiveUntil': (None, 'dateTime', 'effective until', 'End of validity; absent = open-ended.', UTC),
    'websiteUrl': (None, 'anyURI', 'website URL', '', ''),
    'phone': (None, 'string', 'phone', '', ''),
    'email': (None, 'string', 'email', 'Lower-case email address.', ''),
    'quantity': (None, 'integer', 'quantity', 'Number of units; always positive.', ''),
    'monetaryAmount': (None, 'decimal', 'monetary amount', 'Super-property of every money value.', MONEY),
    'identifier': (None, 'string', 'identifier', 'Super-property of every business identifier.', ''),
    # reference
    'countryCode': ('Country', 'string', 'country code', 'ISO 3166-1 alpha-2.', ''),
    'countryName': ('Country', 'string', 'country name', '', ''),
    'currencyCode': ('Currency', 'string', 'currency code', 'ISO 4217.', ''),
    'currencyName': ('Currency', 'string', 'currency name', '', ''),
    'minorUnitDigits': ('Currency', 'integer', 'minor unit digits', 'Digits after the decimal point '
                        '(2 for USD, 0 for JPY).', ''),
    # catalog
    'categoryCode': ('Category', 'string', 'category code', 'Stable code or full browse path.', ''),
    'categoryName': ('Category', 'string', 'category name', '', ''),
    'categoryDescription': ('Category', 'string', 'category description', '', ''),
    'sortOrder': ('Category', 'integer', 'sort order', '', ''),
    'manufacturerName': ('Manufacturer', 'string', 'manufacturer name', 'Legal company name.', ''),
    'manufacturerCode': ('Manufacturer', 'string', 'manufacturer code', 'Short code, e.g. SNY.', ''),
    'supportEmail': ('Manufacturer', 'string', 'support email', 'Warranty inquiries.', ''),
    'brandName': ('Brand', 'string', 'brand name', '', ''),
    'modelNumber': ('ProductModel', 'string', 'model number', "Manufacturer's model or part number.", ''),
    'modelName': ('ProductModel', 'string', 'model name', '', ''),
    'modelYear': ('ProductModel', 'integer', 'model year', '', ''),
    'releaseDate': ('ProductModel', 'date', 'release date', '', ''),
    'discontinuedDate': ('ProductModel', 'date', 'discontinued date', 'Absent while still sold.', ''),
    'sku': ('Product', 'string', 'SKU', "Retailer's stock keeping unit.", ''),
    'upc': ('Product', 'string', 'UPC', 'UPC-A barcode, 12 digits.', ''),
    'ean': ('Product', 'string', 'EAN', 'EAN-13 barcode.', ''),
    'gtin': ('Product', 'string', 'GTIN', 'GTIN-14 case barcode.', ''),
    'marketplaceProductId': ('Product', 'string', 'marketplace product id', 'Marketplace catalog '
                             'number, e.g. a BigRiver number.', ''),
    'productName': ('Product', 'string', 'product name', 'Short name for search results and carts.', ''),
    'productLongName': ('Product', 'string', 'product long name', 'Title for the detail page.', ''),
    'productDescription': ('Product', 'string', 'product description', '', ''),
    'weightInGrams': ('Product', 'integer', 'weight in grams', '', 'Grams.'),
    'msrp': ('Product', 'decimal', 'MSRP', "Manufacturer's suggested retail price.", MONEY),
    'isTaxable': ('Product', 'boolean', 'is taxable', '', ''),
    'isAdultOnly': ('Product', 'boolean', 'is adult only', '', ''),
    'attributeKey': ('ProductAttribute', 'string', 'attribute key', "Lower snake_case, e.g. 'color'.", ''),
    'attributeValue': ('ProductAttribute', 'string', 'attribute value', '', ''),
    'confidence': ('ProductAttribute', 'decimal', 'confidence', 'Only for machine-inferred values.', PCT),
    'durationMonths': ('WarrantyPlan', 'integer', 'duration in months', '', ''),
    'warrantyProvider': ('WarrantyPlan', 'string', 'warranty provider', '', ''),
    'coversParts': ('WarrantyPlan', 'boolean', 'covers parts', '', ''),
    'coversLabor': ('WarrantyPlan', 'boolean', 'covers labor', '', ''),
    'warrantyTerms': ('WarrantyPlan', 'string', 'warranty terms', '', ''),
    # sellers, offers, stock
    'sellerHandle': ('Seller', 'string', 'seller handle', 'URL-safe unique handle.', ''),
    'sellerName': ('Seller', 'string', 'seller name', '', ''),
    'isFirstParty': ('Seller', 'boolean', 'is first party', 'Sold by the platform itself.', ''),
    'sellerRating': ('Seller', 'decimal', 'seller rating', '0.0 to 5.0.', ''),
    'shipsFromRegion': ('Seller', 'string', 'ships from region', 'ISO 3166-2, e.g. US-NJ.', ''),
    'fulfilledByPlatform': ('Seller', 'boolean', 'fulfilled by platform', '', ''),
    'onboardedAt': ('Seller', 'dateTime', 'onboarded at', '', UTC),
    'price': ('Offer', 'decimal', 'price', '', MONEY),
    'cost': ('Offer', 'decimal', 'cost', "Seller's unit cost.", MONEY),
    'warehouseCode': ('Warehouse', 'string', 'warehouse code', '', ''),
    'warehouseName': ('Warehouse', 'string', 'warehouse name', '', ''),
    'quantityOnHand': ('InventoryPosition', 'integer', 'quantity on hand', '', ''),
    'quantityReserved': ('InventoryPosition', 'integer', 'quantity reserved', '', ''),
    'quantityOnOrder': ('InventoryPosition', 'integer', 'quantity on order', '', ''),
    'reorderPoint': ('InventoryPosition', 'integer', 'reorder point', '', ''),
    'binLocation': ('InventoryPosition', 'string', 'bin location', '', ''),
    'lastCountedDate': ('InventoryPosition', 'date', 'last counted date', '', ''),
    # customers and addresses
    'customerNumber': ('Customer', 'string', 'customer number', 'Account number or id.', ''),
    'loyaltyNumber': ('Customer', 'string', 'loyalty number', '', ''),
    'firstName': ('Customer', 'string', 'first name', '', ''),
    'lastName': ('Customer', 'string', 'last name', '', ''),
    'marketingOptIn': ('Customer', 'boolean', 'marketing opt-in', '', ''),
    'recipientName': ('Address', 'string', 'recipient name', '', ''),
    'streetAddress': ('Address', 'string', 'street address', 'Street lines joined by newlines.', ''),
    'city': ('Address', 'string', 'city', '', ''),
    'regionCode': ('Address', 'string', 'region code', 'ISO 3166-2, e.g. US-TX.', ''),
    'postalCode': ('Address', 'string', 'postal code', '', ''),
    # orders
    'orderNumber': ('Order', 'string', 'order number', 'Human-readable number; unique within its source.', ''),
    'customerEmail': ('Order', 'string', 'customer email', 'Email on the order; required for guests.', ''),
    'subtotalAmount': ('Order', 'decimal', 'subtotal', 'Sum of quantity x unit price, before discounts.', MONEY),
    'discountTotal': ('Order', 'decimal', 'discount total', '', MONEY),
    'taxTotal': ('Order', 'decimal', 'tax total', '', MONEY),
    'shippingTotal': ('Order', 'decimal', 'shipping total', '', MONEY),
    'grandTotal': ('Order', 'decimal', 'grand total', 'subtotal - discount + tax + shipping.', MONEY),
    'placedAt': ('Order', 'dateTime', 'placed at', 'When checkout completed.', UTC),
    'closedAt': ('Order', 'dateTime', 'closed at', 'When it was abandoned, expired or cancelled.', UTC),
    'lineNumber': ('OrderLine', 'integer', 'line number', '', ''),
    'unitPrice': ('OrderLine', 'decimal', 'unit price', 'Price per unit in the order currency.', MONEY),
    'originalUnitPrice': ('OrderLine', 'decimal', 'original unit price', "Price in the seller's "
                          'currency (cc:originalCurrency).', 'Major units of cc:originalCurrency.'),
    'exchangeRateToUSD': ('OrderLine', 'decimal', 'exchange rate to USD', 'USD per one unit of the '
                          'line currency, captured when added.', ''),
    'lineDiscount': ('OrderLine', 'decimal', 'line discount', '', MONEY),
    'lineTax': ('OrderLine', 'decimal', 'line tax', '', MONEY),
    'lineTotal': ('OrderLine', 'decimal', 'line total', 'quantity x unit price - line discount.', MONEY),
    'isSubscription': ('OrderLine', 'boolean', 'is subscription', 'Part of a subscribe-and-save plan.', ''),
    'isGift': ('OrderLine', 'boolean', 'is gift', '', ''),
    'giftMessage': ('OrderLine', 'string', 'gift message', '', ''),
    'giftWrap': ('OrderLine', 'boolean', 'gift wrap', '', ''),
    'addedAt': ('OrderLine', 'dateTime', 'added at', 'When the line was added to the cart.', UTC),
    'removedAt': ('OrderLine', 'dateTime', 'removed at', 'When the shopper removed the line.', UTC),
    'isRemoved': ('OrderLine', 'boolean', 'is removed', 'The shopper took the line out of the cart.', ''),
    # promotions and discounts
    'promotionCode': ('Promotion', 'string', 'promotion code', 'Absent for automatic deals.', ''),
    'promotionName': ('Promotion', 'string', 'promotion name', '', ''),
    'promotionDescription': ('Promotion', 'string', 'promotion description', '', ''),
    'eventName': ('Promotion', 'string', 'event name', "e.g. 'Black Friday'.", ''),
    'partnerCompany': ('Promotion', 'string', 'partner company', 'External co-sponsor.', ''),
    'discountPercent': ('Promotion', 'decimal', 'discount percent', '', PCT),
    'amountOff': ('Promotion', 'decimal', 'amount off', 'Flat amount off.', MONEY),
    'minimumOrderAmount': ('Promotion', 'decimal', 'minimum order amount', '', MONEY),
    'buyQuantity': ('Promotion', 'integer', 'buy quantity', "'Buy 2 get 1': 2.", ''),
    'getQuantity': ('Promotion', 'integer', 'get quantity', "'Buy 2 get 1': 1.", ''),
    'maxRedemptions': ('Promotion', 'integer', 'max redemptions', '', ''),
    'isStackable': ('Promotion', 'boolean', 'is stackable', 'Can combine with other promotions.', ''),
    'targetAttributeKey': ('Promotion', 'string', 'target attribute key', 'Applies to products '
                           'with this attribute key...', ''),
    'targetAttributeValue': ('Promotion', 'string', 'target attribute value', '...and this value.', ''),
    'discountAmount': ('AppliedDiscount', 'decimal', 'discount amount', '', MONEY),
    'discountReason': ('AppliedDiscount', 'string', 'discount reason', 'Free-text reason, e.g. '
                       "'manager override'.", ''),
    'appliedAt': ('AppliedDiscount', 'dateTime', 'applied at', '', UTC),
    # payments, shipments, returns
    'paymentAmount': ('Payment', 'decimal', 'payment amount', '', MONEY),
    'cardBrand': ('Payment', 'string', 'card brand', '', ''),
    'cardLast4': ('Payment', 'string', 'card last 4', 'Never the full card number.', ''),
    'processorReference': (None, 'string', 'processor reference', 'Payment gateway reference.', ''),
    'authorizedAt': ('Payment', 'dateTime', 'authorized at', '', UTC),
    'capturedAt': ('Payment', 'dateTime', 'captured at', '', UTC),
    'carrier': ('Shipment', 'string', 'carrier', '', ''),
    'serviceLevel': ('Shipment', 'string', 'service level', '', ''),
    'trackingNumber': ('Shipment', 'string', 'tracking number', '', ''),
    'shippingCost': ('Shipment', 'decimal', 'shipping cost', '', MONEY),
    'shippedAt': ('Shipment', 'dateTime', 'shipped at', '', UTC),
    'deliveredAt': ('Shipment', 'dateTime', 'delivered at', '', UTC),
    'rmaNumber': ('ReturnAuthorization', 'string', 'RMA number', '', ''),
    'requestedAt': ('ReturnAuthorization', 'dateTime', 'requested at', '', UTC),
    'approvedAt': ('ReturnAuthorization', 'dateTime', 'approved at', '', UTC),
    'receivedAt': ('ReturnAuthorization', 'dateTime', 'received at', '', UTC),
    'returnClosedAt': ('ReturnAuthorization', 'dateTime', 'return closed at', '', UTC),
    'restockingFee': ('ReturnLine', 'decimal', 'restocking fee', '', MONEY),
    'refundAmount': ('Refund', 'decimal', 'refund amount', '', MONEY),
    'refundedAt': ('Refund', 'dateTime', 'refunded at', '', UTC),
}

SUB_PROPERTIES = {
    'monetaryAmount': ['msrp', 'price', 'cost', 'subtotalAmount', 'discountTotal', 'taxTotal',
                       'shippingTotal', 'grandTotal', 'unitPrice', 'originalUnitPrice', 'lineDiscount',
                       'lineTax', 'lineTotal', 'amountOff', 'minimumOrderAmount', 'discountAmount',
                       'paymentAmount', 'shippingCost', 'restockingFee', 'refundAmount'],
    'identifier': ['sku', 'upc', 'ean', 'gtin', 'marketplaceProductId', 'modelNumber', 'orderNumber',
                   'customerNumber', 'loyaltyNumber', 'promotionCode', 'rmaNumber', 'sellerHandle',
                   'warehouseCode', 'categoryCode', 'manufacturerCode', 'trackingNumber'],
    'email': ['customerEmail', 'supportEmail'],
}

# owl:hasKey for reference data whose keys are global standards.
KEYS = {'Country': ['countryCode'], 'Currency': ['currencyCode']}

# Disjoint top-level business concepts (code lists excluded).
DISJOINT = ['Category', 'Manufacturer', 'Brand', 'ProductModel', 'Product', 'ProductAttribute',
            'WarrantyPlan', 'Seller', 'Offer', 'Warehouse', 'InventoryPosition', 'Customer', 'Address',
            'Order', 'OrderLine', 'Promotion', 'AppliedDiscount', 'Payment', 'Shipment', 'ShipmentLine',
            'ReturnAuthorization', 'ReturnLine', 'Refund', 'Country', 'Currency', 'CodeList']
