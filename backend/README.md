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

# 4. Start local server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Interactive Swagger Docs: `http://localhost:8000/docs`
- ReDoc Docs: `http://localhost:8000/redoc`

### Running Tests

```bash
uv run pytest
```
All tests execute against an isolated in-memory SQLite database with foreign-key enforcement enabled.
