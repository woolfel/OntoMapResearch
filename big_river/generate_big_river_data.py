"""Generate sample data for BigRiver (big_river.sql).

BigRiver is a marketplace: first-party BigRiver retail plus third-party
stores selling everything AcmeShopping (garden, home improvement, DIY
tools) and BobsUncle (snacks, drinks, pain relief, paper, pens, road-trip
items) sell.

The catalog is NOT invented here. It reuses the brands and models built
by ../acme_data/generate_acme_data.py and
../bobs_uncle/generate_bobs_uncle_data.py, rebuilt with the same seeds,
so model numbers and UPC/EAN barcodes match the other two sample data
sets. ETL can therefore match the same product across sources.
(BobsUncle's in-store foodservice items and protection plan are not sold
online.)

The data keeps BigRiver's documented habits:
  * UUID keys (TEXT), BigRiver numbers in PRD_ID ('BR' + 10 characters)
  * no brand table: PRD_BRAND_TEXT is typed by sellers ('Ironwood Tools',
    'IRONWOOD TOOLS', 'Ironwood')
  * extra attributes as key/value PRODUCT_TAGS (SELLER, BRAND or ML with
    a confidence)
  * a few duplicate listings of the same product (same UPC, different
    PRD_ID and wording)
  * multi-currency stores (USD, CAD, EUR, GBP) with the FX rate captured
    on each ITEM
  * discount percentages as fractions (0.150 = 15%)
  * every timestamp is a TIMESTAMP 'YYYY-MM-DD HH:MM:SS' in UTC;
    open-ended promotions end '9999-12-31 23:59:59' because
    PRM_END_DATE is NOT NULL
  * one promotion per item line plus an optional cart-level coupon

Output: big_river_sample_data.sql next to this script. Deterministic
(fixed random seed).

    python3 generate_big_river_data.py [--carts 500] [--seed 11]
    sqlite3 big_river.db < ../big_river.sql
    sqlite3 big_river.db < big_river_sample_data.sql
"""
import argparse
import random
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True             # keep __pycache__ out of the other data folders
sys.path[:0] = [str(HERE.parent / 'acme_data'), str(HERE.parent / 'bobs_uncle')]
import generate_acme_data as acme          # noqa: E402
import generate_bobs_uncle_data as bob     # noqa: E402

# Seeds the other generators use by default; the catalogs must be rebuilt
# with the same seed to get the same models and barcodes.
ACME_SEED = 42
BOB_SEED = 7

USD_PER = {'USD': 1.0, 'CAD': 0.735, 'EUR': 1.085, 'GBP': 1.27}
OPEN_ENDED = '9999-12-31 23:59:59'

# ---------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------

# handle, display name, 1st party, country, ccy, rating, status, region,
#   FBBR, groups sold (or 'brand:<name>'), onboarded, closed/suspended
STORES = [
    ('bigriver-retail',        'BigRiver',                   1, 'US', 'USD', 4.6, 'LIVE',      'US-WA', 1, {'*'},                 '2019-01-01', None),
    ('tool-haven',             'Tool Haven',                 0, 'US', 'USD', 4.7, 'LIVE',      'US-OH', 1, {'diy', 'home'},       '2020-03-14', None),
    ('garden-gate-supply',     'Garden Gate Supply',         0, 'US', 'USD', 4.4, 'LIVE',      'US-OR', 0, {'garden'},            '2020-08-02', None),
    ('fix-it-corner',          'Fix-It Corner',              0, 'US', 'USD', 4.1, 'LIVE',      'US-GA', 0, {'home', 'diy'},       '2021-02-20', None),
    ('maple-leaf-hardware',    'Maple Leaf Hardware',        0, 'CA', 'CAD', 4.5, 'LIVE',      'CA-ON', 0, {'diy', 'home', 'garden'}, '2021-05-11', None),
    ('werkstatt-direkt',       'Werkstatt Direkt',           0, 'DE', 'EUR', 4.3, 'LIVE',      'DE-BY', 0, {'diy'},               '2022-01-09', None),
    ('snack-shack-direct',     'Snack Shack Direct',         0, 'US', 'USD', 4.2, 'LIVE',      'US-TX', 1, {'grocery'},           '2020-11-30', None),
    ('pantry-pal',             'Pantry Pal',                 0, 'US', 'USD', 4.0, 'LIVE',      'US-NJ', 0, {'grocery', 'health'}, '2021-07-04', None),
    ('wellness-way',           'Wellness Way',               0, 'US', 'USD', 4.8, 'LIVE',      'US-IL', 1, {'health'},            '2020-06-18', None),
    ('inkwell-office',         'Inkwell Office',             0, 'US', 'USD', 4.3, 'LIVE',      'US-MA', 0, {'office'},            '2021-09-27', None),
    ('roadside-auto-parts',    'Roadside Auto Parts',        0, 'US', 'USD', 3.9, 'LIVE',      'US-MO', 0, {'auto'},              '2022-04-15', None),
    ('gadget-galaxy',          'Gadget Galaxy',              0, 'US', 'USD', 4.1, 'LIVE',      'US-CA', 1, {'elec'},              '2020-02-29', None),
    ('union-jack-pantry',      'Union Jack Pantry',          0, 'GB', 'GBP', 4.4, 'LIVE',      'GB-LND', 0, {'grocery'},          '2022-10-01', None),
    ('ironwood-tools-official', 'Ironwood Tools Official',   0, 'US', 'USD', 4.8, 'LIVE',      'US-PA', 1, {'brand:Ironwood Tools'}, '2021-03-01', None),
    ('greenthumb-official',    'GreenThumb Official Store',  0, 'CA', 'CAD', 4.6, 'LIVE',      'CA-BC', 0, {'brand:GreenThumb'},  '2022-02-14', None),
    ('crunchwell-official',    'Crunchwell Official',        0, 'US', 'USD', 4.5, 'LIVE',      'US-KS', 1, {'brand:CRW'},         '2023-05-05', None),
    ('cheap-charge-outlet',    'Cheap Charge Outlet',        0, 'CN', 'USD', 3.2, 'SUSPENDED', 'CN-GD', 0, {'elec'},              '2023-01-17', '2026-02-10 00:00:00'),
    ('old-mill-hardware',      'Old Mill Hardware',          0, 'US', 'USD', 4.0, 'CLOSED',    'US-VT', 0, {'garden', 'home'},    '2019-09-09', '2025-08-31 23:59:59'),
]

# ---------------------------------------------------------------------
# Browse paths, countries and groups for the reused catalogs
# ---------------------------------------------------------------------

BOB_BROWSE = {
    'snack': 'grocery>snacks', 'candy': 'grocery>candy-and-gum', 'cold': 'grocery>beverages',
    'hot': 'grocery>coffee-and-tea', 'otc': 'health>medicine-cabinet', 'office': 'office>supplies',
    'auto': 'automotive>car-care', 'elec': 'electronics>phone-accessories',
    'travel': 'travel>accessories',
}
BOB_GROUP = {'snack': 'grocery', 'candy': 'grocery', 'cold': 'grocery', 'hot': 'grocery',
             'otc': 'health', 'travel': 'health', 'office': 'office', 'auto': 'auto', 'elec': 'elec'}
COUNTRY_ISO = {'USA': 'US', 'Canada': 'CA', 'United Kingdom': 'GB', 'India': 'IN',
               'Japan': 'JP', 'China': 'CN', 'Italy': 'IT', 'Mexico': 'MX'}
CONSUMABLE_GROUPS = {'grocery', 'health', 'office'}

GIFT_MESSAGES = ['Happy birthday!', 'Enjoy the new tools!', 'For your road trip - drive safe!',
                 'Congrats on the new place!', 'Happy holidays from all of us.',
                 'Thinking of you - feel better soon.']


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def ts(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def new_uuid(rng) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def money(x) -> str:
    return f'{x:.2f}'


def price_99(amount: float) -> float:
    """Marketplace-style price: round to the nearest x.99 / x.49."""
    whole = max(int(round(amount)), 1)
    return whole - 0.01 if whole >= 5 else whole - 0.51


# ---------------------------------------------------------------------
# Catalog: reuse Acme and BobsUncle brands/models
# ---------------------------------------------------------------------

def source_catalog():
    """Rebuild the other generators' catalogs exactly as they produced them."""
    acme_rng = random.Random(ACME_SEED)
    acme_brands = acme.build_brands()
    acme_models = acme.build_models(acme_rng, acme_brands)
    bob_rng = random.Random(BOB_SEED)
    bob_brands, bob_products = bob.build_catalog(bob_rng)
    return acme_brands, acme_models, bob_brands, bob_products


def acme_browse_path(category_id):
    names = {c[0]: c[2] for c in acme.CATEGORIES}
    return '>'.join(slug(names[c]) for c in reversed(acme.category_ancestors(category_id)))


def brand_text_variants(name, legal):
    first = name.split()[0]
    return [name, name, name.upper(), first if len(first) > 4 else name, legal]


def build_listings(rng):
    acme_brands, acme_models, bob_brands, bob_products = source_catalog()
    brand_by_id = {b['BrandId']: b for b in acme_brands}
    country_by_brand = {spec[0]: spec[2] for spec in acme.BRANDS}
    bob_brand_rows = {b['brand_id']: b for b in bob_brands}
    listings = []

    for m in acme_models:
        b = brand_by_id[m['BrandId']]
        dept = acme.department_of(m['CategoryId'])
        listings.append(dict(
            src='ACME', src_key=m['Sku'], group={1: 'garden', 2: 'home', 3: 'diy'}[dept],
            name=m['ModelName'],
            long_name=f"{m['ModelName']}, Model {m['ModelNumber']}",
            brand_name=b['BrandName'],
            brand_texts=brand_text_variants(b['BrandName'], b['ManufacturerName']),
            mfr_part=m['ModelNumber'], upc=m['UpcCode'], country=country_by_brand[b['BrandName']],
            path=acme_browse_path(m['CategoryId']),
            grams=int(round(m['WeightLbs'] * 453.59237)),
            base_usd=m['MSRP'] / 100, active=not m['IsDiscontinued'],
            color=None, size=None, warranty_months=None))

    for p in bob_products:
        if p['kind'] in ('fresh', 'plan'):
            continue                                      # not sold online
        b = bob_brand_rows[p['brand_id']]
        spellings, countries = bob.MANUFACTURERS[b['mfr_cd']][:2]
        listings.append(dict(
            src='BOBSUNCLE', src_key=p['sku'], group=BOB_GROUP[p['dept']],
            name=p['short_desc'], long_name=p['long_desc'].rstrip('.'),
            brand_name=spellings[0], brand_texts=spellings, brand_code=b['mfr_cd'],
            mfr_part=b['model_no'], upc=p['upc_cd'] or p['ean_cd'],   # EAN-13 lands in PRD_UPC
            country=COUNTRY_ISO[countries[0]],
            path=BOB_BROWSE[p['dept']] + ('>pain-relief' if 'mg' in p['short_desc'] else ''),
            grams=int(round(float(p['wt_lbs']) * 453.59237)),
            base_usd=p['retail_price_cents'] / 100, active=not p['discontinued'],
            color=p['color_desc'], size=p['size_desc'], warranty_months=p['warr_months']))

    products = []
    for l in listings:
        products.append(make_product(rng, l))
        if rng.random() < 0.05:                           # duplicate listing by another seller
            dup = dict(l, name=reword(rng, l['name']), duplicate_of=products[-1]['PRD_UUID'])
            products.append(make_product(rng, dup))
    return products


def reword(rng, name):
    options = [name + ' - NEW', name.replace(' ', '  ', 1), name.upper(),
               re.sub(r'(\d+)-Pack', r'\1 Pack', name) + ' (Pack)', name + ' | Fast Shipping']
    return rng.choice(options)


def make_product(rng, l):
    alnum = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789'
    return dict(
        listing=l,
        PRD_UUID=new_uuid(rng),
        PRD_ID='BR' + ''.join(rng.choice(alnum) for _ in range(10)),
        PRD_NAME=l['name'][:200],
        PRD_LONG_NAME=l['long_name'] if rng.random() < 0.85 else None,
        PRD_BRAND_TEXT=rng.choice(l['brand_texts']) if rng.random() < 0.95 else None,
        PRD_MFR_PART_NO=(l['mfr_part'] if rng.random() < 0.8 else l['mfr_part'].replace('-', ''))
                        if rng.random() < 0.92 else None,
        PRD_UPC=l['upc'] if rng.random() < 0.93 else None,
        PRD_CNTRY_ORGN=l['country'] if rng.random() < 0.85 else None,
        PRD_BROWSE_PATH=l['path'],
        PRD_WEIGHT_GRAMS=l['grams'] if rng.random() < 0.9 else None,
        PRD_IS_ADULT=0,
        PRD_IS_ACTIVE=1 if l['active'] else 0)


def build_tags(rng, products):
    tags = []

    def add(p, key, value, source, conf=None):
        created = datetime(2024, 1, 1) + timedelta(minutes=rng.randint(0, 900 * 24 * 60))
        tags.append(dict(TAG_PRD_UUID=p['PRD_UUID'], TAG_KEY=key, TAG_VALUE=value,
                         TAG_SOURCE=source,
                         TAG_CONFIDENCE=None if conf is None else round(conf, 2),
                         TAG_CREATED_DATE=ts(created)))

    for p in products:
        l, name = p['listing'], p['listing']['name']
        if l['color']:
            add(p, 'color', l['color'].lower(), 'SELLER')
        if l['size']:
            add(p, 'size', l['size'], 'SELLER')
        if l['warranty_months']:
            add(p, 'warranty', f"{l['warranty_months']} months limited", 'BRAND')
        if l['src'] == 'ACME':
            volts = re.search(r'(\d+)V ', name)
            if volts:
                add(p, 'voltage', f'{volts.group(1)}V', 'BRAND')
            if volts or 'Cordless' in name:
                add(p, 'power_source', 'cordless', 'BRAND')
            elif 'Gas' in name:
                add(p, 'power_source', 'gas', 'BRAND')
            elif any(w in name for w in ('Corded', 'Electric', 'Grinder', 'Sander', 'Circular Saw', 'Miter')):
                add(p, 'power_source', 'corded', 'SELLER')
            for material in ('Fiberglass', 'Aluminum', 'Steel', 'Cedar', 'Brass', 'Vinyl'):
                if material in name:
                    add(p, 'material', material.lower(), 'SELLER')
            if l['group'] in ('diy',) and rng.random() < 0.5:
                add(p, 'warranty', rng.choice(['1 year limited', '3 year limited', 'lifetime']), 'BRAND')
            if l['group'] == 'garden':
                add(p, 'season', rng.choice(['spring', 'spring', 'summer']), 'ML', rng.uniform(0.55, 0.95))
        if any(w in name for w in ('Solar', 'LED', 'Drip', 'Mulch', 'Sparkling', 'Notebook', 'Copy Paper')):
            add(p, 'eco', 'true', 'ML', rng.uniform(0.6, 0.98))
        if any(w in name for w in ('Sugar Free', 'Diet')):
            add(p, 'dietary', 'sugar_free', 'ML', rng.uniform(0.8, 0.99))
        if l['group'] in CONSUMABLE_GROUPS:
            add(p, 'subscribe_eligible', 'true', 'SELLER')
        if rng.random() < 0.08:                            # noisy ML guesses
            add(p, 'gift_idea', 'true', 'ML', rng.uniform(0.3, 0.7))
    return tags


def build_stores(rng):
    stores = []
    for (handle, name, fp, country, ccy, rating, status, region, fbbr, sells,
         onboarded, ended) in STORES:
        start = datetime.fromisoformat(onboarded + ' 00:00:00') + timedelta(hours=rng.randint(8, 20))
        stores.append(dict(STR_UUID=new_uuid(rng), STR_HANDLE=handle, STR_DISPLAY_NAME=name,
                           STR_IS_FIRST_PARTY=fp, STR_COUNTRY_ISO=country, STR_DEFAULT_CCY=ccy,
                           STR_RATING=rating, STR_ONBOARDED_DATE=ts(start),
                           STR_STATUS=status, STR_DRP_SHP_REGION=region,
                           STR_EFF_DATE=ts(start), STR_EXP_DATE=ended, STR_FBBR=fbbr,
                           sells=sells, ends=datetime.fromisoformat(ended) if ended else None))
    return stores


def store_sells(store, product):
    l = product['listing']
    for rule in store['sells']:
        if rule == '*' or rule == l['group']:
            return True
        if rule.startswith('brand:'):
            b = rule[6:]
            if b == l['brand_name'] or b == l.get('brand_code'):
                return True
    return False


def build_offers(rng, products, stores):
    """Which stores sell which product, at what price (store currency)."""
    offers = {}
    first_party = stores[0]
    for p in products:
        eligible = [s for s in stores[1:] if store_sells(s, p)]
        dup = 'duplicate_of' in p['listing']
        chosen = rng.sample(eligible, k=min(len(eligible), 1 if dup else rng.choice([1, 1, 2, 2, 3])))
        if not dup:                                       # brand stores always carry their brand
            chosen += [s for s in eligible if s not in chosen
                       and any(r.startswith('brand:') for r in s['sells'])]
        if not dup and rng.random() < 0.55:
            chosen.append(first_party)
        if not chosen:
            chosen = [first_party]
        offers[p['PRD_UUID']] = []
        for s in chosen:
            usd = p['listing']['base_usd'] * rng.uniform(0.85, 1.12)
            offers[p['PRD_UUID']].append(dict(store=s, price=price_99(usd / USD_PER[s['STR_DEFAULT_CCY']])))
    return offers


def build_promotions(rng, products, stores):
    by_handle = {s['STR_HANDLE']: s for s in stores}
    promos = []

    def add(label, scope, start, end, funded='PLATFORM', store=None, code=None, target=None,
            tag=None, pct=None, amt=None, ccy=None, buy=None, get=None, max_red=None):
        promos.append(dict(PRM_UUID=new_uuid(rng), PRM_COUPON_CODE=code, PRM_LABEL=label,
                           PRM_FUNDED_BY=funded,
                           PRM_STR_UUID=by_handle[store]['STR_UUID'] if store else None,
                           PRM_SCOPE=scope,
                           PRM_TARGET_PRD_UUID=target['PRD_UUID'] if target else None,
                           PRM_TARGET_TAG_KEY=tag[0] if tag else None,
                           PRM_TARGET_TAG_VALUE=tag[1] if tag else None,
                           PRM_PCT_OFF=pct, PRM_AMT_OFF=amt, PRM_AMT_CCY=ccy,
                           PRM_BUY_QTY=buy, PRM_GET_QTY=get,
                           PRM_START_DATE=start, PRM_END_DATE=end or OPEN_ENDED,
                           PRM_MAX_REDEMPTIONS=max_red, redeemed=0))

    add('Big River Days: 10% off everything', 'SITEWIDE', '2025-07-08 07:00:00', '2025-07-10 06:59:59', pct=0.10)
    add('Big River Days: 10% off everything', 'SITEWIDE', '2026-07-14 07:00:00', '2026-07-16 06:59:59', pct=0.10)
    add('Black Friday: 20% off', 'SITEWIDE', '2025-11-28 05:00:00', '2025-12-02 07:59:59', pct=0.20)
    add('Earth Week: 15% off eco-friendly', 'TAG', '2025-04-18 00:00:00', '2025-04-26 23:59:59',
        tag=('eco', 'true'), pct=0.15)
    add('Earth Week: 15% off eco-friendly', 'TAG', '2026-04-17 00:00:00', '2026-04-25 23:59:59',
        tag=('eco', 'true'), pct=0.15)
    add('Cordless Tool Event: 12% off', 'TAG', '2025-05-01 00:00:00', '2026-06-30 23:59:59',
        funded='STORE', store='tool-haven', tag=('power_source', 'cordless'), pct=0.12)
    add('Subscribe & Save extra 5%', 'TAG', '2025-01-01 00:00:00', None,
        tag=('subscribe_eligible', 'true'), pct=0.05)
    candidates = [p for p in products if p['PRD_IS_ACTIVE'] and 'duplicate_of' not in p['listing']
                  and p['listing']['base_usd'] >= 20]
    for p in rng.sample(candidates, k=8):                  # lightning deals: no code, short window
        start = datetime(2025, 1, 15) + timedelta(days=rng.randint(0, 600), hours=rng.randint(8, 18))
        add(f"Lightning Deal: {p['PRD_NAME'][:60]}", 'PRODUCT', ts(start), ts(start + timedelta(hours=48)),
            target=p, pct=rng.choice([0.20, 0.25, 0.30, 0.35]), max_red=rng.choice([25, 50, 100]))
    chips = next(p for p in products if p['listing']['name'].startswith('Crunchwell Sea Salt Potato Chips 2.5'))
    add('Buy 2 Get 1 Free: Crunchwell chips', 'PRODUCT', '2025-03-01 00:00:00', '2026-12-31 23:59:59',
        funded='STORE', store='crunchwell-official', target=chips, buy=2, get=1)
    add('C$10 off Maple Leaf Hardware', 'SITEWIDE', '2025-09-01 00:00:00', '2025-10-31 23:59:59',
        funded='STORE', store='maple-leaf-hardware', code='MAPLE10', amt=10.00, ccy='CAD')
    add('$5 off your first order', 'CART', '2025-01-01 00:00:00', None, code='WELCOME5', amt=5.00, ccy='USD')
    add('10% off garden orders', 'CART', '2025-03-01 00:00:00', '2025-05-31 23:59:59', code='GARDEN10', pct=0.10)
    add('10% off garden orders', 'CART', '2026-03-01 00:00:00', '2026-05-31 23:59:59', code='GARDEN10B', pct=0.10)
    add('C$20 off C$150+', 'CART', '2025-06-01 00:00:00', None, code='SAVE20CA', amt=20.00, ccy='CAD',
        max_red=200)
    return promos


def promo_active(p, when: datetime):
    return (datetime.fromisoformat(p['PRM_START_DATE']) <= when <= datetime.fromisoformat(p['PRM_END_DATE'])
            and (p['PRM_MAX_REDEMPTIONS'] is None or p['redeemed'] < p['PRM_MAX_REDEMPTIONS']))


def promo_applies(p, product, store, tags_by_product, subscribe=False):
    if p['PRM_SCOPE'] == 'CART':
        return False
    if p['PRM_TARGET_TAG_KEY'] == 'subscribe_eligible' and not subscribe:
        return False
    if p['PRM_STR_UUID'] and p['PRM_STR_UUID'] != store['STR_UUID']:
        return False
    if p['PRM_SCOPE'] == 'PRODUCT':
        return p['PRM_TARGET_PRD_UUID'] == product['PRD_UUID']
    if p['PRM_SCOPE'] == 'TAG':
        return (p['PRM_TARGET_TAG_KEY'], p['PRM_TARGET_TAG_VALUE']) in tags_by_product.get(product['PRD_UUID'], set())
    return True                                            # SITEWIDE


def savings_for(p, price, qty, ccy):
    if p['PRM_BUY_QTY']:
        free = (qty // (p['PRM_BUY_QTY'] + p['PRM_GET_QTY'])) * p['PRM_GET_QTY']
        return round(free * price, 2)
    if p['PRM_PCT_OFF']:
        return round(price * qty * p['PRM_PCT_OFF'], 2)
    amount = p['PRM_AMT_OFF'] * USD_PER[p['PRM_AMT_CCY']] / USD_PER[ccy]
    return round(min(amount, price * qty), 2)


def random_time(rng, start: date, end: date) -> datetime:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    weights = [acme.MONTH_WEIGHT[d.month] * 0.5 + bob.MONTH_WEIGHT[d.month] * 0.5
               + (2.5 if (d.month, d.day) in ((11, 28), (11, 29), (12, 1), (7, 8), (7, 9), (7, 14), (7, 15)) else 0)
               for d in days]
    d = rng.choices(days, weights=weights)[0]
    hour = rng.choices(range(24), weights=bob.HOUR_WEIGHT)[0]
    return datetime(d.year, d.month, d.day, hour, rng.randint(0, 59), rng.randint(0, 59))


def build_carts(rng, n_carts, products, offers, promos, tags, as_of: datetime):
    tags_by_product = {}
    for t in tags:
        tags_by_product.setdefault(t['TAG_PRD_UUID'], set()).add((t['TAG_KEY'], t['TAG_VALUE']))
    by_group = {}
    for p in products:
        if p['PRD_IS_ACTIVE']:
            by_group.setdefault(p['listing']['group'], []).append(p)
    group_weights = {'grocery': 26, 'health': 12, 'office': 6, 'auto': 4, 'elec': 10,
                     'garden': 15, 'home': 13, 'diy': 14}
    accounts = [(new_uuid(rng), f"{rng.choice(bob.FIRST_NAMES)}.{rng.choice(bob.LAST_NAMES)}{i}@example.com")
                for i in range(220)]
    us_regions = ['US-TX', 'US-CA', 'US-NY', 'US-FL', 'US-IL', 'US-WA', 'US-OH', 'US-GA',
                  'US-NJ', 'US-CO', 'US-AZ', 'US-MN', 'US-MO', 'US-OR']
    ca_regions = ['CA-ON', 'CA-BC', 'CA-QC', 'CA-AB']
    cart_coupons = [p for p in promos if p['PRM_SCOPE'] == 'CART']
    product_by_uuid = {p['PRD_UUID']: p for p in products}

    carts, items = [], []
    for created in sorted(random_time(rng, date(2025, 1, 1), as_of.date() - timedelta(days=1))
                          for _ in range(n_carts)):
        canada = rng.random() < 0.12
        region = rng.choice(ca_regions if canada else us_regions)
        display_ccy = 'CAD' if canada else 'USD'
        if rng.random() < 0.82:
            account_id, email = rng.choice(accounts)
        else:
            account_id = None
            email = f'guest{rng.randint(1000, 99999)}@example.com'
        device = rng.choices(['DESKTOP', 'IOS', 'ANDROID', 'ALEXA'], weights=[40, 30, 25, 5])[0]

        n_lines = 1 if device == 'ALEXA' else rng.choices([1, 2, 3, 4, 5, 6], weights=[30, 28, 20, 11, 7, 4])[0]
        groups = list(group_weights)
        if device == 'ALEXA':                              # voice re-orders are consumables
            groups = ['grocery', 'health', 'office']
        lines, added, attempts = [], created, 0
        while len(lines) < n_lines and attempts < 30:
            attempts += 1
            g = rng.choices(groups, weights=[group_weights[x] for x in groups])[0]
            p = rng.choice(by_group[g])
            deals = [pr for pr in promos if pr['PRM_SCOPE'] == 'PRODUCT' and pr['PRM_BUY_QTY'] is None
                     and promo_active(pr, created)]                   # lightning deals
            if not lines and deals and rng.random() < 0.7:     # a running deal draws the shopper in
                p = product_by_uuid[rng.choice(deals)['PRM_TARGET_PRD_UUID']]
                g = p['listing']['group']
            live = [o for o in offers[p['PRD_UUID']] if o['store']['ends'] is None or created < o['store']['ends']]
            if not live or any(l['product'] is p for l in lines):
                continue
            offer = rng.choice(live)
            for pr in promos:                                  # prefer the store running a deal
                if (pr['PRM_TARGET_PRD_UUID'] == p['PRD_UUID'] and pr['PRM_STR_UUID']
                        and promo_active(pr, created) and rng.random() < 0.6):
                    offer = next((o for o in live if o['store']['STR_UUID'] == pr['PRM_STR_UUID']), offer)
            store, ccy = offer['store'], offer['store']['STR_DEFAULT_CCY']
            consumable = g in CONSUMABLE_GROUPS
            subscribe = consumable and account_id is not None and rng.random() < 0.18
            qty = rng.choices([1, 2, 3, 4, 6], weights=[60, 20, 10, 6, 4])[0] if consumable else \
                  rng.choices([1, 2], weights=[90, 10])[0]
            bogo = next((pr for pr in promos if pr['PRM_BUY_QTY'] and pr['PRM_TARGET_PRD_UUID'] == p['PRD_UUID']
                         and pr['PRM_STR_UUID'] == store['STR_UUID'] and promo_active(pr, created)), None)
            if bogo and rng.random() < 0.6:
                qty = bogo['PRM_BUY_QTY'] + bogo['PRM_GET_QTY']
            fx = 1.0 if ccy == 'USD' else round(USD_PER[ccy] * rng.uniform(0.985, 1.015), 6)
            added = added + timedelta(seconds=rng.randint(15, 600))
            promo, saving = None, 0.0
            candidates = [pr for pr in promos if promo_active(pr, added)
                          and promo_applies(pr, p, store, tags_by_product, subscribe)]
            if candidates:
                pr = max(candidates, key=lambda c: savings_for(c, offer['price'], qty, ccy))
                if pr['PRM_COUPON_CODE'] is None or rng.random() < 0.35:
                    s = savings_for(pr, offer['price'], qty, ccy)
                    if s > 0:
                        promo, saving = pr, s
            gift = rng.random() < 0.04
            lines.append(dict(product=p, store=store, qty=qty, price=offer['price'], ccy=ccy, fx=fx,
                              promo=promo, saving=saving, subscribe=subscribe, gift=gift,
                              added=added))

        age_hours = (as_of - created).total_seconds() / 3600
        if age_hours < 72 and rng.random() < 0.6:
            state = 'ACTIVE'
        else:
            state = rng.choices(['PURCHASED', 'EXPIRED', 'SAVED_FOR_LATER', 'ACTIVE'],
                                weights=[78, 12, 7, 3])[0]
        last_touch = lines[-1]['added'] + timedelta(minutes=rng.randint(0, 30))
        purchased = last_touch + timedelta(minutes=rng.randint(1, 15)) if state == 'PURCHASED' else None

        coupon = None
        if state == 'PURCHASED' and rng.random() < 0.12:
            usable = [c for c in cart_coupons if promo_active(c, purchased)
                      and (c['PRM_AMT_CCY'] in (None, display_ccy))]
            if usable:
                coupon = rng.choice(usable)
                coupon['redeemed'] += 1
        if state == 'PURCHASED':                           # only purchases count as redemptions
            for l in lines:
                if l['promo']:
                    l['promo']['redeemed'] += 1

        sc_uuid = new_uuid(rng)
        carts.append(dict(
            SC_UUID=sc_uuid, SC_ACCOUNT_ID=account_id, SC_SESSION_TOKEN='%064x' % rng.getrandbits(256),
            SC_CUSTOMER_EMAIL=email, SC_STATE=state,
            SC_CART_PRM_UUID=coupon['PRM_UUID'] if coupon else None,
            SC_DISPLAY_CCY=display_ccy, SC_DEVICE=device,
            SC_CREATED_DATE=ts(created),
            SC_UPDATED_DATE=ts(purchased or last_touch),
            SC_PURCHASED_DATE=ts(purchased) if purchased else None,
            SC_SHIP_REGION=region if state == 'PURCHASED' or rng.random() < 0.5 else None))
        for l in lines:
            items.append(dict(
                ITM_UUID=new_uuid(rng), ITM_SC_UUID=sc_uuid, ITM_PRD_UUID=l['product']['PRD_UUID'],
                ITM_STR_UUID=l['store']['STR_UUID'], ITM_QTY=l['qty'], ITM_OFFER_PRICE=l['price'],
                ITM_PRICE_CCY=l['ccy'], ITM_FX_RATE_TO_USD=l['fx'],
                ITM_PRM_UUID=l['promo']['PRM_UUID'] if l['promo'] else None,
                ITM_PRM_SAVINGS=l['saving'], ITM_IS_SUBSCRIBE_SAVE=int(l['subscribe']),
                ITM_IS_GIFT=int(l['gift']),
                ITM_GIFT_MSG=rng.choice(GIFT_MESSAGES) if l['gift'] and rng.random() < 0.8 else None,
                ITM_GIFT_WRAP=int(l['gift'] and rng.random() < 0.5),
                ITM_ADDED_DATE=ts(l['added'])))
    return carts, items


# ---------------------------------------------------------------------
# SQL output
# ---------------------------------------------------------------------

def sql(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert(table: str, columns: list, rows: list) -> str:
    out = [f'INSERT INTO {table} ({", ".join(columns)}) VALUES']
    out += ['    (' + ', '.join(r) + ')' + (',' if i < len(rows) - 1 else ';') for i, r in enumerate(rows)]
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--carts', type=int, default=500)
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--as-of', default='2026-10-01 00:00:00', help='"now" for the data set (UTC)')
    args = ap.parse_args()
    rng = random.Random(args.seed)
    as_of = datetime.fromisoformat(args.as_of)

    stores = build_stores(rng)
    products = build_listings(rng)
    tags = build_tags(rng, products)
    offers = build_offers(rng, products, stores)
    promos = build_promotions(rng, products, stores)
    carts, items = build_carts(rng, args.carts, products, offers, promos, tags, as_of)

    def num(x, fmt):
        return 'NULL' if x is None else format(x, fmt)

    out = [
        '-- =====================================================================',
        '-- BigRiver sample data: marketplace selling the AcmeShopping (garden,',
        '-- home improvement, DIY tools) and BobsUncle (convenience) catalogs.',
        f'-- Generated by generate_big_river_data.py --carts {args.carts} --seed {args.seed}',
        '-- Brands, model numbers and UPC/EAN codes match the AcmeShopping and',
        '-- BobsUncle sample data. Load after big_river.sql. All names are',
        '-- fictional; emails use example.com and websites the .example TLD.',
        '-- =====================================================================',
        '',
        'PRAGMA foreign_keys = ON;',
        'BEGIN TRANSACTION;',
        '',
        insert('STORE',
               ['STR_UUID', 'STR_HANDLE', 'STR_DISPLAY_NAME', 'STR_IS_FIRST_PARTY', 'STR_COUNTRY_ISO',
                'STR_DEFAULT_CCY', 'STR_RATING', 'STR_ONBOARDED_DATE', 'STR_STATUS',
                'STR_DRP_SHP_REGION', 'STR_EFF_DATE', 'STR_EXP_DATE', 'STR_FBBR'],
               [[sql(s['STR_UUID']), sql(s['STR_HANDLE']), sql(s['STR_DISPLAY_NAME']),
                 sql(s['STR_IS_FIRST_PARTY']), sql(s['STR_COUNTRY_ISO']), sql(s['STR_DEFAULT_CCY']),
                 num(s['STR_RATING'], '.1f'), sql(s['STR_ONBOARDED_DATE']), sql(s['STR_STATUS']),
                 sql(s['STR_DRP_SHP_REGION']), sql(s['STR_EFF_DATE']), sql(s['STR_EXP_DATE']),
                 sql(s['STR_FBBR'])] for s in stores]),
        '',
        insert('PRODUCT',
               ['PRD_UUID', 'PRD_ID', 'PRD_NAME', 'PRD_LONG_NAME', 'PRD_BRAND_TEXT', 'PRD_MFR_PART_NO',
                'PRD_UPC', 'PRD_CNTRY_ORGN', 'PRD_BROWSE_PATH', 'PRD_WEIGHT_GRAMS', 'PRD_IS_ADULT',
                'PRD_IS_ACTIVE'],
               [[sql(p[c]) for c in ['PRD_UUID', 'PRD_ID', 'PRD_NAME', 'PRD_LONG_NAME', 'PRD_BRAND_TEXT',
                                     'PRD_MFR_PART_NO', 'PRD_UPC', 'PRD_CNTRY_ORGN', 'PRD_BROWSE_PATH',
                                     'PRD_WEIGHT_GRAMS', 'PRD_IS_ADULT', 'PRD_IS_ACTIVE']]
                for p in products]),
        '',
        insert('PRODUCT_TAGS',
               ['TAG_PRD_UUID', 'TAG_KEY', 'TAG_VALUE', 'TAG_SOURCE', 'TAG_CONFIDENCE', 'TAG_CREATED_DATE'],
               [[sql(t['TAG_PRD_UUID']), sql(t['TAG_KEY']), sql(t['TAG_VALUE']), sql(t['TAG_SOURCE']),
                 num(t['TAG_CONFIDENCE'], '.2f'), sql(t['TAG_CREATED_DATE'])] for t in tags]),
        '',
        insert('PROMOTIONS',
               ['PRM_UUID', 'PRM_COUPON_CODE', 'PRM_LABEL', 'PRM_FUNDED_BY', 'PRM_STR_UUID', 'PRM_SCOPE',
                'PRM_TARGET_PRD_UUID', 'PRM_TARGET_TAG_KEY', 'PRM_TARGET_TAG_VALUE', 'PRM_PCT_OFF',
                'PRM_AMT_OFF', 'PRM_AMT_CCY', 'PRM_BUY_QTY', 'PRM_GET_QTY', 'PRM_START_DATE',
                'PRM_END_DATE', 'PRM_MAX_REDEMPTIONS'],
               [[sql(p['PRM_UUID']), sql(p['PRM_COUPON_CODE']), sql(p['PRM_LABEL']), sql(p['PRM_FUNDED_BY']),
                 sql(p['PRM_STR_UUID']), sql(p['PRM_SCOPE']), sql(p['PRM_TARGET_PRD_UUID']),
                 sql(p['PRM_TARGET_TAG_KEY']), sql(p['PRM_TARGET_TAG_VALUE']), num(p['PRM_PCT_OFF'], '.3f'),
                 num(p['PRM_AMT_OFF'], '.2f'), sql(p['PRM_AMT_CCY']), sql(p['PRM_BUY_QTY']),
                 sql(p['PRM_GET_QTY']), sql(p['PRM_START_DATE']), sql(p['PRM_END_DATE']),
                 sql(p['PRM_MAX_REDEMPTIONS'])] for p in promos]),
        '',
        insert('SHOPPING_CART',
               ['SC_UUID', 'SC_ACCOUNT_ID', 'SC_SESSION_TOKEN', 'SC_CUSTOMER_EMAIL', 'SC_STATE',
                'SC_CART_PRM_UUID', 'SC_DISPLAY_CCY', 'SC_DEVICE', 'SC_CREATED_DATE',
                'SC_UPDATED_DATE', 'SC_PURCHASED_DATE', 'SC_SHIP_REGION'],
               [[sql(c[k]) for k in ['SC_UUID', 'SC_ACCOUNT_ID', 'SC_SESSION_TOKEN', 'SC_CUSTOMER_EMAIL',
                                     'SC_STATE', 'SC_CART_PRM_UUID', 'SC_DISPLAY_CCY', 'SC_DEVICE',
                                     'SC_CREATED_DATE', 'SC_UPDATED_DATE',
                                     'SC_PURCHASED_DATE', 'SC_SHIP_REGION']] for c in carts]),
        '',
        insert('ITEM',
               ['ITM_UUID', 'ITM_SC_UUID', 'ITM_PRD_UUID', 'ITM_STR_UUID', 'ITM_QTY', 'ITM_OFFER_PRICE',
                'ITM_PRICE_CCY', 'ITM_FX_RATE_TO_USD', 'ITM_PRM_UUID', 'ITM_PRM_SAVINGS',
                'ITM_IS_SUBSCRIBE_SAVE', 'ITM_IS_GIFT', 'ITM_GIFT_MSG', 'ITM_GIFT_WRAP', 'ITM_ADDED_DATE'],
               [[sql(i['ITM_UUID']), sql(i['ITM_SC_UUID']), sql(i['ITM_PRD_UUID']), sql(i['ITM_STR_UUID']),
                 sql(i['ITM_QTY']), money(i['ITM_OFFER_PRICE']), sql(i['ITM_PRICE_CCY']),
                 format(i['ITM_FX_RATE_TO_USD'], '.6f'), sql(i['ITM_PRM_UUID']), money(i['ITM_PRM_SAVINGS']),
                 sql(i['ITM_IS_SUBSCRIBE_SAVE']), sql(i['ITM_IS_GIFT']), sql(i['ITM_GIFT_MSG']),
                 sql(i['ITM_GIFT_WRAP']), sql(i['ITM_ADDED_DATE'])] for i in items]),
        '',
        'COMMIT;',
        '',
    ]
    path = HERE / 'big_river_sample_data.sql'
    path.write_text('\n'.join(out))
    print(f'{path.name}: {len(stores)} stores, {len(products)} products, {len(tags)} tags, '
          f'{len(promos)} promotions, {len(carts)} carts, {len(items)} items')


if __name__ == '__main__':
    main()
