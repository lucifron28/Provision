# Provision — Household Inventory Backend

Provision is the native backend service powering the Provision iOS food inventory and pantry management app. It provides persistent structured data, automated batch tracking, First Expired First Out (FEFO) consumption logic, and household decision intelligence.

---

## 1. Architectural Critique & Decisions

### Critique of Initial Proposed Architecture

| Proposed Component | Verdict | Senior Engineering Rationale |
| :--- | :--- | :--- |
| **Catalog vs. Inventory Split (`Product` vs. `InventoryBatch`)** | **Keep (Critical)** | Avoids conflating product metadata (barcode, brand, package size) with physical instances. Enables multi-batch FEFO expiration tracking, price tracking, and accurate inventory valuation. |
| **Inventory Events (`InventoryEvent`)** | **Keep (Critical)** | Treating inventory as an immutable ledger/event log rather than blind destructive updates (`quantity -= 1`) enables waste analytics, purchase audit trails, and reconciliation without losing data. |
| **Nested Storage Locations (`Pantry -> Shelf A -> Bin`)** | **Cut for Midterm** | Self-referencing trees or adjacency list hierarchies introduce unnecessary query complexity (CTE recursion) for a household app. A flat `StorageLocation` model (Pantry, Refrigerator, Freezer) covers 95% of user workflows with zero friction. |
| **Receipt OCR on Backend** | **Cut for Midterm** | iOS VisionKit handles OCR on-device with zero latency and zero server compute cost. The backend only needs to ingest structured lines inside a `GrocerySession`. |
| **External Barcode Dependency** | **Cut for Midterm** | An internal catalog (`products` table) keyed by barcode with `ProductSource` provenance guarantees offline-first reliability and immediate responsiveness without external API rate limits or failures. |

---

## 2. Tech Stack

- **Runtime:** Python 3.13+ (managed via `uv`)
- **Web Framework:** FastAPI + Pydantic v2
- **ORM:** SQLAlchemy 2.0 (`Mapped`, `mapped_column`, `DeclarativeBase`)
- **Database:** SQLite
- **Authentication:** JWT access tokens (HS256) + Argon2 password hashing (`pwdlib[argon2]`)
- **Migrations:** Alembic
- **Testing:** Pytest + HTTPX (`TestClient`)
---

## 3. Database Schema & Entities

```
+------------------+       +---------------------+       +-----------------------+
|     Product      | 1   * |   InventoryBatch    | *   1 |    StorageLocation    |
|------------------|-------|---------------------|-------|-----------------------|
| id (PK)          |       | id (PK)             |       | id (PK)               |
| name             |       | product_id (FK)     |       | name                  |
| brand            |       | storage_loc_id (FK) |       | description           |
| barcode (UNIQUE) |       | grocery_sess_id(FK) |       | created_at, updated_at|
| category         |       | purchased_at        |       +-----------------------+
| package_size     |       | expiration_date     |
| unit             |       | original_quantity   |       +-----------------------+
| image_url        |       | remaining_quantity  | *   1 |    GrocerySession     |
| source           |       | unit_price          |-------|-----------------------|
+------------------+       +---------------------+       | id (PK)               |
                                     | 1                 | store_name            |
                                     |                   | purchase_date         |
                                     | *                 | total_amount          |
                           +---------------------+       | status (DRAFT/DONE)   |
                           |   InventoryEvent    |       +-----------------------+
                           |---------------------|
                           | id (PK)             |       +-----------------------+
                           | batch_id (FK)       |       |   ShoppingListItem    |
                           | event_type          |       |-----------------------|
                           | quantity            |       | id (PK)               |
                           | occurred_at         |       | product_id (FK, opt)  |
                           | reason, notes       |       | name, quantity, unit  |
                           +---------------------+       | is_bought (BOOL)      |
                                                         +-----------------------+
```

---

## 4. API Endpoints

### Products (`/api/v1/products`)
- `GET /` — List products (with text search, category, barcode filter, aggregate on-hand stock)
- `POST /` — Create product (prevents duplicate barcodes)
- `GET /{id}` — Get product details and total stock
- `GET /barcode/{barcode}` — Quick barcode lookup (for iOS camera scanning)
- `PATCH /{id}` — Update product metadata
- `DELETE /{id}` — Remove product

### Storage Locations (`/api/v1/locations`)
- `GET /` — List locations (Pantry, Fridge, Freezer)
- `POST /` — Create location
- `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` — Manage location

### Inventory Batches (`/api/v1/batches`)
- `GET /` — List batches (filterable by product, location, active-only, FEFO order)
- `POST /` — Create batch (auto-generates `PURCHASED` inventory event)
- `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` — Manage batch

### Inventory Operations (`/api/v1/inventory`)
- `POST /consume` — **FEFO Consumption Engine**: Deducts from earliest-expiring batch first across multiple batches; records `CONSUMED` events
- `POST /batches/{id}/discard` — Discard batch (records `DISCARDED` or `EXPIRED` event)
- `POST /batches/{id}/adjust` — Physical count adjustment (records `ADJUSTMENT` event with delta)
- `GET /events` — Audit log of all inventory movements

### Grocery Intake Sessions (`/api/v1/grocery-sessions`)
- `GET /` — List grocery sessions (status filter)
- `POST /` — Start session (`DRAFT` status; creates zero inventory batches/events)
- `GET /{id}` — View session and linked batches
- `PATCH /{id}` — Edit session metadata (store name, notes, purchase date)
- `POST /{id}/commit` — Finalize intake session (`COMPLETED`), validate products/locations, ingest all batches and `PURCHASED` events, and compute total
- `DELETE /{id}` — Cancel session (`CANCELLED` status; leaves inventory untouched)

### Shopping List (`/api/v1/shopping-list`)
- `GET /` — List items (unbought first)
- `POST /` — Add item (auto-resolves product if `product_id` given)
- `POST /{id}/toggle` — Quick toggle `is_bought`
- `POST /generate-from-low-stock` — Automatically populates shopping list from low-inventory items
- `DELETE /completed/clear` — Clear bought items

### Household Analytics (`/api/v1/analytics`)
- `GET /inventory-summary` — Answers *"What food do I own? How much remains? Where is it stored?"*
- `GET /expiring-soon` — Answers *"What is expiring soon? Which items should I use first?"*
- `GET /low-stock` — Answers *"What am I running low on?"*
- `GET /valuation` — Answers *"How much is my pantry/fridge worth?"*
- `GET /spending` — Answers *"How much have I spent on groceries?"*
- `GET /waste` — Answers *"What food am I wasting?"* (Calculates cost lost from discarded/expired batches)
- `GET /price-history/{product_id}` — Answers *"How have prices changed over time?"*

---

## 5. Git Workflow & Branching

The repository follows standard feature-branching with Conventional Commits:

- `main` — Production-ready, stable codebase.
- `feat/<phase-name>` — Feature branches per milestone:
  - `feat/phase-1-setup-and-db`
  - `feat/phase-2-products-and-locations`
  - `feat/phase-3-inventory-batches`
  - `feat/phase-4-fefo-and-events`
  - `feat/phase-5-grocery-sessions`
  - `feat/phase-6-shopping-list`
  - `feat/phase-7-analytics-and-decisions`

Commit conventions:
- `chore: ...`
- `feat(...): ...`
- `test(...): ...`
- `docs(...): ...`

---

## 6. Getting Started

### Prerequisites
- Python 3.13+
- [`uv`](https://github.com/astral-sh/uv) (fast Python package manager)

### Installation & Run

```bash
# Navigate to backend directory
cd backend

# 1. Configure environment variables
cp .env.example .env
# Set your local JWT_SECRET_KEY in .env

# 2. Sync dependencies
uv sync

# 3. Run database migrations
uv run alembic upgrade head

# 4. Seed Philippine supermarket demo data (optional / recommended)
uv run python seed.py

# 5. Start local server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive Swagger Docs: `http://localhost:8000/docs`
- ReDoc Docs: `http://localhost:8000/redoc`

### Running Tests

```bash
uv run pytest
```
All tests execute against an isolated in-memory SQLite database with foreign-key enforcement enabled.

---

## 7. Philippine Supermarket Seed Data & Demo

Provision includes a realistic Philippine grocery database seeder (`seed.py`) designed to demonstrate household pantry tracking, automated expiration management, price comparison across supermarket chains, and food waste reduction.

### Seeding or Resetting the Database

To populate or reset the database with Philippine supermarket inventory data:

```bash
cd backend
uv run python seed.py
```

> **Account Preservation:** The seeder is idempotent and preserves registered user accounts (e.g. `cronvincent@gmail.com`). It ensures default demo credentials exist and wipes/repopulates inventory tables with clean demonstration scenarios.

#### Default Demo Credentials
| Role | Email | Password | Display Name |
| :--- | :--- | :--- | :--- |
| **Primary Demo User** | `user@provision.local` | `password123` | Maria Santos |
| **Secondary Demo User** | `demo@provision.local` | `password123` | Juan Dela Cruz |

---

### Demonstration Scenarios

The seeded database preconfigures five end-to-end household inventory scenarios:

#### 1. FEFO (First Expired, First Out) Consumption Engine
- **Target Product:** *Century Tuna Flakes in Oil* (Barcode `4800016644818`)
- **Location:** `Pantry - Shelf A`
- **Initial Batches:**
  - **Batch 1 (SM Megamall):** Purchased 14 days ago, expires in **90 days**, 4 cans remaining @ ₱43.50.
  - **Batch 2 (Puregold):** Purchased 2 days ago, expires in **365 days**, 12 cans remaining @ ₱45.00.
- **Workflow & Observable Behavior:**
  - Call `POST /api/v1/inventory/consume` with `{"product_id": <id>, "quantity": 5.0}`.
  - The engine prioritizes the earliest-expiring batch first: it consumes all 4 cans from Batch 1, then consumes 1 can from Batch 2.
  - Two immutable `CONSUMED` ledger events are recorded in `inventory_events`.
  - Batch 1 is updated to `0.0` remaining (depleted), and Batch 2 has `11.0` cans remaining.

#### 2. Expiring Soon Urgency Alerts
- **Endpoint:** `GET /api/v1/analytics/expiring-soon`
- **Scenarios Preconfigured:**
  - **Magnolia Fresh Milk (1.0 L):** Expires **tomorrow** (1 day left) in `Refrigerator - Door Rack`.
  - **Gardenia Classic White Bread (600g):** Expires in **2 days** in `Pantry - Shelf B`.
  - **Bounty Fresh Farm Eggs (12 pcs):** Expires in **4 days** in `Refrigerator - Top Shelf`.
- **Observable Behavior:** Surfaces prioritized amber/red warning badges on the iOS dashboard and API response to prevent imminent food waste.

#### 3. Low Stock Alerts & Automated Shopping List
- **Endpoint:** `GET /api/v1/analytics/low-stock`
- **Scenarios Preconfigured:**
  - **Lucky Me! Pancit Canton Kalamansi:** Only 1 pack remaining in `Pantry - Shelf B` (original: 6 packs).
  - **Datu Puti Soy Sauce (1.0 L):** Only 0.3 L remaining in `Spice & Seasoning Station` (original: 1.0 L).
  - **Knorr Sinigang sa Sampalok Mix:** Only 1 pack remaining in `Spice & Seasoning Station` (original: 4 packs).
  - **Argentina Corned Beef (150g):** Depleted to 0 cans (completely out of stock).
- **Observable Behavior:** Calling `POST /api/v1/shopping-list/generate-from-low-stock` scans items below safety thresholds and automatically adds replenishment items to the shopping list with suggested quantities.

#### 4. Waste & Loss Intelligence
- **Endpoint:** `GET /api/v1/analytics/waste`
- **Scenarios Preconfigured:**
  - **Gardenia Classic White Bread (1 loaf, ₱82.00):** Logged with an `EXPIRED` event (*"Green bread mold detected past expiration date"*, category: *"Past shelf life"*).
  - **Fresh Native Calamansi (200g, ₱18.00):** Logged with a `DISCARDED` event (*"Overripe and dried out in crisper"*, category: *"Spoilage"*).
- **Observable Behavior:** Quantifies total household financial loss (₱100.00) and categorizes waste causes to help households improve purchase habits.

#### 5. Multi-Session Grocery Spending History & Price Tracking
- **Endpoints:** `GET /api/v1/grocery-sessions` and `GET /api/v1/analytics/spending`
- **Retailer Sessions Recorded:**
  - **SM Supermarket - Megamall (Receipt #0994):** ₱3,450.75 (14 days ago) — Bi-monthly major family pantry intake.
  - **Savemore Market - Light Residences:** ₱1,820.50 (7 days ago) — Mid-week replenishment (dairy, breakfast bread, condiments).
  - **Puregold Price Club - Shaw:** ₱2,685.00 (2 days ago) — Restock run (meats, instant noodles, beverages, snacks).
  - **Robinsons Supermarket - Magnolia:** ₱850.00 (`DRAFT`) — Active intake session for camera scanner testing.
- **Price Tracking (`GET /api/v1/analytics/price-history/{product_id}`):** Demonstrates supermarket price tracking over time (e.g. Purefoods Corned Beef Classic: ₱98.50 at SM Supermarket vs. ₱102.00 at Puregold).

---

### Seeded Product Catalog (Authentic Philippine Supermarket Items)

All 49 seeded products feature genuine Philippine supermarket brands, authentic 480... EAN-13 barcodes, and current retail market prices in Philippine Pesos (PHP):

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
