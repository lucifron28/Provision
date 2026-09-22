# Provision

Smart household food inventory and pantry management system.

---

## Tech Stack

- **Frontend:** Swift + native SwiftUI (Deployment Target: iOS 26.5+)
- **Backend:** FastAPI + SQLAlchemy 2.0 + SQLite
- **Authentication:** JWT access tokens (HS256) + Argon2 password hashing (`pwdlib[argon2]`)
- **Token Storage:** Native iOS Keychain Services (`Security` framework)

---

## Project Structure

```text
Provision/
├── backend/                      # FastAPI + SQLite REST API
├── frontend/                     # Native SwiftUI iOS application (Xcode project)
└── provision_reference_screens/  # Design and reference exports
```

---

## Getting Started

### Backend Execution

From the repository root:

```bash
# 1. Enter backend directory
cd backend

# 2. Configure local environment variables
cp .env.example .env
# Set your local JWT_SECRET_KEY in .env

# 3. Sync dependencies
uv sync

# 4. Apply database migrations
uv run alembic upgrade head

# 5. Seed Philippine supermarket demo data (optional / recommended)
uv run python seed.py

# 6. Run automated test suite
uv run pytest

# 7. Start local development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive OpenAPI Swagger Docs: `http://localhost:8000/docs`

---

### Frontend Execution

Open the iOS project in Xcode:

```bash
open frontend/frontend.xcodeproj
```

- **Deployment Target:** iOS 26.5+
- **Frontend:** Native SwiftUI
- **Simulator Development:** Connects by default to `http://127.0.0.1:8000/api/v1`.
- **Physical Device Testing:** Set your development Mac's LAN IP in `APIEnvironment.localDeviceHost` (`frontend/frontend/Core/APIClient.swift`). Local HTTP traffic is permitted via `NSAllowsLocalNetworking`.

---

## Philippine Supermarket Seed Data & Demo

Provision is pre-seeded with authentic Philippine supermarket items, realistic multi-batch inventory scenarios, supermarket intake sessions, audit event logs, and shopping list items to deliver an out-of-the-box demonstration experience.

### Seeding or Resetting the Database

Run the database seeder from the `backend/` directory:

```bash
cd backend
uv run python seed.py
```

> **Safe Re-seeding:** The seeder is idempotent. It preserves existing registered user accounts (such as `cronvincent@gmail.com`), guarantees the default demo credentials below, and refreshes the inventory tables with clean demonstration scenarios.

### Default Demo Credentials

| Account | Email | Password | Display Name |
| :--- | :--- | :--- | :--- |
| **Primary Demo User** | `user@provision.local` | `password123` | Maria Santos |
| **Secondary Demo User** | `demo@provision.local` | `password123` | Juan Dela Cruz |

---

### Demonstration Scenarios

The seeded database pre-populates five realistic scenarios demonstrating household food intelligence:

#### 1. FEFO (First Expired, First Out) Consumption Demonstration
- **Target Product:** *Century Tuna Flakes in Oil* (Barcode `4800016644818`)
- **Location:** `Pantry - Shelf A`
- **Multi-Batch State:**
  - **Batch 1 (Earliest / SM Megamall):** Purchased 14 days ago, expires in **90 days**, 4 cans remaining @ ₱43.50.
  - **Batch 2 (Newer / Puregold):** Purchased 2 days ago, expires in **365 days**, 12 cans remaining @ ₱45.00.
- **Workflow & Observable Behavior:**
  - Calling `POST /api/v1/inventory/consume` with `product_id` and quantity `5.0` automatically drains all 4 cans from Batch 1 first, then consumes 1 can from Batch 2.
  - Creates two immutable `CONSUMED` ledger entries in `inventory_events`.
  - Leaves Batch 1 with `0.0` remaining (depleted) and Batch 2 with `11.0` cans remaining.

#### 2. Expiring Soon Urgency Alerts
- **Endpoint:** `GET /api/v1/analytics/expiring-soon` (powers iOS Home dashboard alerts)
- **Scenarios Preconfigured:**
  - **Magnolia Fresh Milk (1.0 L):** Expires **tomorrow** (1 day left) in `Refrigerator - Door Rack`.
  - **Gardenia Classic White Bread (600g):** Expires in **2 days** in `Pantry - Shelf B`.
  - **Bounty Fresh Farm Eggs (12 pcs):** Expires in **4 days** in `Refrigerator - Top Shelf`.
- **Observable Behavior:** Highlights expiring products with amber/red urgency cards on the iOS Home tab to prevent food waste before spoilage.

#### 3. Low Stock Alerts & Automated Shopping List
- **Endpoint:** `GET /api/v1/analytics/low-stock`
- **Scenarios Preconfigured:**
  - **Lucky Me! Pancit Canton Kalamansi:** Only 1 pack remaining in `Pantry - Shelf B` (original: 6 packs).
  - **Datu Puti Soy Sauce (1.0 L):** Only 0.3 L remaining in `Spice & Seasoning Station` (original: 1.0 L).
  - **Knorr Sinigang sa Sampalok Mix:** Only 1 pack remaining in `Spice & Seasoning Station` (original: 4 packs).
  - **Argentina Corned Beef (150g):** Depleted to 0 cans (completely out of stock).
- **Observable Behavior:** One-tap replenishment generation via `POST /api/v1/shopping-list/generate-from-low-stock` identifies depleted items and adds them to the household shopping list with suggested restock quantities.

#### 4. Waste & Loss Financial Intelligence
- **Endpoint:** `GET /api/v1/analytics/waste`
- **Scenarios Preconfigured:**
  - **Gardenia Classic White Bread (1 loaf, ₱82.00):** Logged with an `EXPIRED` event (*"Green bread mold detected past expiration date"*, reason: *"Past shelf life"*).
  - **Fresh Native Calamansi (200g, ₱18.00):** Logged with a `DISCARDED` event (*"Overripe and dried out in crisper"*, reason: *"Spoilage"*).
- **Observable Behavior:** Shows total household financial loss (₱100.00 total) and groups waste reasons to encourage smarter shopping and consumption habits.

#### 5. Multi-Session Grocery Spending History & Price Tracking
- **Endpoints:** `GET /api/v1/grocery-sessions` and `GET /api/v1/analytics/spending`
- **Retailer Intake Sessions:**
  - **SM Supermarket - Megamall (Receipt #0994):** ₱3,450.75 (14 days ago) — Bi-monthly major household stock-up.
  - **Savemore Market - Light Residences:** ₱1,820.50 (7 days ago) — Mid-week replenishment (dairy, breakfast, condiments).
  - **Puregold Price Club - Shaw:** ₱2,685.00 (2 days ago) — Restock run (meats, instant noodles, beverages, snacks).
  - **Robinsons Supermarket - Magnolia:** ₱850.00 (`DRAFT`) — Active intake session for live scanner testing.
- **Price Tracking:** Tracks price trends across stores over time (e.g. Purefoods Corned Beef Classic: ₱98.50 at SM Megamall vs. ₱102.00 at Puregold, queryable via `GET /api/v1/analytics/price-history/{product_id}`).

---

### Table of Seeded Philippine Supermarket Products

All 49 catalog products are authentic Philippine supermarket items with valid 480... EAN-13 barcodes and typical retail pricing in Philippine Pesos (PHP):

| Category | Name | Brand | Barcode | Size | Price (PHP) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Canned Goods** | Century Tuna Flakes in Oil | Century Tuna | `4800016644818` | 180 g (can) | ₱44.50 |
| **Canned Goods** | Century Tuna Hot & Spicy | Century Tuna | `4800016644825` | 180 g (can) | ₱45.00 |
| **Canned Goods** | San Marino Corned Tuna | San Marino | `4800110025421` | 180 g (can) | ₱48.50 |
| **Canned Goods** | Purefoods Corned Beef Classic | Purefoods | `4800361389440` | 210 g (can) | ₱102.00 |
| **Canned Goods** | Mega Sardines in Tomato Sauce with Chili | Mega Sardines | `4800168100217` | 155 g (can) | ₱26.75 |
| **Canned Goods** | 555 Fried Sardines Escabeche | 555 | `4800016555121` | 155 g (can) | ₱28.50 |
| **Canned Goods** | CDO Karne Norte | CDO | `4800888139580` | 150 g (can) | ₱38.00 |
| **Canned Goods** | Spam Luncheon Meat Classic | SPAM | `037600104616` | 340 g (can) | ₱195.00 |
| **Canned Goods** | Argentina Corned Beef | Argentina | `4800110014029` | 150 g (can) | ₱39.50 |
| **Noodles & Quick Meals** | Lucky Me! Pancit Canton Kalamansi | Lucky Me! | `4800361005210` | 80 g (pack) | ₱15.50 |
| **Noodles & Quick Meals** | Lucky Me! Pancit Canton Chilimansi | Lucky Me! | `4800361005319` | 80 g (pack) | ₱15.50 |
| **Noodles & Quick Meals** | Lucky Me! Pancit Canton Extra Hot Chili | Lucky Me! | `4800361005418` | 80 g (pack) | ₱15.50 |
| **Noodles & Quick Meals** | Lucky Me! Pancit Canton Original | Lucky Me! | `4800361005111` | 80 g (pack) | ₱15.50 |
| **Noodles & Quick Meals** | Lucky Me! Instant Mami Chicken | Lucky Me! | `4800361001113` | 55 g (pack) | ₱13.75 |
| **Noodles & Quick Meals** | Nissin Cup Noodles Seafood | Nissin | `4800016053016` | 60 g (cup) | ₱32.00 |
| **Condiments & Sauces** | Datu Puti Soy Sauce | Datu Puti | `4801981110010` | 1.0 L | ₱48.00 |
| **Condiments & Sauces** | Datu Puti White Vinegar | Datu Puti | `4801981120019` | 1.0 L | ₱44.50 |
| **Condiments & Sauces** | Silver Swan Soy Sauce | Silver Swan | `4800038101115` | 1.0 L | ₱49.00 |
| **Condiments & Sauces** | UFC Tamis Anghang Banana Catsup | UFC | `4801668601017` | 550 g | ₱41.50 |
| **Condiments & Sauces** | Mang Tomas All-Around Sarsa | Mang Tomas | `4801668201019` | 330 g | ₱39.00 |
| **Condiments & Sauces** | Knorr Sinigang sa Sampalok Mix Original | Knorr | `4800888121110` | 44 g (pack) | ₱25.00 |
| **Condiments & Sauces** | Knorr Liquid Seasoning Original | Knorr | `4800888111111` | 250 mL | ₱82.00 |
| **Condiments & Sauces** | Golden Fiesta Pure Palm Cooking Oil | Golden Fiesta | `4801981440018` | 1.0 L | ₱95.00 |
| **Condiments & Sauces** | Mama Sita's Oyster Sauce | Mama Sita's | `4800088111119` | 405 g | ₱68.50 |
| **Dairy & Chilled** | Magnolia Fresh Milk | Magnolia | `4800110041117` | 1.0 L | ₱108.00 |
| **Dairy & Chilled** | Magnolia Gold Pure Butter Salted | Magnolia | `4800110031118` | 225 g | ₱165.00 |
| **Dairy & Chilled** | Eden Original Cheese Melt | Eden | `4800016021114` | 165 g (block) | ₱62.00 |
| **Dairy & Chilled** | Nestlé All-Purpose Cream | Nestlé | `7613035612118` | 250 mL | ₱74.00 |
| **Dairy & Chilled** | Alaska Sweetened Condensed Milk | Alaska | `4800016042119` | 300 g (can) | ₱64.00 |
| **Dairy & Chilled** | Alaska Evaporated Milk | Alaska | `4800016041112` | 370 g (can) | ₱42.00 |
| **Dairy & Chilled** | Bear Brand Fortified Powdered Milk Drink | Bear Brand | `7613035111116` | 300 g | ₱125.00 |
| **Dairy & Chilled** | Bounty Fresh Farm Eggs (Medium Dozen) | Bounty Fresh | `4800999000042` | 12 pcs | ₱110.00 |
| **Frozen & Meats** | Purefoods Tender Juicy Hotdog Classic | Purefoods | `4800361301114` | 1.0 kg | ₱215.00 |
| **Frozen & Meats** | CDO Funtastyk Young Pork Tocino | CDO | `4800888123456` | 450 g | ₱120.00 |
| **Frozen & Meats** | Pampanga's Best Pork Longganisa | Pampanga's Best | `4806501234567` | 500 g | ₱135.00 |
| **Snacks & Bakery** | Gardenia Classic White Bread | Gardenia | `4806500800018` | 600 g (loaf) | ₱82.00 |
| **Snacks & Bakery** | SkyFlakes Crackers Tub | M.Y. San | `4800016001017` | 800 g (tub) | ₱188.00 |
| **Snacks & Bakery** | Piattos Cheese Flavored Potato Crisps | Jack 'n Jill | `4800016601019` | 85 g (bag) | ₱38.50 |
| **Snacks & Bakery** | Oishi Prawn Crackers | Oishi | `4800194111118` | 90 g (bag) | ₱24.00 |
| **Snacks & Bakery** | Kopiko Blanca 3-in-1 Coffee Mix | Kopiko | `8996001414002` | 10 packs | ₱85.00 |
| **Snacks & Bakery** | Choc Nut Peanut Milk Chocolate | Choc Nut | `4800055111111` | 24 pcs | ₱45.00 |
| **Grains & Staples** | Harvester's Dinorado Special Rice | Harvester's | `4806511110015` | 5.0 kg | ₱325.00 |
| **Grains & Staples** | Harvester's Sinandomeng Premium Rice | Harvester's | `4806511110022` | 5.0 kg | ₱290.00 |
| **Beverages** | San Miguel Pale Pilsen | San Miguel | `4800010111118` | 330 mL (can) | ₱52.00 |
| **Beverages** | C2 Cool & Clean Green Tea Apple | C2 | `4800016777110` | 500 mL (bottle) | ₱26.00 |
| **Beverages** | Royal Tru-Orange | Royal | `4800001112225` | 1.5 L | ₱68.00 |
| **Fresh Produce** | Fresh Native Calamansi | Local Produce | `4800999000011` | 500 g | ₱45.00 |
| **Fresh Produce** | Native Red Onion (Sibuyas) | Local Produce | `4800999000028` | 1.0 kg | ₱120.00 |
| **Fresh Produce** | Native Garlic (Bawang) | Local Produce | `4800999000035` | 500 g | ₱80.00 |

---

## Important Domain Limitation

> **Notice:** Provision currently authenticates access to a single shared household pantry. Per-user and multi-household data isolation is reserved for future development.

---

## Midterm Project Status (~50% Complete)

This project is intentionally at **approximately 50% completion** for the iOS Development midterm milestone:

### Implemented (Midterm Scope):
- User registration, login, and `/auth/me` verification with Argon2 password hashing.
- JWT access tokens stored in native iOS Keychain with automatic session restoration.
- Protected household pantry API: Catalog, Storage Locations, Inventory Batches, FEFO Consumption, Discard, Physical Count Adjustments, Shopping List, and Household Analytics.
- Native SwiftUI 5-tab app shell (`Home`, `Inventory`, `Scan`, `Shopping`, `Analytics`), user profile/logout sheet, and Product Detail with FEFO batch inspection.
- Prototype Scan UI simulation.

### Reserved for Final Project:
- Real camera and `AVFoundation` barcode scanning pipeline.
- `VisionKit` OCR for receipt intake and package expiration date extraction.
- Automatic inventory commit from live intake scanning.
- Offline-first local database caching (SwiftData / Core Data).
- Background expiration alert notifications.
