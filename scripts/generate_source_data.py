"""
Generate the simulated operational data for Vireo Wholesale (a fictional company).

The output is a set of CSV files in data/source_csv/ that mirror the tables in
database/source/01_create_source_schema.sql. Load them with
scripts/setup_source_db.py.

The data is random but reproducible (fixed seed), so everyone who runs this
script gets exactly the same database.

Usage:
    python scripts/generate_source_data.py
    python scripts/generate_source_data.py --seed 7 --out data/source_csv
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

START = date(2023, 1, 1)
END = date(2026, 8, 31)

# -----------------------------------------------------------------------------
# Reference data
# -----------------------------------------------------------------------------
COUNTRIES = {
    "Hungary":  {"code": "HU", "currency": "HUF", "weight": 0.32,
                 "cities": ["Budapest", "Budapest", "Budapest", "Debrecen", "Szeged", "Pécs", "Győr", "Miskolc", "Kecskemét"],
                 "suffixes": ["Kft.", "Kft.", "Zrt.", "Bt."],
                 "manual_date_fmt": "%Y.%m.%d."},
    "Austria":  {"code": "AT", "currency": "EUR", "weight": 0.22,
                 "cities": ["Vienna", "Vienna", "Graz", "Linz", "Salzburg", "Innsbruck"],
                 "suffixes": ["GmbH", "GmbH", "AG"],
                 "manual_date_fmt": "%d.%m.%Y"},
    "Czechia":  {"code": "CZ", "currency": "CZK", "weight": 0.20,
                 "cities": ["Prague", "Prague", "Brno", "Ostrava", "Plzeň"],
                 "suffixes": ["s.r.o.", "s.r.o.", "a.s."],
                 "manual_date_fmt": "%d.%m.%Y"},
    "Slovakia": {"code": "SK", "currency": "EUR", "weight": 0.12,
                 "cities": ["Bratislava", "Bratislava", "Košice", "Žilina", "Nitra"],
                 "suffixes": ["s.r.o.", "a.s."],
                 "manual_date_fmt": "%d.%m.%Y"},
    "Romania":  {"code": "RO", "currency": "RON", "weight": 0.14,
                 "cities": ["Bucharest", "Bucharest", "Cluj-Napoca", "Timișoara", "Iași", "Oradea"],
                 "suffixes": ["S.R.L.", "S.R.L.", "S.A."],
                 "manual_date_fmt": "%d/%m/%Y"},
}

# Messy ways the same country is typed into the customer master
COUNTRY_VARIANTS = {
    "Hungary":  ["HU", "hungary", "Hungary ", "Magyarország"],
    "Austria":  ["AT", "Österreich", "austria"],
    "Czechia":  ["Czech Republic", "CZ", "czechia"],
    "Slovakia": ["SK", "Slovak Republic"],
    "Romania":  ["RO", "romania"],
}

# (first, last, territory, hire_date, termination_date, share of territory's customers)
SALES_REPS = [
    ("Anna", "Kovács", "Hungary", "2016-03-01", None, 0.30),
    ("Péter", "Nagy", "Hungary", "2018-09-15", None, 0.30),
    ("Eszter", "Tóth", "Hungary", "2020-02-01", None, 0.25),
    ("Gábor", "Szabó", "Hungary", "2022-06-01", None, 0.15),
    ("Lukas", "Gruber", "Austria", "2015-01-10", None, 0.40),
    ("Sophie", "Huber", "Austria", "2019-04-01", None, 0.35),
    ("Maximilian", "Bauer", "Austria", "2021-10-01", None, 0.25),
    ("Jan", "Novák", "Czechia", "2017-05-01", None, 0.40),
    ("Tereza", "Svobodová", "Czechia", "2019-11-01", None, 0.35),
    ("Martin", "Dvořák", "Czechia", "2022-01-15", None, 0.25),
    ("Lucia", "Horváthová", "Slovakia", "2018-02-01", None, 0.55),
    ("Tomáš", "Kučera", "Slovakia", "2021-07-01", None, 0.45),
    # Story: the key account manager in Romania leaves at the end of March 2025
    ("Andrei", "Popescu", "Romania", "2014-06-01", "2025-03-31", 0.70),
    ("Ioana", "Ionescu", "Romania", "2023-09-01", None, 0.30),
]

NAME_PREFIXES = [
    "Danube", "Alpine", "Carpathian", "Nova", "Summit", "Blue River", "Silverline", "Oakwood",
    "Horizon", "Central", "Metro", "Pannon", "Bohemia", "Tatra", "Vista", "Apex", "Crown",
    "Delta", "Evergreen", "Granite", "Harbor", "Iron Gate", "Lumen", "Meridian", "Northstar",
    "Orbit", "Pioneer", "Quantum", "Riverside", "Sterling", "Trident", "Unity", "Vertex",
    "Westbrook", "Zenith", "Amber", "Beacon", "Cedar", "Duna", "Falcon", "Greenfield",
]
NAME_INDUSTRIES = [
    "Logistics", "Dental Clinic", "Hotels", "Engineering", "Law Office", "Accounting",
    "Language School", "Software", "Manufacturing", "Retail", "Property Management",
    "Medical Center", "Construction", "Consulting", "Foods", "Printing House",
    "Auto Service", "Fitness", "Architects", "Insurance Brokers", "Pharmacy", "Media",
]

SEGMENTS = {
    #               share  orders/month  qty multiplier  discount range   monthly churn
    "Enterprise": (0.10, 3.2, 2.6, (0.08, 0.15), 0.002),
    "Mid-Market": (0.30, 1.6, 1.4, (0.03, 0.08), 0.006),
    "SMB":        (0.60, 0.6, 0.7, (0.00, 0.03), 0.014),
}

SEASONALITY = {1: 0.90, 2: 0.95, 3: 1.05, 4: 1.00, 5: 1.00, 6: 0.95,
               7: 0.85, 8: 0.75, 9: 1.10, 10: 1.10, 11: 1.15, 12: 0.95}

# category: (suppliers, cost ratio, qty range, base line weight)
CATEGORIES = {
    "Paper & Printing":      (["PaperMill Europa", "Printwell Supplies"], 0.76, (5, 60), 0.30),
    "Cleaning & Hygiene":    (["Aurora Hygiene", "CleanWave Industrial"], 0.68, (3, 40), 0.25),
    "Breakroom & Catering":  (["Kaffeehaus Trading", "Pantry Partners"], 0.72, (3, 30), 0.20),
    "Tech Accessories":      (["Voltix Distribution", "NordTech Components"], 0.64, (1, 15), 0.15),
    "Office Furniture":      (["Ergonom Furniture Works", "Modulo Office"], 0.58, (1, 6), 0.10),
}

# category -> list of (product name, list price EUR, variants)
CATALOG = {
    "Paper & Printing": [
        ("A4 Copy Paper 80g, 500 sheets", 4.90, [""]),
        ("A3 Copy Paper 80g, 500 sheets", 9.80, [""]),
        ("A4 Premium Paper 100g, 500 sheets", 7.50, [""]),
        ("Toner Cartridge", 69.00, ["Black", "Cyan", "Magenta", "Yellow"]),
        ("Inkjet Cartridge", 24.00, ["Black", "Colour"]),
        ("Labels A4 24/sheet, 100 sheets", 18.00, [""]),
        ("Envelopes C4, 250 pcs", 21.00, [""]),
        ("Envelopes DL, 500 pcs", 16.00, [""]),
        ("Sticky Notes 76x76, 12 pads", 8.50, ["Yellow", "Neon Mix"]),
        ("Ring Binders A4, 10 pcs", 22.00, ["Black", "Blue"]),
        ("Notebooks A5 Ruled, 10 pcs", 19.00, [""]),
        ("Ballpoint Pens, 50 pcs", 14.00, ["Blue", "Black"]),
        ("Whiteboard Markers, 12 pcs", 11.00, [""]),
        ("Stapler Heavy Duty", 27.00, [""]),
        ("Staples 24/6, 5000 pcs", 3.20, [""]),
        ("Document Wallets, 50 pcs", 12.00, [""]),
        ("Laminating Pouches A4, 100 pcs", 15.00, [""]),
    ],
    "Cleaning & Hygiene": [
        ("Hand Soap Refill 5L", 14.00, [""]),
        ("Hand Sanitizer Gel 1L", 7.90, [""]),
        ("Paper Towels Z-fold, 20 packs", 32.00, [""]),
        ("Toilet Paper 2-ply, 64 rolls", 38.00, [""]),
        ("Jumbo Toilet Rolls, 6 pcs", 29.00, [""]),
        ("Multi-surface Cleaner 5L", 19.00, [""]),
        ("Floor Cleaner Concentrate 10L", 34.00, [""]),
        ("Disinfectant Spray 750ml, 12 pcs", 42.00, [""]),
        ("Nitrile Gloves, 100 pcs", 8.90, ["Size S", "Size M", "Size L", "Size XL"]),
        ("Garbage Bags 120L, 100 pcs", 24.00, [""]),
        ("Microfibre Cloths, 50 pcs", 27.00, [""]),
        ("Mop Set with Bucket", 45.00, [""]),
        ("Soap Dispenser Wall-mounted", 36.00, [""]),
        ("Dishwasher Tablets, 200 pcs", 39.00, [""]),
    ],
    "Breakroom & Catering": [
        ("Coffee Beans 1kg", 21.00, ["Espresso", "Crema", "Decaf"]),
        ("Ground Coffee 500g", 8.50, [""]),
        ("Coffee Capsules, 100 pcs", 29.00, ["Intense", "Lungo"]),
        ("Tea Assortment, 100 bags", 9.00, [""]),
        ("Sugar Sticks, 1000 pcs", 17.00, [""]),
        ("Milk Portions, 240 pcs", 19.00, [""]),
        ("Paper Cups 200ml, 1000 pcs", 26.00, [""]),
        ("Wooden Stirrers, 1000 pcs", 6.50, [""]),
        ("Bottled Water 0.5L, 24 pcs", 7.20, ["Still", "Sparkling"]),
        ("Biscuit Assortment 2kg", 23.00, [""]),
        ("Napkins 33x33, 2000 pcs", 21.00, [""]),
        ("Water Filter Cartridge", 31.00, [""]),
    ],
    "Tech Accessories": [
        ("Wireless Mouse", 19.00, ["Black", "Grey"]),
        ("Wireless Keyboard & Mouse Set", 49.00, ["HU layout", "DE layout", "CZ layout"]),
        ("USB-C Hub 7-in-1", 45.00, [""]),
        ("USB-C Charging Cable 2m", 12.00, [""]),
        ("HDMI Cable 2m", 9.00, [""]),
        ("Monitor FHD", 129.00, ['24"', '27"']),
        ("Laptop Stand Aluminium", 39.00, [""]),
        ("Webcam 1080p", 59.00, [""]),
        ("USB Headset with Mic", 55.00, [""]),
        ("Docking Station USB-C", 149.00, [""]),
        ("Power Strip 6-way", 18.00, [""]),
        ("Portable SSD 1TB", 89.00, [""]),
        ("Laptop Backpack 15.6\"", 42.00, [""]),
    ],
    "Office Furniture": [
        ("Ergonomic Office Chair", 289.00, ["Black", "Grey"]),
        ("Height-adjustable Desk 160x80", 549.00, [""]),
        ("Office Desk 140x70", 259.00, ["Oak", "White"]),
        ("Meeting Table 240x100", 689.00, [""]),
        ("Visitor Chairs, 4 pcs", 299.00, [""]),
        ("Filing Cabinet 3-drawer", 219.00, [""]),
        ("Mobile Pedestal", 179.00, [""]),
        ("Bookshelf 5-tier", 189.00, [""]),
        ("Acoustic Desk Divider", 129.00, [""]),
        ("Dual Monitor Arm", 119.00, [""]),
        ("Adjustable Footrest", 39.00, [""]),
        ("Whiteboard 180x120", 159.00, [""]),
    ],
}

RETURN_REASONS = ["Damaged in transit", "Defective", "Wrong item delivered", "Ordered by mistake"]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def month_starts(start: date, end: date) -> list[date]:
    months, d = [], date(start.year, start.month, 1)
    while d <= end:
        months.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return months


def days_in_month(d: date) -> int:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - d).days


def add_business_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def price_factor(category: str, d: date) -> float:
    """List price index vs. 2023: +3% every January (Tech only +1%)."""
    step = 0.01 if category == "Tech Accessories" else 0.03
    return (1 + step) ** (d.year - 2023)


def cost_periods(category: str) -> list[tuple[date, float]]:
    """(valid_from, cost index vs. 2023). Tech gets hit by supplier price rises."""
    if category == "Tech Accessories":
        return [(date(2023, 1, 1), 1.00), (date(2024, 1, 1), 1.02),
                (date(2025, 3, 1), 1.02 * 1.16), (date(2026, 1, 1), 1.02 * 1.16 * 1.07)]
    return [(date(2023, 1, 1), 1.00), (date(2024, 1, 1), 1.025),
            (date(2025, 1, 1), 1.025 ** 2), (date(2026, 1, 1), 1.025 ** 3)]


# -----------------------------------------------------------------------------
# Generator
# -----------------------------------------------------------------------------
class Generator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

    # --- reference tables ----------------------------------------------------
    def build_reps(self) -> pd.DataFrame:
        rows = []
        for i, (first, last, terr, hired, left, _) in enumerate(SALES_REPS, start=101):
            email = f"{first}.{last}@vireo-wholesale.example".lower()
            email = (email.replace("á", "a").replace("é", "e").replace("ó", "o")
                     .replace("ř", "r").replace("š", "s").replace("č", "c").replace("ž", "z"))
            rows.append(dict(rep_id=i, first_name=first, last_name=last, email=email,
                             territory=terr, hire_date=hired, termination_date=left))
        return pd.DataFrame(rows)

    def build_products(self):
        rows, costs = [], []
        pid = 1001
        for category, items in CATALOG.items():
            suppliers, cost_ratio, _, _ = CATEGORIES[category]
            prefix = "".join(w[0] for w in category.replace("&", "").split())[:3].upper()
            for n, (name, price, variants) in enumerate(items, start=1):
                supplier = suppliers[n % 2]
                for v_idx, variant in enumerate(variants):
                    full_name = f"{name} - {variant}" if variant else name
                    sku = f"{prefix}-{n:03d}{'' if not variant else chr(65 + v_idx)}"
                    base_price = round(price * self.rng.uniform(0.97, 1.03), 2)
                    ratio = cost_ratio * self.rng.uniform(0.95, 1.05)
                    current_price = round(base_price * price_factor(category, END), 2)
                    rows.append(dict(product_id=pid, sku=sku, product_name=full_name,
                                     category=category, supplier=supplier,
                                     list_price_eur=current_price, is_active=True,
                                     tmp_base_price=base_price))
                    periods = cost_periods(category)
                    for k, (valid_from, idx) in enumerate(periods):
                        valid_to = periods[k + 1][0] - timedelta(days=1) if k + 1 < len(periods) else None
                        costs.append(dict(product_id=pid, valid_from=valid_from, valid_to=valid_to,
                                          unit_cost_eur=round(base_price * ratio * idx, 2)))
                    pid += 1
        products = pd.DataFrame(rows)
        # a few discontinued items
        products.loc[products.sample(6, random_state=1).index, "is_active"] = False
        return products, pd.DataFrame(costs)

    def build_fx(self) -> pd.DataFrame:
        anchors = {  # (months since start, units per EUR)
            "HUF": [(0, 400.0), (6, 380.0), (18, 392.0), (24, 410.0), (36, 402.0), (43, 395.0)],
            "CZK": [(0, 24.1), (12, 24.6), (24, 25.2), (36, 24.9), (43, 24.6)],
            "RON": [(0, 4.92), (12, 4.96), (24, 4.98), (36, 5.04), (43, 5.07)],
        }
        rows = []
        for i, m in enumerate(month_starts(START, END)):
            rows.append(dict(rate_month=m, currency="EUR", units_per_eur=1.0))
            for cur, pts in anchors.items():
                x, y = zip(*pts)
                val = float(np.interp(i, x, y)) * self.rng.uniform(0.992, 1.008)
                rows.append(dict(rate_month=m, currency=cur, units_per_eur=round(val, 4)))
        return pd.DataFrame(rows)

    # --- customers -----------------------------------------------------------
    def _unique_name(self, used: set, suffix: str) -> str:
        while True:
            name = f"{self.rng.choice(NAME_PREFIXES)} {self.rng.choice(NAME_INDUSTRIES)}"
            key = name.lower()
            if key not in used:
                used.add(key)
                return f"{name} {suffix}"

    def build_customers(self, reps: pd.DataFrame) -> pd.DataFrame:
        used, rows = set(), []
        countries = list(COUNTRIES)
        weights = [COUNTRIES[c]["weight"] for c in countries]
        seg_names = list(SEGMENTS)
        seg_weights = [SEGMENTS[s][0] for s in seg_names]

        # 300 existing customers + steady acquisition (growing slightly over time)
        created = [datetime(2016, 1, 1) + timedelta(days=self.rng.randint(0, 7 * 365 - 1)) for _ in range(300)]
        for i, m in enumerate(month_starts(START, END)):
            for _ in range(self.np_rng.poisson(4.0 + i * 0.06)):
                created.append(datetime(m.year, m.month, self.rng.randint(1, days_in_month(m)),
                                        self.rng.randint(8, 17), self.rng.randint(0, 59)))
        created.sort()

        for cid, created_at in enumerate(created, start=10001):
            country = self.rng.choices(countries, weights)[0]
            segment = self.rng.choices(seg_names, seg_weights)[0]
            terr_reps = [r for r in SALES_REPS if r[2] == country]
            rep = self.rng.choices(terr_reps, [r[5] for r in terr_reps])[0]
            rep_id = int(reps.loc[(reps.first_name == rep[0]) & (reps.last_name == rep[1]), "rep_id"].iloc[0])
            rows.append(dict(
                customer_id=cid,
                customer_name=self._unique_name(used, self.rng.choice(COUNTRIES[country]["suffixes"])),
                segment=segment, city=self.rng.choice(COUNTRIES[country]["cities"]),
                country=country, assigned_rep_id=rep_id, created_at=created_at,
                tmp_activity=float(self.np_rng.lognormal(0, 0.45)),
            ))
        return pd.DataFrame(rows)

    # --- orders --------------------------------------------------------------
    def build_orders(self, customers, reps, products, fx):
        rng = self.rng
        rep_by_name = {(r.first_name, r.last_name): r.rep_id for r in reps.itertuples()}
        departed_rep = rep_by_name[("Andrei", "Popescu")]
        successor_rep = rep_by_name[("Ioana", "Ionescu")]
        departure = date(2025, 3, 31)

        fx_lookup = {(r.rate_month, r.currency): r.units_per_eur for r in fx.itertuples()}
        prods_by_cat = {c: list(products[products.category == c].itertuples()) for c in CATEGORIES}
        cat_names = list(CATEGORIES)

        orders, lines = [], []
        order_id, line_id = 500001, 1
        churned: set[int] = set()
        months = month_starts(START, END)
        total_months = len(months)

        for m_idx, m in enumerate(months):
            season = SEASONALITY[m.month]
            # Tech accessories grow their share of the basket over time
            tech_share = 0.10 + 0.12 * m_idx / total_months
            cat_weights = [CATEGORIES[c][3] for c in cat_names]
            cat_weights[cat_names.index("Tech Accessories")] = tech_share

            for c in customers.itertuples():
                if c.customer_id in churned or c.created_at.date() > date(m.year, m.month, days_in_month(m)):
                    continue
                share, rate, qty_mult, disc_rng, churn = SEGMENTS[c.segment]
                romania_hit = (c.country == "Romania" and c.assigned_rep_id == departed_rep
                               and m > departure)
                if romania_hit:
                    churn *= 5
                    rate *= 0.55
                if rng.random() < churn:
                    churned.add(c.customer_id)
                    continue

                n_orders = self.np_rng.poisson(rate * season * c.tmp_activity)
                for _ in range(n_orders):
                    first_day = max(1, c.created_at.day) if (c.created_at.year, c.created_at.month) == (m.year, m.month) else 1
                    day = rng.randint(first_day, days_in_month(m))
                    od = date(m.year, m.month, day)
                    if od.weekday() >= 5 and rng.random() < 0.9:
                        od = add_business_days(od, 1)
                    if od > END:
                        continue

                    # rep at the time of the order
                    rep_id = c.assigned_rep_id
                    if rep_id == departed_rep and od > departure:
                        rep_id = successor_rep

                    channel = rng.choices(["Web Shop", "Sales Rep", "Phone/Email", "EDI"],
                                          [0.35, 0.30, 0.25, 0.10] if c.segment != "Enterprise"
                                          else [0.15, 0.25, 0.15, 0.45])[0]
                    currency = COUNTRIES[c.country]["currency"]
                    if c.segment == "Enterprise" and currency != "EUR" and c.customer_id % 5 == 0:
                        currency = "EUR"   # some large accounts are invoiced in EUR
                    rate_fx = fx_lookup[(date(od.year, od.month, 1), currency)]

                    if rng.random() < 0.03:
                        status = "Cancelled"
                    elif (END - od).days <= 3:
                        status = "Open"
                    elif (END - od).days <= 10:
                        status = rng.choice(["Shipped", "Delivered"])
                    else:
                        status = "Delivered"
                    ship = None
                    if status in ("Shipped", "Delivered"):
                        ship = add_business_days(od, rng.randint(1, 5))

                    # created_at = when the order was keyed into the system. Manual channels
                    # are often entered a few days late, so it is NOT the business order date.
                    entry_lag = 0 if channel in ("Web Shop", "EDI") else rng.choice([0, 0, 0, 1, 1, 2, 3, 5])
                    entry_day = od + timedelta(days=entry_lag)
                    created_at = datetime(entry_day.year, entry_day.month, entry_day.day,
                                          rng.randint(7, 18), rng.randint(0, 59), rng.randint(0, 59))
                    orders.append(dict(
                        order_id=order_id,
                        order_number=f"SO-{od.year}-{order_id - 500000:06d}",
                        customer_id=c.customer_id, rep_id=rep_id,
                        tmp_order_date=od, tmp_ship_date=ship, tmp_country=c.country,
                        status=status, currency=currency, sales_channel=channel,
                        created_at=created_at,
                    ))

                    n_lines = min(1 + self.np_rng.poisson(2.4), 10)
                    chosen = set()
                    for _ in range(n_lines):
                        cat = rng.choices(cat_names, cat_weights)[0]
                        p = rng.choice(prods_by_cat[cat])
                        if p.product_id in chosen:
                            continue
                        chosen.add(p.product_id)
                        lo, hi = CATEGORIES[cat][2]
                        qty = max(1, round(rng.randint(lo, hi) * qty_mult))
                        price_eur = p.tmp_base_price * price_factor(cat, od)
                        decimals = 0 if currency == "HUF" else 2
                        lines.append(dict(
                            order_line_id=line_id, order_id=order_id, product_id=int(p.product_id),
                            quantity=qty, unit_price=round(price_eur * rate_fx, decimals),
                            discount_pct=round(rng.uniform(*disc_rng), 3),
                            tmp_category=cat, tmp_supplier=p.supplier,
                        ))
                        line_id += 1
                    order_id += 1

        return pd.DataFrame(orders), pd.DataFrame(lines)

    def build_returns(self, orders, lines):
        rng = self.rng
        delivered = orders.loc[orders.status == "Delivered", ["order_id", "tmp_ship_date"]]
        df = lines.merge(delivered, on="order_id")
        rows, rid = [], 70001
        for r in df.itertuples():
            p = 0.012
            if r.tmp_supplier == "Aurora Hygiene":
                p = 0.07          # story: one supplier has a quality problem
            elif r.tmp_category == "Office Furniture":
                p = 0.03
            if rng.random() < p:
                reason = ("Defective" if r.tmp_supplier == "Aurora Hygiene" and rng.random() < 0.7
                          else rng.choice(RETURN_REASONS))
                rdate = r.tmp_ship_date + timedelta(days=rng.randint(2, 30))
                if rdate > END:
                    continue
                rows.append(dict(return_id=rid, order_id=r.order_id, product_id=r.product_id,
                                 return_date=rdate, quantity=rng.randint(1, max(1, r.quantity // 2 + 1)),
                                 reason=reason))
                rid += 1
        return pd.DataFrame(rows)

    # -------------------------------------------------------------------------
    # Data quality problems (the kind every real source system has)
    # -------------------------------------------------------------------------
    def make_messy(self, customers, products, orders, lines):
        rng = self.rng

        # 1) Order dates stored as text; format depends on how the order was entered
        def fmt_order_date(o):
            od, ts = o.tmp_order_date, o.created_at
            if o.sales_channel in ("Web Shop", "EDI"):
                return ts.strftime("%Y-%m-%dT%H:%M:%S")
            if o.sales_channel == "Phone/Email":
                return od.strftime(COUNTRIES[o.tmp_country]["manual_date_fmt"])
            return od.strftime("%Y-%m-%d")

        orders["order_date"] = [fmt_order_date(o) for o in orders.itertuples()]
        orders["ship_date"] = [d.strftime("%Y-%m-%d") if d else None for d in orders.tmp_ship_date]

        # 2) Typo'd years (2025 -> 2052 etc.)
        iso_idx = orders.index[orders.sales_channel == "Sales Rep"]
        for i in rng.sample(list(iso_idx), 6):
            d = orders.at[i, "order_date"]
            orders.at[i, "order_date"] = d[:2] + d[3] + d[2] + d[4:]

        # 3) Missing ship dates on some delivered orders
        deliv = orders.index[orders.status == "Delivered"]
        orders.loc[rng.sample(list(deliv), int(len(deliv) * 0.01)), "ship_date"] = None

        # 4) Inconsistent status spelling
        variants = {"Delivered": ["delivered", "DELIVERED", "Delivered "],
                    "Cancelled": ["Canceled", "CANCELLED", "cancelled"],
                    "Shipped": ["shipped", "SHIPPED"], "Open": ["open", "OPEN"]}
        for i in rng.sample(list(orders.index), int(len(orders) * 0.08)):
            orders.at[i, "status"] = rng.choice(variants[orders.at[i, "status"]])

        # 5) Messy currency codes
        for i in rng.sample(list(orders.index), int(len(orders) * 0.02)):
            orders.at[i, "currency"] = orders.at[i, "currency"].lower()
        huf = list(orders.index[orders.currency == "HUF"])
        orders.loc[rng.sample(huf, int(len(huf) * 0.01)), "currency"] = "Ft"
        orders.loc[rng.sample(list(orders.index), int(len(orders) * 0.004)), "currency"] = None
        # ... and a handful of Hungarian orders labelled EUR although the amounts are in HUF
        huf_now = list(orders.index[orders.currency == "HUF"])
        orders.loc[rng.sample(huf_now, 15), "currency"] = "EUR"

        # 6) Order-line problems
        lines.loc[rng.sample(list(lines.index), int(len(lines) * 0.008)), "unit_price"] = None
        disc = list(lines.index[lines.discount_pct > 0.01])
        pct_idx = rng.sample(disc, int(len(disc) * 0.01))
        lines.loc[pct_idx, "discount_pct"] = (lines.loc[pct_idx, "discount_pct"] * 100).round(1)
        bad_qty = rng.sample(list(lines.index), int(len(lines) * 0.003))
        lines.loc[bad_qty, "quantity"] = [rng.choice([0, -1, -2, -5]) for _ in bad_qty]

        # 7) Duplicate products created during an ERP migration (June 2024):
        #    same item, different SKU spelling; later orders use the new record
        products = products.drop(columns="tmp_base_price")
        dup_rows = []
        next_pid = int(products.product_id.max()) + 1
        order_dates = orders.set_index("order_id").tmp_order_date
        for p in products.sample(8, random_state=3).itertuples():
            sku = rng.choice([p.sku.lower(), p.sku + " ", p.sku.replace("-", "")])
            name = rng.choice([p.product_name.upper(), p.product_name.replace(",", ""),
                               "  " + p.product_name])
            dup_rows.append(dict(product_id=next_pid, sku=sku, product_name=name, category=p.category,
                                 supplier=p.supplier, list_price_eur=p.list_price_eur, is_active=True))
            idx = lines.index[(lines.product_id == p.product_id) &
                              (lines.order_id.map(order_dates) >= date(2024, 6, 1))]
            lines.loc[[i for i in idx if rng.random() < 0.6], "product_id"] = next_pid
            next_pid += 1
        products = pd.concat([products, pd.DataFrame(dup_rows)], ignore_index=True)

        # 8) Duplicate orders (double-submitted from the web shop)
        dup_src = orders[orders.sales_channel == "Web Shop"].sample(frac=0.012, random_state=5)
        next_oid = int(orders.order_id.max()) + 1
        next_lid = int(lines.order_line_id.max()) + 1
        new_orders, new_lines = [], []
        for o in dup_src.to_dict("records"):
            new = dict(o, order_id=next_oid, created_at=o["created_at"] + timedelta(seconds=rng.randint(2, 40)))
            new_orders.append(new)
            for ln in lines[lines.order_id == o["order_id"]].to_dict("records"):
                new_lines.append(dict(ln, order_line_id=next_lid, order_id=next_oid))
                next_lid += 1
            next_oid += 1
        orders = pd.concat([orders, pd.DataFrame(new_orders)], ignore_index=True)
        lines = pd.concat([lines, pd.DataFrame(new_lines)], ignore_index=True)

        # 9) Test / demo customers that must be excluded from reporting
        test_ids = [99901, 99902]
        test_rows = [
            dict(customer_id=99901, customer_name="TEST CUSTOMER - DO NOT USE", segment="SMB",
                 city="Budapest", country="Hungary", assigned_rep_id=101,
                 created_at=datetime(2024, 2, 12, 9, 30)),
            dict(customer_id=99902, customer_name="Demo Account (IT)", segment="Enterprise",
                 city="Vienna", country="Austria", assigned_rep_id=105,
                 created_at=datetime(2024, 9, 3, 14, 5)),
        ]
        sample_orders = orders[orders.order_id < 600000].sample(40, random_state=9)
        for k, o in enumerate(sample_orders.to_dict("records")):
            new = dict(o, order_id=next_oid, customer_id=test_ids[k % 2],
                       order_number=f"TEST-{k:04d}")
            orders = pd.concat([orders, pd.DataFrame([new])], ignore_index=True)
            src = lines[lines.order_id == o["order_id"]].to_dict("records")
            lines = pd.concat([lines, pd.DataFrame([dict(l, order_line_id=next_lid + j, order_id=next_oid)
                                                    for j, l in enumerate(src)])], ignore_index=True)
            next_lid += len(src)
            next_oid += 1

        # 10) Orphan orders: customer records deleted from the master
        orphan_idx = rng.sample(list(orders.index[orders.customer_id < 99900]), 10)
        orders.loc[orphan_idx, "customer_id"] = [90001 + i for i in range(10)]

        # 11) Customer master: messy names and countries, a few duplicates
        customers = customers.drop(columns="tmp_activity")
        customers = pd.concat([customers, pd.DataFrame(test_rows)], ignore_index=True)
        for i in rng.sample(list(customers.index), int(len(customers) * 0.05)):
            n = customers.at[i, "customer_name"]
            customers.at[i, "customer_name"] = rng.choice([n.upper(), "  " + n, n + "  ", n.replace(".", "")])
        for i in rng.sample(list(customers.index), int(len(customers) * 0.15)):
            customers.at[i, "country"] = rng.choice(COUNTRY_VARIANTS[customers.at[i, "country"]])
        customers.loc[rng.sample(list(customers.index), int(len(customers) * 0.02)), "country"] = None

        dup_c, next_cid = [], 20001
        for c in customers[customers.customer_id < 99900].sample(6, random_state=11).to_dict("records"):
            name = c["customer_name"].strip()
            dup_c.append(dict(c, customer_id=next_cid,
                              customer_name=rng.choice([name.upper(), name.replace(".", ""), name.lower()]),
                              created_at=c["created_at"] + timedelta(days=rng.randint(200, 600))))
            mask = (orders.customer_id == c["customer_id"])
            move = [i for i in orders.index[mask] if rng.random() < 0.4]
            orders.loc[move, "customer_id"] = next_cid
            next_cid += 1
        customers = pd.concat([customers, pd.DataFrame(dup_c)], ignore_index=True)

        return customers, products, orders, lines

    # -------------------------------------------------------------------------
    def run(self, out_dir: Path):
        reps = self.build_reps()
        products, costs = self.build_products()
        fx = self.build_fx()
        customers = self.build_customers(reps)
        orders, lines = self.build_orders(customers, reps, products, fx)
        returns = self.build_returns(orders, lines)
        customers, products, orders, lines = self.make_messy(customers, products, orders, lines)

        order_cols = ["order_id", "order_number", "customer_id", "rep_id", "order_date", "ship_date",
                      "status", "currency", "sales_channel", "created_at"]
        line_cols = ["order_line_id", "order_id", "product_id", "quantity", "unit_price", "discount_pct"]
        customer_cols = ["customer_id", "customer_name", "segment", "city", "country",
                         "assigned_rep_id", "created_at"]

        # reassign the departed rep's customers (current state of the master data)
        rep_id = {(r.first_name, r.last_name): r.rep_id for r in reps.itertuples()}
        customers.loc[customers.assigned_rep_id == rep_id[("Andrei", "Popescu")], "assigned_rep_id"] = \
            rep_id[("Ioana", "Ionescu")]

        tables = {
            "sales_reps": reps,
            "customers": customers[customer_cols],
            "products": products,
            "product_cost_history": costs,
            "fx_rates": fx,
            "orders": orders[order_cols].sort_values("order_id"),
            "order_lines": lines[line_cols].sort_values("order_line_id"),
            "returns": returns,
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            if "customer_id" in df and name in ("orders",):
                df["customer_id"] = df["customer_id"].astype("Int64")
            if name == "order_lines":
                df["quantity"] = df["quantity"].astype("Int64")
            df.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8")
            print(f"  {name:<22} {len(df):>8,} rows")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "source_csv")
    args = parser.parse_args()
    print(f"Generating Vireo Wholesale source data (seed={args.seed}) ...")
    Generator(args.seed).run(args.out)
    print(f"Done. CSV files written to {args.out}")


if __name__ == "__main__":
    main()
