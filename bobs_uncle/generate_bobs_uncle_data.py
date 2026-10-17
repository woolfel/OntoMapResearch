"""Generate sample data for BobsUncle (bobs_uncle.sql).

Fictional convenience-store franchise with rest-stop locations across the
central US: snacks, drinks, basic pain medication, paper, pens and other
road-trip items. Every manufacturer, product and customer is made up;
emails use the reserved example.com domain and websites the reserved
.example TLD.

The data deliberately keeps the legacy habits documented in
bobs_uncle.sql, so ETL has realistic mess to clean up:
  * manufacturer names spelled inconsistently ('Crunchwell Foods',
    'CRUNCHWELL FOODS', 'Crunchwell Foods Inc.') and free-text countries
  * free-text department names ('Snacks', 'SNACKS', 'Salty Snacks')
  * 'YYYYMMDD' text dates, 'Y'/'N' flags, money in INTEGER cents
  * timestamps in local store time (US/Central), no time zone
  * returns as negative quantities, free-text discount reasons,
    soft-deleted cart lines (removed_flg = 'Y')

Output: bobs_uncle_sample_data.sql next to this script. Deterministic
(fixed random seed).

    python3 generate_bobs_uncle_data.py [--carts 500] [--seed 7]
    sqlite3 bobs_uncle.db < ../bobs_uncle.sql
    sqlite3 bobs_uncle.db < bobs_uncle_sample_data.sql
"""
import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------

# code -> (spellings seen in the legacy data, HQ country spellings,
#          warranty phone, warranty email, website)
MANUFACTURERS = {
    'CRW': (['Crunchwell Foods', 'CRUNCHWELL FOODS', 'Crunchwell Foods Inc.', 'crunchwell foods'],
            ['USA', 'US', 'United States'], '1-800-555-0101', 'care@crunchwell.example', 'https://www.crunchwell.example'),
    'PGJ': (['Prairie Gold Jerky', 'Prairie Gold Jerky Co', 'PRAIRIE GOLD'],
            ['USA', 'United States '], '1-800-555-0102', None, 'https://www.prairiegold.example'),
    'SSC': (['Sweet Summit Confections', 'Sweet Summit', 'SWEET SUMMIT CONF.'],
            ['Canada', 'CA', 'canada'], '1-800-555-0103', 'hello@sweetsummit.example', 'https://www.sweetsummit.example'),
    'CBS': (['Clearbrook Springs', 'CLEARBROOK SPRINGS', 'Clearbrook Springs Water Co.'],
            ['USA', 'US'], '1-800-555-0104', None, 'https://www.clearbrook.example'),
    'FZC': (['FizzCo Beverages', 'Fizzco', 'FIZZCO BEV'],
            ['USA', 'U.S.A.'], '1-800-555-0105', 'consumer@fizzco.example', 'https://www.fizzco.example'),
    'BLT': (['Bolt Energy', 'BOLT ENERGY DRINKS', 'Bolt Energy LLC'],
            ['USA', 'US'], '1-800-555-0106', None, 'https://www.boltenergy.example'),
    'RHR': (['Roadhouse Roasters', 'ROADHOUSE ROASTERS'],
            ['USA'], '1-800-555-0107', 'coffee@roadhouse.example', 'https://www.roadhouse.example'),
    'MLT': (['Meadowlark Tea Co.', 'Meadowlark Tea', 'MEADOWLARK'],
            ['United Kingdom', 'UK', 'GB'], '+44 20 7946 0108', None, 'https://www.meadowlarktea.example'),
    'HWP': (['HealWell Pharma', 'HEALWELL PHARMACEUTICALS', 'Healwell'],
            ['USA', 'US'], '1-800-555-0109', 'safety@healwell.example', 'https://www.healwell.example'),
    'CLM': (['Calmwell Health', 'CALMWELL', 'Calmwell Health Products'],
            ['India', 'IN', 'india'], '1-800-555-0110', None, 'https://www.calmwell.example'),
    'INK': (['Inkline', 'INKLINE PENS', 'Inkline Writing Co.'],
            ['Japan', 'JP', 'Japan '], '1-800-555-0111', 'support@inkline.example', 'https://www.inkline.example'),
    'PPT': (['PaperTrail', 'Paper Trail', 'PAPERTRAIL PAPER PRODUCTS'],
            ['USA', 'US'], '1-800-555-0112', None, 'https://www.papertrail.example'),
    'RDR': (['RoadReady Auto', 'ROADREADY', 'Road Ready Automotive'],
            ['USA', 'US'], '1-800-555-0113', 'help@roadready.example', 'https://www.roadready.example'),
    'CHG': (['ChargeUp Electronics', 'CHARGEUP', 'Charge Up Electronics Ltd'],
            ['China', 'CN', 'PRC'], '1-800-555-0114', 'warranty@chargeup.example', 'https://www.chargeup.example'),
    'SVS': (['Sunvista Eyewear', 'SUNVISTA'],
            ['Italy', 'IT'], '1-800-555-0115', None, 'https://www.sunvista.example'),
    'FRK': (['FreshKit Personal Care', 'Freshkit', 'FRESHKIT'],
            ['Mexico', 'MX', 'mexico'], '1-800-555-0116', None, 'https://www.freshkit.example'),
    'BOB': (["Bob's Uncle", "BOB'S UNCLE", 'Bobs Uncle Store Brand'],
            ['USA'], '1-800-555-0199', 'service@bobsuncle.example', 'https://www.bobsuncle.example'),
}

# Department spellings drift between store systems and data-entry clerks.
DEPARTMENTS = {
    'snack':  ['Snacks', 'SNACKS', 'Salty Snacks'],
    'candy':  ['Candy & Gum', 'Candy', 'CANDY/GUM'],
    'cold':   ['Beverages', 'Cold Drinks', 'BEVERAGE'],
    'hot':    ['Hot Beverages', 'Coffee Bar'],
    'fresh':  ['Foodservice', 'Hot Food', 'FOOD SVC'],
    'otc':    ['Health & Beauty', 'HBA', 'Pharmacy/OTC'],
    'office': ['Office Supplies', 'Stationery', 'OFFICE'],
    'auto':   ['Automotive', 'AUTO'],
    'elec':   ['Electronics', 'Mobile Accessories'],
    'travel': ['Travel', 'Travel Essentials', 'TRAVEL/SUNDRY'],
}

# (mfr code, model no, name, dept, size, price cents, lbs, kind, variants)
#   kind: 'std' (UPC), 'import' (EAN-13), 'fresh' (no barcode),
#         'elec' (UPC + manufacturer warranty), 'med' (non-taxable)
#   variants: list of colors -> one sku per color sharing the brand row
CATALOG = [
    ('CRW', 'CW-SEA-2',   'Crunchwell Sea Salt Potato Chips',     'snack', '2.5 oz', 229, 0.2, 'std', None),
    ('CRW', 'CW-BBQ-2',   'Crunchwell BBQ Potato Chips',          'snack', '2.5 oz', 229, 0.2, 'std', None),
    ('CRW', 'CW-JAL-2',   'Crunchwell Jalapeno Kettle Chips',     'snack', '2.5 oz', 249, 0.2, 'std', None),
    ('CRW', 'CW-SEA-8',   'Crunchwell Sea Salt Potato Chips',     'snack', '8 oz',   479, 0.6, 'std', None),
    ('CRW', 'CW-PRT-3',   'Crunchwell Pretzel Twists',            'snack', '3 oz',   199, 0.2, 'std', None),
    ('CRW', 'CW-TRL-4',   'Crunchwell Trail Mix',                 'snack', '4 oz',   399, 0.3, 'std', None),
    ('CRW', 'CW-PNT-6',   'Crunchwell Honey Roasted Peanuts',     'snack', '6 oz',   349, 0.4, 'std', None),
    ('CRW', 'CW-SNF-1',   'Crunchwell Sunflower Seeds',           'snack', '5.25 oz', 279, 0.4, 'std', None),
    ('PGJ', 'PG-ORG-3',   'Prairie Gold Original Beef Jerky',     'snack', '3.25 oz', 899, 0.3, 'std', None),
    ('PGJ', 'PG-TER-3',   'Prairie Gold Teriyaki Beef Jerky',     'snack', '3.25 oz', 899, 0.3, 'std', None),
    ('PGJ', 'PG-STK-1',   'Prairie Gold Smoked Meat Stick',       'snack', '1 oz',   189, 0.1, 'std', None),
    ('SSC', 'SS-CHB-1',   'Sweet Summit Milk Chocolate Bar',      'candy', '1.55 oz', 199, 0.1, 'import', None),
    ('SSC', 'SS-PBC-2',   'Sweet Summit Peanut Butter Cups',      'candy', '1.5 oz', 199, 0.1, 'import', None),
    ('SSC', 'SS-GUM-14',  'Sweet Summit Spearmint Gum',           'candy', '14 ct',  179, 0.1, 'import', None),
    ('SSC', 'SS-SRB-5',   'Sweet Summit Sour Gummy Bears',        'candy', '5 oz',   269, 0.3, 'import', None),
    ('SSC', 'SS-MNT-1',   'Sweet Summit Peppermint Tin',          'candy', '1.76 oz', 249, 0.1, 'import', None),
    ('BOB', 'BU-CKE-1',   "Bob's Uncle Chocolate Chip Cookie",    'candy', '1 ct',   149, 0.1, 'fresh', None),
    ('CBS', 'CB-WTR-16',  'Clearbrook Spring Water',              'cold',  '16.9 oz', 149, 1.1, 'std', None),
    ('CBS', 'CB-WTR-1L',  'Clearbrook Spring Water',              'cold',  '1 L',    229, 2.2, 'std', None),
    ('CBS', 'CB-WTR-24',  'Clearbrook Spring Water 24-Pack',      'cold',  '24 x 16.9 oz', 699, 26.5, 'std', None),
    ('CBS', 'CB-SPK-LM',  'Clearbrook Sparkling Water Lime',      'cold',  '20 oz',  199, 1.3, 'std', None),
    ('FZC', 'FZ-COL-20',  'FizzCo Cola',                          'cold',  '20 oz',  249, 1.3, 'std', None),
    ('FZC', 'FZ-DCL-20',  'FizzCo Diet Cola',                     'cold',  '20 oz',  249, 1.3, 'std', None),
    ('FZC', 'FZ-LML-20',  'FizzCo Lemon-Lime Soda',               'cold',  '20 oz',  249, 1.3, 'std', None),
    ('FZC', 'FZ-RTB-20',  'FizzCo Root Beer',                     'cold',  '20 oz',  249, 1.3, 'std', None),
    ('FZC', 'FZ-SPT-28',  'FizzCo Sports Drink Blue Rush',        'cold',  '28 oz',  279, 1.8, 'std', None),
    ('FZC', 'FZ-SPT-28F', 'FizzCo Sports Drink Fruit Punch',      'cold',  '28 oz',  279, 1.8, 'std', None),
    ('BLT', 'BL-ORG-16',  'Bolt Energy Original',                 'cold',  '16 oz',  329, 1.1, 'std', None),
    ('BLT', 'BL-SFR-16',  'Bolt Energy Sugar Free',               'cold',  '16 oz',  329, 1.1, 'std', None),
    ('BLT', 'BL-SHT-2',   'Bolt Energy Shot Berry',               'cold',  '2 oz',   349, 0.2, 'std', None),
    ('RHR', 'RR-CBR-11',  'Roadhouse Cold Brew Coffee',           'cold',  '11 oz',  399, 0.8, 'std', None),
    ('MLT', 'ML-ICT-18',  'Meadowlark Sweet Iced Tea',            'cold',  '18.5 oz', 229, 1.2, 'import', None),
    ('MLT', 'ML-GRT-18',  'Meadowlark Green Tea with Honey',      'cold',  '18.5 oz', 229, 1.2, 'import', None),
    ('BOB', 'BU-FTN-32',  "Bob's Uncle Fountain Drink",           'cold',  '32 oz',  179, 2.1, 'fresh', None),
    ('BOB', 'BU-FTN-44',  "Bob's Uncle Fountain Drink",           'cold',  '44 oz',  209, 2.9, 'fresh', None),
    ('BOB', 'BU-ICE-10',  "Bob's Uncle Bagged Ice",               'cold',  '10 lb',  329, 10.0, 'fresh', None),
    ('BOB', 'BU-COF-16',  "Bob's Uncle Fresh Brewed Coffee",      'hot',   '16 oz',  199, 1.0, 'fresh', None),
    ('BOB', 'BU-COF-24',  "Bob's Uncle Fresh Brewed Coffee",      'hot',   '24 oz',  249, 1.5, 'fresh', None),
    ('BOB', 'BU-CAP-12',  "Bob's Uncle French Vanilla Cappuccino", 'hot',  '12 oz',  219, 0.8, 'fresh', None),
    ('BOB', 'BU-HDG-1',   "Bob's Uncle Roller Grill Hot Dog",     'fresh', '1 ct',   199, 0.3, 'fresh', None),
    ('BOB', 'BU-TQT-1',   "Bob's Uncle Beef Taquito",             'fresh', '1 ct',   179, 0.2, 'fresh', None),
    ('BOB', 'BU-BRT-1',   "Bob's Uncle Breakfast Burrito",        'fresh', '1 ct',   349, 0.5, 'fresh', None),
    ('BOB', 'BU-PZS-1',   "Bob's Uncle Pepperoni Pizza Slice",    'fresh', '1 ct',   299, 0.4, 'fresh', None),
    ('HWP', 'HW-IBU-24',  'HealWell Ibuprofen 200 mg Tablets',    'otc',   '24 ct',  699, 0.1, 'med', None),
    ('HWP', 'HW-IBU-2',   'HealWell Ibuprofen 200 mg Travel Pack', 'otc',  '2 ct',   199, 0.1, 'med', None),
    ('HWP', 'HW-ACE-24',  'HealWell Acetaminophen 500 mg Caplets', 'otc',  '24 ct',  699, 0.1, 'med', None),
    ('HWP', 'HW-ACE-2',   'HealWell Acetaminophen 500 mg Travel Pack', 'otc', '2 ct', 199, 0.1, 'med', None),
    ('HWP', 'HW-ASP-30',  'HealWell Low Dose Aspirin 81 mg',      'otc',   '30 ct',  549, 0.1, 'med', None),
    ('HWP', 'HW-NAP-12',  'HealWell Naproxen Sodium 220 mg',      'otc',   '12 ct',  599, 0.1, 'med', None),
    ('HWP', 'HW-ALG-10',  'HealWell Allergy Relief 10 mg',        'otc',   '10 ct',  899, 0.1, 'med', None),
    ('CLM', 'CL-ANT-12',  'Calmwell Antacid Chewables',           'otc',   '12 ct',  349, 0.1, 'med', None),
    ('CLM', 'CL-MOT-8',   'Calmwell Motion Sickness Tablets',     'otc',   '8 ct',   499, 0.1, 'med', None),
    ('FRK', 'FK-SAN-2',   'FreshKit Hand Sanitizer',              'otc',   '2 oz',   199, 0.2, 'std', None),
    ('FRK', 'FK-LIP-1',   'FreshKit SPF 15 Lip Balm',             'otc',   '0.15 oz', 249, 0.1, 'std', None),
    ('FRK', 'FK-TBK-1',   'FreshKit Travel Toothbrush Kit',       'travel', '1 ct',  499, 0.2, 'std', None),
    ('FRK', 'FK-WIP-20',  'FreshKit Refreshing Wipes',            'travel', '20 ct', 299, 0.3, 'std', None),
    ('FRK', 'FK-SUN-3',   'FreshKit SPF 30 Sunscreen',            'travel', '3 oz',  799, 0.3, 'std', None),
    ('INK', 'IK-BP-BLK',  'Inkline Ballpoint Pen 2-Pack',         'office', 'Medium 1.0 mm', 299, 0.1, 'import', ['Black', 'Blue']),
    ('INK', 'IK-GEL-4',   'Inkline Gel Pens 4-Pack',              'office', 'Fine 0.7 mm', 599, 0.1, 'import', ['Black', 'Assorted']),
    ('INK', 'IK-HLT-2',   'Inkline Highlighters 2-Pack',          'office', 'Chisel tip', 349, 0.1, 'import', ['Yellow', 'Pink']),
    ('INK', 'IK-MRK-1',   'Inkline Permanent Marker',             'office', 'Fine', 229, 0.1, 'import', ['Black']),
    ('PPT', 'PT-NBK-70',  'PaperTrail Spiral Notebook',           'office', '70 sheets', 249, 0.4, 'std', None),
    ('PPT', 'PT-PAD-50',  'PaperTrail Legal Pad',                 'office', '50 sheets', 299, 0.5, 'std', None),
    ('PPT', 'PT-PPR-100', 'PaperTrail Copy Paper',                'office', '100 sheets', 399, 1.1, 'std', None),
    ('PPT', 'PT-ENV-10',  'PaperTrail Envelopes #10',             'office', '10 ct', 249, 0.2, 'std', None),
    ('PPT', 'PT-TAP-1',   'PaperTrail Clear Tape with Dispenser', 'office', '0.75 x 650 in', 279, 0.2, 'std', None),
    ('PPT', 'PT-MAP-TX',  'PaperTrail Texas Road Atlas',          'travel', 'Folded', 699, 0.4, 'std', None),
    ('RDR', 'RR-OIL-5W',  'RoadReady 5W-30 Motor Oil',            'auto',   '1 qt',  899, 2.0, 'std', None),
    ('RDR', 'RR-WSH-1G',  'RoadReady Windshield Washer Fluid',    'auto',   '1 gal', 499, 8.5, 'std', None),
    ('RDR', 'RR-AIR-1',   'RoadReady Car Air Freshener',          'auto',   '1 ct',  249, 0.1, 'std', ['Pine', 'New Car', 'Vanilla']),
    ('RDR', 'RR-TGA-1',   'RoadReady Tire Pressure Gauge',        'auto',   '1 ct',  699, 0.2, 'std', None),
    ('CHG', 'CU-USBC-3',  'ChargeUp USB-C Charging Cable',        'elec',   '3 ft',  1499, 0.2, 'elec', ['Black', 'White']),
    ('CHG', 'CU-LTN-3',   'ChargeUp Lightning Charging Cable',    'elec',   '3 ft',  1499, 0.2, 'elec', ['White']),
    ('CHG', 'CU-CAR-2',   'ChargeUp Dual-Port Car Charger',       'elec',   '30 W',  1999, 0.2, 'elec', None),
    ('CHG', 'CU-EAR-1',   'ChargeUp Wired Earbuds',               'elec',   '1 ct',  1299, 0.2, 'elec', ['Black', 'White']),
    ('CHG', 'CU-PWR-10',  'ChargeUp Portable Power Bank',         'elec',   '10000 mAh', 2999, 0.5, 'elec', None),
    ('CHG', 'CU-BTS-1',   'ChargeUp Bluetooth Speaker',           'elec',   '1 ct',  3499, 0.9, 'elec', None),
    ('CHG', 'CU-BAT-AA',  'ChargeUp Alkaline Batteries AA',       'elec',   '4 ct',  699, 0.2, 'std', None),
    ('SVS', 'SV-AVI-1',   'Sunvista Aviator Sunglasses',          'travel', 'One size', 1499, 0.1, 'std', ['Gold/Green', 'Black']),
    ('SVS', 'SV-SPT-1',   'Sunvista Sport Wrap Sunglasses',       'travel', 'One size', 1299, 0.1, 'std', ['Black', 'Red']),
    ('BOB', 'BU-PLN-1Y',  "Bob's Uncle 1-Year Electronics Protection Plan", 'elec', '12 months', 499, 0.0, 'plan', None),
]

# Franchise locations: rest stops along interstates in Central Time.
STORES = [('TX01', 'Amarillo, TX', 0.0825, '79101'), ('TX02', 'Waco, TX', 0.0825, '76701'),
          ('OK01', 'Oklahoma City, OK', 0.0863, '73102'), ('KS01', 'Salina, KS', 0.0915, '67401'),
          ('MO01', 'Joplin, MO', 0.0848, '64801'), ('AR01', 'Russellville, AR', 0.0950, '72801')]
DC = 'DC01'                      # distribution center that ships web orders
WEB_TAX = 0.0825

# Relative traffic: summer road trips and holidays are busiest.
MONTH_WEIGHT = {1: 0.7, 2: 0.7, 3: 1.0, 4: 1.0, 5: 1.2, 6: 1.5,
                7: 1.6, 8: 1.4, 9: 1.0, 10: 0.9, 11: 1.2, 12: 1.3}
HOUR_WEIGHT = [2, 1, 1, 1, 2, 4, 7, 9, 8, 6, 6, 8, 10, 8, 6, 7, 9, 10, 9, 7, 6, 5, 4, 3]

FIRST_NAMES = ['alex', 'jordan', 'taylor', 'morgan', 'casey', 'riley', 'jamie',
               'avery', 'quinn', 'rowan', 'sam', 'drew', 'reese', 'kai']
LAST_NAMES = ['rivera', 'chen', 'patel', 'okafor', 'novak', 'haddad', 'moreau',
              'tanaka', 'brennan', 'silva', 'nguyen', 'fischer', 'larsen', 'ibarra']


def check_digit(body: str) -> str:
    """GS1 check digit, valid for UPC-A, EAN-13 and GTIN-14 bodies."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


def yyyymmdd(d: date) -> str:
    return d.strftime('%Y%m%d')


def sql(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert(table: str, columns: list, rows: list) -> str:
    out = [f'INSERT INTO {table} ({", ".join(columns)}) VALUES']
    out += ['    (' + ', '.join(sql(v) for v in r) + ')' + (',' if i < len(rows) - 1 else ';')
            for i, r in enumerate(rows)]
    return '\n'.join(out)


# ---------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------

def build_catalog(rng):
    brands, products = [], []
    sku_no = 4001
    for mfr_cd, model_no, name, dept, size, price, lbs, kind, variants in CATALOG:
        spellings, countries, phone, email, web = MANUFACTURERS[mfr_cd]
        avail = date(2019, 1, 1) + timedelta(days=rng.randint(0, 2000))
        discontinued = rng.random() < 0.05 and kind not in ('fresh', 'plan')
        brand_id = len(brands) + 1
        brands.append(dict(
            brand_id=brand_id, mfr_cd=mfr_cd, mfr_nm=rng.choice(spellings),
            mfr_hq_country=rng.choice(countries), mfr_contact_phone=phone,
            mfr_contact_email=email, mfr_website_url=web, model_no=model_no,
            model_nm=name, model_yr=avail.year, avail_dt=yyyymmdd(avail),
            discontinue_dt=yyyymmdd(date(2026, 3, 31)) if discontinued else rng.choice([None, '']),
            active_flg='N' if discontinued else 'Y'))
        for color in variants or [None]:
            upc = ean = gtin = None
            if kind in ('std', 'elec', 'med'):
                upc = check_digit(f'0{rng.randint(10**9, 10**10 - 1)}')
                if rng.random() < 0.3:               # case-pack barcode for distribution
                    gtin = check_digit('1' + upc[:-1].zfill(12))
            elif kind == 'import':
                ean = check_digit(str(rng.choice([400, 500, 690, 760, 840])) + str(rng.randint(10**8, 10**9 - 1)))
            warranty = {}
            if kind == 'elec':
                warranty = dict(warr_type='MFR', warr_months=rng.choice([6, 12]),
                                warr_provider=rng.choice(spellings), warr_parts_flg='Y',
                                warr_labor_flg='N',
                                warr_terms_txt='Replacement for defects in materials and workmanship. '
                                               'Keep your receipt.')
            elif kind == 'plan':
                warranty = dict(warr_type='EXTENDED', warr_months=12,
                                warr_provider='Roadside Protection Partners', warr_parts_flg='Y',
                                warr_labor_flg='Y',
                                warr_terms_txt='One replacement of a covered electronics item within 12 '
                                               'months of purchase, including accidental damage.')
            else:
                warranty = dict(warr_type=rng.choice(['NONE', None]))
            created = avail - timedelta(days=rng.randint(5, 60))
            products.append(dict(
                sku=f'BU-{sku_no:07d}', brand_id=brand_id, upc_cd=upc, ean_cd=ean, gtin_cd=gtin,
                short_desc=f'{name} {size}' + (f' {color}' if color else ''),
                long_desc=f'{name}, {size}.' + (f' Color: {color}.' if color else '')
                          + (' Freshly prepared in store.' if kind == 'fresh' else ''),
                dept_nm=rng.choice(DEPARTMENTS[dept]), color_desc=color, size_desc=size,
                wt_lbs=lbs, retail_price_cents=price,
                cost_cents=None if kind == 'plan' else int(price * rng.uniform(0.45, 0.70)),
                taxable_flg='N' if kind == 'med' or model_no.startswith('CB-WTR') else 'Y',
                warr_type=warranty.get('warr_type'), warr_months=warranty.get('warr_months'),
                warr_provider=warranty.get('warr_provider'), warr_parts_flg=warranty.get('warr_parts_flg'),
                warr_labor_flg=warranty.get('warr_labor_flg'), warr_terms_txt=warranty.get('warr_terms_txt'),
                created_dt=created.isoformat(),
                last_upd_ts=f'{created + timedelta(days=rng.randint(0, 600))} {rng.randint(6, 22):02d}:{rng.randint(0, 59):02d}:00'
                            if rng.random() < 0.8 else None,
                kind=kind, discontinued=discontinued, dept=dept))
            sku_no += 1
    return brands, products


def build_inventory(rng, products):
    rows = []
    for p in products:
        if p['kind'] == 'plan':
            continue                                  # a service, nothing on the shelf
        for whse, *_ in STORES + [(DC,)]:
            if whse != DC and rng.random() < 0.08:
                continue                              # not every store stocks every item
            if p['discontinued']:
                on_hand, on_order = rng.randint(0, 3), 0
            elif whse == DC:
                on_hand, on_order = rng.randint(100, 900), rng.choice([0, 0, 240, 480])
            else:
                on_hand, on_order = rng.randint(0, 60), rng.choice([0, 0, 0, 12, 24])
            aisle = {'snack': 'A', 'candy': 'B', 'cold': 'C', 'hot': 'H', 'fresh': 'F',
                     'otc': 'D', 'office': 'E', 'auto': 'G', 'elec': 'K', 'travel': 'T'}[p['dept']]
            rows.append(dict(sku=p['sku'], whse_cd=whse, qty_on_hand=on_hand,
                             qty_reserved=rng.randint(0, 2) if whse == DC else 0,
                             qty_on_order=on_order,
                             reorder_pt=None if p['kind'] == 'fresh' else (120 if whse == DC else rng.choice([6, 8, 12])),
                             bin_loc=f'{aisle}-{rng.randint(1, 12):02d}-{rng.randint(1, 5)}',
                             last_cnt_dt=yyyymmdd(date(2026, 9, 1) + timedelta(days=rng.randint(0, 28)))))
    return rows


PROMOTIONS = [
    # promo_cd, promo_desc, funded_by, mfr_cd, scope, pct, cents, min cents, effective, expiration, active, stackable
    (None,         'Crunchwell Chips 2 for $4',               'MFR',      'CRW', 'PRODUCT', None, None, None, '2025-01-01', None,         'Y', 'N'),
    (None,         'Hot Dog + Fountain Drink Combo $1 Off',   'RETAILER', None,  'DEPT',    None, 100,  None, '2025-01-01', None,         'Y', 'Y'),
    ('ROADTRIP25', 'Summer Road Trip 10% Off Snacks & Drinks', 'RETAILER', None, 'DEPT',    10.0, None, None, '2025-06-01', '2025-08-31', 'Y', 'N'),
    ('ROADTRIP26', 'Summer Road Trip 10% Off Snacks & Drinks', 'RETAILER', None, 'DEPT',    10.0, None, None, '2026-06-01', '2026-08-31', 'Y', 'N'),
    ('BOLT2',      'Bolt Energy 2 for $5',                    'MFR',      'BLT', 'PRODUCT', None, None, None, '2025-03-01', '2026-12-31', 'Y', 'N'),
    ('FUEL5',      '$5 Off In-Store Purchase of $25+',        'RETAILER', None,  'CART',    None, 500,  2500, '2025-01-01', None,         'Y', 'N'),
    ('APP15',      '15% Off First App Order',                 'RETAILER', None,  'CART',    15.0, None, 1000, '2025-04-01', None,         'Y', 'N'),
    ('CHARGE20',   'ChargeUp Accessories 20% Off',            'MFR',      'CHG', 'PRODUCT', 20.0, None, None, '2025-11-28', '2025-12-31', 'Y', 'N'),
    ('BF2025',     'Black Friday 25% Off Electronics',        'RETAILER', None,  'DEPT',    25.0, None, None, '2025-11-28', '2025-11-30', 'Y', 'N'),
    ('COLDFLU',    'Cold & Flu Season $1 Off Pain Relief',    'MFR',      'HWP', 'PRODUCT', None, 100,  None, '2025-10-01', '2026-03-31', 'N', 'N'),
]


def local_time(rng, start: date, end: date) -> datetime:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    weights = [MONTH_WEIGHT[d.month] * (1.4 if d.weekday() in (4, 5, 6) else 1.0) for d in days]
    d = rng.choices(days, weights=weights)[0]
    return datetime(d.year, d.month, d.day, rng.choices(range(24), weights=HOUR_WEIGHT)[0],
                    rng.randint(0, 59), rng.randint(0, 59))


def build_carts(rng, n_carts, products, as_of: datetime):
    by_dept = {}
    for p in products:
        if not p['discontinued'] and p['kind'] != 'plan':
            by_dept.setdefault(p['dept'], []).append(p)
    plan = next(p for p in products if p['kind'] == 'plan')
    dept_weights = {'cold': 30, 'snack': 18, 'candy': 12, 'hot': 10, 'fresh': 10, 'otc': 6,
                    'travel': 5, 'office': 3, 'auto': 3, 'elec': 3}
    loyalty = [f'L{rng.randint(10**8, 10**9 - 1)}' for _ in range(120)]
    emails = [f'{rng.choice(FIRST_NAMES)}.{rng.choice(LAST_NAMES)}{i}@example.com' for i in range(60)]

    carts, items, seq_by_day = [], [], {}
    times = sorted(local_time(rng, date(2025, 1, 1), as_of.date() - timedelta(days=1))
                   for _ in range(n_carts))
    returnable = []                                    # checked-out lines that could come back
    for created in times:
        day = created.strftime('%y%m%d')
        seq_by_day[day] = seq_by_day.get(day, 0) + 1
        cart_no = f'C{day}{seq_by_day[day]:05d}'
        channel = rng.choices(['POS', 'APP', 'WEB'], weights=[86, 11, 3])[0]
        store = rng.choice(STORES)
        whse = DC if channel == 'WEB' else store[0]
        age_days = (as_of - created).days

        # A few POS carts are returns of something bought earlier.
        if channel == 'POS' and returnable and rng.random() < 0.012:
            orig = rng.choice(returnable)
            returnable.remove(orig)
            qty = -orig['qty']
            lines = [dict(sku=orig['sku'], qty=qty, unit_price_cents=orig['unit_price_cents'],
                          disc_cents=-orig['disc_cents'] if orig['disc_cents'] else 0,
                          disc_reason=orig['disc_reason'], ext_warr_sku=None, removed_flg='N',
                          taxable=orig['taxable'])]
            cust, guest = orig['cust_ref'], 'N' if orig['cust_ref'] else 'Y'
            stat = 'C'
        else:
            if channel == 'POS':
                cust = rng.choice(loyalty) if rng.random() < 0.35 else None
            else:
                cust = rng.choice(emails if rng.random() < 0.6 else loyalty)
            guest = 'Y' if cust is None else 'N'
            if age_days < 1 and rng.random() < 0.5:
                stat = 'O'
            else:
                stat = rng.choices(['C', 'A', 'X'], weights=[90, 7 if channel != 'POS' else 1, 2])[0]

            n_lines = rng.choices([1, 2, 3, 4, 5, 6], weights=[30, 30, 20, 10, 6, 4])[0]
            lines = []
            for _ in range(n_lines):
                dept = rng.choices(list(dept_weights), weights=list(dept_weights.values()))[0]
                p = rng.choice(by_dept[dept])
                if any(l['sku'] == p['sku'] for l in lines):
                    continue
                qty = rng.choices([1, 2, 3, 4], weights=[75, 17, 5, 3])[0] if p['kind'] != 'elec' else 1
                lines.append(dict(sku=p['sku'], qty=qty, unit_price_cents=p['retail_price_cents'],
                                  disc_cents=0, disc_reason=None, ext_warr_sku=None,
                                  removed_flg='N', taxable=p['taxable_flg'] == 'Y', product=p))
                # Protection plan sold with pricier electronics.
                if p['kind'] == 'elec' and p['retail_price_cents'] >= 1999 and rng.random() < 0.35:
                    lines[-1]['ext_warr_sku'] = plan['sku']
                    lines.append(dict(sku=plan['sku'], qty=1, unit_price_cents=plan['retail_price_cents'],
                                      disc_cents=0, disc_reason=None, ext_warr_sku=None,
                                      removed_flg='N', taxable=True, product=plan))
            apply_discounts(rng, lines, created, channel)
            # Shoppers sometimes put an item back (soft delete).
            if len(lines) > 1 and rng.random() < 0.06:
                rng.choice(lines)['removed_flg'] = 'Y'

        active = [l for l in lines if l['removed_flg'] == 'N']
        merch = sum(l['qty'] * l['unit_price_cents'] - l['disc_cents'] for l in active)
        taxable = sum(l['qty'] * l['unit_price_cents'] - l['disc_cents'] for l in active if l['taxable'])
        rate = WEB_TAX if channel == 'WEB' else store[2]
        ship = 499 if channel == 'WEB' and merch < 3500 and merch > 0 else 0
        checked_out = stat == 'C'
        tax = round(taxable * rate)
        checkout = created + timedelta(minutes=rng.randint(1, 6) if channel == 'POS' else rng.randint(3, 40))

        carts.append(dict(
            cart_no=cart_no, cust_ref=cust, guest_flg=guest, cart_stat=stat,
            created_ts=created.strftime('%Y-%m-%d %H:%M:%S'),
            checkout_ts=checkout.strftime('%Y-%m-%d %H:%M:%S') if checked_out else None,
            channel_cd=channel,
            ship_zip=rng.choice(['73301', '75201', '64108', '67202', '72201', '74103']) if channel == 'WEB' else None,
            tax_cents=tax if checked_out else None,
            ship_cents=ship if checked_out else None,
            total_cents=merch + tax + ship if checked_out else None))
        for seq, l in enumerate(lines, start=1):
            added = created + timedelta(seconds=20 * seq + rng.randint(0, 40))
            items.append(dict(cart_no=cart_no, line_seq=seq, sku=l['sku'], qty=l['qty'],
                              unit_price_cents=l['unit_price_cents'], disc_cents=l['disc_cents'],
                              disc_reason=l['disc_reason'], ext_warr_sku=l['ext_warr_sku'],
                              fulfil_whse_cd=whse, added_ts=added.strftime('%Y-%m-%d %H:%M:%S'),
                              removed_flg=l['removed_flg']))
            if (checked_out and l['qty'] > 0 and l['removed_flg'] == 'N'
                    and l.get('product', {}).get('kind') in ('elec', 'std', 'import')):
                returnable.append(dict(sku=l['sku'], qty=l['qty'], unit_price_cents=l['unit_price_cents'],
                                       disc_cents=l['disc_cents'], disc_reason=l['disc_reason'],
                                       taxable=l['taxable'], cust_ref=cust))
    return carts, items


def apply_discounts(rng, lines, when: datetime, channel):
    """Discounts land on cart_item as cents + free-text reason, the way
    store clerks and the POS recorded them (inconsistent wording on purpose)."""
    d = when.date()
    for l in lines:
        p = l['product']
        if p['kind'] == 'plan':
            continue
        if 'Crunchwell' in p['short_desc'] and '2.5 oz' in p['short_desc'] and l['qty'] >= 2:
            l['disc_cents'] = l['qty'] * l['unit_price_cents'] - (l['qty'] // 2) * 400 - (l['qty'] % 2) * l['unit_price_cents']
            l['disc_reason'] = rng.choice(['2 FOR $4', '2/$4 CHIPS', 'mfr deal 2 for 4'])
        elif 'Bolt Energy' in p['short_desc'] and '16 oz' in p['short_desc'] and l['qty'] >= 2 \
                and date(2025, 3, 1) <= d <= date(2026, 12, 31):
            l['disc_cents'] = l['qty'] * l['unit_price_cents'] - (l['qty'] // 2) * 500 - (l['qty'] % 2) * l['unit_price_cents']
            l['disc_reason'] = rng.choice(['BOLT2', 'bolt 2 for $5'])
        elif p['dept'] in ('snack', 'cold', 'candy') and (date(2025, 6, 1) <= d <= date(2025, 8, 31)
                                                          or date(2026, 6, 1) <= d <= date(2026, 8, 31)) \
                and rng.random() < 0.25:
            l['disc_cents'] = round(l['qty'] * l['unit_price_cents'] * 0.10)
            l['disc_reason'] = rng.choice(['ROADTRIP', 'road trip 10%', 'ROADTRIP25' if d.year == 2025 else 'ROADTRIP26'])
        elif p['kind'] == 'elec' and date(2025, 11, 28) <= d <= date(2025, 11, 30):
            l['disc_cents'] = round(l['qty'] * l['unit_price_cents'] * 0.25)
            l['disc_reason'] = rng.choice(['BF2025', 'BF SALE', 'black friday'])
    hot_dog = next((l for l in lines if 'Hot Dog' in l['product']['short_desc'] and not l['disc_cents']), None)
    if hot_dog and any('Fountain Drink' in l['product']['short_desc'] for l in lines):
        hot_dog['disc_cents'] = 100
        hot_dog['disc_reason'] = rng.choice(['COMBO', 'hotdog+drink combo', 'COMBO $1'])
    # Cart-level coupons have nowhere else to go: the clerk puts them on line 1.
    merch = sum(l['qty'] * l['unit_price_cents'] - l['disc_cents'] for l in lines)
    first = lines[0]
    if not first['disc_cents'] and first['product']['kind'] != 'plan':
        if channel == 'POS' and merch >= 2500 and rng.random() < 0.15:
            first['disc_cents'] = min(500, first['qty'] * first['unit_price_cents'])
            first['disc_reason'] = rng.choice(['coupon FUEL5', 'COUPON fuel5', 'FUEL5'])
        elif channel == 'APP' and merch >= 1000 and rng.random() < 0.20:
            first['disc_cents'] = min(round(merch * 0.15), first['qty'] * first['unit_price_cents'])
            first['disc_reason'] = rng.choice(['APP15', 'app 15% first order'])
        elif rng.random() < 0.01:
            first['disc_cents'] = min(rng.choice([50, 100, 200]), first['qty'] * first['unit_price_cents'])
            first['disc_reason'] = rng.choice(['manager override', 'damaged pkg', 'MGR OVRD', 'price match'])


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--carts', type=int, default=500)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--as-of', default='2026-10-01 00:00:00',
                    help='"now" for the data set (US/Central); drives open carts')
    args = ap.parse_args()
    rng = random.Random(args.seed)
    as_of = datetime.fromisoformat(args.as_of)

    brands, products = build_catalog(rng)
    inventory = build_inventory(rng, products)
    carts, items = build_carts(rng, args.carts, products, as_of)

    brand_cols = ['brand_id', 'mfr_cd', 'mfr_nm', 'mfr_hq_country', 'mfr_contact_phone',
                  'mfr_contact_email', 'mfr_website_url', 'model_no', 'model_nm', 'model_yr',
                  'avail_dt', 'discontinue_dt', 'active_flg']
    product_cols = ['sku', 'brand_id', 'upc_cd', 'ean_cd', 'gtin_cd', 'short_desc', 'long_desc',
                    'dept_nm', 'color_desc', 'size_desc', 'wt_lbs', 'retail_price_cents',
                    'cost_cents', 'taxable_flg', 'warr_type', 'warr_months', 'warr_provider',
                    'warr_parts_flg', 'warr_labor_flg', 'warr_terms_txt', 'created_dt', 'last_upd_ts']
    inv_cols = ['sku', 'whse_cd', 'qty_on_hand', 'qty_reserved', 'qty_on_order', 'reorder_pt',
                'bin_loc', 'last_cnt_dt']
    cart_cols = ['cart_no', 'cust_ref', 'guest_flg', 'cart_stat', 'created_ts', 'checkout_ts',
                 'channel_cd', 'ship_zip', 'tax_cents', 'ship_cents', 'total_cents']
    item_cols = ['cart_no', 'line_seq', 'sku', 'qty', 'unit_price_cents', 'disc_cents',
                 'disc_reason', 'ext_warr_sku', 'fulfil_whse_cd', 'added_ts', 'removed_flg']
    promo_cols = ['promo_cd', 'promo_desc', 'funded_by', 'mfr_cd', 'scope', 'discount_pct',
                  'discount_cents', 'min_order_cents', 'effective_dt', 'expiration_dt',
                  'active_flg', 'stackable_flg']

    out = [
        '-- =====================================================================',
        "-- BobsUncle sample data: fictional rest-stop convenience franchise",
        '-- (snacks, drinks, pain relief, paper, pens and road-trip items).',
        f'-- Generated by generate_bobs_uncle_data.py --carts {args.carts} --seed {args.seed}',
        '-- Load after bobs_uncle.sql. All names are fictional; emails use',
        '-- example.com and websites the reserved .example TLD.',
        '--',
        '-- Legacy habits are intentional (see bobs_uncle.sql): inconsistent',
        "-- manufacturer/department spellings, 'YYYYMMDD' text dates, Y/N flags,",
        '-- cents, local US/Central timestamps, negative-qty returns, free-text',
        "-- discount reasons and soft-deleted lines (removed_flg = 'Y').",
        '-- =====================================================================',
        '',
        'PRAGMA foreign_keys = ON;',
        'BEGIN TRANSACTION;',
        '',
        insert('brand', brand_cols, [[b[c] for c in brand_cols] for b in brands]),
        '',
        insert('product', product_cols, [[p[c] for c in product_cols] for p in products]),
        '',
        insert('inventory', inv_cols, [[r[c] for c in inv_cols] for r in inventory]),
        '',
        insert('promotion', promo_cols, [list(p) for p in PROMOTIONS]),
        '',
        insert('cart', cart_cols, [[c[k] for k in cart_cols] for c in carts]),
        '',
        insert('cart_item', item_cols, [[i[k] for k in item_cols] for i in items]),
        '',
        'COMMIT;',
        '',
    ]
    path = Path(__file__).with_name('bobs_uncle_sample_data.sql')
    path.write_text('\n'.join(out))
    print(f'{path.name}: {len(brands)} brand rows, {len(products)} products, '
          f'{len(inventory)} inventory rows, {len(PROMOTIONS)} promotions, '
          f'{len(carts)} carts, {len(items)} cart items')


if __name__ == '__main__':
    main()
