"""
Provision Pantry & Inventory Seed Script
Populates the SQLite database with authentic Philippine supermarket products,
realistic inventory batches (FEFO demonstration), grocery sessions (SM Supermarket, Savemore, Puregold),
audit events (consumption, waste/expiration), and shopping list items.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.core.time import household_today
from app.models.base import Base
from app.models.product import Product, ProductSource
from app.models.location import StorageLocation
from app.models.session import GrocerySession, GrocerySessionStatus
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.models.shopping import ShoppingListItem
from app.models.user import User


def seed_database(reset: bool = True, db: Optional[Session] = None) -> Dict[str, int]:
    print("🌱 Starting Provision database seeding with Philippine grocery data...")

    should_close = False
    if db is None:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        should_close = True
    else:
        Base.metadata.create_all(bind=db.get_bind())
    try:
        # 1. Setup / Preserve Users
        print("\n[1/7] Ensuring demo and existing user accounts...")
        existing_users = {u.email: u for u in db.query(User).all()}

        demo_users_data = [
            ("user@provision.local", "password123", "Maria Santos"),
            ("demo@provision.local", "password123", "Juan Dela Cruz"),
        ]

        for email, pwd, name in demo_users_data:
            if email not in existing_users:
                new_user = User(
                    email=email,
                    hashed_password=hash_password(pwd),
                    display_name=name,
                    is_active=True,
                )
                db.add(new_user)
                print(f"  + Created user: {email} ({name})")
            else:
                print(f"  * User already exists: {email}")

        db.commit()

        # 2. Reset Inventory Data if requested
        if reset:
            print("\n[2/7] Clearing previous inventory data (preserving users)...")
            db.query(InventoryEvent).delete()
            db.query(InventoryBatch).delete()
            db.query(ShoppingListItem).delete()
            db.query(GrocerySession).delete()
            db.query(StorageLocation).delete()
            db.query(Product).delete()
            db.commit()
            print("  ✓ Cleared previous inventory tables successfully.")

        # 3. Storage Locations
        print("\n[3/7] Seeding storage locations...")
        locations_data = [
            ("Pantry - Shelf A", "Canned goods, soups, preserved meats, and tuna"),
            ("Pantry - Shelf B", "Noodles, pasta, snacks, biscuits, and rice"),
            ("Refrigerator - Top Shelf", "Dairy, cheese, eggs, and opened jars"),
            ("Refrigerator - Door Rack", "Beverages, milk cartons, condiments, and sauces"),
            ("Refrigerator - Crisper", "Fresh vegetables, fruits, and calamansi"),
            ("Freezer", "Frozen processed meats, hotdogs, and tocino"),
            ("Spice & Seasoning Station", "Cooking oils, soy sauce, vinegars, salt, and seasoning packets"),
        ]

        existing_locs = {loc.name: loc for loc in db.query(StorageLocation).all()}
        loc_map: Dict[str, StorageLocation] = {}
        for name, desc in locations_data:
            if name in existing_locs:
                loc = existing_locs[name]
            else:
                loc = StorageLocation(name=name, description=desc)
                db.add(loc)
                db.flush()
                print(f"  + Storage Location: {name}")
            loc_map[name] = loc
        db.commit()

        # 4. Grocery Sessions
        print("\n[4/7] Seeding grocery intake sessions...")
        now = datetime.now(timezone.utc)
        today = household_today()

        sessions_data = [
            (
                "SM Supermarket - Megamall (Receipt #0994)",
                now - timedelta(days=14, hours=3),
                Decimal("3450.75"),
                GrocerySessionStatus.COMPLETED,
                "Regular bi-monthly family grocery run. Receipt #0994 scanned via mobile intake.",
            ),
            (
                "Savemore Market - Light Residences",
                now - timedelta(days=7, hours=2),
                Decimal("1820.50"),
                GrocerySessionStatus.COMPLETED,
                "Mid-week replenishment: dairy, breakfast bread, coffee, and pantry sauces.",
            ),
            (
                "Puregold Price Club - Shaw",
                now - timedelta(days=2, hours=5),
                Decimal("2685.00"),
                GrocerySessionStatus.COMPLETED,
                "Restock run for hotdogs, pancit canton, beer, and snacks.",
            ),
            (
                "Robinsons Supermarket - Magnolia",
                now,
                Decimal("850.00"),
                GrocerySessionStatus.DRAFT,
                "Draft session for testing live intake scanning and receipt matching.",
            ),
        ]

        existing_sessions = {s.store_name: s for s in db.query(GrocerySession).all()}
        session_map: Dict[str, GrocerySession] = {}
        for store, pdate, total, status, notes in sessions_data:
            if store in existing_sessions:
                sess = existing_sessions[store]
            else:
                sess = GrocerySession(
                    store_name=store,
                    purchase_date=pdate,
                    total_amount=total,
                    status=status,
                    notes=notes,
                )
                db.add(sess)
                db.flush()
                print(f"  + Grocery Session: {store} [{status.value}] (₱{total})")
            session_map[store] = sess
        db.commit()

        # 5. Product Catalog (Authentic Philippine Supermarket Products)
        print("\n[5/7] Seeding Philippine product catalog...")
        products_catalog = [
            # Canned Goods
            {
                "name": "Century Tuna Flakes in Oil",
                "brand": "Century Tuna",
                "barcode": "4800016644818",
                "category": "Canned Goods",
                "package_size": 180.0,
                "unit": "cans",
                "default_price": Decimal("44.50"),
            },
            {
                "name": "Century Tuna Hot & Spicy",
                "brand": "Century Tuna",
                "barcode": "4800016644825",
                "category": "Canned Goods",
                "package_size": 180.0,
                "unit": "cans",
                "default_price": Decimal("45.00"),
            },
            {
                "name": "San Marino Corned Tuna",
                "brand": "San Marino",
                "barcode": "4800110025421",
                "category": "Canned Goods",
                "package_size": 180.0,
                "unit": "cans",
                "default_price": Decimal("48.50"),
            },
            {
                "name": "Purefoods Corned Beef Classic",
                "brand": "Purefoods",
                "barcode": "4800361389440",
                "category": "Canned Goods",
                "package_size": 210.0,
                "unit": "cans",
                "default_price": Decimal("102.00"),
            },
            {
                "name": "Mega Sardines in Tomato Sauce with Chili",
                "brand": "Mega Sardines",
                "barcode": "4800168100217",
                "category": "Canned Goods",
                "package_size": 155.0,
                "unit": "cans",
                "default_price": Decimal("26.75"),
            },
            {
                "name": "555 Fried Sardines Escabeche",
                "brand": "555",
                "barcode": "4800016555121",
                "category": "Canned Goods",
                "package_size": 155.0,
                "unit": "cans",
                "default_price": Decimal("28.50"),
            },
            {
                "name": "CDO Karne Norte",
                "brand": "CDO",
                "barcode": "4800888139580",
                "category": "Canned Goods",
                "package_size": 150.0,
                "unit": "cans",
                "default_price": Decimal("38.00"),
            },
            {
                "name": "Spam Luncheon Meat Classic",
                "brand": "SPAM",
                "barcode": "037600104616",
                "category": "Canned Goods",
                "package_size": 340.0,
                "unit": "cans",
                "default_price": Decimal("195.00"),
            },
            {
                "name": "Argentina Corned Beef",
                "brand": "Argentina",
                "barcode": "4800110014029",
                "category": "Canned Goods",
                "package_size": 150.0,
                "unit": "cans",
                "default_price": Decimal("39.50"),
            },
            # Noodles & Quick Meals
            {
                "name": "Lucky Me! Pancit Canton Kalamansi",
                "brand": "Lucky Me!",
                "barcode": "4800361005210",
                "category": "Noodles & Quick Meals",
                "package_size": 80.0,
                "unit": "packs",
                "default_price": Decimal("15.50"),
            },
            {
                "name": "Lucky Me! Pancit Canton Chilimansi",
                "brand": "Lucky Me!",
                "barcode": "4800361005319",
                "category": "Noodles & Quick Meals",
                "package_size": 80.0,
                "unit": "packs",
                "default_price": Decimal("15.50"),
            },
            {
                "name": "Lucky Me! Pancit Canton Extra Hot Chili",
                "brand": "Lucky Me!",
                "barcode": "4800361005418",
                "category": "Noodles & Quick Meals",
                "package_size": 80.0,
                "unit": "packs",
                "default_price": Decimal("15.50"),
            },
            {
                "name": "Lucky Me! Pancit Canton Original",
                "brand": "Lucky Me!",
                "barcode": "4800361005111",
                "category": "Noodles & Quick Meals",
                "package_size": 80.0,
                "unit": "packs",
                "default_price": Decimal("15.50"),
            },
            {
                "name": "Lucky Me! Instant Mami Chicken",
                "brand": "Lucky Me!",
                "barcode": "4800361001113",
                "category": "Noodles & Quick Meals",
                "package_size": 55.0,
                "unit": "packs",
                "default_price": Decimal("13.75"),
            },
            {
                "name": "Nissin Cup Noodles Seafood",
                "brand": "Nissin",
                "barcode": "4800016053016",
                "category": "Noodles & Quick Meals",
                "package_size": 60.0,
                "unit": "cups",
                "default_price": Decimal("32.00"),
            },
            # Condiments & Sauces
            {
                "name": "Datu Puti Soy Sauce",
                "brand": "Datu Puti",
                "barcode": "4801981110010",
                "category": "Condiments & Sauces",
                "package_size": 1.0,
                "unit": "L",
                "default_price": Decimal("48.00"),
            },
            {
                "name": "Datu Puti White Vinegar",
                "brand": "Datu Puti",
                "barcode": "4801981120019",
                "category": "Condiments & Sauces",
                "package_size": 1.0,
                "unit": "L",
                "default_price": Decimal("44.50"),
            },
            {
                "name": "Silver Swan Soy Sauce",
                "brand": "Silver Swan",
                "barcode": "4800038101115",
                "category": "Condiments & Sauces",
                "package_size": 1.0,
                "unit": "L",
                "default_price": Decimal("49.00"),
            },
            {
                "name": "UFC Tamis Anghang Banana Catsup",
                "brand": "UFC",
                "barcode": "4801668601017",
                "category": "Condiments & Sauces",
                "package_size": 550.0,
                "unit": "g",
                "default_price": Decimal("41.50"),
            },
            {
                "name": "Mang Tomas All-Around Sarsa",
                "brand": "Mang Tomas",
                "barcode": "4801668201019",
                "category": "Condiments & Sauces",
                "package_size": 330.0,
                "unit": "g",
                "default_price": Decimal("39.00"),
            },
            {
                "name": "Knorr Sinigang sa Sampalok Mix Original",
                "brand": "Knorr",
                "barcode": "4800888121110",
                "category": "Condiments & Sauces",
                "package_size": 44.0,
                "unit": "packs",
                "default_price": Decimal("25.00"),
            },
            {
                "name": "Knorr Liquid Seasoning Original",
                "brand": "Knorr",
                "barcode": "4800888111111",
                "category": "Condiments & Sauces",
                "package_size": 250.0,
                "unit": "mL",
                "default_price": Decimal("82.00"),
            },
            {
                "name": "Golden Fiesta Pure Palm Cooking Oil",
                "brand": "Golden Fiesta",
                "barcode": "4801981440018",
                "category": "Condiments & Sauces",
                "package_size": 1.0,
                "unit": "L",
                "default_price": Decimal("95.00"),
            },
            {
                "name": "Mama Sita's Oyster Sauce",
                "brand": "Mama Sita's",
                "barcode": "4800088111119",
                "category": "Condiments & Sauces",
                "package_size": 405.0,
                "unit": "g",
                "default_price": Decimal("68.50"),
            },
            # Dairy & Chilled
            {
                "name": "Magnolia Fresh Milk",
                "brand": "Magnolia",
                "barcode": "4800110041117",
                "category": "Dairy & Chilled",
                "package_size": 1.0,
                "unit": "L",
                "default_price": Decimal("108.00"),
            },
            {
                "name": "Magnolia Gold Pure Butter Salted",
                "brand": "Magnolia",
                "barcode": "4800110031118",
                "category": "Dairy & Chilled",
                "package_size": 225.0,
                "unit": "g",
                "default_price": Decimal("165.00"),
            },
            {
                "name": "Eden Original Cheese Melt",
                "brand": "Eden",
                "barcode": "4800016021114",
                "category": "Dairy & Chilled",
                "package_size": 165.0,
                "unit": "blocks",
                "default_price": Decimal("62.00"),
            },
            {
                "name": "Nestlé All-Purpose Cream",
                "brand": "Nestlé",
                "barcode": "7613035612118",
                "category": "Dairy & Chilled",
                "package_size": 250.0,
                "unit": "mL",
                "default_price": Decimal("74.00"),
            },
            {
                "name": "Alaska Sweetened Condensed Milk",
                "brand": "Alaska",
                "barcode": "4800016042119",
                "category": "Dairy & Chilled",
                "package_size": 300.0,
                "unit": "cans",
                "default_price": Decimal("64.00"),
            },
            {
                "name": "Alaska Evaporated Milk",
                "brand": "Alaska",
                "barcode": "4800016041112",
                "category": "Dairy & Chilled",
                "package_size": 370.0,
                "unit": "cans",
                "default_price": Decimal("42.00"),
            },
            {
                "name": "Bear Brand Fortified Powdered Milk Drink",
                "brand": "Bear Brand",
                "barcode": "7613035111116",
                "category": "Dairy & Chilled",
                "package_size": 300.0,
                "unit": "g",
                "default_price": Decimal("125.00"),
            },
            {
                "name": "Bounty Fresh Farm Eggs (Medium Dozen)",
                "brand": "Bounty Fresh",
                "barcode": "4800999000042",
                "category": "Dairy & Chilled",
                "package_size": 12.0,
                "unit": "pcs",
                "default_price": Decimal("110.00"),
            },
            # Frozen & Meats
            {
                "name": "Purefoods Tender Juicy Hotdog Classic",
                "brand": "Purefoods",
                "barcode": "4800361301114",
                "category": "Frozen & Meats",
                "package_size": 1.0,
                "unit": "kg",
                "default_price": Decimal("215.00"),
            },
            {
                "name": "CDO Funtastyk Young Pork Tocino",
                "brand": "CDO",
                "barcode": "4800888123456",
                "category": "Frozen & Meats",
                "package_size": 450.0,
                "unit": "g",
                "default_price": Decimal("120.00"),
            },
            {
                "name": "Pampanga's Best Pork Longganisa",
                "brand": "Pampanga's Best",
                "barcode": "4806501234567",
                "category": "Frozen & Meats",
                "package_size": 500.0,
                "unit": "g",
                "default_price": Decimal("135.00"),
            },
            # Snacks & Bakery
            {
                "name": "Gardenia Classic White Bread",
                "brand": "Gardenia",
                "barcode": "4806500800018",
                "category": "Snacks & Bakery",
                "package_size": 600.0,
                "unit": "loaves",
                "default_price": Decimal("82.00"),
            },
            {
                "name": "SkyFlakes Crackers Tub",
                "brand": "M.Y. San",
                "barcode": "4800016001017",
                "category": "Snacks & Bakery",
                "package_size": 800.0,
                "unit": "tubs",
                "default_price": Decimal("188.00"),
            },
            {
                "name": "Piattos Cheese Flavored Potato Crisps",
                "brand": "Jack 'n Jill",
                "barcode": "4800016601019",
                "category": "Snacks & Bakery",
                "package_size": 85.0,
                "unit": "bags",
                "default_price": Decimal("38.50"),
            },
            {
                "name": "Oishi Prawn Crackers",
                "brand": "Oishi",
                "barcode": "4800194111118",
                "category": "Snacks & Bakery",
                "package_size": 90.0,
                "unit": "bags",
                "default_price": Decimal("24.00"),
            },
            {
                "name": "Kopiko Blanca 3-in-1 Coffee Mix",
                "brand": "Kopiko",
                "barcode": "8996001414002",
                "category": "Snacks & Bakery",
                "package_size": 10.0,
                "unit": "packs",
                "default_price": Decimal("85.00"),
            },
            {
                "name": "Choc Nut Peanut Milk Chocolate",
                "brand": "Choc Nut",
                "barcode": "4800055111111",
                "category": "Snacks & Bakery",
                "package_size": 24.0,
                "unit": "pcs",
                "default_price": Decimal("45.00"),
            },
            # Grains & Staples
            {
                "name": "Harvester's Dinorado Special Rice",
                "brand": "Harvester's",
                "barcode": "4806511110015",
                "category": "Grains & Staples",
                "package_size": 5.0,
                "unit": "kg",
                "default_price": Decimal("325.00"),
            },
            {
                "name": "Harvester's Sinandomeng Premium Rice",
                "brand": "Harvester's",
                "barcode": "4806511110022",
                "category": "Grains & Staples",
                "package_size": 5.0,
                "unit": "kg",
                "default_price": Decimal("290.00"),
            },
            # Beverages
            {
                "name": "San Miguel Pale Pilsen",
                "brand": "San Miguel",
                "barcode": "4800010111118",
                "category": "Beverages",
                "package_size": 330.0,
                "unit": "cans",
                "default_price": Decimal("52.00"),
            },
            {
                "name": "C2 Cool & Clean Green Tea Apple",
                "brand": "C2",
                "barcode": "4800016777110",
                "category": "Beverages",
                "package_size": 500.0,
                "unit": "bottles",
                "default_price": Decimal("26.00"),
            },
            {
                "name": "Royal Tru-Orange",
                "brand": "Royal",
                "barcode": "4800001112225",
                "category": "Beverages",
                "package_size": 1.5,
                "unit": "L",
                "default_price": Decimal("68.00"),
            },
            # Fresh Produce
            {
                "name": "Fresh Native Calamansi",
                "brand": "Local Produce",
                "barcode": "4800999000011",
                "category": "Fresh Produce",
                "package_size": 500.0,
                "unit": "g",
                "default_price": Decimal("45.00"),
            },
            {
                "name": "Native Red Onion (Sibuyas)",
                "brand": "Local Produce",
                "barcode": "4800999000028",
                "category": "Fresh Produce",
                "package_size": 1.0,
                "unit": "kg",
                "default_price": Decimal("120.00"),
            },
            {
                "name": "Native Garlic (Bawang)",
                "brand": "Local Produce",
                "barcode": "4800999000035",
                "category": "Fresh Produce",
                "package_size": 500.0,
                "unit": "g",
                "default_price": Decimal("80.00"),
            },
        ]

        existing_prods_by_name = {p.name: p for p in db.query(Product).all()}
        existing_prods_by_barcode = {p.barcode: p for p in db.query(Product).all() if p.barcode}
        prod_map: Dict[str, Product] = {}
        for pdata in products_catalog:
            if pdata["name"] in existing_prods_by_name:
                prod = existing_prods_by_name[pdata["name"]]
            elif pdata["barcode"] and pdata["barcode"] in existing_prods_by_barcode:
                prod = existing_prods_by_barcode[pdata["barcode"]]
            else:
                prod = Product(
                    name=pdata["name"],
                    brand=pdata["brand"],
                    barcode=pdata["barcode"],
                    category=pdata["category"],
                    package_size=pdata["package_size"],
                    unit=pdata["unit"],
                    source=ProductSource.USER_CONFIRMED,
                )
                db.add(prod)
                db.flush()
            prod_map[pdata["name"]] = prod
        db.commit()
        print(f"  ✓ Seeded {len(prod_map)} authentic Philippine products across {len(set(p['category'] for p in products_catalog))} categories.")

        # 6. Inventory Batches & FEFO Setup
        print("\n[6/7] Seeding inventory batches, FEFO queues, and audit events...")
        sm_session = session_map["SM Supermarket - Megamall (Receipt #0994)"]
        savemore_session = session_map["Savemore Market - Light Residences"]
        puregold_session = session_map["Puregold Price Club - Shaw"]

        # Specifications for batches to demonstrate:
        # - Expiring soon (1, 2, 4 days) -> Alerts & urgent action cards
        # - Low stock (<= 2.0) -> Restock needed cards
        # - Multi-batch FEFO (Century Tuna, Purefoods Corned Beef)
        # - Price history (multiple purchase events across sessions with varying unit prices)
        # - Healthy pantry stock
        # - Out-of-stock product (Argentina Corned Beef with 0 remaining)

        batches_spec = [
            # 1. Expiring in 2 days (Gardenia Bread) -> URGENT ALERT
            {
                "product": "Gardenia Classic White Bread",
                "location": "Pantry - Shelf B",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=2),
                "original_quantity": 2.0,
                "remaining_quantity": 1.0,
                "unit_price": Decimal("82.00"),
                "events": [
                    (EventType.PURCHASED, 2.0, now - timedelta(days=2), "Intake from Puregold"),
                    (EventType.CONSUMED, 1.0, now - timedelta(days=1), "Breakfast toast with butter"),
                ],
            },
            # 2. Expiring Tomorrow (Magnolia Fresh Milk) -> URGENT ALERT
            {
                "product": "Magnolia Fresh Milk",
                "location": "Refrigerator - Door Rack",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=6),
                "expiration_date": today + timedelta(days=1),
                "original_quantity": 2.0,
                "remaining_quantity": 1.0,
                "unit_price": Decimal("108.00"),
                "events": [
                    (EventType.PURCHASED, 2.0, now - timedelta(days=6), "Intake from Savemore"),
                    (EventType.CONSUMED, 1.0, now - timedelta(days=3), "Cereal breakfast and milk tea"),
                ],
            },
            # 3. Expiring in 4 days (Bounty Fresh Eggs)
            {
                "product": "Bounty Fresh Farm Eggs (Medium Dozen)",
                "location": "Refrigerator - Top Shelf",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=4),
                "original_quantity": 12.0,
                "remaining_quantity": 8.0,
                "unit_price": Decimal("9.17"), # ₱110 / 12 pcs
                "events": [
                    (EventType.PURCHASED, 12.0, now - timedelta(days=7), "Intake from Savemore"),
                    (EventType.CONSUMED, 4.0, now - timedelta(days=4), "Scrambled eggs with onions"),
                ],
            },
            # 4. FEFO Demonstration: Century Tuna Flakes in Oil (2 Batches)
            # Batch 1 (USE FIRST): Expiring in 90 days, 4 cans remaining
            {
                "product": "Century Tuna Flakes in Oil",
                "location": "Pantry - Shelf A",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=90),
                "original_quantity": 6.0,
                "remaining_quantity": 4.0,
                "unit_price": Decimal("43.50"), # Price point 1
                "events": [
                    (EventType.PURCHASED, 6.0, now - timedelta(days=14), "Intake from SM Megamall (Receipt #0994)"),
                    (EventType.CONSUMED, 2.0, now - timedelta(days=9), "Tuna omelette breakfast"),
                ],
            },
            # Batch 2 (Rest of Stock): Expiring in 365 days, 12 cans remaining
            {
                "product": "Century Tuna Flakes in Oil",
                "location": "Pantry - Shelf A",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=365),
                "original_quantity": 12.0,
                "remaining_quantity": 12.0,
                "unit_price": Decimal("45.00"), # Price point 2
                "events": [
                    (EventType.PURCHASED, 12.0, now - timedelta(days=2), "Intake from Puregold Price Club"),
                ],
            },
            # 5. Price History Demonstration: Purefoods Corned Beef Classic (2 Batches)
            # Batch 1: Purchased 14 days ago at ₱98.50
            {
                "product": "Purefoods Corned Beef Classic",
                "location": "Pantry - Shelf A",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=300),
                "original_quantity": 4.0,
                "remaining_quantity": 2.0,
                "unit_price": Decimal("98.50"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 2.0, now - timedelta(days=8), "Corned beef silog dinner"),
                ],
            },
            # Batch 2: Purchased 2 days ago at ₱102.00
            {
                "product": "Purefoods Corned Beef Classic",
                "location": "Pantry - Shelf A",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=450),
                "original_quantity": 4.0,
                "remaining_quantity": 4.0,
                "unit_price": Decimal("102.00"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=2), "Intake from Puregold"),
                ],
            },
            # 6. Low Stock Alerts: Lucky Me! Pancit Canton Kalamansi (1 pack left)
            {
                "product": "Lucky Me! Pancit Canton Kalamansi",
                "location": "Pantry - Shelf B",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=120),
                "original_quantity": 6.0,
                "remaining_quantity": 1.0,
                "unit_price": Decimal("15.50"),
                "events": [
                    (EventType.PURCHASED, 6.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 5.0, now - timedelta(days=6), "Family afternoon merienda"),
                ],
            },
            # 7. Low Stock Alerts: Datu Puti Soy Sauce (0.3 L left)
            {
                "product": "Datu Puti Soy Sauce",
                "location": "Spice & Seasoning Station",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=360),
                "original_quantity": 1.0,
                "remaining_quantity": 0.3,
                "unit_price": Decimal("48.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 0.7, now - timedelta(days=5), "Chicken Pork Adobo marinade"),
                ],
            },
            # 8. Low Stock Alerts: Knorr Sinigang sa Sampalok (1 pack left)
            {
                "product": "Knorr Sinigang sa Sampalok Mix Original",
                "location": "Spice & Seasoning Station",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=180),
                "original_quantity": 4.0,
                "remaining_quantity": 1.0,
                "unit_price": Decimal("25.00"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 3.0, now - timedelta(days=7), "Sinigang na Baboy Sunday lunch"),
                ],
            },
            # 9. Out of Stock Product: Argentina Corned Beef (0 remaining)
            {
                "product": "Argentina Corned Beef",
                "location": "Pantry - Shelf A",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=200),
                "original_quantity": 2.0,
                "remaining_quantity": 0.0,
                "unit_price": Decimal("39.50"),
                "events": [
                    (EventType.PURCHASED, 2.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 2.0, now - timedelta(days=10), "Ginisang corned beef with potatoes"),
                ],
            },
            # 10. Healthy Inventory: Rice (Staple)
            {
                "product": "Harvester's Dinorado Special Rice",
                "location": "Pantry - Shelf B",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=180),
                "original_quantity": 5.0,
                "remaining_quantity": 4.0,
                "unit_price": Decimal("65.00"), # ₱325 / 5kg
                "events": [
                    (EventType.PURCHASED, 5.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 1.0, now - timedelta(days=7), "Daily dinner rice"),
                ],
            },
            # 11. Frozen Hotdogs
            {
                "product": "Purefoods Tender Juicy Hotdog Classic",
                "location": "Freezer",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=90),
                "original_quantity": 1.0,
                "remaining_quantity": 1.0,
                "unit_price": Decimal("215.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=2), "Intake from Puregold"),
                ],
            },
            # 12. Frozen Tocino
            {
                "product": "CDO Funtastyk Young Pork Tocino",
                "location": "Freezer",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=60),
                "original_quantity": 2.0,
                "remaining_quantity": 2.0,
                "unit_price": Decimal("120.00"),
                "events": [
                    (EventType.PURCHASED, 2.0, now - timedelta(days=2), "Intake from Puregold"),
                ],
            },
            # 13. Canned Seafood: San Marino Corned Tuna
            {
                "product": "San Marino Corned Tuna",
                "location": "Pantry - Shelf A",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=400),
                "original_quantity": 4.0,
                "remaining_quantity": 4.0,
                "unit_price": Decimal("48.50"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=7), "Intake from Savemore"),
                ],
            },
            # 14. Mega Sardines
            {
                "product": "Mega Sardines in Tomato Sauce with Chili",
                "location": "Pantry - Shelf A",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=500),
                "original_quantity": 6.0,
                "remaining_quantity": 6.0,
                "unit_price": Decimal("26.75"),
                "events": [
                    (EventType.PURCHASED, 6.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                ],
            },
            # 15. Spam
            {
                "product": "Spam Luncheon Meat Classic",
                "location": "Pantry - Shelf A",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=600),
                "original_quantity": 3.0,
                "remaining_quantity": 2.0,
                "unit_price": Decimal("195.00"),
                "events": [
                    (EventType.PURCHASED, 3.0, now - timedelta(days=7), "Intake from Savemore"),
                    (EventType.CONSUMED, 1.0, now - timedelta(days=3), "Spam and eggs breakfast"),
                ],
            },
            # 16. Pancit Canton Chilimansi
            {
                "product": "Lucky Me! Pancit Canton Chilimansi",
                "location": "Pantry - Shelf B",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=180),
                "original_quantity": 6.0,
                "remaining_quantity": 6.0,
                "unit_price": Decimal("15.50"),
                "events": [
                    (EventType.PURCHASED, 6.0, now - timedelta(days=2), "Intake from Puregold"),
                ],
            },
            # 17. Pancit Canton Extra Hot Chili
            {
                "product": "Lucky Me! Pancit Canton Extra Hot Chili",
                "location": "Pantry - Shelf B",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=180),
                "original_quantity": 4.0,
                "remaining_quantity": 4.0,
                "unit_price": Decimal("15.50"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=2), "Intake from Puregold"),
                ],
            },
            # 18. Dairy: Eden Cheese
            {
                "product": "Eden Original Cheese Melt",
                "location": "Refrigerator - Top Shelf",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=90),
                "original_quantity": 2.0,
                "remaining_quantity": 2.0,
                "unit_price": Decimal("62.00"),
                "events": [
                    (EventType.PURCHASED, 2.0, now - timedelta(days=7), "Intake from Savemore"),
                ],
            },
            # 19. Dairy: Magnolia Butter
            {
                "product": "Magnolia Gold Pure Butter Salted",
                "location": "Refrigerator - Top Shelf",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=120),
                "original_quantity": 1.0,
                "remaining_quantity": 0.75,
                "unit_price": Decimal("165.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=7), "Intake from Savemore"),
                    (EventType.CONSUMED, 0.25, now - timedelta(days=4), "Butter for toast and baking"),
                ],
            },
            # 20. Dairy: Nestlé All-Purpose Cream
            {
                "product": "Nestlé All-Purpose Cream",
                "location": "Refrigerator - Top Shelf",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=150),
                "original_quantity": 3.0,
                "remaining_quantity": 3.0,
                "unit_price": Decimal("74.00"),
                "events": [
                    (EventType.PURCHASED, 3.0, now - timedelta(days=7), "Intake from Savemore"),
                ],
            },
            # 21. Condiments: Datu Puti White Vinegar
            {
                "product": "Datu Puti White Vinegar",
                "location": "Spice & Seasoning Station",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=365),
                "original_quantity": 1.0,
                "remaining_quantity": 0.8,
                "unit_price": Decimal("44.50"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 0.2, now - timedelta(days=8), "Vinegar dipping sauce with garlic"),
                ],
            },
            # 22. Condiments: UFC Banana Catsup
            {
                "product": "UFC Tamis Anghang Banana Catsup",
                "location": "Refrigerator - Door Rack",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=240),
                "original_quantity": 1.0,
                "remaining_quantity": 0.9,
                "unit_price": Decimal("41.50"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=7), "Intake from Savemore"),
                    (EventType.CONSUMED, 0.1, now - timedelta(days=3), "Catsup for hotdogs"),
                ],
            },
            # 23. Condiments: Mang Tomas Sarsa
            {
                "product": "Mang Tomas All-Around Sarsa",
                "location": "Refrigerator - Door Rack",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=240),
                "original_quantity": 1.0,
                "remaining_quantity": 1.0,
                "unit_price": Decimal("39.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=7), "Intake from Savemore"),
                ],
            },
            # 24. Condiments: Cooking Oil
            {
                "product": "Golden Fiesta Pure Palm Cooking Oil",
                "location": "Spice & Seasoning Station",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=365),
                "original_quantity": 1.0,
                "remaining_quantity": 0.6,
                "unit_price": Decimal("95.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 0.4, now - timedelta(days=6), "Frying oil for breakfast"),
                ],
            },
            # 25. Condiments: Knorr Liquid Seasoning
            {
                "product": "Knorr Liquid Seasoning Original",
                "location": "Spice & Seasoning Station",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=365),
                "original_quantity": 1.0,
                "remaining_quantity": 0.85,
                "unit_price": Decimal("82.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 0.15, now - timedelta(days=5), "Fried rice seasoning"),
                ],
            },
            # 26. Snacks: SkyFlakes Crackers Tub (with physical count adjustment event)
            {
                "product": "SkyFlakes Crackers Tub",
                "location": "Pantry - Shelf B",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=210),
                "original_quantity": 1.0,
                "remaining_quantity": 0.8,
                "unit_price": Decimal("188.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 0.15, now - timedelta(days=9), "Afternoon merienda crackers"),
                    (EventType.ADJUSTMENT, -0.05, now - timedelta(days=4), "Pantry audit reconciliation count adjustment"),
                ],
            },
            # 27. Snacks: Piattos Cheese
            {
                "product": "Piattos Cheese Flavored Potato Crisps",
                "location": "Pantry - Shelf B",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=150),
                "original_quantity": 4.0,
                "remaining_quantity": 3.0,
                "unit_price": Decimal("38.50"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=2), "Intake from Puregold"),
                    (EventType.CONSUMED, 1.0, now - timedelta(days=1), "Movie night snack"),
                ],
            },
            # 28. Coffee: Kopiko Blanca
            {
                "product": "Kopiko Blanca 3-in-1 Coffee Mix",
                "location": "Pantry - Shelf B",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=270),
                "original_quantity": 1.0, # 1 bag of 10s
                "remaining_quantity": 1.0,
                "unit_price": Decimal("85.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=7), "Intake from Savemore"),
                ],
            },
            # 29. Beverages: San Miguel Beer
            {
                "product": "San Miguel Pale Pilsen",
                "location": "Refrigerator - Door Rack",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=180),
                "original_quantity": 6.0,
                "remaining_quantity": 6.0,
                "unit_price": Decimal("52.00"),
                "events": [
                    (EventType.PURCHASED, 6.0, now - timedelta(days=2), "Intake from Puregold"),
                ],
            },
            # 30. Beverages: C2 Green Tea Apple
            {
                "product": "C2 Cool & Clean Green Tea Apple",
                "location": "Refrigerator - Door Rack",
                "session": puregold_session,
                "purchased_at": now - timedelta(days=2),
                "expiration_date": today + timedelta(days=120),
                "original_quantity": 4.0,
                "remaining_quantity": 3.0,
                "unit_price": Decimal("26.00"),
                "events": [
                    (EventType.PURCHASED, 4.0, now - timedelta(days=2), "Intake from Puregold"),
                    (EventType.CONSUMED, 1.0, now - timedelta(days=1), "Chilled tea drink"),
                ],
            },
            # 31. Fresh Calamansi
            {
                "product": "Fresh Native Calamansi",
                "location": "Refrigerator - Crisper",
                "session": savemore_session,
                "purchased_at": now - timedelta(days=7),
                "expiration_date": today + timedelta(days=10),
                "original_quantity": 500.0,
                "remaining_quantity": 350.0,
                "unit_price": Decimal("0.09"), # ₱45 / 500g
                "events": [
                    (EventType.PURCHASED, 500.0, now - timedelta(days=7), "Intake from Savemore"),
                    (EventType.CONSUMED, 150.0, now - timedelta(days=4), "Squeezed for bistek and iced juice"),
                ],
            },
            # 32. Native Garlic & Onion
            {
                "product": "Native Red Onion (Sibuyas)",
                "location": "Pantry - Shelf B",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=21),
                "original_quantity": 1.0,
                "remaining_quantity": 0.6,
                "unit_price": Decimal("120.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 0.4, now - timedelta(days=7), "Sautéing aromatics for meals"),
                ],
            },
            {
                "product": "Native Garlic (Bawang)",
                "location": "Pantry - Shelf B",
                "session": sm_session,
                "purchased_at": now - timedelta(days=14),
                "expiration_date": today + timedelta(days=30),
                "original_quantity": 500.0,
                "remaining_quantity": 300.0,
                "unit_price": Decimal("0.16"), # ₱80 / 500g
                "events": [
                    (EventType.PURCHASED, 500.0, now - timedelta(days=14), "Intake from SM Supermarket"),
                    (EventType.CONSUMED, 200.0, now - timedelta(days=6), "Garlic fried rice and cooking"),
                ],
            },
            # 33. Waste Demonstration: Expired Bread batch in the past
            {
                "product": "Gardenia Classic White Bread",
                "location": "Pantry - Shelf B",
                "session": sm_session,
                "purchased_at": now - timedelta(days=18),
                "expiration_date": today - timedelta(days=8),
                "original_quantity": 1.0,
                "remaining_quantity": 0.0,
                "unit_price": Decimal("82.00"),
                "events": [
                    (EventType.PURCHASED, 1.0, now - timedelta(days=18), "Intake from SM Supermarket"),
                    (EventType.EXPIRED, 1.0, now - timedelta(days=8), "Green bread mold detected past expiration date", "Past shelf life"),
                ],
            },
            # 34. Waste Demonstration: Spoiled produce batch in the past
            {
                "product": "Fresh Native Calamansi",
                "location": "Refrigerator - Crisper",
                "session": sm_session,
                "purchased_at": now - timedelta(days=20),
                "expiration_date": today - timedelta(days=5),
                "original_quantity": 200.0,
                "remaining_quantity": 0.0,
                "unit_price": Decimal("0.09"),
                "events": [
                    (EventType.PURCHASED, 200.0, now - timedelta(days=20), "Intake from SM Supermarket"),
                    (EventType.DISCARDED, 200.0, now - timedelta(days=5), "Overripe and dried out in crisper", "Spoilage"),
                ],
            },
        ]

        total_batches = 0
        total_events = 0

        for bspec in batches_spec:
            product = prod_map[bspec["product"]]
            location = loc_map[bspec["location"]]
            session = bspec["session"]

            if not reset:
                existing_batch = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.product_id == product.id,
                        InventoryBatch.storage_location_id == location.id,
                        InventoryBatch.grocery_session_id == session.id,
                        InventoryBatch.expiration_date == bspec["expiration_date"],
                    )
                    .first()
                )
                if existing_batch:
                    continue
            batch = InventoryBatch(
                product_id=product.id,
                storage_location_id=location.id,
                grocery_session_id=session.id,
                purchased_at=bspec["purchased_at"],
                expiration_date=bspec["expiration_date"],
                original_quantity=bspec["original_quantity"],
                remaining_quantity=bspec["remaining_quantity"],
                unit_price=bspec["unit_price"],
            )
            db.add(batch)
            db.flush()
            total_batches += 1

            for ev_spec in bspec["events"]:
                ev_type = ev_spec[0]
                qty = ev_spec[1]
                ev_time = ev_spec[2]
                reason = ev_spec[3]
                notes = ev_spec[4] if len(ev_spec) > 4 else None

                event = InventoryEvent(
                    batch_id=batch.id,
                    event_type=ev_type,
                    quantity=qty,
                    occurred_at=ev_time,
                    reason=reason,
                    notes=notes,
                )
                db.add(event)
                total_events += 1

        db.commit()
        print(f"  ✓ Seeded {total_batches} inventory batches with {total_events} audit events.")

        # 7. Shopping List Items
        print("\n[7/7] Seeding household shopping list...")
        shopping_spec = [
            # Active (unbought) items linked to products
            {
                "product": "Lucky Me! Pancit Canton Kalamansi",
                "name": "Lucky Me! Pancit Canton Kalamansi",
                "quantity": 6.0,
                "unit": "packs",
                "is_bought": False,
                "notes": "Urgent restock: only 1 pack left in pantry!",
            },
            {
                "product": "Datu Puti Soy Sauce",
                "name": "Datu Puti Soy Sauce",
                "quantity": 1.0,
                "unit": "L",
                "is_bought": False,
                "notes": "Low stock alert (0.3 L remaining)",
            },
            {
                "product": "Knorr Sinigang sa Sampalok Mix Original",
                "name": "Knorr Sinigang sa Sampalok Mix Original",
                "quantity": 3.0,
                "unit": "packs",
                "is_bought": False,
                "notes": "For Sunday pork sinigang lunch",
            },
            {
                "product": "Century Tuna Flakes in Oil",
                "name": "Century Tuna Flakes in Oil",
                "quantity": 6.0,
                "unit": "cans",
                "is_bought": False,
                "notes": "Stock up for rainy season emergency pantry",
            },
            # Unlinked generic shopping items
            {
                "product": None,
                "name": "Refined White Sugar",
                "quantity": 1.0,
                "unit": "kg",
                "is_bought": False,
                "notes": "Victoria or Robinsons brand for baking and morning coffee",
            },
            {
                "product": None,
                "name": "Paper Towels / Kitchen Roll",
                "quantity": 2.0,
                "unit": "rolls",
                "is_bought": False,
                "notes": "Sanicare 2-ply embossed",
            },
            # Completed (bought) items
            {
                "product": "Purefoods Tender Juicy Hotdog Classic",
                "name": "Purefoods Tender Juicy Hotdog Classic",
                "quantity": 1.0,
                "unit": "kg",
                "is_bought": True,
                "notes": f"Purchased at Puregold on {(today - timedelta(days=2)).isoformat()}",
            },
            {
                "product": "Gardenia Classic White Bread",
                "name": "Gardenia Classic White Bread",
                "quantity": 2.0,
                "unit": "loaves",
                "is_bought": True,
                "notes": f"Purchased at Puregold on {(today - timedelta(days=2)).isoformat()}",
            },
            {
                "product": "San Miguel Pale Pilsen",
                "name": "San Miguel Pale Pilsen",
                "quantity": 6.0,
                "unit": "cans",
                "is_bought": True,
                "notes": f"Purchased at Puregold on {(today - timedelta(days=2)).isoformat()}",
            },
        ]

        total_shopping = 0
        for sitem in shopping_spec:
            if not reset:
                existing_item = (
                    db.query(ShoppingListItem)
                    .filter(ShoppingListItem.name == sitem["name"])
                    .first()
                )
                if existing_item:
                    continue
            prod_id = prod_map[sitem["product"]].id if sitem["product"] else None
            item = ShoppingListItem(
                product_id=prod_id,
                name=sitem["name"],
                quantity=sitem["quantity"],
                unit=sitem["unit"],
                is_bought=sitem["is_bought"],
                notes=sitem["notes"],
            )
            db.add(item)
            total_shopping += 1

        db.commit()
        print(f"  ✓ Seeded {total_shopping} shopping list items ({len([s for s in shopping_spec if not s['is_bought']])} active, {len([s for s in shopping_spec if s['is_bought']])} completed).")

        # Summary Verification Output
        print("\n" + "=" * 60)
        print("🎉 Provision Household Database Seeding Complete!")
        print("=" * 60)
        user_count = db.query(User).count()
        loc_count = db.query(StorageLocation).count()
        sess_count = db.query(GrocerySession).count()
        prod_count = db.query(Product).count()
        batch_count = db.query(InventoryBatch).count()
        active_batches = db.query(InventoryBatch).filter(InventoryBatch.remaining_quantity > 0).count()
        event_count = db.query(InventoryEvent).count()
        shop_count = db.query(ShoppingListItem).count()

        print(f"Users:              {user_count} accounts")
        print(f"Storage Locations:  {loc_count} locations")
        print(f"Grocery Sessions:   {sess_count} sessions (3 completed, 1 draft)")
        print(f"Catalog Products:   {prod_count} Philippine supermarket products")
        print(f"Inventory Batches:  {batch_count} batches ({active_batches} active on-hand)")
        print(f"Inventory Events:   {event_count} ledger movements (purchases, consumptions, waste)")
        print(f"Shopping List:      {shop_count} items")
        print("=" * 60)
        print("Demo Credentials:")
        print("  Email:    user@provision.local")
        print("  Password: password123")
        print("=" * 60)

        return {
            "users": user_count,
            "locations": loc_count,
            "sessions": sess_count,
            "products": prod_count,
            "batches": batch_count,
            "active_batches": active_batches,
            "events": event_count,
            "shopping_items": shop_count,
        }

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding database: {e}", file=sys.stderr)
        raise
    finally:
        if should_close:
            db.close()

if __name__ == "__main__":
    reset_flag = "--no-reset" not in sys.argv
    seed_database(reset=reset_flag)
