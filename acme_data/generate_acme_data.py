"""Generate sample data for AcmeShopping (acme_shopping.sql).

Fictional hardware store selling garden, home improvement and DIY tools.
Every brand, product, customer and email address is made up; emails use
the reserved example.com domain and websites the reserved .example TLD.

Output: acme_sample_data.sql (INSERT statements) next to this script.
The data is deterministic (fixed random seed), so re-running produces
the same file.

    python3 generate_acme_data.py [--orders 500] [--seed 42]
    sqlite3 acme.db < ../acme_shopping.sql
    sqlite3 acme.db < acme_sample_data.sql

Money follows the Acme conventions: NUMERIC dollars, discount percents
as whole numbers (15.00 = 15%). Totals are computed in cents and always
add up: LineTotal = Quantity * UnitPrice - LineDiscount and
GrandTotal = SubTotal - DiscountTotal + TaxTotal + ShippingTotal.
"""
import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------
# Catalog definition
# ---------------------------------------------------------------------

# (id, parent id, name, short description)
CATEGORIES = [
    (1,  None, 'Garden',                 'Lawn, garden and outdoor tools'),
    (2,  None, 'Home Improvement',       'Paint, plumbing, electrical and more'),
    (3,  None, 'DIY Tools',              'Power tools, hand tools and hardware'),
    (10, 1,    'Lawn Mowers & Trimmers', 'Mowers, string trimmers and edgers'),
    (11, 1,    'Garden Hand Tools',      'Shovels, rakes, pruners and trowels'),
    (12, 1,    'Watering & Irrigation',  'Hoses, sprinklers and drip kits'),
    (13, 1,    'Planters & Soil',        'Pots, raised beds, soil and mulch'),
    (20, 2,    'Paint & Supplies',       'Paint, brushes, rollers and tape'),
    (21, 2,    'Plumbing',               'Faucets, fittings and repair kits'),
    (22, 2,    'Electrical',             'Outlets, switches, wire and boxes'),
    (23, 2,    'Lighting',               'Fixtures, bulbs and outdoor lights'),
    (24, 2,    'Flooring',               'Laminate, vinyl plank and underlayment'),
    (30, 3,    'Power Tools',            'Corded and cordless power tools'),
    (31, 30,   'Drills & Drivers',       'Drills, impact drivers and bits'),
    (32, 30,   'Saws',                   'Circular, miter, jig and reciprocating saws'),
    (33, 30,   'Sanders & Grinders',     'Orbital sanders and angle grinders'),
    (34, 3,    'Hand Tools',             'Hammers, wrenches, pliers and screwdrivers'),
    (35, 3,    'Fasteners & Hardware',   'Screws, nails, anchors and hinges'),
    (36, 3,    'Storage & Workbenches',  'Tool boxes, chests and workbenches'),
    (37, 3,    'Ladders',                'Step, extension and multi-position ladders'),
]

# (name, manufacturer legal name, country, departments it sells in)
BRANDS = [
    ('Ironwood Tools',     'Ironwood Tool Company, Inc.',      'US', {3}),
    ('Kestrel Power',      'Kestrel Power Tools Co., Ltd.',    'TW', {3}),
    ('VoltEdge',           'VoltEdge Industries GmbH',         'DE', {3, 2}),
    ('SureGrip',           'SureGrip Hand Tools LLC',          'US', {3, 1}),
    ('TrueLevel',          'TrueLevel Instruments Ltd.',       'GB', {3}),
    ('Summit Ladders',     'Summit Climbing Products Corp.',   'US', {3}),
    ('Granite & Grain',    'Granite and Grain Workshop Co.',   'CA', {3, 2}),
    ('Bramblewood Garden', 'Bramblewood Outdoor Living Inc.',  'US', {1}),
    ('GreenThumb',         'GreenThumb Horticulture Ltd.',     'CA', {1}),
    ('TerraForge',         'TerraForge Outdoor Equipment Co.', 'US', {1}),
    ('AquaFlow',           'AquaFlow Water Products Ltd.',     'CN', {1, 2}),
    ('Northpeak',          'Northpeak Manufacturing S.A.',     'MX', {1, 3}),
    ('Brightline',         'Brightline Electric Co., Ltd.',    'VN', {2}),
    ('Copperleaf',         'Copperleaf Plumbing Supply Inc.',  'US', {2}),
    ('Hearthstone Home',   'Hearthstone Home Products Corp.',  'US', {2}),
    ('Driftstone Floors',  'Driftstone Flooring K.K.',         'JP', {2}),
    ('Oakhaven Paints',    'Oakhaven Coatings Company',        'US', {2}),
    ('PlankMaster',        'PlankMaster Fastening Co., Ltd.',  'KR', {3, 2}),
]

# category id -> [(product name, price range $, weight range lbs, max qty)]
PRODUCT_TYPES = {
    10: [('{v}V Cordless String Trimmer', (89, 219), (6, 11), 1),
         ('21" Self-Propelled Gas Mower', (299, 549), (65, 85), 1),
         ('{v}V Brushless Lawn Mower', (329, 649), (45, 62), 1),
         ('Cordless Leaf Blower', (99, 249), (5, 9), 1),
         ('Electric Hedge Trimmer', (59, 149), (6, 9), 1)],
    11: [('Round Point Shovel', (24, 49), (4, 6), 2),
         ('Bypass Pruning Shears', (14, 39), (0.4, 0.8), 3),
         ('Steel Bow Rake', (19, 39), (3, 5), 2),
         ('Ergonomic Hand Trowel', (8, 19), (0.3, 0.6), 4),
         ('Telescoping Loppers', (34, 69), (3, 5), 1)],
    12: [('50 ft Kink-Free Garden Hose', (29, 69), (6, 10), 3),
         ('Oscillating Lawn Sprinkler', (14, 39), (1, 2), 3),
         ('Drip Irrigation Starter Kit', (39, 89), (2, 4), 2),
         ('8-Pattern Hose Nozzle', (9, 24), (0.4, 0.8), 4),
         ('Wall-Mount Hose Reel', (49, 129), (10, 18), 1)],
    13: [('Cedar Raised Garden Bed 4x8', (89, 189), (40, 60), 1),
         ('Premium Potting Mix 2 cu ft', (9, 18), (20, 25), 6),
         ('Self-Watering Planter 16"', (24, 59), (3, 6), 4),
         ('Natural Hardwood Mulch 2 cu ft', (4, 8), (20, 30), 10)],
    20: [('Interior Eggshell Paint 1 gal', (29, 64), (10, 12), 4),
         ('Exterior Satin Paint 5 gal', (169, 289), (55, 60), 2),
         ('9" Paint Roller Kit', (14, 29), (2, 3), 3),
         ('Angled Sash Brush 2.5"', (8, 22), (0.2, 0.4), 4),
         ('Multi-Surface Painter\'s Tape 3-Pack', (12, 24), (1, 2), 5)],
    21: [('Single-Handle Kitchen Faucet', (89, 249), (5, 8), 1),
         ('PEX Crimp Tool Kit', (39, 89), (2, 4), 1),
         ('Toilet Repair Kit', (14, 34), (1, 2), 2),
         ('Brass Ball Valve 3/4"', (9, 24), (0.6, 1.2), 4),
         ('Water Heater Expansion Tank', (39, 79), (5, 8), 1)],
    22: [('Tamper-Resistant Outlet 10-Pack', (14, 39), (1, 2), 3),
         ('Smart Wi-Fi Light Switch', (19, 44), (0.3, 0.6), 6),
         ('12/2 NM-B Wire 50 ft', (49, 89), (8, 11), 3),
         ('Non-Contact Voltage Tester', (14, 34), (0.2, 0.4), 2),
         ('GFCI Outlet 20A', (16, 29), (0.4, 0.6), 6)],
    23: [('LED A19 Bulb 8-Pack', (12, 29), (1, 2), 4),
         ('Solar Pathway Lights 6-Pack', (29, 69), (3, 5), 3),
         ('Motion-Sensor Flood Light', (39, 99), (2, 4), 2),
         ('Flush Mount Ceiling Light', (34, 119), (3, 6), 3),
         ('Under-Cabinet LED Light Kit', (29, 79), (1, 3), 2)],
    24: [('Waterproof Vinyl Plank 20 sq ft', (45, 89), (35, 45), 10),
         ('Laminate Flooring 24 sq ft', (39, 79), (40, 50), 10),
         ('Foam Underlayment 100 sq ft', (19, 39), (4, 6), 4),
         ('Flooring Installation Kit', (19, 39), (3, 5), 1)],
    31: [('{v}V Brushless Drill/Driver Kit', (99, 229), (3, 5), 1),
         ('{v}V Impact Driver', (89, 199), (2.5, 4), 1),
         ('Hammer Drill 1/2" Corded', (69, 149), (5, 7), 1),
         ('Drill & Drive Bit Set 100-Piece', (19, 49), (2, 3), 2)],
    32: [('7-1/4" Circular Saw', (79, 189), (8, 12), 1),
         ('10" Sliding Compound Miter Saw', (229, 499), (45, 60), 1),
         ('{v}V Cordless Jig Saw', (89, 179), (4, 6), 1),
         ('Reciprocating Saw', (79, 169), (7, 9), 1),
         ('Circular Saw Blade 3-Pack', (19, 44), (1, 2), 3)],
    33: [('5" Random Orbit Sander', (59, 129), (3, 5), 1),
         ('4-1/2" Angle Grinder', (49, 119), (4, 6), 1),
         ('Sanding Disc Assortment 50-Pack', (14, 29), (1, 2), 3),
         ('Detail Sander', (39, 79), (2, 3), 1)],
    34: [('16 oz Fiberglass Claw Hammer', (19, 39), (1.5, 2), 2),
         ('Ratcheting Screwdriver Set', (19, 49), (1, 2), 2),
         ('Adjustable Wrench Set 3-Piece', (24, 54), (2, 3), 2),
         ('Mechanics Tool Set 120-Piece', (89, 179), (12, 18), 1),
         ('Locking Pliers Set', (24, 49), (2, 3), 2),
         ('25 ft Tape Measure', (12, 29), (0.8, 1.2), 3),
         ('48" Box Beam Level', (29, 79), (2, 4), 1)],
    35: [('Deck Screws #8 x 2-1/2" 5 lb', (24, 44), (5, 5), 6),
         ('Drywall Anchor Kit 200-Piece', (12, 24), (1, 2), 4),
         ('Galvanized Common Nails 5 lb', (14, 26), (5, 5), 6),
         ('Heavy-Duty Door Hinges 3-Pack', (9, 22), (1, 2), 6),
         ('Cabinet Hardware Pulls 10-Pack', (19, 45), (1, 2), 4)],
    36: [('26" Rolling Tool Chest', (199, 449), (80, 120), 1),
         ('Portable Tool Box 22"', (24, 59), (4, 7), 2),
         ('Adjustable Steel Workbench 6 ft', (149, 329), (70, 95), 1),
         ('Wall Pegboard Organizer Kit', (34, 79), (8, 14), 2)],
    37: [('6 ft Fiberglass Step Ladder', (89, 169), (14, 18), 1),
         ('24 ft Aluminum Extension Ladder', (219, 399), (35, 45), 1),
         ('17 ft Multi-Position Ladder', (179, 299), (30, 38), 1),
         ('2-Step Folding Stool', (29, 59), (6, 9), 2)],
}

# Seasonality: relative order volume per month (garden peaks in spring).
MONTH_WEIGHT = {1: 0.6, 2: 0.7, 3: 1.2, 4: 1.6, 5: 1.7, 6: 1.3,
                7: 1.0, 8: 0.9, 9: 0.9, 10: 0.9, 11: 1.4, 12: 1.2}

FIRST_NAMES = ['Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Jamie',
               'Avery', 'Quinn', 'Rowan', 'Sam', 'Drew', 'Reese', 'Kai', 'Emerson',
               'Harper', 'Logan', 'Parker', 'Skyler', 'Dakota', 'Finley', 'Hayden']
LAST_NAMES = ['Rivera', 'Chen', 'Patel', 'Okafor', 'Novak', 'Haddad', 'Lindqvist',
              'Moreau', 'Tanaka', 'Kowalski', 'Brennan', 'Silva', 'Nguyen', 'Fischer',
              'Abara', 'Larsen', 'Duarte', 'Whitfield', 'Ibarra', 'Sato']
US_ZIPS = ['02139', '10027', '19103', '27601', '30309', '33139', '37203', '44113',
           '48226', '53202', '55401', '60614', '63110', '64108', '73102', '75201',
           '78701', '80202', '84111', '85004', '89501', '94110', '97205', '98101']
CA_POSTAL = ['M5V 2T6', 'H2X 1Y4', 'V6B 1A1', 'T2P 3E5', 'K1P 5J2']
GIFT_MESSAGES = ['Happy birthday! Build something great.',
                 'Congrats on the new house!',
                 'Happy Father\'s Day!',
                 'For your garden - enjoy the spring!',
                 'Merry Christmas from all of us.',
                 'Thanks for all your help with the deck.']
TAX_RATE_BY_ZIP_PREFIX = {'0': 0.0625, '1': 0.08875, '2': 0.0725, '3': 0.07,
                          '4': 0.0675, '5': 0.055, '6': 0.0625, '7': 0.0825,
                          '8': 0.0685, '9': 0.0725}


def upc_with_check_digit(body11: str) -> str:
    """UPC-A: 11 digits + check digit."""
    odd = sum(int(d) for d in body11[0::2])
    even = sum(int(d) for d in body11[1::2])
    return body11 + str((10 - (odd * 3 + even) % 10) % 10)


def money(cents: int) -> str:
    return f'{cents / 100:.2f}'


def sql(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert(table: str, columns: list, rows: list) -> str:
    cols = ', '.join(f'"{c}"' for c in columns)
    lines = [f'INSERT INTO "{table}" ({cols}) VALUES']
    lines += ['    (' + ', '.join(r) + ')' + (',' if i < len(rows) - 1 else ';')
              for i, r in enumerate(rows)]
    return '\n'.join(lines)


def ts(d: datetime) -> str:
    return d.strftime('%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------

def build_brands():
    rows = []
    for i, (name, legal, country, _) in enumerate(BRANDS, start=1):
        slug = ''.join(c for c in name.lower() if c.isalnum())
        rows.append(dict(BrandId=i, BrandName=name, ManufacturerName=legal,
                         CountryOfOrigin=country,
                         WebsiteUrl=f'https://www.{slug}.example',
                         CreatedDate='2024-01-15 09:00:00',
                         LastUpdate='2024-01-15 09:00:00'))
    return rows


def department_of(category_id):
    parents = {c[0]: c[1] for c in CATEGORIES}
    while parents[category_id] is not None:
        category_id = parents[category_id]
    return category_id


def build_models(rng, brands):
    models, model_id, sku = [], 1, 10001
    for category_id, types in PRODUCT_TYPES.items():
        dept = department_of(category_id)
        sellers = [b for b, spec in zip(brands, BRANDS) if dept in spec[3]]
        for name, (p_lo, p_hi), (w_lo, w_hi), max_qty in types:
            for brand in rng.sample(sellers, k=min(len(sellers), rng.choice([1, 2, 2, 3]))):
                volts = rng.choice([18, 20, 40]) if '{v}' in name else None
                model_name = f"{brand['BrandName']} {name.format(v=volts)}"
                code = ''.join(w[0] for w in brand['BrandName'].replace('&', '').split()).upper()
                release = date(2021, 1, 1) + timedelta(days=rng.randint(0, 1500))
                discontinued = rng.random() < 0.06
                msrp_cents = rng.randint(p_lo, p_hi) * 100 + rng.choice([99, 99, 49, 0])
                models.append(dict(
                    ModelId=model_id,
                    BrandId=brand['BrandId'],
                    CategoryId=category_id,
                    ModelNumber=f'{code}-{rng.randint(1000, 9999)}{rng.choice("ABCDEFX")}',
                    ModelName=model_name,
                    Sku=f'ACME-{sku}',
                    UpcCode=upc_with_check_digit(f'0{rng.randint(10**9, 10**10 - 1)}'),
                    MSRP=msrp_cents,
                    CurrencyCode='USD',
                    WeightLbs=round(rng.uniform(w_lo, w_hi), 3),
                    ReleaseDate=release.isoformat(),
                    EffectiveDate=f'{release.isoformat()} 00:00:00',
                    ExpirationDate='2026-06-30 23:59:59' if discontinued else None,
                    CreatedDate=f'{(release - timedelta(days=30)).isoformat()} 09:00:00',
                    LastUpdate='2026-07-01 02:00:00' if discontinued
                               else f'{(release + timedelta(days=rng.randint(0, 300))).isoformat()} 09:00:00',
                    IsDiscontinued=discontinued,
                    max_qty=max_qty))
                model_id += 1
                sku += 1
    return models


def build_promotions(brands, models):
    by_name = {b['BrandName']: b['BrandId'] for b in brands}
    feature_model = next(m for m in models if 'Miter Saw' in m['ModelName'])
    p = []

    def add(**kw):
        base = dict(PromotionCode=None, EventName=None, AppliesToModelId=None,
                    AppliesToBrandId=None, AppliesToCategoryId=None,
                    DiscountPercent=None, DiscountAmount=None, MinimumOrderAmount=None,
                    AssociatedCompany=None, IsActive=True, IsStackable=False)
        base.update(kw)
        base['PromotionId'] = len(p) + 1
        p.append(base)

    add(PromotionName='Spring Garden Kickoff 2025', PromotionType='CATEGORY',
        EventName='Spring Garden Kickoff', AppliesToCategoryId=1, DiscountPercent=15,
        EffectiveDate='2025-03-15 00:00:00', ExpirationDate='2025-04-30 23:59:59')
    add(PromotionName='Spring Garden Kickoff 2026', PromotionType='CATEGORY',
        EventName='Spring Garden Kickoff', AppliesToCategoryId=1, DiscountPercent=15,
        EffectiveDate='2026-03-15 00:00:00', ExpirationDate='2026-04-30 23:59:59')
    add(PromotionName="Father's Day Power Tool Sale 2025", PromotionType='CATEGORY',
        EventName="Father's Day", AppliesToCategoryId=30, DiscountPercent=20,
        EffectiveDate='2025-06-01 00:00:00', ExpirationDate='2025-06-15 23:59:59')
    add(PromotionName="Father's Day Power Tool Sale 2026", PromotionType='CATEGORY',
        EventName="Father's Day", AppliesToCategoryId=30, DiscountPercent=20,
        EffectiveDate='2026-06-01 00:00:00', ExpirationDate='2026-06-21 23:59:59')
    add(PromotionName='Black Friday Doorbusters 2025', PromotionType='EVENT',
        EventName='Black Friday', DiscountPercent=25,
        EffectiveDate='2025-11-28 00:00:00', ExpirationDate='2025-12-01 23:59:59')
    add(PromotionName='Kestrel Power Brand Days', PromotionType='BRAND',
        AppliesToBrandId=by_name['Kestrel Power'], DiscountPercent=10,
        AssociatedCompany='Kestrel Power Tools Co., Ltd.',
        EffectiveDate='2025-09-01 00:00:00', ExpirationDate='2025-09-30 23:59:59')
    add(PromotionName='Oakhaven Paint Weekend', PromotionType='BRAND',
        AppliesToBrandId=by_name['Oakhaven Paints'], DiscountPercent=30,
        AssociatedCompany='Oakhaven Coatings Company',
        EffectiveDate='2026-05-22 00:00:00', ExpirationDate='2026-05-25 23:59:59')
    add(PromotionName=f"$50 Off {feature_model['ModelName']}", PromotionType='MODEL',
        AppliesToModelId=feature_model['ModelId'], DiscountAmount=5000,
        EffectiveDate='2025-07-01 00:00:00', ExpirationDate='2026-08-31 23:59:59')
    add(PromotionName='$10 Off Orders Over $100', PromotionType='ORDER',
        PromotionCode='SAVE10', DiscountAmount=1000, MinimumOrderAmount=10000,
        EffectiveDate='2025-01-01 00:00:00', ExpirationDate=None)
    add(PromotionName='New Customer 10% Off', PromotionType='ORDER',
        PromotionCode='WELCOME10', DiscountPercent=10, MinimumOrderAmount=2500,
        EffectiveDate='2025-01-01 00:00:00', ExpirationDate=None)
    add(PromotionName='Winter Workshop Clearance', PromotionType='CATEGORY',
        PromotionCode='WORKSHOP15', AppliesToCategoryId=36, DiscountPercent=15,
        EffectiveDate='2026-01-05 00:00:00', ExpirationDate='2026-02-28 23:59:59',
        IsActive=False)
    return p


def build_customers(rng, count=180):
    customers = []
    for cid in range(1, count + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f'{first.lower()}.{last.lower()}{cid}@example.com'
        canada = rng.random() < 0.06
        customers.append(dict(CustomerId=7000 + cid, email=email,
                              country='CA' if canada else 'US',
                              postal=rng.choice(CA_POSTAL if canada else US_ZIPS)))
    return customers


def category_ancestors(category_id):
    parents = {c[0]: c[1] for c in CATEGORIES}
    out = []
    while category_id is not None:
        out.append(category_id)
        category_id = parents[category_id]
    return out


def promo_active(promo, when: datetime):
    start = datetime.fromisoformat(promo['EffectiveDate'])
    end = datetime.fromisoformat(promo['ExpirationDate']) if promo['ExpirationDate'] else None
    return promo['IsActive'] and start <= when and (end is None or when <= end)


def line_qualifies(promo, model):
    t = promo['PromotionType']
    if t == 'EVENT':
        return True
    if t == 'CATEGORY':
        return promo['AppliesToCategoryId'] in category_ancestors(model['CategoryId'])
    if t == 'BRAND':
        return promo['AppliesToBrandId'] == model['BrandId']
    if t == 'MODEL':
        return promo['AppliesToModelId'] == model['ModelId']
    return False


def random_order_time(rng, start: date, end: date) -> datetime:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    weights = [MONTH_WEIGHT[d.month] * (1.6 if d.weekday() >= 5 else 1.0) for d in days]
    d = rng.choices(days, weights=weights)[0]
    hour = rng.choices(range(24), weights=[1, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 10,
                                           10, 9, 8, 8, 8, 9, 10, 10, 8, 5, 3, 2])[0]
    return datetime(d.year, d.month, d.day, hour, rng.randint(0, 59), rng.randint(0, 59))


def build_orders(rng, n_orders, models, promotions, customers, as_of: datetime):
    sellable = [m for m in models if not m['IsDiscontinued']]
    orders, items = [], []
    times = sorted(random_order_time(rng, date(2025, 1, 1), as_of.date() - timedelta(days=1))
                   for _ in range(n_orders))
    item_id = 1
    for n, when in enumerate(times, start=1):
        registered = rng.random() < 0.72
        cust = rng.choice(customers) if registered else None
        if cust:
            email, country, postal = cust['email'], cust['country'], cust['postal']
        else:
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            email = f'{first.lower()}{rng.randint(10, 999)}@example.com'
            country, postal = 'US', rng.choice(US_ZIPS)

        # Pick a promotion the customer could use on this date (~30% of orders).
        active = [p for p in promotions if promo_active(p, when)]
        promo = rng.choice(active) if active and rng.random() < 0.30 else None

        # Lines: favour products the promotion applies to, so it gets used.
        n_lines = rng.choices([1, 2, 3, 4, 5], weights=[38, 30, 18, 9, 5])[0]
        pool = sellable
        if promo and promo['PromotionType'] != 'ORDER':
            pool = [m for m in sellable if line_qualifies(promo, m)] or sellable
        picked = rng.sample(pool, k=1) + rng.sample(sellable, k=n_lines - 1)
        picked = list({m['ModelId']: m for m in picked}.values())   # no duplicate models

        lines, subtotal, line_disc_total = [], 0, 0
        for line_no, m in enumerate(picked, start=1):
            qty = rng.randint(1, m['max_qty']) if rng.random() < 0.35 else 1
            unit = m['MSRP'] if rng.random() < 0.8 else int(round(m['MSRP'] * rng.choice([0.9, 0.95]) / 100) * 100 - 1)
            disc = 0
            if promo and promo['PromotionType'] != 'ORDER' and line_qualifies(promo, m):
                if promo['DiscountPercent']:
                    disc = round(qty * unit * promo['DiscountPercent'] / 100)
                else:
                    disc = min(promo['DiscountAmount'] * qty, qty * unit)
            gift = rng.random() < 0.05
            lines.append(dict(OrderItemId=item_id, LineNumber=line_no, ModelId=m['ModelId'],
                              Quantity=qty, UnitPrice=unit, LineDiscount=disc,
                              LineTotal=qty * unit - disc, IsGift=gift,
                              GiftMessage=rng.choice(GIFT_MESSAGES) if gift else None,
                              GiftWrap=gift and rng.random() < 0.6))
            item_id += 1
            subtotal += qty * unit
            line_disc_total += disc

        order_disc = 0
        if promo and promo['PromotionType'] == 'ORDER':
            if subtotal >= (promo['MinimumOrderAmount'] or 0):
                order_disc = promo['DiscountAmount'] or round(subtotal * promo['DiscountPercent'] / 100)
            else:
                promo = None                        # code entered but order too small
        if promo and promo['PromotionType'] != 'ORDER' and line_disc_total == 0:
            promo = None
        discount_total = line_disc_total + order_disc

        taxable = subtotal - discount_total
        rate = 0.13 if country == 'CA' else TAX_RATE_BY_ZIP_PREFIX[postal[0]]
        tax = round(taxable * rate)
        heavy = any(next(mm for mm in models if mm['ModelId'] == l['ModelId'])['WeightLbs'] > 40
                    for l in lines)
        shipping = 0 if taxable >= 4900 and not heavy else (4999 if heavy else 799)
        if country == 'CA':
            shipping += 1500

        age = (as_of - when).days
        status = ('Pending' if age < 4 else 'Shipped' if age < 14 else 'Delivered')
        r = rng.random()
        if r < 0.04:
            status = 'Cancelled'
        elif r < 0.075 and age >= 10:
            status = 'Returned'

        orders.append(dict(OrderId=100000 + n, OrderNumber=f'AS-{when:%y%m}-{n:05d}',
                           CustomerId=cust['CustomerId'] if cust else None,
                           CustomerEmail=email, OrderDate=ts(when), OrderStatus=status,
                           PromotionId=promo['PromotionId'] if promo else None,
                           SubTotal=subtotal, DiscountTotal=discount_total,
                           TaxTotal=tax, ShippingTotal=shipping,
                           GrandTotal=subtotal - discount_total + tax + shipping,
                           CurrencyCode='USD', ShipToPostalCode=postal,
                           ShipToCountry=country, lines=lines))
        for l in lines:
            items.append(dict(l, OrderId=100000 + n))
    return orders, items


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--orders', type=int, default=500)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--as-of', default='2026-10-01 00:00:00',
                    help='"today" for the data set; drives order statuses')
    args = ap.parse_args()
    rng = random.Random(args.seed)
    as_of = datetime.fromisoformat(args.as_of)

    brands = build_brands()
    models = build_models(rng, brands)
    promotions = build_promotions(brands, models)
    customers = build_customers(rng)
    orders, items = build_orders(rng, args.orders, models, promotions, customers, as_of)

    out = [
        '-- =====================================================================',
        '-- AcmeShopping sample data: fictional hardware store',
        '-- (garden, home improvement and DIY tools).',
        f'-- Generated by generate_acme_data.py --orders {args.orders} --seed {args.seed}',
        '-- Load after acme_shopping.sql. All names are fictional; emails use',
        '-- example.com and websites the reserved .example TLD.',
        '-- =====================================================================',
        '',
        'PRAGMA foreign_keys = ON;',
        'BEGIN TRANSACTION;',
        '',
        insert('CatalogCategory',
               ['CategoryId', 'ParentCategoryId', 'CategoryName', 'CategoryShortDesc',
                'SortOrder', 'IsActive', 'EffectiveDate', 'CreatedDate', 'LastUpdate'],
               [[sql(c[0]), sql(c[1]), sql(c[2]), sql(c[3]), sql(i), '1',
                 sql('2024-01-01 00:00:00'), sql('2024-01-01 00:00:00'), sql('2024-01-01 00:00:00')]
                for i, c in enumerate(CATEGORIES)]),
        '',
        insert('Brand',
               ['BrandId', 'BrandName', 'ManufacturerName', 'CountryOfOrigin', 'WebsiteUrl',
                'IsActive', 'CreatedDate', 'LastUpdate'],
               [[sql(b['BrandId']), sql(b['BrandName']), sql(b['ManufacturerName']),
                 sql(b['CountryOfOrigin']), sql(b['WebsiteUrl']), '1',
                 sql(b['CreatedDate']), sql(b['LastUpdate'])] for b in brands]),
        '',
        insert('Model',
               ['ModelId', 'BrandId', 'CategoryId', 'ModelNumber', 'ModelName', 'Sku', 'UpcCode',
                'MSRP', 'CurrencyCode', 'WeightLbs', 'ReleaseDate', 'EffectiveDate',
                'ExpirationDate', 'CreatedDate', 'LastUpdate', 'IsDiscontinued'],
               [[sql(m['ModelId']), sql(m['BrandId']), sql(m['CategoryId']), sql(m['ModelNumber']),
                 sql(m['ModelName']), sql(m['Sku']), sql(m['UpcCode']), money(m['MSRP']),
                 sql('USD'), sql(m['WeightLbs']), sql(m['ReleaseDate']), sql(m['EffectiveDate']),
                 sql(m['ExpirationDate']), sql(m['CreatedDate']), sql(m['LastUpdate']),
                 sql(m['IsDiscontinued'])] for m in models]),
        '',
        insert('Promotions',
               ['PromotionId', 'PromotionCode', 'PromotionName', 'PromotionType', 'EventName',
                'AppliesToModelId', 'AppliesToBrandId', 'AppliesToCategoryId',
                'DiscountPercent', 'DiscountAmount', 'MinimumOrderAmount', 'AssociatedCompany',
                'EffectiveDate', 'ExpirationDate', 'IsActive', 'IsStackable'],
               [[sql(p['PromotionId']), sql(p['PromotionCode']), sql(p['PromotionName']),
                 sql(p['PromotionType']), sql(p['EventName']), sql(p['AppliesToModelId']),
                 sql(p['AppliesToBrandId']), sql(p['AppliesToCategoryId']),
                 f"{p['DiscountPercent']:.2f}" if p['DiscountPercent'] else 'NULL',
                 money(p['DiscountAmount']) if p['DiscountAmount'] else 'NULL',
                 money(p['MinimumOrderAmount']) if p['MinimumOrderAmount'] else 'NULL',
                 sql(p['AssociatedCompany']), sql(p['EffectiveDate']), sql(p['ExpirationDate']),
                 sql(p['IsActive']), sql(p['IsStackable'])] for p in promotions]),
        '',
        insert('Order',
               ['OrderId', 'OrderNumber', 'CustomerId', 'CustomerEmail', 'OrderDate',
                'OrderStatus', 'PromotionId', 'SubTotal', 'DiscountTotal', 'TaxTotal',
                'ShippingTotal', 'GrandTotal', 'CurrencyCode', 'ShipToPostalCode', 'ShipToCountry'],
               [[sql(o['OrderId']), sql(o['OrderNumber']), sql(o['CustomerId']),
                 sql(o['CustomerEmail']), sql(o['OrderDate']), sql(o['OrderStatus']),
                 sql(o['PromotionId']), money(o['SubTotal']), money(o['DiscountTotal']),
                 money(o['TaxTotal']), money(o['ShippingTotal']), money(o['GrandTotal']),
                 sql('USD'), sql(o['ShipToPostalCode']), sql(o['ShipToCountry'])]
                for o in orders]),
        '',
        insert('OrderItem',
               ['OrderItemId', 'OrderId', 'LineNumber', 'ModelId', 'Quantity', 'UnitPrice',
                'LineDiscount', 'LineTotal', 'IsGift', 'GiftMessage', 'GiftWrap'],
               [[sql(i['OrderItemId']), sql(i['OrderId']), sql(i['LineNumber']), sql(i['ModelId']),
                 sql(i['Quantity']), money(i['UnitPrice']), money(i['LineDiscount']),
                 money(i['LineTotal']), sql(i['IsGift']), sql(i['GiftMessage']), sql(i['GiftWrap'])]
                for i in items]),
        '',
        'COMMIT;',
        '',
    ]
    path = Path(__file__).with_name('acme_sample_data.sql')
    path.write_text('\n'.join(out))
    print(f'{path.name}: {len(CATEGORIES)} categories, {len(brands)} brands, '
          f'{len(models)} models, {len(promotions)} promotions, '
          f'{len(orders)} orders, {len(items)} order items')


if __name__ == '__main__':
    main()
